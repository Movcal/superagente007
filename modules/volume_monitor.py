import requests
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
VOLUMEN_THRESHOLD = float(os.getenv("VOLUMEN_THRESHOLD", 5))
VOLUMEN_TIMEFRAME_MIN = int(os.getenv("VOLUMEN_TIMEFRAME_MIN", 5))
ALERTS_FILE = "data/volume_alerts.json"
HISTORY_FILE = "data/volume_history.json"

# Tokens con liquidez verificada en PancakeSwap BSC (>$10k)
# Investigacion completa: 2026-06-16 | Script: investigate_liquidity.py
# De 149 permitidos en el hackathon, 86 tienen pool activa con liquidez suficiente
TOKENS = [
    "ETH","XRP","TRX","DOGE","ZEC","ADA","LINK","BCH","TON","LTC",
    "AVAX","SHIB","WLFI","DOT","UNI","ASTER","DEXE","ETC","AAVE","ATOM",
    "FIL","INJ","FET","BONK","PENGU","CAKE","SIREN","LUNC","ZRO","BTT",
    "FLOKI","PENDLE","AXS","TWT","HOME","COMP","XCN","GENIUS","XPL","SKYAI",
    "APE","SFP","TAG","AB","SAHARA","CHEEMS","BANANAS31","RIVER","MYX","FORM",
    "LAB","HTX","UB","DUCKY","WFI","KOGE","GOMINING","0G","BEAM",
    "MY","SOON","AIOZ","ZIG","TAC","HUMA","ZIL","VELO","BRETT","OPEN",
    "BSB","TOSHI","BAS","KAVA","IRYS","DUSK","SUSHI","PEAQ","COAI",
    "BDCA","BNB","Q","FF","B","BabyDoge",
]

STABLECOINS = {
    "USDT","USDC","DAI","BUSD","TUSD","FDUSD","FRAX","FRXUSD","USDD","USD1",
    "USDe","USDf","USDF","DUSD","XUSD","EURI","lisUSD","STABLE","XAUM","XAUt",
    "SMILEK","GUA","M","U"
}

PRIORITY_TOKENS = ["BNB", "CAKE", "ASTER", "FLOKI"]

# Mapa de fuentes de datos por vela de 5min.
# Verificado: 2026-06-19 contra APIs de Gate.io, KuCoin, MEXC.
# Gate.io es la fuente principal (no bloqueada desde DigitalOcean VPS).
# Formato: symbol -> (exchange, symbol_en_exchange)
EXCHANGE_SOURCE = {
    # Gate.io con simbolo diferente al nuestro
    "TON":      ("gate",    "GRAM"),
    "BabyDoge": ("gate",    "BABYDOGE"),
    # MEXC — unica fuente disponible para estos 3
    "BSB":      ("mexc",    "BSB"),
    "RIVER":    ("mexc",    "RIVER"),
    "BDCA":     ("mexc",    "BDCA"),
    # KuCoin
    "TAC":      ("kucoin",  "TAC"),
    # CMC 24h fallback — sin par en CEX accesible desde VPS
    "DUCKY":    ("cmc",     "DUCKY"),
    "KOGE":     ("cmc",     "KOGE"),
}
# Todos los demas van a Gate.io con su simbolo normal


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open("logs/volume_monitor.log", "a") as f:
        f.write(line + "\n")


# ── Fuentes de velas por exchange ─────────────────────────────────────────────

def fetch_gate_candle(gate_symbol):
    """Ultima vela completada de 5min de Gate.io.
    Retorna (vol_usdt, open, close) o None.
    Gate formato: [timestamp, vol_quote, close, high, low, open, vol_base]
    """
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/candlesticks",
            params={"currency_pair": f"{gate_symbol}_USDT", "interval": "5m", "limit": "3"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if len(data) >= 2:
                c = data[-2]  # -1 es la vela formandose, -2 es la ultima completada
                return float(c[1]), float(c[5]), float(c[2])  # vol_usdt, open, close
    except Exception as e:
        log(f"Error Gate.io {gate_symbol}: {e}")
    return None


def fetch_gate_candles_bulk(gate_symbol, limit=900):
    """Trae las ultimas N velas completadas de 5min de Gate.io (maximo 1000).
    Retorna (current_tuple, history_vols) donde:
      - current_tuple = (vol_usdt, open, close) de la ultima vela completada
      - history_vols  = lista de vol_usdt de las velas anteriores (~898)
    """
    try:
        r = requests.get(
            "https://api.gateio.ws/api/v4/spot/candlesticks",
            params={"currency_pair": f"{gate_symbol}_USDT", "interval": "5m", "limit": str(limit)},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            if len(data) < 3:
                return None, []
            # data[-1] = vela formandose (excluir)
            # data[-2] = ultima vela completada = actual
            # data[:-2] = historial
            current = data[-2]
            history_candles = data[:-2]
            current_tuple = (float(current[1]), float(current[5]), float(current[2]))
            history_vols = [float(c[1]) for c in history_candles]
            return current_tuple, history_vols
    except Exception as e:
        log(f"Error Gate.io bulk {gate_symbol}: {e}")
    return None, []


def load_watchlist_symbols():
    """Retorna el set de simbolos actualmente en watchlist."""
    if not os.path.exists("data/watchlist.json"):
        return set()
    try:
        with open("data/watchlist.json") as f:
            return set(json.load(f).keys())
    except Exception:
        return set()


def is_top2_spike(current_vol, history_vols):
    """Retorna True si current_vol esta entre las 2 velas mas grandes del historial."""
    if len(history_vols) < 10:
        return False
    top2_threshold = sorted(history_vols, reverse=True)[1]  # 2do mas grande
    return current_vol >= top2_threshold


def fetch_mexc_candle(symbol):
    """Ultima vela completada de 5min de MEXC.
    MEXC formato: [timestamp, open, high, low, close, vol_base, ...]
    """
    try:
        r = requests.get(
            "https://api.mexc.com/api/v3/klines",
            params={"symbol": f"{symbol}USDT", "interval": "5m", "limit": "3"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if len(data) >= 2:
                c = data[-2]
                open_  = float(c[1])
                close  = float(c[4])
                vol_base = float(c[5])
                vol_usdt = vol_base * close  # aproximacion en USDT
                return vol_usdt, open_, close
    except Exception as e:
        log(f"Error MEXC {symbol}: {e}")
    return None


def fetch_kucoin_candle(symbol):
    """Ultima vela completada de 5min de KuCoin.
    KuCoin formato (descendente): [timestamp, open, close, high, low, vol_base, turnover_usdt]
    """
    try:
        r = requests.get(
            "https://api.kucoin.com/api/v1/market/candles",
            params={"type": "5min", "symbol": f"{symbol}-USDT"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if len(data) >= 2:
                c = data[1]  # KuCoin retorna descendente, index 1 = ultima completada
                open_    = float(c[1])
                close    = float(c[2])
                vol_usdt = float(c[6])  # turnover en USDT
                return vol_usdt, open_, close
    except Exception as e:
        log(f"Error KuCoin {symbol}: {e}")
    return None


def fetch_cmc_volumes(symbols):
    """Fallback CMC 24h para tokens sin par en CEX. Retorna {symbol: vol_24h}."""
    results = {}
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": ",".join(symbols), "convert": "USD"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            for symbol, info in data.items():
                if isinstance(info, list):
                    info = info[0]
                vol = info.get("quote", {}).get("USD", {}).get("volume_24h", 0)
                results[symbol] = vol
    except Exception as e:
        log(f"Error CMC fallback: {e}")
    return results


def fetch_candle_for_token(symbol):
    """Obtiene (vol_usdt, open, close) de la ultima vela completada segun la fuente configurada."""
    source_info = EXCHANGE_SOURCE.get(symbol)
    if source_info:
        exchange, ex_symbol = source_info
        if exchange == "gate":
            return fetch_gate_candle(ex_symbol)
        elif exchange == "mexc":
            return fetch_mexc_candle(ex_symbol)
        elif exchange == "kucoin":
            return fetch_kucoin_candle(ex_symbol)
        elif exchange == "cmc":
            return None  # se maneja en lote aparte
    else:
        return fetch_gate_candle(symbol)  # Gate con simbolo normal


def fetch_all_volumes():
    """Trae volumen de todos los tokens. Retorna {symbol: (vol_usdt, open, close)}."""
    results = {}
    cmc_fallback = [s for s in TOKENS if EXCHANGE_SOURCE.get(s, ("gate",))[0] == "cmc"]

    for symbol in TOKENS:
        if symbol in STABLECOINS:
            continue
        if symbol in cmc_fallback:
            continue
        candle = fetch_candle_for_token(symbol)
        if candle:
            results[symbol] = candle
        time.sleep(0.12)  # ~8 req/s, dentro del limite de Gate.io

    # CMC fallback en lote
    if cmc_fallback:
        cmc_vols = fetch_cmc_volumes(cmc_fallback)
        for sym, vol in cmc_vols.items():
            results[sym] = (vol, 0, 0)  # sin OHLC

    return results


# ── Historia y alertas ────────────────────────────────────────────────────────

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_alert(alert):
    alerts = load_alerts()
    alerts.append(alert)
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)
    log(f"ALERTA GUARDADA: {alert['symbol']} - {alert['ratio']:.1f}x volumen | precio {alert['price_change_pct']:+.2f}%")


def load_watchlist_thresholds():
    """Lee watchlist.json y retorna {symbol: threshold}."""
    thresholds = {}
    if not os.path.exists("data/watchlist.json"):
        return thresholds
    try:
        with open("data/watchlist.json", "r") as f:
            watchlist = json.load(f)
        for symbol, entry in watchlist.items():
            days = entry.get("days_in_watchlist", 0)
            thresholds[symbol] = 2.0 if days >= 3 else 3.0
    except Exception:
        pass
    return thresholds


def check_volume_spikes(candle_data, history):
    """Compara volumen de la vela actual contra baseline de 24 velas (2 horas).
    Solo genera alerta si el precio tambien subio (confirmacion de direccion).
    """
    watchlist_thresholds = load_watchlist_thresholds()
    alerts = []

    for symbol, (current_vol, open_, close) in candle_data.items():
        if current_vol == 0:
            continue

        past_readings = history.get(symbol, [])
        if len(past_readings) < 6:
            continue

        baseline_readings = past_readings[-24:] if len(past_readings) >= 24 else past_readings
        baseline = sum(baseline_readings) / len(baseline_readings)
        if baseline == 0:
            continue

        ratio = current_vol / baseline
        is_priority = symbol in PRIORITY_TOKENS
        threshold = watchlist_thresholds.get(symbol, VOLUMEN_THRESHOLD)

        # Confirmacion de direccion: precio subio con el volumen
        # Para CMC fallback (open=0) se omite este filtro
        price_up = (close > open_) if open_ > 0 else True
        price_change_pct = round((close - open_) / open_ * 100, 2) if open_ > 0 else 0

        if ratio >= threshold and price_up:
            alert = {
                "symbol":           symbol,
                "ratio":            round(ratio, 2),
                "current_volume":   current_vol,
                "avg_volume":       baseline,
                "open":             open_,
                "close":            close,
                "price_change_pct": price_change_pct,
                "timestamp":        datetime.utcnow().isoformat(),
                "priority":         is_priority,
                "threshold_used":   threshold,
                "in_watchlist":     symbol in watchlist_thresholds,
            }
            alerts.append(alert)
            save_alert(alert)

    return alerts


def update_history(history, candle_data):
    """Agrega volumen actual al historial. Mantiene las ultimas 48 lecturas (4 horas)."""
    for symbol, (vol, open_, close) in candle_data.items():
        if symbol not in history:
            history[symbol] = []
        history[symbol].append(vol)
        history[symbol] = history[symbol][-48:]
    return history


# ── Loop principal ────────────────────────────────────────────────────────────

def run_once():
    """Ejecuta una sola revision de volumenes. Retorna lista de alertas."""
    log("Revisando volumenes por vela 5min...")

    watchlist_symbols = load_watchlist_symbols()
    history = load_history()
    candle_data = {}
    alerts = []

    for symbol in TOKENS:
        if symbol in STABLECOINS:
            continue

        source_info = EXCHANGE_SOURCE.get(symbol)
        exchange   = source_info[0] if source_info else "gate"
        ex_symbol  = source_info[1] if source_info else symbol

        if exchange == "cmc":
            continue  # se procesa en lote aparte

        # ── Gate.io: TODOS usan top-2 de 1000 velas ──────────────────────────
        if exchange == "gate":
            current_tuple, hist_vols = fetch_gate_candles_bulk(ex_symbol, limit=900)
            if current_tuple:
                current_vol, open_, close = current_tuple
                candle_data[symbol] = current_tuple
                price_up = close > open_ if open_ > 0 else False
                price_change_pct = round((close - open_) / open_ * 100, 2) if open_ > 0 else 0

                if price_up and is_top2_spike(current_vol, hist_vols):
                    avg_vol = round(sum(hist_vols) / len(hist_vols), 2) if hist_vols else 0
                    ratio   = round(current_vol / avg_vol, 2) if avg_vol > 0 else 0
                    alert = {
                        "symbol":           symbol,
                        "ratio":            ratio,
                        "current_volume":   current_vol,
                        "avg_volume":       avg_vol,
                        "open":             open_,
                        "close":            close,
                        "price_change_pct": price_change_pct,
                        "timestamp":        datetime.utcnow().isoformat(),
                        "priority":         symbol in PRIORITY_TOKENS,
                        "threshold_used":   "top2_of_1000",
                        "in_watchlist":     symbol in watchlist_symbols,
                    }
                    alerts.append(alert)
                    save_alert(alert)
                    log(f"ALERTA [TOP-2/1000]: {symbol} | vol ${current_vol:,.0f} | precio {price_change_pct:+.2f}%")

        # ── MEXC / KuCoin: metodo clasico (sin bulk disponible) ──────────────
        else:
            if exchange == "mexc":
                candle = fetch_mexc_candle(ex_symbol)
            elif exchange == "kucoin":
                candle = fetch_kucoin_candle(ex_symbol)
            if candle:
                candle_data[symbol] = candle

        time.sleep(0.12)

    # CMC fallback en lote para tokens sin par en CEX
    cmc_fallback = [s for s in TOKENS if EXCHANGE_SOURCE.get(s, ("gate",))[0] == "cmc" and s not in STABLECOINS]
    if cmc_fallback:
        cmc_vols = fetch_cmc_volumes(cmc_fallback)
        for sym, vol in cmc_vols.items():
            candle_data[sym] = (vol, 0, 0)

    log(f"Tokens consultados: {len(candle_data)}")

    # Metodo clasico solo para MEXC/KuCoin (sin bulk disponible)
    non_gate_data = {s: v for s, v in candle_data.items()
                     if EXCHANGE_SOURCE.get(s, ("gate",))[0] in ("mexc", "kucoin")}
    classic_alerts = check_volume_spikes(non_gate_data, history)
    alerts.extend(classic_alerts)

    history = update_history(history, candle_data)
    save_history(history)

    if alerts:
        log(f"SPIKES DETECTADOS: {len(alerts)} token(s)")
        for a in alerts:
            priority_tag = " [PRIORITARIO]" if a["priority"] else ""
            log(f"  -> {a['symbol']}: {a['ratio']:.1f}x volumen | precio {a['price_change_pct']:+.2f}%{priority_tag}")
    else:
        log("Sin spikes detectados.")

    return alerts


def run_loop():
    """Loop principal: revisa cada 5 minutos."""
    log("=== Monitor de Volumen iniciado (velas 5min) ===")
    log(f"Threshold: {VOLUMEN_THRESHOLD}x | Intervalo: {VOLUMEN_TIMEFRAME_MIN} min")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"Error en ciclo: {e}")
        time.sleep(VOLUMEN_TIMEFRAME_MIN * 60)


if __name__ == "__main__":
    run_loop()
