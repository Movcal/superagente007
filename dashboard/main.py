"""
Superagente007 Dashboard — Backend API
Correr con: cd C:\\Users\\Jorge\\Superagente007 && python dashboard/main.py
"""
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json, os, re, requests, time, subprocess
from datetime import datetime
from dotenv import load_dotenv

# Rutas base
DASHBOARD_DIR = Path(__file__).parent           # Superagente007/dashboard/
BASE_DIR      = DASHBOARD_DIR.parent            # Superagente007/

load_dotenv(BASE_DIR / ".env")

CAPITAL_TOTAL     = float(os.getenv("CAPITAL_TOTAL", 100))
MAX_POSICIONES    = int(os.getenv("MAX_POSICIONES", 2))
DASHBOARD_TOKEN   = os.getenv("DASHBOARD_TOKEN", "")
CMC_API_KEY       = os.getenv("CMC_API_KEY", "")
CMC_MCP_URL       = "https://mcp.coinmarketcap.com/mcp"

# Cache de narrativas (24 horas — el volumen de una narrativa no cambia en minutos)
_narratives_cache = {"data": None, "ts": 0}
NARRATIVES_TTL    = 86400  # segundos

# Cache de wallet (1 hora)
_wallet_cache = {"total_usd": None, "ts": 0}
WALLET_TTL    = 3600  # segundos

app = FastAPI(title="Superagente007 Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ── wallet balance helper ─────────────────────────────────────────────────────

def get_wallet_total_usd():
    """Obtiene el total USD de la wallet via twak. Cache 1 hora."""
    now = time.time()
    if _wallet_cache["total_usd"] is not None and (now - _wallet_cache["ts"]) < WALLET_TTL:
        return _wallet_cache["total_usd"]
    try:
        result = subprocess.run(
            ["twak", "wallet", "portfolio"],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            if "Total USD:" in line:
                m = re.search(r'\$([0-9]+\.?[0-9]*)', line)
                if m:
                    total = float(m.group(1))
                    _wallet_cache["total_usd"] = total
                    _wallet_cache["ts"] = now
                    return total
    except Exception:
        pass
    return _wallet_cache["total_usd"] if _wallet_cache["total_usd"] is not None else CAPITAL_TOTAL


# ── CMC MCP helper ────────────────────────────────────────────────────────────

def fetch_narratives_from_mcp():
    """Llama al CMC MCP para obtener narrativas trending. Resultado cacheado 10 min."""
    now = time.time()
    if _narratives_cache["data"] and (now - _narratives_cache["ts"]) < NARRATIVES_TTL:
        return _narratives_cache["data"]

    try:
        headers = {
            "X-CMC-MCP-API-KEY": CMC_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        s = requests.Session()
        s.headers.update(headers)
        s.post(CMC_MCP_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "dashboard", "version": "1.0"}}
        }, timeout=10)
        s.post(CMC_MCP_URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=5)

        r = s.post(CMC_MCP_URL, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "trending_crypto_narratives", "arguments": {}}
        }, timeout=15)

        text = r.json().get("result", {}).get("content", [{}])[0].get("text", "")
        raw  = json.loads(text)
        rows = raw.get("categoryList", {}).get("rows", [])

        narratives = []
        for row in rows[:6]:
            change_24h = row[5] if len(row) > 5 else ""
            change_7d  = row[6] if len(row) > 6 else ""
            keywords   = row[15] if len(row) > 15 else []
            top_coins  = []
            if len(row) > 17 and isinstance(row[17], dict):
                coin_rows = row[17].get("rows", [])
                top_coins = [c[0] for c in coin_rows[:3] if c]

            narratives.append({
                "rank":       row[0],
                "name":       row[3] if len(row) > 3 else "",
                "url":        row[2] if len(row) > 2 else "",
                "change_24h": change_24h,
                "change_7d":  change_7d,
                "keywords":   keywords[:3] if isinstance(keywords, list) else [],
                "top_coins":  top_coins,
            })

        _narratives_cache["data"] = narratives
        _narratives_cache["ts"]   = now
        return narratives
    except Exception:
        return _narratives_cache["data"] or []


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
        "capital_total": get_wallet_total_usd(),
        "capital_desplegado": round(capital_desplegado, 2),
        "capital_libre": round(get_wallet_total_usd() - capital_desplegado, 2),
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

            # Cambio 24h de stablecoins via CoinGecko markets
            stable_change_24h = None
            try:
                sr = requests.get(
                    "https://api.coingecko.com/api/v3/coins/markets",
                    params={"vs_currency": "usd", "ids": "tether,usd-coin,dai,first-digital-usd,binance-usd",
                            "order": "market_cap_desc", "per_page": 5, "page": 1},
                    timeout=8
                )
                if sr.status_code == 200:
                    stable_coins = sr.json()
                    total_stable_mc = sum(c.get("market_cap", 0) for c in stable_coins)
                    if total_stable_mc > 0:
                        weighted_chg = sum(
                            c.get("market_cap_change_percentage_24h", 0) * c.get("market_cap", 0)
                            for c in stable_coins
                        ) / total_stable_mc
                        stable_change_24h = round(weighted_chg, 2)
            except Exception:
                pass

            result["global"] = {
                "total_market_cap_formatted":      fmt_usd(total_mc),
                "total_market_cap_usd":            total_mc,
                "market_cap_change_24h":           round(mc_chg, 2),
                "btc_dominance":                   btc_dom,
                "eth_dominance":                   eth_dom,
                "stablecoin_dominance":            stable_dom,
                "stablecoin_market_cap_formatted": fmt_usd(stable_mc),
                "stablecoin_change_24h":           stable_change_24h,
            }

            # Interpretacion del agente — BTC dominance
            if btc_dom >= 60:
                btc_text = (
                    f"BTC controls {btc_dom}% of the market. Active defensive mode: "
                    "investors are favoring Bitcoin over altcoins. "
                    "Alts tend to have more limited moves in this context."
                )
            elif btc_dom >= 50:
                btc_text = (
                    f"BTC dominance in mid range ({btc_dom}%). Gradual rotation "
                    "toward altcoins underway. Opportunities in tokens with their own "
                    "catalysts, such as BNB ecosystem projects."
                )
            else:
                btc_text = (
                    f"Low BTC dominance ({btc_dom}%): active altcoin season. "
                    "Capital is flowing into smaller projects — higher upside "
                    "potential, but also higher volatility."
                )

            # Agent interpretation — stablecoins
            if stable_dom > 12:
                stable_text = (
                    f"Stablecoins represent {stable_dom}% of the total market — "
                    "HIGH level. Caution signal: many investors are sheltered "
                    "waiting for the right moment to enter the market."
                )
                divergence = "SHELTER"
            elif stable_dom < 7:
                stable_text = (
                    f"Stablecoins represent only {stable_dom}% of the market — "
                    "LOW level. Capital is actively rotating into crypto projects. "
                    "Positive signal for the market overall."
                )
                divergence = "ROTATION"
            else:
                stable_text = (
                    f"Stablecoins represent {stable_dom}% of the market — "
                    "NEUTRAL level. No major flows in or out of stablecoins. "
                    "The market is in equilibrium."
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


CATEGORY_TOKENS = {
    "layer-1":      ["ETH", "ADA", "TRX", "ATOM", "DOT", "NEAR", "AVAX", "BNB"],
    "defi":         ["UNI", "AAVE", "CAKE", "SUSHI", "COMP", "PENDLE", "STG", "1INCH"],
    "ai-infra":     ["FET", "0G", "AIOZ", "PEAQ", "SKYAI", "COAI"],
    "memecoin":     ["DOGE", "SHIB", "BONK", "FLOKI", "CHEEMS"],
    "payments":     ["XRP", "XLM", "ACH", "GENIUS", "WFI"],
    "governance":   ["WLFI", "UNI", "COMP", "MKR"],
    "infrastructure": ["LINK", "BAND", "API3", "ZIG"],
    "privacy-coin": ["ZEC", "ROSE", "AXL"],
    "rwa":          ["RIO", "CPOOL", "XCN"],
    "layer-2":      ["ARB", "OP", "ZKS", "METIS"],
    "layer-0":      ["DOT", "ATOM", "AXL"],
    "oracle":       ["LINK", "BAND", "API3"],
    "socialfi":     ["DESO", "LOOKS"],
    "ai":           ["FET", "SKYAI", "0G", "AIOZ"],
}

CATEGORY_DISPLAY = {
    "layer-1": "Layer 1", "defi": "DeFi", "ai-infra": "IA Infrastructure",
    "memecoin": "Memecoins", "payments": "Payments", "governance": "Governance",
    "infrastructure": "Infrastructure", "privacy-coin": "Privacy", "rwa": "RWA",
    "layer-2": "Layer 2", "layer-0": "Layer 0", "oracle": "Oracles",
    "socialfi": "SocialFi", "ai": "Inteligencia Artificial",
}

def get_token_changes(symbols):
    """Obtiene cambio 24h de una lista de symbols via CMC."""
    if not symbols or not CMC_API_KEY:
        return {}
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": ",".join(symbols), "convert": "USD"},
            timeout=10
        )
        if r.status_code == 200:
            out = {}
            for sym, data in r.json().get("data", {}).items():
                if isinstance(data, list): data = data[0]
                chg = data.get("quote", {}).get("USD", {}).get("percent_change_24h", None)
                if chg is not None:
                    out[sym] = round(chg, 2)
            return out
    except Exception:
        pass
    return {}


@app.get("/api/narratives", dependencies=[Depends(verify_token)])
async def get_narratives():
    # Leer el resumen diario mas reciente
    summaries_dir = BASE_DIR / "data" / "daily_summaries"
    summary = None
    if summaries_dir.exists():
        files = sorted(summaries_dir.glob("*.json"), reverse=True)
        if files:
            try:
                summary = json.loads(files[0].read_text(encoding="utf-8"))
            except Exception:
                pass

    if not summary:
        return {"narratives": [], "key_insight": None, "risk_alert": None, "summary_date": None}

    trending_up   = summary.get("trending_up", [])[:3]
    sector_outlook = summary.get("sector_outlook", {})

    # Para cada narrativa top: obtener tokens y su % 24h
    all_symbols = []
    for cat in trending_up:
        all_symbols += CATEGORY_TOKENS.get(cat, [])
    changes = get_token_changes(list(set(all_symbols)))

    narratives = []
    for i, cat in enumerate(trending_up):
        tokens = CATEGORY_TOKENS.get(cat, [])
        # Ordenar por mejor % 24h
        ranked = sorted(
            [(sym, changes.get(sym)) for sym in tokens if changes.get(sym) is not None],
            key=lambda x: x[1], reverse=True
        )
        top2 = ranked[:2]  # Solo mostramos 2 tokens (no revelamos todo)
        narratives.append({
            "rank":    i + 1,
            "cat":     cat,
            "name":    CATEGORY_DISPLAY.get(cat, cat),
            "outlook": sector_outlook.get(cat, ""),
            "top_tokens": [{"symbol": s, "change_24h": c} for s, c in top2],
        })

    return {
        "narratives":    narratives,
        "key_insight":   summary.get("key_insight"),
        "risk_alert":    summary.get("risk_alert"),
        "summary_date":  summary.get("date"),
    }


@app.get("/api/costs", dependencies=[Depends(verify_token)])
async def get_costs():
    """Resumen de costos: Claude API + trades simulados (paper mode)."""

    # Costos de Claude
    claude_calls = 0
    claude_cost_total = 0.0
    claude_tokens_in  = 0
    claude_tokens_out = 0
    cost_log = BASE_DIR / "logs" / "claude_costs.log"
    if cost_log.exists():
        for line in cost_log.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                parts = line.split("|")
                for p in parts:
                    p = p.strip()
                    if p.startswith("in="):
                        claude_tokens_in  += int(p.split("=")[1].split()[0])
                        claude_tokens_out += int(p.split("out=")[1].split()[0])
                    if p.startswith("cost="):
                        claude_cost_total += float(p.replace("cost=$",""))
                claude_calls += 1
            except Exception:
                pass

    # Trades simulados
    paper_file = BASE_DIR / "data" / "paper_trades.json"
    paper_trades = []
    total_pnl = 0.0
    total_invested = 0.0
    if paper_file.exists():
        try:
            all_trades = json.loads(paper_file.read_text(encoding="utf-8"))
            sells = [t for t in all_trades if t.get("type") == "SELL"]
            buys  = [t for t in all_trades if t.get("type") == "BUY"]
            total_invested = sum(t.get("capital", 0) for t in buys)
            total_pnl = sum(t.get("pnl_usd", 0) for t in sells)
            paper_trades = sells[-10:]  # ultimas 10 ventas
        except Exception:
            pass

    return {
        "claude": {
            "calls":       claude_calls,
            "tokens_in":   claude_tokens_in,
            "tokens_out":  claude_tokens_out,
            "cost_usd":    round(claude_cost_total, 5),
            "cost_per_call": round(claude_cost_total / claude_calls, 5) if claude_calls else 0,
        },
        "paper_trading": {
            "total_invested_usd": round(total_invested, 2),
            "total_pnl_usd":      round(total_pnl, 4),
            "total_pnl_pct":      round((total_pnl / total_invested * 100), 2) if total_invested else 0,
            "recent_trades":      paper_trades,
        }
    }


@app.get("/api/pnl", dependencies=[Depends(verify_token)])
async def get_pnl():
    """PnL por token basado en posiciones cerradas."""
    positions_file = BASE_DIR / "data" / "open_positions.json"
    by_token = {}

    if positions_file.exists():
        try:
            positions = json.loads(positions_file.read_text(encoding="utf-8"))
            closed = [p for p in positions if p.get("status") == "CLOSED"]
            for p in closed:
                symbol = p.get("symbol", "?")
                pnl_pct = p.get("pnl_pct")
                pnl_usd = p.get("pnl_usd")
                capital = p.get("capital", 0)

                # Si no tiene pnl_pct guardado, intentar calcular desde paper_trades
                if pnl_pct is None:
                    paper_file = BASE_DIR / "data" / "paper_trades.json"
                    if paper_file.exists():
                        pt = json.loads(paper_file.read_text(encoding="utf-8"))
                        entry_time = p.get("entry_time", "")[:16]
                        for t in pt:
                            if t.get("type") == "SELL" and t.get("symbol") == symbol:
                                pnl_pct = t.get("pnl_pct")
                                pnl_usd = t.get("pnl_usd")
                                break

                if symbol not in by_token:
                    by_token[symbol] = {
                        "symbol": symbol,
                        "trades": 0,
                        "wins": 0,
                        "losses": 0,
                        "total_pnl_pct": 0.0,
                        "total_pnl_usd": 0.0,
                        "total_capital": 0.0,
                    }

                by_token[symbol]["trades"] += 1
                by_token[symbol]["total_capital"] = round(by_token[symbol]["total_capital"] + capital, 4)

                if pnl_pct is not None:
                    by_token[symbol]["total_pnl_pct"] = round(by_token[symbol]["total_pnl_pct"] + pnl_pct, 2)
                    by_token[symbol]["total_pnl_usd"] = round(by_token[symbol]["total_pnl_usd"] + (pnl_usd or 0), 4)
                    if pnl_pct >= 0:
                        by_token[symbol]["wins"] += 1
                    else:
                        by_token[symbol]["losses"] += 1

        except Exception:
            pass

    result = []
    for sym, d in by_token.items():
        trades = d["trades"]
        wins   = d["wins"]
        result.append({
            "symbol":       sym,
            "trades":       trades,
            "wins":         wins,
            "losses":       d["losses"],
            "win_rate":     round(wins / trades * 100) if trades else 0,
            "avg_pnl_pct":  round(d["total_pnl_pct"] / trades, 2) if trades else 0,
            "total_pnl_usd": d["total_pnl_usd"],
            "total_capital": d["total_capital"],
        })

    result.sort(key=lambda x: x["total_pnl_usd"], reverse=True)
    total_pnl = round(sum(r["total_pnl_usd"] for r in result), 4)
    total_trades = sum(r["trades"] for r in result)
    total_wins   = sum(r["wins"] for r in result)

    return {
        "by_token": result,
        "summary": {
            "total_trades":  total_trades,
            "total_wins":    total_wins,
            "win_rate":      round(total_wins / total_trades * 100) if total_trades else 0,
            "total_pnl_usd": total_pnl,
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True,
                app_dir=str(DASHBOARD_DIR))
