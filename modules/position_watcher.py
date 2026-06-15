import json
import os
import sys
import pathlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY    = os.getenv("CMC_API_KEY")
CMC_MCP_URL    = "https://mcp.coinmarketcap.com/mcp"
POSITIONS_FILE = "data/open_positions.json"
WATCHER_LOG    = "logs/position_watcher.log"
COMPLIANCE_FILE = "data/compliance_trades.json"

# Umbrales de salida
TAKE_PROFIT_PCT   = 15.0   # salir si sube 15%
STOP_LOSS_PCT     = -8.0   # salir si baja 8%
BTC_DROP_ALERT_PCT = -3.0  # salir de alts si BTC cae 3%

# Palabras clave de noticias negativas que fuerzan salida inmediata
NEWS_EXIT_KEYWORDS = [
    "hack", "exploit", "rug", "scam", "fraud", "arrest", "ban",
    "sec", "lawsuit", "breach", "attack", "stolen", "insolvent",
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
                title   = (row[0] if len(row) > 0 else "").lower()
                content = (row[1] if len(row) > 1 else "").lower()
                combined = title + " " + content
                for kw in NEWS_EXIT_KEYWORDS:
                    if kw in combined:
                        return True, f"noticia negativa detectada: '{kw}' en '{row[0][:60]}'"

        # 2. RSI y MACD
        ta = _mcp_call(session, "get_crypto_technical_analysis", {"id": cmc_id})
        if ta:
            rsi14 = float(ta.get("rsi", {}).get("rsi14", 50))
            macd_hist = float(ta.get("macd", {}).get("histogram", 0))

            if rsi14 > 75:
                return True, f"RSI14 sobrecomprado ({rsi14:.1f}) — momentum agotándose"

            if rsi14 > 70 and macd_hist < 0:
                return True, f"RSI alto ({rsi14:.1f}) + MACD histogram negativo ({macd_hist:.6f}) — señal de reversión"

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
    Retorna: (debe_salir, razon) o (False, None)
    """
    symbol = position["symbol"]
    entry_time = datetime.fromisoformat(position["entry_time"])
    hold_max_hours = position.get("hold_max_hours", 12)
    hours_open = (datetime.utcnow() - entry_time.replace(tzinfo=None)).total_seconds() / 3600

    entry_price = get_entry_price(position)

    # 1. Tiempo maximo excedido
    if hours_open >= hold_max_hours:
        return True, f"tiempo maximo alcanzado ({hold_max_hours}h)"

    # 2. BTC cayo mas del 3% (macro negativa)
    if btc_change <= BTC_DROP_ALERT_PCT:
        return True, f"BTC cayo {btc_change:.2f}% (proteccion macro)"

    if entry_price and current_price:
        pct_change = ((current_price - entry_price) / entry_price) * 100

        # 3. Take profit
        if pct_change >= TAKE_PROFIT_PCT:
            return True, f"take profit: +{pct_change:.2f}%"

        # 4. Stop loss
        if pct_change <= STOP_LOSS_PCT:
            return True, f"stop loss: {pct_change:.2f}%"

        log(f"{symbol}: precio ${current_price:.4f} | entrada ~${entry_price:.4f} | cambio: {pct_change:+.2f}%")

    return False, None


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

        should_exit, reason = check_exit_conditions(position, current_price, btc_change)

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
