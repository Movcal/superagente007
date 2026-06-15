"""
Analizador de contexto de mercado — CMC MCP + Claude (Haiku).

Usa el MCP de CoinMarketCap (con API key, sin pago por llamada) para obtener:
- Metricas globales del mercado (Fear & Greed, market cap, dominancia)
- Analisis tecnico del token (RSI, MACD, EMA, Fibonacci)
- Noticias recientes del token
- Narrativas trending del mercado
- Eventos macro proximos

CLAUDE_ENABLED=false (default): solo loguea lo que haria, NO afecta decisiones.
CLAUDE_ENABLED=true           : modifica decisiones del agente.

Activar el dia de la competicion (22 junio) cambiando .env
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CLAUDE_ENABLED    = os.getenv("CLAUDE_ENABLED", "false").lower() == "true"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CMC_API_KEY       = os.getenv("CMC_API_KEY", "")

CMC_MCP_URL = "https://mcp.coinmarketcap.com/mcp"
NEWS_LOG    = "logs/news_analyzer.log"

# Modelo economico para monitoreo continuo
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Cache de IDs CMC para no repetir busquedas
_id_cache = {}


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    mode = "[DRY-RUN]" if not CLAUDE_ENABLED else "[LIVE]"
    line = f"[{timestamp}] [NEWS] {mode} {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(NEWS_LOG, "a") as f:
        f.write(line + "\n")


# ── Cliente MCP de CMC ────────────────────────────────────────────────────────

class CMCMCPClient:
    """Cliente MCP para CMC AI Agent Hub. Inicializa sesion y llama herramientas."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "X-CMC-MCP-API-KEY": CMC_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        })
        self._initialized = False

    def _initialize(self):
        try:
            self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "superagente007", "version": "1.0"}
                }
            }, timeout=15)
            self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"
            }, timeout=10)
            self._initialized = True
        except Exception as e:
            log(f"Error inicializando MCP: {e}")

    def call(self, tool_name, arguments=None):
        if not self._initialized:
            self._initialize()
        try:
            r = self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}}
            }, timeout=20)
            result = r.json().get("result", {})
            content = result.get("content", [{}])
            text = content[0].get("text", "") if content else ""
            if text.startswith("error:"):
                log(f"MCP tool {tool_name} error: {text}")
                return None
            return json.loads(text) if text else None
        except Exception as e:
            log(f"Error llamando MCP tool {tool_name}: {e}")
            return None


# ── Funciones de contexto usando MCP ─────────────────────────────────────────

def _get_cmc_id(client, symbol):
    """Obtiene el ID numerico de CMC para un symbol. Usa cache."""
    if symbol in _id_cache:
        return _id_cache[symbol]
    results = client.call("search_cryptos", {"query": symbol})
    if results and isinstance(results, list):
        for item in results:
            if item.get("symbol", "").upper() == symbol.upper():
                _id_cache[symbol] = item["id"]
                return item["id"]
    return None


def fetch_global_metrics(client):
    """Metricas globales: Fear & Greed, market cap, dominancia BTC."""
    data = client.call("get_global_metrics_latest")
    if not data:
        return None
    # Extraer solo lo relevante para el contexto
    market_size = data.get("market_size", {})
    total_cap = market_size.get("total_crypto_market_cap_usd", {})
    fg = data.get("fear_and_greed_index", {})
    return {
        "market_cap": total_cap.get("current"),
        "market_cap_change_24h": total_cap.get("percent_change", {}).get("24h"),
        "fear_greed_value": fg.get("value"),
        "fear_greed_label": fg.get("value_classification"),
    }


def fetch_technical_analysis(client, symbol):
    """RSI, MACD, EMA, Fibonacci para el token."""
    cmc_id = _get_cmc_id(client, symbol)
    if not cmc_id:
        log(f"No se encontro ID CMC para {symbol}")
        return None
    return client.call("get_crypto_technical_analysis", {"id": cmc_id})


def fetch_token_news(client, symbol):
    """Ultimas noticias del token."""
    cmc_id = _get_cmc_id(client, symbol)
    if not cmc_id:
        return None
    data = client.call("get_crypto_latest_news", {"id": cmc_id})
    if not data:
        return None
    rows = data.get("rows", [])
    # Retorna los titulos y contenido resumido de las 3 noticias mas recientes
    news = []
    for row in rows[:3]:
        news.append({"title": row[0], "summary": row[1][:200] if len(row) > 1 else ""})
    return news


def fetch_trending_narratives(client):
    """Narrativas trending del mercado."""
    data = client.call("trending_crypto_narratives")
    if not data:
        return None
    rows = data.get("categoryList", {}).get("rows", [])
    narratives = []
    for row in rows[:5]:
        narratives.append({
            "rank": row[0],
            "name": row[3] if len(row) > 3 else "",
            "change_24h": row[5] if len(row) > 5 else "",
        })
    return narratives


def fetch_macro_events(client):
    """Eventos macro proximos que pueden mover el mercado."""
    data = client.call("get_upcoming_macro_events")
    if not data:
        return None
    rows = data.get("upcomingEventNews", {}).get("rows", [])
    events = []
    for row in rows[:3]:
        events.append({"title": row[0], "summary": row[1][:150] if len(row) > 1 else "", "date": row[3] if len(row) > 3 else ""})
    return events


# ── Contexto completo para Claude ─────────────────────────────────────────────

def build_context(symbol):
    """Arma el contexto de mercado via CMC MCP."""
    client = CMCMCPClient()
    ctx = {}
    ctx["global_metrics"]       = fetch_global_metrics(client)
    ctx["technical_analysis"]   = fetch_technical_analysis(client, symbol)
    ctx["token_news"]           = fetch_token_news(client, symbol)
    ctx["trending_narratives"]  = fetch_trending_narratives(client)
    ctx["macro_events"]         = fetch_macro_events(client)
    return ctx


# ── Reglas del operador ───────────────────────────────────────────────────────

def load_market_rules():
    rules_path = pathlib.Path(__file__).parent.parent / "knowledge" / "MARKET_RULES.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return "Sin reglas definidas aun. Usar criterio conservador."


# ── Claude ────────────────────────────────────────────────────────────────────

def _call_claude(symbol, context):
    """Llama a Claude Haiku con el contexto y las reglas del operador."""
    try:
        import anthropic
    except ImportError:
        log("Libreria 'anthropic' no instalada. Correr: pip install anthropic")
        return None

    if not ANTHROPIC_API_KEY:
        log("ANTHROPIC_API_KEY no configurada en .env")
        return None

    rules = load_market_rules()
    ctx_text = json.dumps(context, indent=2, ensure_ascii=False, default=str)

    prompt = f"""Sos un analista de trading cripto especializado en BSC/BNB Chain.
Analizá el contexto actual y decidí si es momento de comprar {symbol}.

## REGLAS DEL OPERADOR (seguirlas siempre)
{rules}

## CONTEXTO DE MERCADO AHORA
{ctx_text}

## GUIA DE INTERPRETACION
- global_metrics: Fear & Greed < 25 = panico extremo (SKIP). Caida market cap 24h > 5% = cautela (REDUCE_SIZE).
- technical_analysis: RSI14 > 70 = sobrecomprado (REDUCE_SIZE o SKIP). MACD histogram positivo y creciendo = momentum alcista (PROCEED).
- token_news: noticias negativas recientes sobre el token (hack, exploit, dump coordinado) = SKIP.
- trending_narratives: si el sector del token esta entre los top 3 narrativas con cambio positivo = favor de PROCEED.
- macro_events: eventos macro de alto impacto en las proximas 24-48h = REDUCE_SIZE o SKIP segun gravedad.

## INSTRUCCION
Respondé SOLO con JSON valido, sin texto extra:
{{
  "bias": "bullish" | "bearish" | "neutral",
  "confidence": 0.0,
  "action_modifier": "PROCEED" | "SKIP" | "REDUCE_SIZE",
  "reason": "una linea explicando la decision",
  "risk_notes": "riesgo importante si hay alguno, sino null"
}}

- PROCEED    : contexto favorable, continuar con la decision original
- SKIP       : contexto negativo (guerra, hack, crash macro, RSI extremo), no entrar ahora
- REDUCE_SIZE: entrar pero con 50% menos capital del calculado
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        # Extraer JSON aunque Claude agregue texto extra
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            log(f"Claude no devolvio JSON: {raw[:100]}")
            return None
        result = json.loads(raw[start:end])

        # Calcular tokens usados para monitoreo de costos
        input_tokens  = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens
        cost_usd = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
        log(f"Tokens usados: {input_tokens} in / {output_tokens} out | Costo: ${cost_usd:.5f}")
        log(f"{symbol} -> {result['bias']} ({result['confidence']:.0%}) | "
            f"{result['action_modifier']} | {result['reason']}")

        # Guardar costo acumulado para analisis posterior
        _log_cost(input_tokens, output_tokens, cost_usd)

        return result

    except json.JSONDecodeError as e:
        log(f"JSON invalido de Claude: {e}")
        return None
    except Exception as e:
        log(f"Error llamando a Claude: {e}")
        return None


def _log_cost(input_tokens, output_tokens, cost_usd):
    """Guarda cada llamada en logs/claude_costs.log para monitorear consumo."""
    cost_log = "logs/claude_costs.log"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(cost_log, "a") as f:
        f.write(f"{timestamp} | in={input_tokens} out={output_tokens} cost=${cost_usd:.5f}\n")


# ── Funcion publica ───────────────────────────────────────────────────────────

def get_market_bias(symbol):
    """
    Funcion principal que llama el decision_engine.

    Retorna:
      - None si CLAUDE_ENABLED=false (no afecta la decision)
      - None si ocurre cualquier error (el agente sigue funcionando igual)
      - dict con bias/action_modifier/reason si CLAUDE_ENABLED=true y todo sale bien
    """
    log(f"Analizando contexto para {symbol}...")

    context = build_context(symbol)
    analysis = _call_claude(symbol, context)

    if not analysis:
        return None

    if not CLAUDE_ENABLED:
        log(f"DRY-RUN completado | Si estuviera activo: "
            f"{analysis['action_modifier']} — {analysis['reason']}")
        return None  # No modifica nada cuando esta deshabilitado

    return analysis


# ── Test manual ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test news_analyzer ===")
    print(f"CLAUDE_ENABLED = {CLAUDE_ENABLED}")
    print(f"ANTHROPIC_API_KEY configurada: {'Si' if ANTHROPIC_API_KEY else 'No'}")
    print()

    result = get_market_bias("CAKE")
    if result:
        print(f"Resultado: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print("Resultado: None (DRY-RUN o error — ver logs/news_analyzer.log)")
