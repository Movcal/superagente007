import json
import os
import re
import sys
import pathlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY       = os.getenv("CMC_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"
CMC_MCP_URL    = "https://mcp.coinmarketcap.com/mcp"
POSITIONS_FILE = "data/open_positions.json"
WATCHER_LOG    = "logs/position_watcher.log"
COMPLIANCE_FILE = "data/compliance_trades.json"

# Umbrales de salida — estrategia semana de competencia
STOP_LOSS_PCT      = -3.0  # stop loss fijo (antes de que se active el trailing)
TRAILING_STOP_PCT  = 0.01  # trailing stop: 1% bajo el maximo alcanzado
TRAILING_ACTIVATION = 0.01 # se activa cuando precio sube 1% desde entrada
BTC_DROP_ALERT_PCT = -3.0  # salir de alts si BTC cae 3%

# Palabras clave de noticias negativas que fuerzan salida inmediata
NEWS_EXIT_KEYWORDS = [
    "hack", "exploit", "rug", "scam", "fraud", "arrest", "ban",
    "lawsuit", "breach", "attack", "stolen", "insolvent",
    "bankrupt", "shutdown", "suspend", "delist", "delisted"
]

# Cache de IDs CMC para el watcher
_watcher_id_cache = {}


# ── Cliente MCP liviano para el watcher ──────────────────────────────────────

def _mcp_session():
    """Crea y devuelve una sesion MCP inicializada."""
    s = requests.Session()
    s.headers.update({
        "X-CMC-MCP-API-KEY": CMC_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    })
    s.post(CMC_MCP_URL, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "watcher", "version": "1.0"}}
    }, timeout=10)
    s.post(CMC_MCP_URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=5)
    return s

def _mcp_call(session, tool, args={}):
    try:
        r = session.post(CMC_MCP_URL, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool, "arguments": args}
        }, timeout=20)
        text = r.json().get("result", {}).get("content", [{}])[0].get("text", "")
        if text and not text.startswith("error:"):
            return json.loads(text)
    except Exception:
        pass
    return None

def _get_cmc_id(session, symbol):
    if symbol in _watcher_id_cache:
        return _watcher_id_cache[symbol]
    result = _mcp_call(session, "search_cryptos", {"query": symbol})
    if result and isinstance(result, list):
        for item in result:
            if item.get("symbol", "").upper() == symbol.upper():
                _watcher_id_cache[symbol] = item["id"]
                return item["id"]
    return None


# ── Señales de salida inteligentes via MCP ───────────────────────────────────

def check_mcp_exit_signals(symbol):
    """
    Analiza señales de salida usando CMC MCP.
    Retorna (debe_salir, razon) o (False, None).
    Señales monitoreadas:
    - Noticias negativas confirmadas (hack, exploit, ban, etc.)
    - RSI14 > 75 (sobrecomprado — momentum agotándose)
    - MACD histogram cruzando a negativo (reversión bajista)
    - Narrativa del sector saliendo del top 8
    """
    try:
        session = _mcp_session()
        cmc_id  = _get_cmc_id(session, symbol)
        if not cmc_id:
            return False, None

        # 1. Noticias negativas
        news_data = _mcp_call(session, "get_crypto_latest_news", {"id": cmc_id})
        if news_data:
            rows = news_data.get("rows", [])
            for row in rows[:5]:
                title   = (row[0] if len(row) > 0 else "")
                content = (row[1] if len(row) > 1 else "")
                combined = (title + " " + content).lower()
                for kw in NEWS_EXIT_KEYWORDS:
                    if re.search(r'\b' + re.escape(kw) + r'\b', combined):
                        log(f"Keyword '{kw}' detectado en '{title[:60]}' — evaluando con Claude...")
                        if _evaluate_news_with_claude(symbol, kw, title, content):
                            return True, f"noticia negativa actual confirmada: '{kw}' en '{title[:60]}'"
                        # Si Claude dice que es historico, seguir revisando otras noticias

        # 2. Agotamiento — requiere los 3 juntos: RSI>70 + MACD negativo + volumen normalizado
        ta = _mcp_call(session, "get_crypto_technical_analysis", {"id": cmc_id})
        if ta:
            rsi14     = float(ta.get("rsi", {}).get("rsi14", 50))
            macd_hist = float(ta.get("macd", {}).get("histogram", 0))

            rsi_exhausted  = rsi14 > 70
            macd_bearish   = macd_hist < 0
            vol_normalized = _check_volume_normalized(symbol)

            if rsi_exhausted and macd_bearish and vol_normalized:
                return True, (f"Agotamiento confirmado: RSI {rsi14:.1f} (>70) + "
                              f"MACD hist {macd_hist:.6f} (<0) + volumen normalizado")

        # 3. Narrativa perdiendo fuerza
        narratives = _mcp_call(session, "trending_crypto_narratives")
        if narratives:
            rows = narratives.get("categoryList", {}).get("rows", [])
            top8_names = [r[3].lower() if len(r) > 3 else "" for r in rows[:8]]
            # Buscar si el sector del token sigue en el top 8
            sector_keywords = {
                "ASTER": ["aster", "dex", "perp"],
                "CAKE":  ["binance", "defi", "pancake"],
                "FLOKI": ["meme", "dog"],
                "TWT":   ["binance", "wallet"],
            }
            kws = sector_keywords.get(symbol.upper(), [symbol.lower()])
            sector_present = any(
                any(kw in name for kw in kws)
                for name in top8_names
            )
            if not sector_present and kws:
                return True, f"narrativa de {symbol} salió del top 8 del mercado"

        return False, None

    except Exception as e:
        log(f"Error en check_mcp_exit_signals({symbol}): {e}")
        return False, None


def _evaluate_news_with_claude(symbol, keyword, title, content):
    """
    Evalua si una noticia que contiene un keyword negativo es un evento
    ACTUAL/FUTURO (accionable) o una referencia HISTORICA (ignorar).

    Retorna True si es actual/futuro y debe forzar salida.
    Retorna False si es historico o si Claude no puede evaluar (conservador).
    """
    if not ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = (
            f"You are evaluating whether a crypto news article requires immediate action.\n\n"
            f"Token: {symbol}\n"
            f"Triggered keyword: '{keyword}'\n"
            f"Article title: {title[:200]}\n"
            f"Article content: {content[:400]}\n\n"
            f"Question: Is this article describing a CURRENT or UPCOMING negative event "
            f"that is happening NOW or will happen SOON (actionable)? "
            f"Or is it referencing a PAST/HISTORICAL event (not actionable)?\n\n"
            f"Examples of HISTORICAL (not actionable): 'Back in 2023, the SEC sued...', "
            f"'Lessons from the 2022 hack...', 'How exchanges recovered after the breach'\n"
            f"Examples of CURRENT/UPCOMING (actionable): 'SEC just filed charges against...', "
            f"'Exchange hacked today, funds stolen', 'New ban effective next week'\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{\"is_current_negative\": true/false, \"reason\": \"one line\"}}'
        )
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        is_current = result.get("is_current_negative", False)
        reason = result.get("reason", "")
        log(f"[CLAUDE-NEWS] {symbol} keyword='{keyword}' → {'CURRENT' if is_current else 'HISTORICAL'}: {reason}")
        return is_current
    except Exception as e:
        log(f"[CLAUDE-NEWS] Error evaluando noticia: {e} — defaulting to no-exit")
        return False


def _check_volume_normalized(symbol):
    """
    Verifica si el volumen del token volvió al promedio histórico.
    Retorna True si las últimas 3 lecturas están por debajo del promedio de las anteriores.
    """
    history_file = "data/volume_history.json"
    if not os.path.exists(history_file):
        return False
    try:
        with open(history_file, "r") as f:
            history = json.load(f)
        readings = history.get(symbol, [])
        if len(readings) < 9:
            return False
        baseline = sum(readings[-9:-3]) / 6   # promedio de lecturas 4-9 atras
        recent   = sum(readings[-3:]) / 3     # promedio ultimas 3 lecturas
        if baseline == 0:
            return False
        return (recent / baseline) < 1.5      # volumen normalizado si cayo bajo 1.5x
    except Exception:
        return False


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [WATCHER] {msg}"
    print(line)
    with open(WATCHER_LOG, "a") as f:
        f.write(line + "\n")


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return []


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def get_current_price(symbol):
    """Obtiene el precio actual de un token via CMC."""
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    try:
        r = requests.get(
            url,
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": symbol, "convert": "USD"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            token = data.get(symbol)
            if isinstance(token, list):
                token = token[0]
            if token:
                return token["quote"]["USD"]["price"]
    except Exception as e:
        log(f"Error obteniendo precio de {symbol}: {e}")
    return None


def get_btc_change_1h():
    """Obtiene el cambio de BTC en la ultima hora."""
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    try:
        r = requests.get(
            url,
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": "BTC", "convert": "USD"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            btc = data.get("BTC")
            if isinstance(btc, list):
                btc = btc[0]
            if btc:
                return btc["quote"]["USD"]["percent_change_1h"]
    except Exception as e:
        log(f"Error obteniendo precio de BTC: {e}")
    return 0.0


def get_entry_price(position):
    """Extrae el precio de entrada del resultado del swap."""
    swap = position.get("swap_result", {})
    capital = position.get("capital", 0)
    output_str = swap.get("output", "")
    try:
        amount_received = float(output_str.split()[0])
        if amount_received > 0:
            return capital / amount_received
    except Exception:
        pass
    return None


def check_exit_conditions(position, current_price, btc_change):
    """
    Evalua si se debe salir de una posicion.
    Retorna: (debe_salir, razon, posicion_actualizada)

    Salidas en orden de prioridad:
      1. BTC cae mas del 3% (macro)
      2. Trailing stop 2% (activo cuando precio sube 2% desde entrada)
      3. Stop loss -8% (antes de que el trailing se active)
    Sin tiempo maximo — la posicion dura mientras no se activen las salidas.
    """
    symbol = position["symbol"]

    # 1. BTC cayo mas del 3% (macro negativa)
    if btc_change <= BTC_DROP_ALERT_PCT:
        return True, f"BTC cayo {btc_change:.2f}% (proteccion macro)", position

    entry_price = get_entry_price(position)
    if not entry_price or not current_price:
        return False, None, position

    pct_change = ((current_price - entry_price) / entry_price) * 100

    # Actualizar highest_price
    highest_price = max(position.get("highest_price", entry_price), current_price)
    position["highest_price"] = highest_price

    # 2. Trailing stop (se activa cuando precio sube TRAILING_ACTIVATION desde entrada)
    if highest_price >= entry_price * (1 + TRAILING_ACTIVATION):
        trailing_stop = highest_price * (1 - TRAILING_STOP_PCT)
        if current_price <= trailing_stop:
            return True, (f"trailing stop: precio ${current_price:.4f} bajo "
                          f"${trailing_stop:.4f} (2% bajo maximo ${highest_price:.4f}, "
                          f"ganancia neta: {pct_change:+.2f}%)"), position
        log(f"{symbol}: ${current_price:.4f} | max ${highest_price:.4f} | "
            f"trailing stop ${trailing_stop:.4f} | {pct_change:+.2f}%")
    else:
        # 3. Stop loss fijo mientras trailing no esta activo
        if pct_change <= STOP_LOSS_PCT:
            return True, f"stop loss: {pct_change:.2f}%", position
        log(f"{symbol}: ${current_price:.4f} | entrada ${entry_price:.4f} | "
            f"{pct_change:+.2f}% (trailing aun no activo)")

    return False, None, position


def needs_compliance_trade():
    """Verifica si ya hubo al menos 1 trade hoy."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Revisar posiciones abiertas y cerradas hoy
    positions = load_positions()
    for p in positions:
        entry_date = p.get("entry_time", "")[:10]
        if entry_date == today:
            return False

    # Revisar compliance trades
    if os.path.exists(COMPLIANCE_FILE):
        with open(COMPLIANCE_FILE, "r") as f:
            compliance = json.load(f)
        for t in compliance:
            if t.get("date") == today:
                return False

    return True


def log_compliance_trade():
    """Registra que se hizo un trade de cumplimiento hoy."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    trades = []
    if os.path.exists(COMPLIANCE_FILE):
        with open(COMPLIANCE_FILE, "r") as f:
            trades = json.load(f)
    trades.append({"date": today, "timestamp": datetime.utcnow().isoformat()})
    with open(COMPLIANCE_FILE, "w") as f:
        json.dump(trades, f, indent=2)


def check_all_positions():
    """
    Revisa todas las posiciones abiertas y decide si cerrar alguna.
    Retorna lista de simbolos cerrados.
    """
    from modules.trade_executor import sell

    positions = load_positions()
    open_positions = [p for p in positions if p.get("status") == "OPEN"]

    if not open_positions:
        log("Sin posiciones abiertas.")
        return []

    btc_change = get_btc_change_1h()
    log(f"BTC cambio 1h: {btc_change:+.2f}% | Posiciones abiertas: {len(open_positions)}")

    closed = []
    for position in open_positions:
        symbol = position["symbol"]
        current_price = get_current_price(symbol)

        if not current_price:
            log(f"{symbol}: no se pudo obtener precio, saltando")
            continue

        should_exit, reason, position = check_exit_conditions(position, current_price, btc_change)

        # Si las condiciones basicas no disparan salida, verificar señales MCP
        if not should_exit:
            should_exit, reason = check_mcp_exit_signals(symbol)
            if should_exit:
                log(f"Señal MCP de salida para {symbol}: {reason}")

        if should_exit:
            log(f"SALIENDO de {symbol}: {reason}")
            success = sell(position, reason=reason)
            if success:
                closed.append(symbol)
        else:
            # Guardar highest_price actualizado aunque no haya salida
            all_positions = load_positions()
            for i, p in enumerate(all_positions):
                if p["symbol"] == symbol and p.get("status") == "OPEN":
                    all_positions[i]["highest_price"] = position.get("highest_price", current_price)
                    break
            save_positions(all_positions)

    return closed


def run_compliance_check():
    """
    Verifica si hay que hacer trade de cumplimiento.
    Se ejecuta cerca del final del dia UTC.
    """
    now_utc = datetime.utcnow()
    # Solo ejecutar entre las 22:00 y 23:00 UTC si no hubo trades
    if 22 <= now_utc.hour < 23:
        if needs_compliance_trade():
            log("No hubo trades hoy. Ejecutando trade de cumplimiento...")
            from modules.trade_executor import compliance_trade
            success = compliance_trade()
            if success:
                log_compliance_trade()
                log("Trade de cumplimiento ejecutado correctamente")
        else:
            log("Ya hubo al menos 1 trade hoy, no se necesita compliance trade")


def run_once():
    """Ejecuta una revision completa de posiciones + compliance check."""
    log("Revisando posiciones abiertas...")
    closed = check_all_positions()
    run_compliance_check()
    return closed


if __name__ == "__main__":
    print("=== Prueba del Vigilante de Posiciones ===\n")
    print("Revisando posiciones abiertas...")
    closed = check_all_positions()
    if closed:
        print(f"Posiciones cerradas: {closed}")
    else:
        print("Sin posiciones para cerrar.")

    print(f"\nNecesita trade de cumplimiento hoy: {needs_compliance_trade()}")
