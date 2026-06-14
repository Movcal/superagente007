"""
Analizador de noticias y KOLs — CMC Skills + Claude (Haiku).

CLAUDE_ENABLED=false (default): solo loguea lo que haría, NO afecta decisiones.
CLAUDE_ENABLED=true           : modifica decisiones del agente.

Activar el dia de la competicion (22 junio) cambiando .env
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CLAUDE_ENABLED    = os.getenv("CLAUDE_ENABLED", "false").lower() == "true"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CMC_API_KEY       = os.getenv("CMC_API_KEY", "")

CMC_BASE = "https://pro-api.coinmarketcap.com"
NEWS_LOG = "logs/news_analyzer.log"

# Modelo economico para monitoreo continuo
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    mode = "[DRY-RUN]" if not CLAUDE_ENABLED else "[LIVE]"
    line = f"[{timestamp}] [NEWS] {mode} {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(NEWS_LOG, "a") as f:
        f.write(line + "\n")


# ── CMC: datos disponibles ahora (plan basico) ────────────────────────────────

def _cmc_get(path, params=None):
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
    try:
        r = requests.get(f"{CMC_BASE}{path}", headers=headers,
                         params=params or {}, timeout=20)
        if r.status_code == 200:
            return r.json().get("data")
        log(f"CMC {path} -> HTTP {r.status_code}")
    except Exception as e:
        log(f"Error CMC {path}: {e}")
    return None


def fetch_fear_greed():
    data = _cmc_get("/v1/fear-and-greed/latest")
    if data:
        return {"value": data.get("value", 50),
                "label": data.get("value_classification", "Neutral")}
    return {"value": 50, "label": "Neutral"}


def fetch_trending():
    data = _cmc_get("/v1/cryptocurrency/trending/most-visited", {"limit": 10})
    if data:
        return [item.get("symbol") for item in data]
    return []


# ── CMC Skills (activos con CMC Pro el lunes) ─────────────────────────────────
# Cada funcion tiene un TODO claro para conectar cuando llegue CMC Pro.
# Por ahora retornan None y el agente sigue funcionando sin ellas.

def fetch_macro_news():
    """
    CMC Skill: 'macro news aggregator'
    Noticias macro actuales con nivel de frescura y relevancia.
    TODO (lunes): conectar al endpoint real del Agent Hub.
    """
    # data = _cmc_get("/v2/agent/skill", {"skill": "macro news aggregator"})
    # return data
    return None


def fetch_kol_sentiment(symbol):
    """
    CMC Skill: 'altcoin kol sentiment'
    Sentimiento de KOLs para un token — separa ruido de señal real.
    TODO (lunes): conectar al endpoint real del Agent Hub.
    """
    # data = _cmc_get("/v2/agent/skill", {"skill": "altcoin kol sentiment", "symbol": symbol})
    # return data
    return None


def fetch_market_regime():
    """
    CMC Skill: 'Detect Market Regime'
    Clasifica el regimen: trend_expansion, liquidation_stress, range_chop.
    TODO (lunes): conectar al endpoint real del Agent Hub.
    """
    # data = _cmc_get("/v2/agent/skill", {"skill": "Detect Market Regime"})
    # return data
    return None


# ── Contexto completo para Claude ─────────────────────────────────────────────

def build_context(symbol):
    """Arma el contexto de mercado disponible en este momento."""
    ctx = {}
    ctx["fear_greed"]     = fetch_fear_greed()
    ctx["trending_now"]   = fetch_trending()
    ctx["macro_news"]     = fetch_macro_news()     # None hasta CMC Pro
    ctx["kol_sentiment"]  = fetch_kol_sentiment(symbol)  # None hasta CMC Pro
    ctx["market_regime"]  = fetch_market_regime()  # None hasta CMC Pro
    return ctx


# ── Reglas del operador ───────────────────────────────────────────────────────

def load_market_rules():
    rules_path = pathlib.Path(__file__).parent.parent / "knowledge" / "MARKET_RULES.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return "Sin reglas definidas aun. Usar criterio conservador."


# ── Claude ────────────────────────────────────────────────────────────────────

def _call_claude(symbol, context):
    """Llama a Claude Haiku con el contexto y las reglas del operador."""
    try:
        import anthropic
    except ImportError:
        log("Libreria 'anthropic' no instalada. Correr: pip install anthropic")
        return None

    if not ANTHROPIC_API_KEY:
        log("ANTHROPIC_API_KEY no configurada en .env")
        return None

    rules = load_market_rules()
    ctx_text = json.dumps(context, indent=2, ensure_ascii=False, default=str)

    prompt = f"""Sos un analista de trading cripto especializado en BSC/BNB Chain.
Analizá el contexto actual y decidí si es momento de comprar {symbol}.

## REGLAS DEL OPERADOR (seguirlas siempre)
{rules}

## CONTEXTO DE MERCADO AHORA
{ctx_text}

## INSTRUCCION
Respondé SOLO con JSON valido, sin texto extra:
{{
  "bias": "bullish" | "bearish" | "neutral",
  "confidence": 0.0,
  "action_modifier": "PROCEED" | "SKIP" | "REDUCE_SIZE",
  "reason": "una linea explicando la decision",
  "risk_notes": "riesgo importante si hay alguno, sino null"
}}

- PROCEED    : contexto favorable, continuar con la decision original
- SKIP       : contexto negativo (guerra, hack, crash macro), no entrar ahora
- REDUCE_SIZE: entrar pero con 50% menos capital del calculado
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        # Extraer JSON aunque Claude agregue texto extra
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            log(f"Claude no devolvio JSON: {raw[:100]}")
            return None
        result = json.loads(raw[start:end])

        # Calcular tokens usados para monitoreo de costos
        input_tokens  = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens
        cost_usd = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
        log(f"Tokens usados: {input_tokens} in / {output_tokens} out | Costo: ${cost_usd:.5f}")
        log(f"{symbol} -> {result['bias']} ({result['confidence']:.0%}) | "
            f"{result['action_modifier']} | {result['reason']}")

        # Guardar costo acumulado para analisis posterior
        _log_cost(input_tokens, output_tokens, cost_usd)

        return result

    except json.JSONDecodeError as e:
        log(f"JSON invalido de Claude: {e}")
        return None
    except Exception as e:
        log(f"Error llamando a Claude: {e}")
        return None


def _log_cost(input_tokens, output_tokens, cost_usd):
    """Guarda cada llamada en logs/claude_costs.log para monitorear consumo."""
    cost_log = "logs/claude_costs.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(cost_log, "a") as f:
        f.write(f"{timestamp} | in={input_tokens} out={output_tokens} cost=${cost_usd:.5f}\n")


# ── Funcion publica ───────────────────────────────────────────────────────────

def get_market_bias(symbol):
    """
    Funcion principal que llama el decision_engine.

    Retorna:
      - None si CLAUDE_ENABLED=false (no afecta la decision)
      - None si ocurre cualquier error (el agente sigue funcionando igual)
      - dict con bias/action_modifier/reason si CLAUDE_ENABLED=true y todo sale bien
    """
    log(f"Analizando contexto para {symbol}...")

    context = build_context(symbol)
    analysis = _call_claude(symbol, context)

    if not analysis:
        return None

    if not CLAUDE_ENABLED:
        log(f"DRY-RUN completado | Si estuviera activo: "
            f"{analysis['action_modifier']} — {analysis['reason']}")
        return None  # No modifica nada cuando esta deshabilitado

    return analysis


# ── Test manual ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test news_analyzer ===")
    print(f"CLAUDE_ENABLED = {CLAUDE_ENABLED}")
    print(f"ANTHROPIC_API_KEY configurada: {'Si' if ANTHROPIC_API_KEY else 'No'}")
    print()

    result = get_market_bias("CAKE")
    if result:
        print(f"Resultado: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print("Resultado: None (DRY-RUN o error — ver logs/news_analyzer.log)")
