import json
import os
import sys
import pathlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
POSITIONS_FILE = "data/open_positions.json"
WATCHER_LOG = "logs/position_watcher.log"
COMPLIANCE_FILE = "data/compliance_trades.json"

# Umbrales de salida
TAKE_PROFIT_PCT = 15.0   # salir si sube 15%
STOP_LOSS_PCT = -8.0     # salir si baja 8%
BTC_DROP_ALERT_PCT = -3.0  # salir de alts si BTC cae 3%


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
