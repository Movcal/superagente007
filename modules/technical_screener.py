"""
Technical Screener — RSI + Momentum + MACD para tokens en watchlist.

Usa CMC MCP get_crypto_technical_analysis + CMC quotes API.
Guarda ta_rating, ta_score y volume_threshold en watchlist.json
para que volume_monitor y decision_engine los usen.

Ratings:
  good_entry : ta_score >= 0.2  — buen punto de entrada
  wait       : ta_score >= -0.1 — esperar confirmacion
  avoid      : ta_score < -0.1  — evitar, tendencia negativa

Volume threshold segun dias en watchlist:
  >= 3 dias : 2x
  < 3 dias  : 3x
  sin watchlist: 5x (manejado por volume_monitor)
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY", "")
CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
WATCHLIST_FILE = "data/watchlist.json"
TA_LOG = "logs/technical_screener.log"

_id_cache = {}


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [TA] {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(TA_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Cliente MCP ───────────────────────────────────────────────────────────────

class CMCClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "X-CMC-MCP-API-KEY": CMC_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        })
        self._initialized = False

    def _initialize(self):
        try:
            self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "ta-screener", "version": "1.0"}}
            }, timeout=15)
            self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"
            }, timeout=10)
            self._initialized = True
        except Exception as e:
            log(f"Error inicializando MCP: {e}")

    def call(self, tool_name, arguments=None):
        if not self._initialized:
            self._initialize()
        try:
            r = self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}}
            }, timeout=20)
            result = r.json().get("result", {})
            content = result.get("content", [{}])
            text = content[0].get("text", "") if content else ""
            if text.startswith("error:"):
                return None
            return json.loads(text) if text else None
        except Exception as e:
            log(f"Error llamando {tool_name}: {e}")
            return None


def _get_cmc_id(client, symbol):
    if symbol in _id_cache:
        return _id_cache[symbol]
    results = client.call("search_cryptos", {"query": symbol})
    if results and isinstance(results, list):
        for item in results:
            if item.get("symbol", "").upper() == symbol.upper():
                _id_cache[symbol] = item["id"]
                return item["id"]
    return None


def _fetch_price_momentum(symbol):
    """Obtiene cambios de precio 7d y 30d desde CMC quotes API."""
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
                quote = token.get("quote", {}).get("USD", {})
                return {
                    "price":      quote.get("price", 0),
                    "change_1h":  quote.get("percent_change_1h", 0),
                    "change_24h": quote.get("percent_change_24h", 0),
                    "change_7d":  quote.get("percent_change_7d", 0),
                    "change_30d": quote.get("percent_change_30d", 0),
                }
    except Exception as e:
        log(f"Error obteniendo momentum de {symbol}: {e}")
    return None


# ── Clasificadores individuales ───────────────────────────────────────────────

def analyze_rsi(rsi_value):
    if rsi_value is None:
        return {"value": None, "rating": "sin_datos", "signal": "neutral", "score": 0.0}
    rsi = float(rsi_value)
    if rsi < 30:
        return {"value": rsi, "rating": "oversold",    "signal": "bullish", "score": 0.35}
    elif rsi < 50:
        return {"value": rsi, "rating": "recovering",  "signal": "bullish", "score": 0.20}
    elif rsi < 70:
        return {"value": rsi, "rating": "neutral",     "signal": "neutral", "score": 0.0}
    else:
        return {"value": rsi, "rating": "overbought",  "signal": "bearish", "score": -0.35}


def analyze_macd(macd_data):
    if not macd_data:
        return {"signal": "neutral", "histogram": None, "direction": "unknown", "score": 0.0}
    histogram   = float(macd_data.get("histogram", 0))
    macd_line   = float(macd_data.get("macd", 0))
    signal_line = float(macd_data.get("signal", 0))

    if histogram > 0 and macd_line > signal_line:
        return {"signal": "bullish", "histogram": histogram,
                "direction": "bullish", "macd": macd_line,
                "signal_line": signal_line, "score": 0.35}
    elif histogram < 0 and macd_line < signal_line:
        return {"signal": "bearish", "histogram": histogram,
                "direction": "bearish", "macd": macd_line,
                "signal_line": signal_line, "score": -0.35}
    else:
        return {"signal": "neutral", "histogram": histogram,
                "direction": "crossing", "macd": macd_line,
                "signal_line": signal_line, "score": 0.0}


def analyze_momentum(price_data):
    if not price_data:
        return {"signal": "neutral", "change_7d": None, "change_30d": None, "score": 0.0}
    change_7d  = float(price_data.get("change_7d", 0))
    change_30d = float(price_data.get("change_30d", 0))

    if change_7d > 10 and change_30d > 0:
        signal, score = "bullish_strong", 0.30
    elif change_7d > 0 and change_30d > -20:
        signal, score = "bullish", 0.15
    elif change_7d < -15 and change_30d < -20:
        signal, score = "bearish_strong", -0.30
    elif change_7d < 0:
        signal, score = "bearish", -0.15
    else:
        signal, score = "neutral", 0.0

    return {"signal": signal, "change_7d": change_7d, "change_30d": change_30d, "score": score}


# ── Análisis por token ────────────────────────────────────────────────────────

def screen_token(symbol, days_in_watchlist=0):
    """
    Análisis técnico completo de un token.

    Retorna dict con:
      rsi, macd, momentum, ta_score, ta_rating, volume_threshold, summary
    """
    log(f"Analizando TA: {symbol} ({days_in_watchlist} días en watchlist)...")

    client = CMCClient()
    cmc_id = _get_cmc_id(client, symbol)

    ta_data    = client.call("get_crypto_technical_analysis", {"id": cmc_id}) if cmc_id else None
    price_data = _fetch_price_momentum(symbol)

    rsi_raw  = ta_data.get("rsi", {}).get("rsi14") if ta_data else None
    macd_raw = ta_data.get("macd") if ta_data else None

    rsi      = analyze_rsi(rsi_raw)
    macd     = analyze_macd(macd_raw)
    momentum = analyze_momentum(price_data)

    ta_score = round(max(-1.0, min(1.0, rsi["score"] + macd["score"] + momentum["score"])), 2)

    if ta_score >= 0.2:
        ta_rating = "good_entry"
    elif ta_score >= -0.1:
        ta_rating = "wait"
    else:
        ta_rating = "avoid"

    # Threshold de volumen según días en watchlist
    volume_threshold = 2.0 if days_in_watchlist >= 3 else 3.0

    # Texto resumen para Claude
    rsi_str = f"RSI {rsi['value']:.1f} ({rsi['rating']})" if rsi["value"] else "RSI sin datos"
    macd_str = (f"MACD {macd['direction']} (hist: {macd['histogram']:.6f})"
                if macd["histogram"] is not None else "MACD sin datos")
    mom_str = (f"Momentum {momentum['signal']} (7d: {momentum['change_7d']:+.1f}%, "
               f"30d: {momentum['change_30d']:+.1f}%)"
               if momentum["change_7d"] is not None else "Momentum sin datos")

    summary = f"{rsi_str} | {macd_str} | {mom_str} | Score: {ta_score} → {ta_rating}"
    log(f"{symbol}: {summary}")

    return {
        "symbol":           symbol,
        "rsi":              rsi,
        "macd":             macd,
        "momentum":         momentum,
        "ta_score":         ta_score,
        "ta_rating":        ta_rating,
        "days_in_watchlist": days_in_watchlist,
        "volume_threshold": volume_threshold,
        "summary":          summary,
        "price_data":       price_data,
    }


# ── Escaneo completo de watchlist ─────────────────────────────────────────────

def screen_watchlist():
    """
    Analiza técnicamente todos los tokens de la watchlist.
    Guarda ta_rating, ta_score, volume_threshold en watchlist.json.
    Retorna dict {symbol: resultado_ta}.
    """
    if not os.path.exists(WATCHLIST_FILE):
        log("watchlist.json no encontrado")
        return {}

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        watchlist = json.load(f)

    if not watchlist:
        log("Watchlist vacía, nada que analizar")
        return {}

    log(f"=== TA Scan: {len(watchlist)} tokens en watchlist ===")
    results = {}

    for symbol, entry in watchlist.items():
        days = entry.get("days_in_watchlist", 0)
        try:
            result = screen_token(symbol, days)
            results[symbol] = result
            # Guardar datos TA en la entry de watchlist
            entry["ta_rating"]        = result["ta_rating"]
            entry["ta_score"]         = result["ta_score"]
            entry["volume_threshold"] = result["volume_threshold"]
            entry["ta_summary"]       = result["summary"]
            entry["ta_last_updated"]  = datetime.utcnow().isoformat()
        except Exception as e:
            log(f"Error analizando {symbol}: {e}")

    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)

    good  = sum(1 for r in results.values() if r["ta_rating"] == "good_entry")
    wait  = sum(1 for r in results.values() if r["ta_rating"] == "wait")
    avoid = sum(1 for r in results.values() if r["ta_rating"] == "avoid")
    log(f"TA scan completado: {good} good_entry | {wait} wait | {avoid} avoid")

    return results


def get_token_ta(symbol):
    """
    Retorna el TA guardado en watchlist para un token específico.
    Si no está en watchlist o no tiene TA, retorna None.
    """
    if not os.path.exists(WATCHLIST_FILE):
        return None
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        watchlist = json.load(f)
    entry = watchlist.get(symbol)
    if not entry or "ta_rating" not in entry:
        return None
    return {
        "ta_rating":        entry["ta_rating"],
        "ta_score":         entry["ta_score"],
        "volume_threshold": entry["volume_threshold"],
        "ta_summary":       entry.get("ta_summary", ""),
        "days_in_watchlist": entry.get("days_in_watchlist", 0),
    }


if __name__ == "__main__":
    print("=== Test Technical Screener ===")
    results = screen_watchlist()
    for sym, r in results.items():
        print(f"  {sym}: {r['summary']}")
