"""
Superagente007 Dashboard — Backend API
Correr con: cd C:\\Users\\Jorge\\Superagente007 && python dashboard/main.py
"""
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json, os, re, requests
from datetime import datetime
from dotenv import load_dotenv

# Rutas base
DASHBOARD_DIR = Path(__file__).parent           # Superagente007/dashboard/
BASE_DIR      = DASHBOARD_DIR.parent            # Superagente007/

load_dotenv(BASE_DIR / ".env")

CAPITAL_TOTAL     = float(os.getenv("CAPITAL_TOTAL", 100))
MAX_POSICIONES    = int(os.getenv("MAX_POSICIONES", 2))
DASHBOARD_TOKEN   = os.getenv("DASHBOARD_TOKEN", "")

app = FastAPI(title="Superagente007 Dashboard")

# CORS restringido a localhost unicamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_methods=["GET"],
    allow_headers=["X-Dashboard-Token"],
)


# ── autenticacion ─────────────────────────────────────────────────────────────

async def verify_token(x_dashboard_token: str = Header(default="")):
    """Verifica el token de acceso al dashboard. Si no hay token configurado, permite acceso libre."""
    if DASHBOARD_TOKEN and x_dashboard_token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalido")


# ── helpers ──────────────────────────────────────────────────────────────────

def read_json(relative_path, default=None):
    path = BASE_DIR / relative_path
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [] if default is None else default


def tail_log(relative_path, n=30):
    path = BASE_DIR / relative_path
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return []


def count_cycles_today(log_lines):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return sum(1 for l in log_lines if today in l and "CICLO #" in l)


def parse_last_cycle(log_lines):
    for line in reversed(log_lines):
        m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC)\]', line)
        if m:
            return m.group(1)
    return None


def parse_decisions(n=8):
    lines = tail_log("logs/decisions.log", n=200)
    decisions = []
    for line in reversed(lines):
        m = re.match(r'\[(.+?)\] \[DECISION\] (.+)', line)
        if not m:
            continue
        time_str, msg = m.group(1), m.group(2)
        if "rechazado" in msg.lower():
            action = "rechazado"
        elif "DECISION" in msg and "COMPRAR" in msg:
            action = "compra"
        elif "Evaluando" in msg:
            action = "evaluando"
        else:
            continue
        decisions.append({"time": time_str, "msg": msg, "action": action})
        if len(decisions) >= n:
            break
    return decisions


def fmt_usd(v):
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    # Inyectar el token como variable JS para que el frontend lo use en sus requests
    token_script = f'<script>window.__DT__ = "{DASHBOARD_TOKEN}";</script>'
    html = html.replace("</head>", f"{token_script}\n</head>", 1)
    return HTMLResponse(content=html)


@app.get("/api/state", dependencies=[Depends(verify_token)])
async def get_state():
    positions = read_json("data/open_positions.json", [])
    open_positions = [p for p in positions if p.get("status") == "OPEN"]
    capital_desplegado = sum(p.get("capital", 0) for p in open_positions)

    now = datetime.utcnow()
    for p in open_positions:
        try:
            entry = datetime.fromisoformat(p["entry_time"])
            p["hours_open"] = round((now - entry).total_seconds() / 3600, 1)
        except Exception:
            p["hours_open"] = None

    agent_log = tail_log("logs/agent.log", 200)
    last_cycle = parse_last_cycle(agent_log)
    cycles_today = count_cycles_today(agent_log)

    return {
        "agent_status": "ACTIVO",
        "last_cycle": last_cycle or "Sin ciclos registrados",
        "cycles_today": cycles_today,
        "capital_total": CAPITAL_TOTAL,
        "capital_desplegado": round(capital_desplegado, 2),
        "capital_libre": round(CAPITAL_TOTAL - capital_desplegado, 2),
        "open_positions": open_positions,
        "total_positions": len(open_positions),
        "max_positions": MAX_POSICIONES,
        "recent_decisions": parse_decisions(8),
        "recent_log": tail_log("logs/agent.log", 20),
    }


@app.get("/api/market", dependencies=[Depends(verify_token)])
async def get_market():
    result = {
        "fear_greed": None,
        "global": None,
        "agent_interpretation": {},
    }

    # Fear & Greed — Alternative.me (gratis, sin API key)
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.status_code == 200:
            d = r.json()["data"][0]
            result["fear_greed"] = {
                "value": int(d["value"]),
                "label": d["value_classification"],
            }
    except Exception:
        pass

    # Global metrics — CoinGecko (gratis, sin API key)
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        if r.status_code == 200:
            data = r.json()["data"]
            mcp      = data.get("market_cap_percentage", {})
            total_mc = data.get("total_market_cap", {}).get("usd", 0)
            mc_chg   = data.get("market_cap_change_percentage_24h_usd", 0)
            btc_dom  = round(mcp.get("btc", 0), 1)
            eth_dom  = round(mcp.get("eth", 0), 1)

            stable_keys      = ["usdt", "usdc", "dai", "busd", "tusd", "fdusd", "usdp"]
            stable_dom       = round(sum(mcp.get(k, 0) for k in stable_keys), 1)
            stable_mc        = total_mc * stable_dom / 100

            result["global"] = {
                "total_market_cap_formatted":      fmt_usd(total_mc),
                "total_market_cap_usd":            total_mc,
                "market_cap_change_24h":           round(mc_chg, 2),
                "btc_dominance":                   btc_dom,
                "eth_dominance":                   eth_dom,
                "stablecoin_dominance":            stable_dom,
                "stablecoin_market_cap_formatted": fmt_usd(stable_mc),
            }

            # Interpretacion del agente — BTC dominance
            if btc_dom >= 60:
                btc_text = (
                    f"BTC controla el {btc_dom}% del mercado. Modo defensivo activo: "
                    "los inversores prefieren Bitcoin sobre las altcoins. "
                    "Las alts suelen tener movimientos más limitados en este contexto."
                )
            elif btc_dom >= 50:
                btc_text = (
                    f"Dominancia de BTC en zona media ({btc_dom}%). Hay rotación gradual "
                    "hacia altcoins. Oportunidades en tokens con catalizadores propios como "
                    "los del ecosistema BNB."
                )
            else:
                btc_text = (
                    f"BTC dominancia baja ({btc_dom}%): temporada de altcoins activa. "
                    "El capital fluye hacia proyectos más pequeños — mayor potencial "
                    "de ganancia, pero también mayor volatilidad."
                )

            # Interpretacion — stablecoins
            if stable_dom > 12:
                stable_text = (
                    f"Las stablecoins representan el {stable_dom}% del mercado total — "
                    "nivel ALTO. Señal de cautela: muchos inversores están refugiados "
                    "esperando el momento para entrar al mercado."
                )
                divergence = "REFUGIO"
            elif stable_dom < 7:
                stable_text = (
                    f"Las stablecoins representan solo el {stable_dom}% del mercado — "
                    "nivel BAJO. El dinero está rotando activamente hacia proyectos cripto. "
                    "Señal positiva para el mercado en general."
                )
                divergence = "ROTACION"
            else:
                stable_text = (
                    f"Las stablecoins representan el {stable_dom}% del mercado — "
                    "nivel NEUTRAL. Sin movimientos masivos hacia o desde stablecoins. "
                    "El mercado está en equilibrio."
                )
                divergence = "NEUTRAL"

            result["agent_interpretation"] = {
                "btc_dominance": btc_text,
                "stablecoin":    stable_text,
                "divergence":    divergence,
            }
    except Exception:
        pass

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True,
                app_dir=str(DASHBOARD_DIR))
