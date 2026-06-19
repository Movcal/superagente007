"""
Trade Journal — aprendizaje automatico post-trade.

Cada vez que se cierra una posicion real, Claude Haiku analiza que paso
y escribe una leccion estructurada en data/trade_lessons.json.

El decision_engine lee las lecciones relevantes antes de entrar a un trade,
cerrando el loop de aprendizaje:
  Trade cierra → leccion → siguiente entrada informada → trade mas inteligente
"""
import os
import json
import sys
import pathlib
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CLAUDE_ENABLED   = os.getenv("CLAUDE_ENABLED", "false").lower() == "true"
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
LESSONS_FILE     = "data/trade_lessons.json"
MAX_LESSONS_KEPT = 200   # limite de lecciones en disco
MAX_LESSONS_READ = 10    # cuantas lecciones se pasan al decision_engine


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [JOURNAL] {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open("logs/trade_journal.log", "a") as f:
        f.write(line + "\n")


# ── Persistencia ──────────────────────────────────────────────────────────────

def load_lessons():
    if os.path.exists(LESSONS_FILE):
        with open(LESSONS_FILE) as f:
            return json.load(f)
    return []


def save_lesson(lesson):
    lessons = load_lessons()
    lessons.append(lesson)
    # Mantener solo las ultimas MAX_LESSONS_KEPT
    lessons = lessons[-MAX_LESSONS_KEPT:]
    os.makedirs("data", exist_ok=True)
    with open(LESSONS_FILE, "w") as f:
        json.dump(lessons, f, indent=2)


def get_lessons_for_symbol(symbol, n=5):
    """Retorna las ultimas N lecciones para un simbolo especifico."""
    lessons = load_lessons()
    relevant = [l for l in lessons if l.get("symbol") == symbol]
    return relevant[-n:]


def get_recent_lessons(n=MAX_LESSONS_READ):
    """Retorna las ultimas N lecciones generales (para contexto general)."""
    lessons = load_lessons()
    return lessons[-n:]


def format_lessons_for_prompt(symbol):
    """
    Formatea lecciones del simbolo + lecciones recientes generales
    para incluir en el prompt de Claude al evaluar una entrada.
    """
    symbol_lessons = get_lessons_for_symbol(symbol, n=3)
    recent_lessons = [l for l in get_recent_lessons(n=5) if l.get("symbol") != symbol]

    lines = []

    if symbol_lessons:
        lines.append(f"LECCIONES PREVIAS DE {symbol}:")
        for l in symbol_lessons:
            pnl = f"{l.get('pnl_pct', 0):+.1f}%"
            lines.append(f"  [{l.get('date', '?')}] PnL: {pnl} | {l.get('lesson', '')}")

    if recent_lessons:
        lines.append("LECCIONES RECIENTES (otros tokens):")
        for l in recent_lessons:
            pnl = f"{l.get('pnl_pct', 0):+.1f}%"
            lines.append(f"  [{l.get('symbol', '?')} {l.get('date', '?')}] PnL: {pnl} | {l.get('lesson', '')}")

    return "\n".join(lines) if lines else ""


# ── Analisis con Claude ───────────────────────────────────────────────────────

def _build_prompt(position):
    """Construye el prompt para el analisis post-trade."""
    symbol       = position.get("symbol", "?")
    capital      = position.get("capital", 0)
    entry_price  = position.get("entry_price", 0)
    exit_price   = position.get("exit_price", 0)
    pnl_pct      = position.get("pnl_pct", 0)
    pnl_usd      = position.get("pnl_usd", 0)
    entry_time   = position.get("entry_time", "?")[:16]
    exit_time    = position.get("exit_time", "?")[:16]
    exit_reason  = position.get("exit_reason", "?")
    volume_ratio = position.get("volume_ratio", 0)
    sentiment    = position.get("sentiment", "?")
    narrative    = position.get("narrative", "?")
    reasoning    = position.get("reasoning", "")[:500]
    in_watchlist = position.get("in_watchlist", False)
    path         = position.get("path", "B")

    # Calcular duracion
    try:
        t_entry = datetime.fromisoformat(position.get("entry_time", ""))
        t_exit  = datetime.fromisoformat(position.get("exit_time", ""))
        duracion = round((t_exit - t_entry).total_seconds() / 3600, 1)
    except Exception:
        duracion = "?"

    return f"""Analiza este trade cerrado y extrae UNA leccion concisa (max 2 oraciones) que mejore futuras decisiones.

TRADE:
- Token: {symbol}
- Capital: ${capital}
- Entrada: {entry_time} UTC @ ${entry_price}
- Salida: {exit_time} UTC @ ${exit_price}
- Duracion: {duracion}h
- PnL: {pnl_pct:+.1f}% (${pnl_usd:+.4f})
- Razon de salida: {exit_reason}
- Volumen al entrar: {volume_ratio}x
- Sentimiento: {sentiment}
- Narrativa: {narrative}
- En watchlist: {"Si" if in_watchlist else "No"}
- Camino de entrada: {"A (watchlist+volumen)" if path == "A" else "B (spike sin narrativa)"}

RAZONAMIENTO DE ENTRADA:
{reasoning}

Responde SOLO con un JSON con este formato exacto, sin texto adicional:
{{"lesson": "leccion concisa aqui", "tags": ["tag1", "tag2"], "outcome": "win" o "loss" o "neutral"}}

Tags disponibles: entry_late, entry_good, exit_early, exit_good, stop_loss, take_profit, pump_dump, news_lag, watchlist_worked, watchlist_failed, volume_fake, volume_real, narrative_strong, narrative_weak"""


def analyze_trade(position):
    """
    Analiza un trade cerrado con Claude Haiku y guarda la leccion.
    Silencioso si CLAUDE_ENABLED=false — solo loguea que hubiera hecho.
    """
    symbol   = position.get("symbol", "?")
    pnl_pct  = position.get("pnl_pct")
    pnl_usd  = position.get("pnl_usd")

    # Solo analizar trades con datos de PnL real
    if pnl_pct is None or position.get("recovery"):
        return

    if not CLAUDE_ENABLED:
        log(f"[DRY-RUN] Hubiera analizado trade de {symbol} (PnL: {pnl_pct:+.1f}%)")
        return

    if not ANTHROPIC_KEY:
        log("ANTHROPIC_API_KEY no configurada, saltando analisis")
        return

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        prompt = _build_prompt(position)

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()

        # Extraer JSON de la respuesta
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            log(f"Respuesta de Claude sin JSON valido: {raw[:100]}")
            return

        result = json.loads(raw[start:end])

        lesson = {
            "symbol":      symbol,
            "date":        datetime.utcnow().strftime("%Y-%m-%d"),
            "pnl_pct":     round(pnl_pct, 2),
            "pnl_usd":     round(pnl_usd, 4) if pnl_usd else 0,
            "exit_reason": position.get("exit_reason", ""),
            "narrative":   position.get("narrative", ""),
            "in_watchlist": position.get("in_watchlist", False),
            "lesson":      result.get("lesson", ""),
            "tags":        result.get("tags", []),
            "outcome":     result.get("outcome", "neutral"),
            "timestamp":   datetime.utcnow().isoformat(),
        }

        save_lesson(lesson)
        log(f"Leccion guardada para {symbol} ({pnl_pct:+.1f}%): {lesson['lesson'][:80]}")

    except Exception as e:
        log(f"Error analizando trade de {symbol}: {e}")
