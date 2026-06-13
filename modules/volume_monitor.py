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

# 149 tokens permitidos en el hackathon
TOKENS = [
    "ETH","USDT","USDC","XRP","TRX","DOGE","ZEC","ADA","LINK","BCH","DAI","TON",
    "USD1","USDe","LTC","AVAX","SHIB","WLFI","DOT","UNI","ASTER","DEXE","USDD",
    "ETC","AAVE","ATOM","FIL","INJ","NIGHT","FET","TUSD","BONK","PENGU","CAKE",
    "SIREN","LUNC","ZRO","KITE","FDUSD","BEAT","BTT","NFT","EDGE","FLOKI","LDO",
    "PENDLE","NEX","STG","AXS","TWT","HOME","RAY","COMP","GWEI","XCN","GENIUS",
    "XPL","BAT","SKYAI","APE","IP","SFP","TAG","NXPC","AB","SAHARA","1INCH",
    "CHEEMS","BANANAS31","RIVER","MYX","RAVE","SNX","FORM","LAB","HTX","USDf",
    "CTM","BDX","SLX","UB","DUCKY","FRAX","BILL","WFI","KOGE","ALE","FRXUSD",
    "USDF","GOMINING","VCNT","GUA","DUSD","SMILEK","0G","BEAM","MY","SOON",
    "REAL","AIOZ","ZIG","YFI","TAC","CYS","ZAMA","TRIA","HUMA","PLUME","ZIL",
    "XPR","ZETA","NILA","ROSE","VELO","UAI","BRETT","OPEN","BSB","TOSHI","BAS",
    "ACH","AXL","LUR","ELF","KAVA","APR","IRYS","EURI","XUSD","BARD","DUSK",
    "SUSHI","PEAQ","COAI","BDCA","XAUM","BNB","PIEVERSE","Q","lisUSD","XAUt",
    "M","U","STABLE","H","FF","B","BabyDoge"
]

# Tokens prioritarios del ecosistema BNB (watchlist especial)
PRIORITY_TOKENS = ["BNB", "CAKE", "ASTER", "FLOKI"]


def get_cmc_headers():
    return {"X-CMC_PRO_API_KEY": CMC_API_KEY}


def fetch_volumes(symbols):
    """Consulta CMC y devuelve volumen 24h por simbolo."""
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    # CMC acepta hasta 100 simbolos por llamada, dividimos en lotes
    results = {}
    batch_size = 90
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            r = requests.get(
                url,
                headers=get_cmc_headers(),
                params={"symbol": ",".join(batch), "convert": "USD"},
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
            log(f"Error consultando CMC: {e}")
        time.sleep(0.5)
    return results


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
    log(f"ALERTA GUARDADA: {alert['symbol']} - {alert['ratio']:.1f}x volumen")


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open("logs/volume_monitor.log", "a") as f:
        f.write(line + "\n")


def check_volume_spikes(current_volumes, history):
    """Compara volumen actual con promedio historico. Devuelve alertas."""
    alerts = []
    for symbol, current_vol in current_volumes.items():
        if current_vol == 0:
            continue

        past_readings = history.get(symbol, [])

        # Necesitamos al menos 3 lecturas para calcular promedio
        if len(past_readings) < 3:
            continue

        avg_vol = sum(past_readings[-6:]) / len(past_readings[-6:])  # promedio ultimas 6 lecturas (30 min)
        if avg_vol == 0:
            continue

        ratio = current_vol / avg_vol
        is_priority = symbol in PRIORITY_TOKENS

        if ratio >= VOLUMEN_THRESHOLD:
            alert = {
                "symbol": symbol,
                "ratio": round(ratio, 2),
                "current_volume": current_vol,
                "avg_volume": avg_vol,
                "timestamp": datetime.utcnow().isoformat(),
                "priority": is_priority
            }
            alerts.append(alert)
            save_alert(alert)

    return alerts


def update_history(history, current_volumes):
    """Agrega la lectura actual al historial. Mantiene las ultimas 24 lecturas (2 horas)."""
    for symbol, vol in current_volumes.items():
        if symbol not in history:
            history[symbol] = []
        history[symbol].append(vol)
        history[symbol] = history[symbol][-24:]  # max 24 lecturas
    return history


def run_once():
    """Ejecuta una sola revision de volumenes. Retorna lista de alertas."""
    log("Revisando volumenes...")
    history = load_history()
    current_volumes = fetch_volumes(TOKENS)
    log(f"Tokens consultados: {len(current_volumes)}")

    alerts = check_volume_spikes(current_volumes, history)
    history = update_history(history, current_volumes)
    save_history(history)

    if alerts:
        log(f"SPIKES DETECTADOS: {len(alerts)} token(s)")
        for a in alerts:
            priority_tag = " [PRIORITARIO]" if a["priority"] else ""
            log(f"  -> {a['symbol']}: {a['ratio']}x volumen{priority_tag}")
    else:
        log("Sin spikes detectados.")

    return alerts


def run_loop():
    """Loop principal: revisa cada 5 minutos."""
    log("=== Monitor de Volumen iniciado ===")
    log(f"Threshold: {VOLUMEN_THRESHOLD}x | Intervalo: {VOLUMEN_TIMEFRAME_MIN} min")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"Error en ciclo: {e}")
        time.sleep(VOLUMEN_TIMEFRAME_MIN * 60)


if __name__ == "__main__":
    run_loop()
