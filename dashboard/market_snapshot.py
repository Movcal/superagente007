"""
Guarda un snapshot diario de métricas globales usando CMC.
Correr una vez por día: venv\\Scripts\\python dashboard\\market_snapshot.py

Guarda en: data/market_history.json
Mantiene los últimos 15 días (descarta el más viejo automáticamente).
"""
import json
import os
import sys
import pathlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

CMC_API_KEY     = os.getenv("CMC_API_KEY")
HISTORY_FILE    = BASE_DIR / "data" / "market_history.json"
MAX_DAYS        = 15
CMC_GLOBAL_URL  = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"


def fetch_global_metrics():
    """Llama a CMC y devuelve las métricas globales crudas."""
    r = requests.get(
        CMC_GLOBAL_URL,
        headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
        params={"convert": "USD"},
        timeout=15
    )
    r.raise_for_status()
    return r.json()["data"]


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def already_saved_today(history):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return any(entry["date"] == today for entry in history)


def main():
    if not CMC_API_KEY:
        print("ERROR: CMC_API_KEY no encontrado en .env")
        sys.exit(1)

    print("Obteniendo métricas globales de CMC...")
    try:
        data = fetch_global_metrics()
    except Exception as e:
        print(f"ERROR al llamar CMC: {e}")
        sys.exit(1)

    # Extraer los 3 items clave
    quote       = data.get("quote", {}).get("USD", {})
    total_mc    = quote.get("total_market_cap", 0)
    stable_mc   = quote.get("stablecoin_market_cap") or data.get("stablecoin_market_cap", 0)
    btc_dom     = data.get("btc_dominance", 0)
    stable_dom  = round(stable_mc / total_mc * 100, 2) if total_mc else 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snapshot = {
        "date":              today,
        "total_market_cap":  round(total_mc),
        "stablecoin_mc":     round(stable_mc),
        "stablecoin_pct":    stable_dom,
        "btc_dominance":     round(btc_dom, 2),
    }

    history = load_history()

    if already_saved_today(history):
        # Actualizar el snapshot de hoy si ya existe
        history = [e for e in history if e["date"] != today]
        print(f"Actualizando snapshot de hoy ({today})...")
    else:
        print(f"Guardando snapshot nuevo para {today}...")

    history.append(snapshot)

    # Mantener solo los últimos MAX_DAYS días
    history = sorted(history, key=lambda x: x["date"])[-MAX_DAYS:]

    save_history(history)
    print(f"OK — {len(history)} días guardados en market_history.json")
    print(f"  Total MC:    ${total_mc/1e12:.2f}T")
    print(f"  Stables MC:  ${stable_mc/1e9:.1f}B ({stable_dom}%)")
    print(f"  BTC Dom:     {btc_dom:.2f}%")


if __name__ == "__main__":
    main()
