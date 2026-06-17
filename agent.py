import time
import sys
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from modules.volume_monitor import run_once as check_volumes
from modules.decision_engine import evaluate as evaluate_decision
from modules.trade_executor import buy
from modules.position_watcher import run_once as check_positions
from modules.reconcile import reconcile
from modules.market_intelligence import (
    scan_news, generate_daily_summary, should_generate_summary,
    update_watchlist, check_watchlist_volume
)

LOOP_INTERVAL_SEC = 300  # 5 minutos
NEWS_SCAN_EVERY_N_CYCLES = 6  # escanea noticias cada ~30 min (6 x 5 min)


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

    # 2. Seguimiento de volumen en watchlist (anticipacion pre-spike)
    evaluated_from_watchlist = set()
    try:
        watchlist_alerts = check_watchlist_volume()
        for wa in watchlist_alerts:
            if wa["level"] >= 2:  # ACELERANDO o SPIKE
                log(f"[WATCHLIST] ATENCION: {wa['symbol']} volumen {wa['status']} "
                    f"{wa['ratio']}x | narrativa {wa['narrative']} ({wa['bull_score']}% bullish)")

            # Entrada temprana: ACELERANDO (2.5x+) con narrativa bullish >= 50%
            # No esperar el 5x si la narrativa ya esta confirmada
            if wa["level"] == 2 and wa.get("bull_score", 0) >= 50:
                sym = wa["symbol"]
                log(f"[WATCHLIST] ENTRADA ANTICIPADA: {sym} {wa['ratio']}x + narrativa {wa['bull_score']}% bullish")
                early_alert = {
                    "symbol":    sym,
                    "ratio":     wa["ratio"],
                    "current_volume": 0,
                    "avg_volume": 0,
                    "timestamp": datetime.utcnow().isoformat(),
                    "priority":  True,
                }
                decision = evaluate_decision(early_alert, path="A")
                evaluated_from_watchlist.add(sym)
                if decision:
                    log(f"Decision WATCHLIST: COMPRAR {sym} con ${decision['capital']}")
                    position = buy(decision)
                    if position:
                        log(f"Posicion abierta via watchlist en {sym}")
                    else:
                        log(f"Fallo al abrir posicion watchlist en {sym}")
    except Exception as e:
        log(f"Error en check_watchlist_volume: {e}")

    # 3. Monitorear volumen de todos los tokens (spike 5x)
    log("--- Monitoreando volumen ---")
    volume_alerts = check_volumes()

    # Para cada alerta de volumen, evaluar si entrar (skip tokens ya evaluados via watchlist)
    if volume_alerts:
        new_alerts = [a for a in volume_alerts if a["symbol"] not in evaluated_from_watchlist]
        log(f"Alertas de volumen detectadas: {len(new_alerts)}")
        for alert in new_alerts:
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

    # Reconcile de estado al arranque: verifica posiciones abiertas contra la wallet real
    reconcile()

    cycle = 0
    while True:
        cycle += 1
        log(f"\n===== CICLO #{cycle} =====")
        try:
            run_cycle()
        except Exception as e:
            log(f"Error en ciclo #{cycle}: {e}")

        # Escaneo de noticias + actualizacion de watchlist cada 30 min
        if cycle % NEWS_SCAN_EVERY_N_CYCLES == 0:
            log("--- Escaneando noticias CMC ---")
            try:
                scan_news()
                update_watchlist()
            except Exception as e:
                log(f"Error en scan/watchlist: {e}")

        # Resumen diario a las 11:00 UTC (si no fue generado aun hoy)
        try:
            if should_generate_summary():
                log("--- Generando resumen diario de narrativas ---")
                generate_daily_summary()
        except Exception as e:
            log(f"Error en generate_daily_summary: {e}")

        log(f"Proximo ciclo en {LOOP_INTERVAL_SEC // 60} minutos...")
        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
