import subprocess
import shutil
import json
import os
import sys
import pathlib
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

from modules.token_registry import get_contract

WALLET_PASSWORD = os.getenv("TWAK_WALLET_PASSWORD")
POSITIONS_FILE = "data/open_positions.json"
TRADES_LOG = "logs/trades.log"

# Token de compra base (todo el capital en USDT antes de comprar)
BASE_TOKEN = "USDT"


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [EXECUTOR] {msg}"
    print(line)
    with open(TRADES_LOG, "a") as f:
        f.write(line + "\n")


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return []


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def run_twak(args):
    """Ejecuta un comando twak y retorna el resultado."""
    # Buscar el ejecutable de twak sin depender de la shell
    twak_exe = shutil.which("twak")
    if not twak_exe:
        log("twak no encontrado en el PATH")
        return None

    # TWAK_WALLET_PASSWORD se pasa como variable de entorno (no como argumento CLI)
    # para que no quede visible en la lista de procesos del sistema
    env = os.environ.copy()
    if WALLET_PASSWORD:
        env["TWAK_WALLET_PASSWORD"] = WALLET_PASSWORD

    cmd = [twak_exe] + args + ["--json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
            env=env
        )
        if result.returncode == 0 and result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout.strip()}
        else:
            log(f"Error twak: {result.stderr.strip()}")
            return None
    except subprocess.TimeoutExpired:
        log("Timeout ejecutando twak")
        return None
    except Exception as e:
        log(f"Excepcion twak: {e}")
        return None


def resolve_token(symbol):
    """Resuelve el contrato BSC de un token o retorna el simbolo si no se encuentra."""
    contract = get_contract(symbol)
    if contract:
        return contract
    log(f"Advertencia: contrato de {symbol} no encontrado, usando simbolo")
    return symbol


def get_quote(from_token, to_token, amount_usd):
    """Obtiene cotizacion del swap sin ejecutarlo."""
    from_addr = resolve_token(from_token)
    to_addr = resolve_token(to_token)
    log(f"Cotizando swap: {amount_usd} {from_token} -> {to_token}")
    result = run_twak([
        "swap", str(amount_usd), from_addr, to_addr,
        "--chain", "bsc",
        "--quote-only"
    ])
    return result


def execute_swap(from_token, to_token, amount_usd):
    """Ejecuta el swap real en PancakeSwap via TWAK."""
    from_addr = resolve_token(from_token)
    to_addr = resolve_token(to_token)
    log(f"Ejecutando swap: {amount_usd} {from_token} -> {to_token} en BSC")
    result = run_twak([
        "swap", str(amount_usd), from_addr, to_addr,
        "--chain", "bsc"
    ])
    return result


def buy(decision):
    """
    Compra el token indicado en la decision.
    Retorna la posicion abierta o None si fallo.
    """
    symbol = decision["symbol"]
    capital = decision["capital"]

    log(f"=== COMPRANDO {symbol} con ${capital} USDT ===")
    log(f"Razonamiento: {decision['reasoning'].splitlines()[0]}")

    # Primero cotizar para verificar
    quote = get_quote(BASE_TOKEN, symbol, capital)
    if not quote:
        log(f"No se pudo obtener cotizacion para {symbol}, abortando")
        return None

    log(f"Cotizacion obtenida para {symbol}")

    # Ejecutar swap real
    swap_result = execute_swap(BASE_TOKEN, symbol, capital)
    if not swap_result:
        log(f"Swap fallido para {symbol}")
        return None

    # Registrar posicion abierta
    position = {
        "symbol": symbol,
        "capital": capital,
        "entry_time": decision["entry_time"],
        "hold_min_hours": decision["hold_min_hours"],
        "hold_max_hours": decision["hold_max_hours"],
        "sentiment": decision["sentiment"],
        "volume_ratio": decision["volume_ratio"],
        "narrative": decision["narrative"],
        "reasoning": decision["reasoning"],
        "swap_result": swap_result,
        "status": "OPEN"
    }

    positions = load_positions()
    positions.append(position)
    save_positions(positions)

    log(f"POSICION ABIERTA: {symbol} | ${capital} | Hold: {decision['hold_min_hours']}-{decision['hold_max_hours']}h")
    return position


def sell(position, reason="señal de salida"):
    """
    Vende el token de una posicion abierta.
    """
    symbol = position["symbol"]
    capital = position["capital"]

    log(f"=== VENDIENDO {symbol} | Razon: {reason} ===")

    swap_result = execute_swap(symbol, BASE_TOKEN, capital)
    if not swap_result:
        log(f"Swap de venta fallido para {symbol}")
        return False

    # Actualizar posicion como cerrada
    positions = load_positions()
    for p in positions:
        if p["symbol"] == symbol and p["status"] == "OPEN":
            p["status"] = "CLOSED"
            p["exit_time"] = datetime.utcnow().isoformat()
            p["exit_reason"] = reason
            p["exit_swap"] = swap_result
    save_positions(positions)

    log(f"POSICION CERRADA: {symbol} | Razon: {reason}")
    return True


def compliance_trade():
    """
    Trade minimo de cumplimiento diario.
    Compra y vende CAKE con $1 para registrar actividad.
    """
    log("=== TRADE DE CUMPLIMIENTO DIARIO ===")

    fake_decision = {
        "symbol": "CAKE",
        "capital": 1.0,
        "entry_time": datetime.utcnow().isoformat(),
        "hold_min_hours": 0,
        "hold_max_hours": 0,
        "sentiment": "NEUTRO",
        "volume_ratio": 1.0,
        "narrative": "defi",
        "reasoning": "Trade de cumplimiento de regla minima diaria (1 trade/dia requerido por el hackathon)"
    }

    # Comprar
    position = buy(fake_decision)
    if not position:
        log("Compliance trade: fallo la compra")
        return False

    # Vender inmediatamente
    import time
    time.sleep(5)
    result = sell(position, reason="compliance trade - venta inmediata")
    return result


if __name__ == "__main__":
    print("=== Prueba del Ejecutor de Trades ===")
    print("Verificando cotizacion de CAKE...")

    quote = get_quote("USDT", "CAKE", 1.0)
    if quote:
        print(f"Cotizacion exitosa: {json.dumps(quote, indent=2)}")
    else:
        print("No se pudo obtener cotizacion. Verifica que TWAK este configurado.")
