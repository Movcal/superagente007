"""
Reconcile de estado al arranque del agente.

Compara open_positions.json (estado guardado) con los balances reales de la wallet BSC.
Garantiza que el bot retome correctamente tras cualquier reinicio o caida.

Flujo:
  PAPER MODE → solo filtra posiciones OPEN del JSON (blockchain no interviene)
  REAL MODE  → por cada posicion OPEN, verifica el balance real via TWAK
               y corrige el JSON si hay desincronizacion
"""
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

from modules.token_registry import get_contract, KNOWN_CONTRACTS

PAPER_MODE       = os.getenv("PAPER_MODE", "false").lower() == "true"
WALLET_ADDRESS   = os.getenv("AGENT_WALLET_ADDRESS", "0xABC819c3aeE6419333d2D7df365484E5CC833222")
WALLET_PASSWORD  = os.getenv("TWAK_WALLET_PASSWORD")
POSITIONS_FILE   = "data/open_positions.json"
RECONCILE_LOG    = "logs/reconcile.log"

# Si el balance real es menos del 2% de lo esperado, consideramos que ya no tenemos el token
BALANCE_TOLERANCE = 0.02

# Tokens que ignoramos en el portfolio (base/gas/stables)
SKIP_SYMBOLS = {"BNB", "WBNB", "USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "FRAX",
                "FRXUSD", "USDD", "USD1", "USDe", "DUSD", "XUSD", "EURI", "lisUSD"}

# Lookup inverso: contract_address_lower -> symbol
CONTRACT_TO_SYMBOL = {v.lower(): k for k, v in KNOWN_CONTRACTS.items()
                      if k not in SKIP_SYMBOLS}


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [RECONCILE] {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(RECONCILE_LOG, "a") as f:
        f.write(line + "\n")


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return []


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def get_token_balance_twak(contract):
    """Consulta el balance real de un token ERC-20 en la wallet via TWAK."""
    twak_exe = shutil.which("twak")
    if not twak_exe:
        log("twak no encontrado en PATH, no se puede verificar balance real")
        return None

    env = os.environ.copy()
    if WALLET_PASSWORD:
        env["TWAK_WALLET_PASSWORD"] = WALLET_PASSWORD

    cmd = [
        twak_exe, "balance",
        "--chain", "bsc",
        "--address", WALLET_ADDRESS,
        "--token", contract,
        "--json"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            # TWAK devuelve "available" como string con el balance
            available = data.get("available", "0")
            return float(available)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        log(f"Error consultando balance para {contract}: {e}")
    return None


def get_usdt_balance():
    """Consulta el balance real de USDT en la wallet."""
    usdt_contract = "0x55d398326f99059fF775485246999027B3197955"
    return get_token_balance_twak(usdt_contract)


def _hours_since(iso_time):
    """Calcula cuantas horas pasaron desde un timestamp ISO."""
    try:
        entry = datetime.fromisoformat(iso_time).replace(tzinfo=None)
        return round((datetime.utcnow() - entry).total_seconds() / 3600, 1)
    except Exception:
        return None


def _log_position_context(position, balance_real=None):
    """Loguea el contexto completo de una posicion que se va a retomar."""
    symbol      = position["symbol"]
    capital     = position.get("capital", 0)
    entry_price = position.get("entry_price", 0)
    tokens      = balance_real if balance_real is not None else position.get("tokens", 0)
    entry_time  = position.get("entry_time", "?")
    hold_max    = position.get("hold_max_hours", "?")
    hold_min    = position.get("hold_min_hours", "?")
    narrative   = position.get("narrative", "?")
    vol_ratio   = position.get("volume_ratio", "?")
    sentiment   = position.get("sentiment", "?")
    hours_open  = _hours_since(entry_time)
    is_paper    = position.get("paper", False)

    log(f"  RETOMANDO {'[PAPER] ' if is_paper else ''}{symbol}")
    log(f"    Entrada : {entry_time[:16]} UTC ({hours_open}h hace)")
    log(f"    Capital : ${capital} USDT | Precio entrada: ${entry_price}")
    log(f"    Tokens  : {tokens}")
    log(f"    Narrativa: {narrative} | Volumen: {vol_ratio}x | Sentimiento: {sentiment}")
    log(f"    Hold    : {hold_min}-{hold_max}h | Tiempo restante max: ~{max(0, float(hold_max) - hours_open) if hours_open else '?'}h")
    log(f"    Salida  : TP +15% | SL -8% | Max {hold_max}h | BTC -3% macro")
    log(f"    Estado  : position_watcher retoma monitoreo automaticamente")


def get_recently_traded_symbols(hours=48):
    """
    Retorna lista de simbolos que aparecen en posiciones CLOSED en las ultimas N horas.
    Estos son los candidatos a tener balance residual si algo fallo al vender.
    """
    symbols = set()
    try:
        positions = load_positions()
        cutoff = datetime.utcnow()
        for p in positions:
            if p.get("status") != "CLOSED":
                continue
            exit_time = p.get("exit_time") or p.get("entry_time", "")
            try:
                t = datetime.fromisoformat(exit_time.replace("Z", ""))
                hours_ago = (cutoff - t).total_seconds() / 3600
                if hours_ago <= hours:
                    sym = p.get("symbol", "")
                    if sym and sym not in SKIP_SYMBOLS:
                        symbols.add(sym)
            except Exception:
                pass
    except Exception:
        pass
    return list(symbols)


def recover_orphan_tokens(open_positions):
    """
    Busca tokens huerfanos verificando balance on-chain de tokens comprados recientemente.
    Solo consulta tokens que aparecen en posiciones CLOSED de las ultimas 48h.
    Solo actua sobre tokens con contrato verificado en nuestro registry.
    Retorna lista de posiciones de recuperacion creadas.
    """
    open_symbols = {p["symbol"] for p in open_positions}
    candidates = get_recently_traded_symbols(hours=48)

    if not candidates:
        log("Sin trades recientes para verificar.")
        return []

    log(f"Verificando balance on-chain de {len(candidates)} token(s) recientes: {candidates}")
    recovered = []

    for symbol in candidates:
        if symbol in open_symbols:
            continue  # ya tiene posicion OPEN registrada

        # SEGURIDAD: solo actuar sobre tokens con contrato en nuestro registry
        known_contract = KNOWN_CONTRACTS.get(symbol)
        if not known_contract:
            log(f"  {symbol}: sin contrato registrado — ignorado por seguridad")
            continue

        balance = get_token_balance_twak(known_contract)
        if balance is None:
            log(f"  {symbol}: TWAK no respondio — ignorado")
            continue

        if balance <= 0:
            continue

        # Estimar valor USD usando el ultimo precio de entrada conocido
        last_price = None
        for p in load_positions():
            if p.get("symbol") == symbol and p.get("entry_price"):
                last_price = p["entry_price"]
        est_usd = balance * last_price if last_price else 0

        # Ignorar si el valor estimado es menor a $0.50 (polvo de ventas al 99.9%)
        if est_usd < 0.50:
            log(f"  {symbol}: balance {balance} (~${est_usd:.4f}) es polvo — ignorado")
            continue

        log(f"  HUERFANO DETECTADO: {balance} {symbol} en wallet sin posicion OPEN")

        recovery_position = {
            "symbol":         symbol,
            "capital":        0,       # desconocido sin precio historico
            "entry_price":    0,
            "tokens":         balance,
            "entry_time":     datetime.utcnow().isoformat(),
            "hold_min_hours": 0,
            "hold_max_hours": 0,
            "sentiment":      "NEUTRO",
            "volume_ratio":   1.0,
            "narrative":      "general",
            "reasoning":      f"RECUPERACION: {balance} {symbol} encontrados en wallet sin posicion OPEN. Vender para recuperar USDT.",
            "status":         "OPEN",
            "recovery":       True,
        }
        recovered.append(recovery_position)

    return recovered


def reconcile():
    """
    Punto de entrada principal. Llamar al inicio del agente.
    Lee el ultimo estado guardado, cruza con balances reales de la wallet,
    y deja el JSON listo para que position_watcher retome donde quedo.
    Retorna la lista de posiciones OPEN validadas.
    """
    log("=" * 55)
    log("RECONCILE DE ARRANQUE — leyendo ultimo estado guardado...")
    log("=" * 55)

    all_positions = load_positions()
    open_positions  = [p for p in all_positions if p.get("status") == "OPEN"]
    closed_positions = [p for p in all_positions if p.get("status") != "OPEN"]

    log(f"Archivo: {POSITIONS_FILE}")
    log(f"  Total registros : {len(all_positions)}")
    log(f"  Posiciones OPEN : {len(open_positions)}")
    log(f"  Posiciones CLOSED: {len(closed_positions)}")

    if not open_positions:
        log("Sin posiciones abiertas en JSON.")
        if not PAPER_MODE:
            log("Verificando wallet por tokens huerfanos...")
            recovered = recover_orphan_tokens([])
            if recovered:
                log(f"  {len(recovered)} token(s) huerfanos encontrados — agregando posiciones de recuperacion")
                for r in recovered:
                    all_positions.append(r)
                save_positions(all_positions)
                log("=" * 55)
                return recovered
        log("Agente arranca desde cero.")
        log("=" * 55)
        return []

    # ── PAPER MODE ─────────────────────────────────────────────────────────────
    if PAPER_MODE:
        log("Modo: PAPER — el JSON es la fuente de verdad (sin verificacion blockchain)")
        log("")
        for p in open_positions:
            _log_position_context(p)
        log("")
        log(f"Resultado: {len(open_positions)} posicion(es) retomadas. position_watcher activo.")
        log("=" * 55)
        return open_positions

    # ── REAL MODE ───────────────────────────────────────────────────────────────
    log(f"Modo: REAL — verificando balances en wallet BSC...")
    log(f"Wallet: {WALLET_ADDRESS}")
    log("")

    usdt_balance = get_usdt_balance()
    if usdt_balance is not None:
        log(f"Balance USDT actual en wallet: ${usdt_balance:,.4f}")
    log("")

    verified   = []
    needs_save = False

    for position in open_positions:
        symbol   = position["symbol"]
        contract = get_contract(symbol)
        expected = position.get("tokens", 0)

        if not contract:
            log(f"  {symbol}: sin contrato BSC en registry — manteniendo sin verificar (fail-safe)")
            _log_position_context(position)
            verified.append(position)
            continue

        actual = get_token_balance_twak(contract)

        if actual is None:
            # TWAK no respondio — fail safe: no descartar la posicion
            log(f"  {symbol}: TWAK no respondio — manteniendo posicion (fail-safe)")
            _log_position_context(position)
            verified.append(position)
            continue

        if expected > 0 and actual < expected * BALANCE_TOLERANCE:
            # Tokens ausentes en wallet — se cerraron externamente o hubo error
            log(f"  {symbol}: DESINCRONIZACION DETECTADA")
            log(f"    Esperado en JSON : {expected}")
            log(f"    Balance real     : {actual}")
            log(f"    Decision: marcando CLOSED — tokens no encontrados en wallet")
            position["status"]      = "CLOSED"
            position["exit_time"]   = datetime.utcnow().isoformat()
            position["exit_reason"] = "reconcile: tokens ausentes en wallet al reiniciar"
            needs_save = True
        else:
            # Tokens presentes — posicion valida, actualizar cantidad exacta
            if actual != expected:
                log(f"  {symbol}: balance ajustado {expected} -> {actual} (balance real)")
                position["tokens"] = actual
                needs_save = True
            _log_position_context(position, balance_real=actual)
            verified.append(position)

    if needs_save:
        save_positions(closed_positions + open_positions)
        log("")
        log("JSON actualizado con estado reconciliado.")

    # ── Detectar tokens huerfanos en wallet sin posicion OPEN ──────────────────
    log("")
    log("Buscando tokens huerfanos en wallet (sin posicion OPEN registrada)...")
    recovered = recover_orphan_tokens(verified)
    if recovered:
        log(f"  {len(recovered)} token(s) huerfanos encontrados — agregando posiciones de recuperacion")
        all_positions = load_positions()
        for r in recovered:
            all_positions.append(r)
            verified.append(r)
        save_positions(all_positions)
    else:
        log("  Sin tokens huerfanos. Wallet y JSON sincronizados.")

    log("")
    log(f"Resultado: {len(verified)} posicion(es) activas. position_watcher retoma monitoreo.")
    log("=" * 55)
    return verified
