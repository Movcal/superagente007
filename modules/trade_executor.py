import subprocess
import shutil
import json
import os
import sys
import requests
import pathlib
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

from modules.token_registry import get_contract
from modules.trade_journal import analyze_trade

WALLET_PASSWORD = os.getenv("TWAK_WALLET_PASSWORD")
CMC_API_KEY     = os.getenv("CMC_API_KEY", "")
PAPER_MODE      = os.getenv("PAPER_MODE", "false").lower() == "true"
POSITIONS_FILE  = "data/open_positions.json"
PAPER_TRADES_FILE = "data/paper_trades.json"
TRADES_LOG      = "logs/trades.log"

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


def get_token_balance(symbol):
    """Consulta el balance real del token en la wallet via TWAK.
    Retorna float con el balance, o None si no se pudo obtener.
    """
    contract = get_contract(symbol)
    if not contract:
        return None
    twak_exe = shutil.which("twak")
    if not twak_exe:
        return None
    env = os.environ.copy()
    if WALLET_PASSWORD:
        env["TWAK_WALLET_PASSWORD"] = WALLET_PASSWORD
    try:
        result = subprocess.run(
            [twak_exe, "balance", "--chain", "bsc", "--token", contract, "--json"],
            capture_output=True, text=True, timeout=30, shell=False, env=env
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            # TWAK retorna {"balance": "123.45", "symbol": "FLOKI", ...}
            bal = data.get("balance") or data.get("formatted") or data.get("amount")
            if bal is not None:
                return float(str(bal).split()[0])
    except Exception as e:
        log(f"Error consultando balance de {symbol}: {e}")
    return None


# ── Paper mode helpers ────────────────────────────────────────────────────────

def load_paper_trades():
    if os.path.exists(PAPER_TRADES_FILE):
        with open(PAPER_TRADES_FILE, "r") as f:
            return json.load(f)
    return []

def save_paper_trades(trades):
    os.makedirs("data", exist_ok=True)
    with open(PAPER_TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)

def get_real_price(symbol):
    """Obtiene el precio real de un token via CMC API."""
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": symbol, "convert": "USD"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            for key in data:
                price = data[key]["quote"]["USD"]["price"]
                return round(price, 8)
    except Exception as e:
        log(f"Error obteniendo precio de {symbol}: {e}")
    return None

def paper_buy(decision):
    """Simula una compra con precio real de CMC. Sin blockchain."""
    symbol  = decision["symbol"]
    capital = decision["capital"]

    price = get_real_price(symbol)
    if not price:
        log(f"[PAPER] No se pudo obtener precio de {symbol}, usando precio simulado")
        price = 1.0

    tokens_bought = round(capital / price, 6)
    log(f"[PAPER] COMPRA SIMULADA: {tokens_bought} {symbol} @ ${price} = ${capital} USDT")

    position = {
        "symbol":          symbol,
        "capital":         capital,
        "entry_price":     price,
        "tokens":          tokens_bought,
        "entry_time":      decision["entry_time"],
        "hold_min_hours":  decision["hold_min_hours"],
        "hold_max_hours":  decision["hold_max_hours"],
        "sentiment":       decision["sentiment"],
        "volume_ratio":    decision["volume_ratio"],
        "narrative":       decision["narrative"],
        "reasoning":       decision["reasoning"],
        "swap_result":     {"paper": True, "price": price, "tokens": tokens_bought},
        "status":          "OPEN",
        "paper":           True,
    }

    # Registrar en paper_trades
    trades = load_paper_trades()
    trades.append({**position, "type": "BUY", "timestamp": datetime.utcnow().isoformat()})
    save_paper_trades(trades)

    return position

def paper_sell(position, reason="señal de salida"):
    """Simula una venta con precio real de CMC. Calcula PnL."""
    symbol  = position["symbol"]
    capital = position["capital"]
    entry_price = position.get("entry_price", 1.0)
    tokens = position.get("tokens", capital)

    exit_price = get_real_price(symbol) or entry_price
    exit_value = round(tokens * exit_price, 4)
    pnl_usd    = round(exit_value - capital, 4)
    pnl_pct    = round((pnl_usd / capital) * 100, 2)

    log(f"[PAPER] VENTA SIMULADA: {tokens} {symbol} @ ${exit_price} = ${exit_value} USDT")
    log(f"[PAPER] PnL: ${pnl_usd} ({pnl_pct:+.2f}%) | Razon: {reason}")

    trades = load_paper_trades()
    trades.append({
        "type":        "SELL",
        "symbol":      symbol,
        "tokens":      tokens,
        "entry_price": entry_price,
        "exit_price":  exit_price,
        "capital_in":  capital,
        "exit_value":  exit_value,
        "pnl_usd":     pnl_usd,
        "pnl_pct":     pnl_pct,
        "reason":      reason,
        "timestamp":   datetime.utcnow().isoformat(),
        "paper":       True,
    })
    save_paper_trades(trades)
    return True, exit_price, pnl_usd, pnl_pct


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
    En PAPER_MODE simula la compra con precio real sin tocar blockchain.
    Retorna la posicion abierta o None si fallo.
    """
    symbol = decision["symbol"]
    capital = decision["capital"]

    log(f"=== {'[PAPER] ' if PAPER_MODE else ''}COMPRANDO {symbol} con ${capital} USDT ===")
    log(f"Razonamiento: {decision['reasoning'].splitlines()[0]}")

    if PAPER_MODE:
        position = paper_buy(decision)
        if position:
            positions = load_positions()
            positions.append(position)
            save_positions(positions)
            log(f"[PAPER] POSICION ABIERTA: {symbol} | ${capital} | Hold: {decision['hold_min_hours']}-{decision['hold_max_hours']}h")
        return position

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

    # Extraer cantidad de tokens y precio de entrada del resultado del swap
    tokens_bought = 0
    entry_price = None
    output_str = swap_result.get("output", "") if isinstance(swap_result, dict) else ""
    if output_str:
        try:
            tokens_bought = float(output_str.split()[0])
            if tokens_bought > 0:
                entry_price = round(capital / tokens_bought, 8)
        except (ValueError, IndexError):
            log(f"No se pudo parsear tokens del output: {output_str!r}")

    if tokens_bought == 0:
        log(f"ADVERTENCIA: no se pudieron extraer tokens del swap_result de {symbol}. La venta futura puede fallar.")

    position = {
        "symbol": symbol,
        "capital": capital,
        "entry_price": entry_price,
        "tokens": tokens_bought,
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
    En PAPER_MODE simula la venta con precio real y calcula PnL.
    """
    symbol = position["symbol"]

    log(f"=== {'[PAPER] ' if PAPER_MODE else ''}VENDIENDO {symbol} | Razon: {reason} ===")

    exit_price = None
    pnl_usd    = None
    pnl_pct    = None

    if PAPER_MODE:
        ok, exit_price, pnl_usd, pnl_pct = paper_sell(position, reason)
    else:
        # Usar 99.9% del balance de tokens para evitar error de balance insuficiente
        tokens = position.get("tokens", 0)
        if not tokens or tokens <= 0:
            log(f"ERROR: posicion de {symbol} no tiene campo 'tokens' valido ({tokens}). Cerrando posicion sin swap para detener el loop.")
            positions = load_positions()
            for p in positions:
                if p["symbol"] == symbol and p["status"] == "OPEN":
                    p["status"] = "CLOSED"
                    p["exit_time"] = datetime.utcnow().isoformat()
                    p["exit_reason"] = f"ERROR: tokens=0, venta no ejecutada — {reason}"
            save_positions(positions)
            return False
        amount_to_sell = round(tokens * 0.999, 8)
        log(f"Vendiendo {amount_to_sell} {symbol} (99.9% de {tokens})")
        swap_result = execute_swap(symbol, BASE_TOKEN, amount_to_sell)
        if not swap_result:
            # Verificar si los tokens ya salieron de la wallet a pesar del error
            # (ocurre cuando TWAK reporta error pero la tx se confirmo on-chain)
            actual_balance = get_token_balance(symbol)
            if actual_balance is not None and actual_balance < (tokens * 0.01):
                log(f"Swap reporto error pero balance real de {symbol} es {actual_balance} (dust) — venta ejecutada on-chain, cerrando posicion")
                ok = True
                exit_price = get_real_price(symbol)
            else:
                log(f"Swap de venta fallido para {symbol} | balance actual: {actual_balance}")
                return False
        else:
            ok = True
        exit_price = get_real_price(symbol)
        if exit_price:
            entry_price = position.get("entry_price") or (position["capital"] / tokens if tokens else None)
            if entry_price:
                pnl_usd = round(amount_to_sell * exit_price - position["capital"], 4)
                pnl_pct = round((pnl_usd / position["capital"]) * 100, 2)

    if ok:
        positions = load_positions()
        for p in positions:
            if p["symbol"] == symbol and p["status"] == "OPEN":
                p["status"]    = "CLOSED"
                p["exit_time"] = datetime.utcnow().isoformat()
                p["exit_reason"] = reason
                if exit_price is not None:
                    p["exit_price"] = exit_price
                if pnl_usd is not None:
                    p["pnl_usd"] = pnl_usd
                if pnl_pct is not None:
                    p["pnl_pct"] = pnl_pct
        save_positions(positions)
        pnl_str = f" | PnL: ${pnl_usd} ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""
        log(f"POSICION CERRADA: {symbol} | Razon: {reason}{pnl_str}")

        # Analisis post-trade: Claude extrae leccion para aprendizaje futuro
        closed_position = next((p for p in load_positions() if p["symbol"] == symbol and p["status"] == "CLOSED" and p.get("exit_time")), None)
        if closed_position:
            try:
                analyze_trade(closed_position)
            except Exception as e:
                log(f"Error en analisis post-trade de {symbol}: {e}")

    return ok


def compliance_trade():
    """
    Trade minimo de cumplimiento diario.
    Compra CAKE con el 6% del balance real y vende inmediatamente.
    """
    import time
    log("=== TRADE DE CUMPLIMIENTO DIARIO ===")

    # Calcular capital: 6% del balance real de USDT
    try:
        from modules.reconcile import get_usdt_balance
        usdt_balance = get_usdt_balance() or 0
    except Exception:
        usdt_balance = 0

    capital = round(usdt_balance * 0.06, 2)
    if capital < 0.50:
        capital = 0.50  # minimo absoluto para que el swap no falle por dust
    log(f"Balance USDT: ${usdt_balance:.2f} | Capital compliance: ${capital:.2f} (6%)")

    fake_decision = {
        "symbol": "CAKE",
        "capital": capital,
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

    # Vender inmediatamente — esperar confirmacion del swap de compra
    time.sleep(10)

    # Los tokens ya vienen correctamente del buy() que parsea swap_result.output
    tokens = position.get("tokens", 0)
    if not tokens or tokens <= 0:
        log("Compliance trade: buy() no retorno tokens validos, abortando")
        return False
    log(f"Vendiendo {tokens} CAKE (del swap de compra)")

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
