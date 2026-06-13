import time
import sys
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from modules.volume_monitor import run_once as check_volumes
from modules.decision_engine import evaluate as evaluate_decision
from modules.trade_executor import buy
from modules.position_watcher import run_once as check_positions

LOOP_INTERVAL_SEC = 300  # 5 minutos


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [AGENTE] {msg}"
    print(line)
    with open("logs/agent.log", "a") as f:
        f.write(line + "\n")


def run_cycle():
    """Un ciclo completo del agente."""

    # 1. Revisar posiciones abiertas (salidas, stop loss, take profit)
    log("--- Revisando posiciones abiertas ---")
    check_positions()

    # 2. Monitorear volumen de los 149 tokens
    log("--- Monitoreando volumen ---")
    volume_alerts = check_volumes()

    # 3. Para cada alerta de volumen, evaluar si entrar
    if volume_alerts:
        log(f"Alertas de volumen detectadas: {len(volume_alerts)}")
        for alert in volume_alerts:
            symbol = alert["symbol"]
            log(f"Evaluando oportunidad en {symbol} ({alert['ratio']}x volumen)...")
            decision = evaluate_decision(alert, path="B")
            if decision:
                log(f"Decision: COMPRAR {symbol} con ${decision['capital']}")
                position = buy(decision)
                if position:
                    log(f"Posicion abierta exitosamente en {symbol}")
                else:
                    log(f"Fallo al abrir posicion en {symbol}")
    else:
        log("Sin alertas de volumen en este ciclo.")


def main():
    log("=" * 60)
    log("SUPERAGENTE007 INICIADO")
    log(f"Intervalo de ciclo: {LOOP_INTERVAL_SEC // 60} minutos")
    log("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        log(f"\n===== CICLO #{cycle} =====")
        try:
            run_cycle()
        except Exception as e:
            log(f"Error en ciclo #{cycle}: {e}")

        log(f"Proximo ciclo en {LOOP_INTERVAL_SEC // 60} minutos...")
        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
