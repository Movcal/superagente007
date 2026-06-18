"""
Market Intelligence — escaner de noticias CMC + sentimiento + acumulacion de narrativas.

Responsabilidades:
  1. scan_news()             : cada 30 min, busca noticias en CMC para los 84 tokens,
                               clasifica sentimiento con Claude Haiku (lotes de 10),
                               acumula {positive, negative, neutral} en narrative_tracker.json.
  2. generate_daily_summary(): a las 11:00 UTC, llama a Claude Haiku con los ultimos 7 dias
                               de datos de narrativas y genera un analisis comparativo.
  3. get_narrative_boost()   : devuelve boost de confianza (0.0-0.25) al decision_engine
                               cuando una narrativa lleva 3+ dias con noticias positivas.
  4. should_generate_summary(): True si es >= 11:00 UTC y el resumen de hoy no existe aun.

Datos persistentes:
  data/cmc_id_cache.json     : {symbol -> cmc_id}
  data/news_seen.json        : {url -> timestamp}, TTL 48h
  data/narrative_tracker.json: {"YYYY-MM-DD": {"categories": {cat: {positive,negative,neutral}}, "tokens": {...}}}
  data/daily_summaries/      : un JSON por dia con el resumen de Claude
"""
import os
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY       = os.getenv("CMC_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_ENABLED    = os.getenv("CLAUDE_ENABLED", "false").lower() == "true"

CMC_MCP_URL  = "https://mcp.coinmarketcap.com/mcp"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

TOKEN_RAW_INFO  = "data/token_raw_info.json"
CMC_ID_CACHE    = "data/cmc_id_cache.json"
NEWS_SEEN_FILE  = "data/news_seen.json"
TRACKER_FILE    = "data/narrative_tracker.json"
SUMMARIES_DIR   = "data/daily_summaries"
WATCHLIST_FILE  = "data/watchlist.json"
VOLUME_HISTORY  = "data/volume_history.json"
MI_LOG          = "logs/market_intelligence.log"

NARRATIVE_TREND_DAYS   = 3   # dias consecutivos para activar boost
NARRATIVE_MIN_POSITIVE = 2   # minimo de noticias positivas por dia para considerar narrativa activa
NEWS_SEEN_TTL_HOURS    = 48
SENTIMENT_BATCH_SIZE   = 10  # articulos por llamada a Claude


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [MI] {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(MI_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Cliente MCP CMC ───────────────────────────────────────────────────────────

class CMCClient:
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
                    "clientInfo": {"name": "superagente007-mi", "version": "1.0"}
                }
            }, timeout=15)
            self.session.post(CMC_MCP_URL, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"
            }, timeout=10)
            self._initialized = True
        except Exception as e:
            log(f"Error inicializando CMC MCP: {e}")

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
                log(f"MCP {tool_name} error: {text}")
                return None
            return json.loads(text) if text else None
        except Exception as e:
            log(f"Error llamando {tool_name}: {e}")
            return None


# ── Token knowledge ───────────────────────────────────────────────────────────

def load_token_knowledge():
    if not os.path.exists(TOKEN_RAW_INFO):
        log(f"Archivo {TOKEN_RAW_INFO} no encontrado")
        return {}
    try:
        with open(TOKEN_RAW_INFO, "r", encoding="utf-8") as f:
            raw = json.load(f)
        knowledge = {}
        items = raw.values() if isinstance(raw, dict) else raw
        for token in items:
            sym = token.get("symbol", "")
            if sym and token.get("keywords"):
                knowledge[sym] = {
                    "category":    token.get("category", ""),
                    "subcategory": token.get("subcategory", ""),
                    "keywords":    token.get("keywords", []),
                }
        log(f"Token knowledge cargado: {len(knowledge)} tokens con keywords")
        return knowledge
    except Exception as e:
        log(f"Error cargando token knowledge: {e}")
        return {}


# ── CMC ID cache ──────────────────────────────────────────────────────────────

def load_cmc_id_cache():
    if os.path.exists(CMC_ID_CACHE):
        with open(CMC_ID_CACHE, "r") as f:
            return json.load(f)
    return {}


def save_cmc_id_cache(cache):
    os.makedirs("data", exist_ok=True)
    with open(CMC_ID_CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def get_cmc_id(client, symbol, id_cache):
    if symbol in id_cache:
        return id_cache[symbol]
    results = client.call("search_cryptos", {"query": symbol})
    if results and isinstance(results, list):
        for item in results:
            if item.get("symbol", "").upper() == symbol.upper():
                id_cache[symbol] = item["id"]
                save_cmc_id_cache(id_cache)
                return item["id"]
    log(f"No se encontro ID CMC para {symbol}")
    return None


# ── News seen tracker ─────────────────────────────────────────────────────────

def load_news_seen():
    if os.path.exists(NEWS_SEEN_FILE):
        with open(NEWS_SEEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_news_seen(seen):
    with open(NEWS_SEEN_FILE, "w") as f:
        json.dump(seen, f)


def clean_old_seen(seen):
    cutoff = time.time() - (NEWS_SEEN_TTL_HOURS * 3600)
    return {url: ts for url, ts in seen.items() if ts > cutoff}


# ── Narrative tracker ─────────────────────────────────────────────────────────

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tracker(tracker):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def _init_sentiment_entry():
    return {"positive": 0, "negative": 0, "neutral": 0}


def update_narrative_tracker(tracker, matched_with_sentiment, knowledge):
    """
    matched_with_sentiment: lista de (symbol, sentiment)
      sentiment = "BULLISH" | "BEARISH" | "NEUTRAL"
    Acumula {positive, negative, neutral} por token y categoria.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if today not in tracker:
        tracker[today] = {"categories": {}, "tokens": {}}

    for symbol, sentiment in matched_with_sentiment:
        key = "positive" if sentiment in ("BULLISH_ALTO", "BULLISH_BAJO") else ("negative" if sentiment == "BEARISH" else "neutral")

        # Token
        tokens_day = tracker[today]["tokens"]
        if symbol not in tokens_day:
            tokens_day[symbol] = _init_sentiment_entry()
        # Manejar formato viejo (int) si existe
        if isinstance(tokens_day[symbol], int):
            tokens_day[symbol] = _init_sentiment_entry()
        tokens_day[symbol][key] += 1

        # Categoria
        cat = knowledge.get(symbol, {}).get("category", "")
        if cat:
            cats_day = tracker[today]["categories"]
            if cat not in cats_day:
                cats_day[cat] = _init_sentiment_entry()
            if isinstance(cats_day[cat], int):
                cats_day[cat] = _init_sentiment_entry()
            cats_day[cat][key] += 1

    return tracker


# ── Confirmacion narrativa pre-spike ─────────────────────────────────────────

def get_narrative_confirmation(symbol, knowledge=None, tracker=None):
    """
    Verifica si un token tiene narrativa positiva PRE-EXISTENTE antes de un spike de volumen.
    Esto cierra el loop: narrativa acumulando (dias) → volumen confirma → ENTRADA.

    Evalua los ultimos 3 dias de noticias del token y retorna:
    {
      "confirmed": True/False,
      "strength": "fuerte" | "moderada" | "debil" | "ninguna",
      "bull_score": 0-100,          # % de noticias bullish
      "positive_days": N,           # dias con al menos 1 noticia positiva
      "total_articles": N,
      "message": "texto explicativo para el reasoning del agente"
    }

    Umbrales:
      - fuerte   : bull_score >= 60% Y positive_days >= 2
      - moderada : bull_score >= 40% Y positive_days >= 1
      - debil    : bull_score >= 25%
      - ninguna  : sin datos o bull_score < 25%
    """
    if knowledge is None:
        knowledge = load_token_knowledge()
    if tracker is None:
        tracker = load_tracker()

    today = datetime.utcnow().date()
    total_pos = total_neg = total_neu = 0
    positive_days = 0

    for i in range(3):  # ultimos 3 dias incluyendo hoy
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = tracker.get(date_str, {})
        token_data = day_data.get("tokens", {}).get(symbol, {})

        if not token_data or isinstance(token_data, int):
            continue

        p = token_data.get("positive", 0)
        n = token_data.get("negative", 0)
        u = token_data.get("neutral", 0)
        total_pos += p
        total_neg += n
        total_neu += u
        if p >= 1:
            positive_days += 1

    total_articles = total_pos + total_neg + total_neu

    if total_articles == 0:
        return {
            "confirmed": False,
            "strength": "none",
            "bull_score": 0,
            "positive_days": 0,
            "total_articles": 0,
            "message": "No news coverage in the last 3 days"
        }

    bull_score = round(total_pos / total_articles * 100)

    if bull_score >= 60 and positive_days >= 2:
        strength  = "strong"
        confirmed = True
        msg = (f"STRONG pre-existing narrative: {bull_score}% bullish "
               f"({total_pos} positive / {total_articles} total over {positive_days} days) — "
               f"market was already building momentum on this token before the spike")
    elif bull_score >= 40 and positive_days >= 1:
        strength  = "moderate"
        confirmed = True
        msg = (f"MODERATE pre-existing narrative: {bull_score}% bullish "
               f"({total_pos} positive / {total_articles} total) — "
               f"there is interest but not yet widespread")
    elif bull_score >= 25:
        strength  = "weak"
        confirmed = False
        msg = (f"WEAK narrative: {bull_score}% bullish — "
               f"volume spike lacks solid news backing")
    else:
        strength  = "none"
        confirmed = False
        msg = (f"No bullish narrative ({bull_score}% positive, {total_neg} negative) — "
               f"spike may be noise or manipulation without fundamentals")

    return {
        "confirmed": confirmed,
        "strength": strength,
        "bull_score": bull_score,
        "positive_days": positive_days,
        "total_articles": total_articles,
        "message": msg
    }


# ── Matching: articulo → tokens ───────────────────────────────────────────────

def match_article_to_tokens(title, content, knowledge):
    text = ((title or "") + " " + (content or "")).lower()
    matched = []
    for symbol, info in knowledge.items():
        for kw in info.get("keywords", []):
            if kw.lower() in text:
                matched.append(symbol)
                break
    return matched


# ── Clasificacion de sentimiento con Claude Haiku ─────────────────────────────

def classify_sentiment_batch(articles):
    """
    Clasifica el sentimiento de una lista de articulos con Claude Haiku.
    articles: lista de dicts {symbol, title, content}
    Retorna: lista de "BULLISH"|"BEARISH"|"NEUTRAL" en el mismo orden.
    """
    if not articles:
        return []

    if not ANTHROPIC_API_KEY:
        log("classify_sentiment_batch: ANTHROPIC_API_KEY no configurada, usando NEUTRAL")
        return ["NEUTRAL"] * len(articles)

    try:
        import anthropic
    except ImportError:
        return ["NEUTRAL"] * len(articles)

    items_text = ""
    for i, a in enumerate(articles, 1):
        title   = (a.get("title") or "")[:120]
        content = (a.get("content") or "")[:200]
        items_text += f"{i}. [{a['symbol']}] {title} — {content}\n"

    prompt = (
        "You are a crypto market sentiment classifier.\n"
        "Classify each article using EXACTLY one of: BULLISH_ALTO, BULLISH_BAJO, BEARISH, NEUTRAL\n\n"
        "Definitions:\n"
        "- BULLISH_ALTO: major catalyst — institutional/government adoption, listing on Binance/Coinbase/Kraken, "
        "partnership with Fortune 500 or top-tier blockchain, integration as payment method at scale, "
        "major protocol upgrade (mainnet launch, v2), regulatory approval\n"
        "- BULLISH_BAJO: minor positive — generic price analysis, small partnership, community sentiment, "
        "minor exchange listing, ecosystem grant, bullish prediction without concrete catalyst\n"
        "- BEARISH: negative news (hack, exploit, shutdown, lawsuit, price crash, token unlock, bearish analysis)\n"
        "- NEUTRAL: general market news, unrelated content, no clear directional bias\n\n"
        "Classify based on impact on THAT specific token in brackets, not the general market.\n\n"
        f"Articles:\n{items_text}\n"
        f"Respond ONLY with valid JSON: {{\"results\": [\"BULLISH_ALTO\", \"NEUTRAL\", ...]}}\n"
        f"Return exactly {len(articles)} items in the same order."
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        parsed  = json.loads(raw[start:end])
        results = parsed.get("results", [])

        cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
        log(f"Sentiment batch {len(articles)} articulos | ${cost:.5f}")

        valid = {"BULLISH_ALTO", "BULLISH_BAJO", "BEARISH", "NEUTRAL"}
        while len(results) < len(articles):
            results.append("NEUTRAL")
        return [r if r in valid else "NEUTRAL" for r in results[:len(articles)]]

    except Exception as e:
        log(f"Error en classify_sentiment_batch: {e}")
        return ["NEUTRAL"] * len(articles)


# ── Trend analysis ────────────────────────────────────────────────────────────

def _get_positive_count(cat_data):
    """Extrae conteo positivo de un entry del tracker (soporta formato viejo int y nuevo dict)."""
    if isinstance(cat_data, dict):
        return cat_data.get("positive", 0)
    return int(cat_data)  # formato viejo: era total, lo tratamos como neutral


def get_narrative_trend(category, tracker, days=4):
    """
    Analiza la tendencia POSITIVA de una categoria en los ultimos N dias.
    Retorna: {"trend": "building"|"stable"|"declining"|"no_data", "daily_positive": [...], "active_days": N}
    """
    today = datetime.utcnow().date()
    positive_counts = []
    for i in range(days - 1, -1, -1):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = tracker.get(date_str, {})
        cat_data = day_data.get("categories", {}).get(category, {})
        positive_counts.append(_get_positive_count(cat_data))

    active_days = sum(1 for c in positive_counts if c >= NARRATIVE_MIN_POSITIVE)

    if active_days == 0:
        return {"trend": "no_data", "daily_positive": positive_counts, "active_days": 0}

    mid = len(positive_counts) // 2
    first_half  = sum(positive_counts[:mid]) if mid > 0 else 0
    second_half = sum(positive_counts[mid:])

    if second_half > first_half * 1.3 and active_days >= 2:
        trend = "building"
    elif second_half < first_half * 0.7:
        trend = "declining"
    else:
        trend = "stable"

    return {"trend": trend, "daily_positive": positive_counts, "active_days": active_days}


def get_narrative_boost(symbol, knowledge=None, tracker=None):
    """
    Boost de confianza para decision_engine basado en narrativa POSITIVA acumulada.
    Retorna float entre 0.0 y 0.20.

    Reglas (solo cuenta noticias BULLISH):
      - Narrativa "building" >= 3 dias activos: +0.20
      - Narrativa "building" 2 dias: +0.12
      - Narrativa "stable"   >= 3 dias: +0.08
      - Resto: 0.0
    """
    if knowledge is None:
        knowledge = load_token_knowledge()
    if tracker is None:
        tracker = load_tracker()

    category = knowledge.get(symbol, {}).get("category", "")
    if not category:
        return 0.0

    trend_info = get_narrative_trend(category, tracker, days=NARRATIVE_TREND_DAYS + 1)
    trend      = trend_info["trend"]
    active_days = trend_info["active_days"]

    if trend == "building" and active_days >= NARRATIVE_TREND_DAYS:
        boost = 0.20
    elif trend == "building" and active_days >= 2:
        boost = 0.12
    elif trend == "stable" and active_days >= NARRATIVE_TREND_DAYS:
        boost = 0.08
    else:
        boost = 0.0

    if boost > 0:
        log(f"{symbol} ({category}): narrativa {trend}, {active_days} dias positivos -> boost +{boost}")

    return boost


# ── Scanner principal ─────────────────────────────────────────────────────────

def scan_news(symbols=None):
    """
    Escanea noticias en CMC para cada token, clasifica sentimiento con Claude Haiku
    y acumula en narrative_tracker.json.

    Flujo:
      1. Por cada token: GET noticias CMC
      2. Filtrar articulos ya vistos (news_seen.json)
      3. Buscar keywords → detectar tokens relevantes
      4. Acumular articulos para clasificacion
      5. Batch classify con Claude Haiku (lotes de SENTIMENT_BATCH_SIZE)
      6. Guardar sentimientos en narrative_tracker
    """
    log("=== Iniciando scan de noticias CMC ===")
    knowledge = load_token_knowledge()
    id_cache  = load_cmc_id_cache()
    seen      = clean_old_seen(load_news_seen())
    tracker   = load_tracker()

    if not knowledge:
        log("Sin token knowledge disponible, abortando scan")
        return {}, {}

    target_symbols = symbols if symbols else list(knowledge.keys())
    client = CMCClient()

    scan_results   = {}
    total_new      = 0
    pending        = []  # [(symbol, title, content), ...]

    for i, symbol in enumerate(target_symbols):
        cmc_id = get_cmc_id(client, symbol, id_cache)
        if not cmc_id:
            continue

        if i > 0 and i % 10 == 0:
            time.sleep(1)

        data = client.call("get_crypto_latest_news", {"id": cmc_id})
        if not data:
            continue

        rows = data.get("rows", [])
        new_articles = []

        for row in rows:
            title   = (row[0] if len(row) > 0 else "") or ""
            content = (row[1] if len(row) > 1 else "") or ""
            url     = (row[2] if len(row) > 2 else "") or ""

            if url in seen:
                continue

            seen[url] = time.time()
            new_articles.append({"title": title, "url": url})
            total_new += 1

            # Detectar tokens relevantes via keywords
            matched = match_article_to_tokens(title, content, knowledge)
            tokens_to_credit = [symbol] if (symbol in matched or not matched) else matched
            for t in tokens_to_credit:
                pending.append((t, title, content))

        if new_articles:
            scan_results[symbol] = new_articles

    # Clasificar sentimiento en lotes con Claude Haiku
    all_sentiments = []
    breaking_news  = {}  # {symbol: titulo} para BULLISH_ALTO
    if pending:
        log(f"Clasificando sentimiento de {len(pending)} menciones con Claude Haiku...")
        for i in range(0, len(pending), SENTIMENT_BATCH_SIZE):
            batch = pending[i:i + SENTIMENT_BATCH_SIZE]
            articles_for_claude = [
                {"symbol": sym, "title": title, "content": content[:300]}
                for sym, title, content in batch
            ]
            sentiments = classify_sentiment_batch(articles_for_claude)
            all_sentiments.extend(sentiments)

        matched_with_sentiment = [
            (sym, sent) for (sym, _, _), sent in zip(pending, all_sentiments)
        ]
        tracker = update_narrative_tracker(tracker, matched_with_sentiment, knowledge)

        bullish_alto = sum(1 for s in all_sentiments if s == "BULLISH_ALTO")
        bullish_bajo = sum(1 for s in all_sentiments if s == "BULLISH_BAJO")
        bearish      = sum(1 for s in all_sentiments if s == "BEARISH")
        neutral      = sum(1 for s in all_sentiments if s == "NEUTRAL")
        log(f"Sentimiento: BULLISH_ALTO={bullish_alto} | BULLISH_BAJO={bullish_bajo} | BEARISH={bearish} | NEUTRAL={neutral}")

        # Identificar tokens con breaking news (BULLISH_ALTO)
        for (sym, title, _), sent in zip(pending, all_sentiments):
            if sent == "BULLISH_ALTO":
                if sym not in breaking_news:
                    breaking_news[sym] = title
                    log(f"[BREAKING] {sym}: '{title[:80]}'")

    save_news_seen(seen)
    save_tracker(tracker)

    log(f"Scan completado: {len(target_symbols)} tokens | "
        f"{total_new} articulos nuevos | {len(pending)} menciones clasificadas")
    return scan_results, breaking_news


# ── Resumen diario con Claude ─────────────────────────────────────────────────

def should_generate_summary():
    now = datetime.utcnow()
    if now.hour < 11:
        return False
    today = now.strftime("%Y-%m-%d")
    return not os.path.exists(os.path.join(SUMMARIES_DIR, f"{today}.json"))


def _build_summary_prompt(tracker):
    today = datetime.utcnow().date()
    days_data = []
    for i in range(6, -1, -1):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day = tracker.get(date_str, {"categories": {}, "tokens": {}})
        days_data.append({"date": date_str, **day})

    days_text = json.dumps(days_data, indent=2, ensure_ascii=False)

    return (
        "You are a crypto market intelligence analyst specialized in BSC/BNB Chain.\n"
        "Analyze 7 days of news sentiment data for our 84 tradeable tokens.\n\n"
        "Each day shows categories and tokens with {positive, negative, neutral} article counts.\n"
        "Focus on POSITIVE counts — these signal genuine bullish narrative building.\n\n"
        f"## DATA (last 7 days)\n{days_text}\n\n"
        "## TASK\nIdentify:\n"
        "1. Categories with growing positive mentions (potential upcoming moves)\n"
        "2. Categories with declining or negative-dominated coverage (avoid)\n"
        "3. Specific tokens accumulating positive narrative for 3+ days\n"
        "4. Any risk alerts (sector with spike of negative news)\n\n"
        f"Respond ONLY with valid JSON:\n"
        '{{\n'
        '  "date": "' + str(today) + '",\n'
        '  "trending_up": ["category1", "category2"],\n'
        '  "trending_down": ["category3"],\n'
        '  "hot_tokens": ["TOKEN1", "TOKEN2"],\n'
        '  "avoid_tokens": ["TOKEN3"],\n'
        '  "sector_outlook": {{"memecoin": "brief", "defi": "brief", "ai-infra": "brief", "layer-1": "brief"}},\n'
        '  "key_insight": "one sentence with the most important insight",\n'
        '  "risk_alert": "risk if any, else null"\n'
        '}}'
    )


def generate_daily_summary():
    if not CLAUDE_ENABLED:
        log("generate_daily_summary: CLAUDE_ENABLED=false, saltando")
        return None
    if not ANTHROPIC_API_KEY:
        log("generate_daily_summary: ANTHROPIC_API_KEY no configurada")
        return None

    tracker = load_tracker()
    if not tracker:
        log("generate_daily_summary: sin datos en tracker, saltando")
        return None

    try:
        import anthropic
    except ImportError:
        log("generate_daily_summary: libreria 'anthropic' no instalada")
        return None

    log("Generando resumen diario con Claude Haiku...")
    prompt = _build_summary_prompt(tracker)

    try:
        anth = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = anth.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            log(f"Claude no devolvio JSON: {raw[:200]}")
            return None

        summary = json.loads(raw[start:end])

        cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
        log(f"Resumen generado | ${cost:.5f}")

        os.makedirs(SUMMARIES_DIR, exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        path = os.path.join(SUMMARIES_DIR, f"{today}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        log(f"Resumen guardado: {path}")
        log(f"Insight: {summary.get('key_insight', 'N/A')}")
        if summary.get("risk_alert"):
            log(f"ALERTA: {summary['risk_alert']}")

        return summary

    except Exception as e:
        log(f"Error generando resumen: {e}")
        return None


# ── Watchlist — seguimiento de tokens con narrativa confirmada ────────────────

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)


def load_trending_categories():
    """Lee las categorias trending_up del resumen diario mas reciente."""
    try:
        files = sorted(pathlib.Path(SUMMARIES_DIR).glob("*.json"), reverse=True)
        if files:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            cats = set(data.get("trending_up", []))
            if cats:
                log(f"[WATCHLIST] Narrativas trending hoy: {', '.join(cats)}")
            return cats
    except Exception:
        pass
    return set()


def update_watchlist():
    """
    Recorre todos los tokens y actualiza la watchlist:
    - Agrega los que tienen narrativa confirmada (moderada o fuerte)
    - Agrega con prioridad TODOS los tokens cuya categoria esta en trending_up del resumen diario
      (umbral reducido a 20% bull_score si la narrativa es trending)
    - Remueve los que perdieron narrativa y no estan en trending
    - Actualiza el estado de los que ya estaban
    """
    knowledge     = load_token_knowledge()
    tracker       = load_tracker()
    watchlist     = load_watchlist()
    trending_cats = load_trending_categories()
    today         = datetime.utcnow().strftime("%Y-%m-%d")
    added = removed = updated = 0

    for symbol in knowledge:
        conf     = get_narrative_confirmation(symbol, knowledge, tracker)
        cat      = knowledge[symbol].get("category", "")
        in_trend = cat in trending_cats

        # Umbral: 40% normal, 20% si la narrativa esta trending en el resumen diario
        threshold = 20 if in_trend else 40
        qualifies = conf["confirmed"] or (in_trend and conf["bull_score"] >= threshold)

        if qualifies:
            added_date = watchlist[symbol].get("added", today) if symbol in watchlist else today
            try:
                days_in_watchlist = (datetime.utcnow().date() -
                                     datetime.strptime(added_date, "%Y-%m-%d").date()).days
            except Exception:
                days_in_watchlist = 0

            entry = {
                "narrative_strength":  conf["strength"],
                "bull_score":          conf["bull_score"],
                "positive_days":       conf["positive_days"],
                "last_updated":        datetime.utcnow().isoformat(),
                "trending_narrative":  in_trend,
                "category":            cat,
                "days_in_watchlist":   days_in_watchlist,
            }
            if symbol not in watchlist:
                entry["added"]         = today
                entry["volume_status"] = "waiting"
                entry["days_in_watchlist"] = 0
                watchlist[symbol]      = entry
                added += 1
                if in_trend and not conf["confirmed"]:
                    log(f"[WATCHLIST] + {symbol} agregado (narrativa {cat} TRENDING, {conf['bull_score']}% bullish)")
                else:
                    log(f"[WATCHLIST] + {symbol} agregado ({conf['strength']}, {conf['bull_score']}% bullish)")
            else:
                watchlist[symbol].update(entry)
                updated += 1
        elif symbol in watchlist and conf["bull_score"] < 25 and not in_trend:
            del watchlist[symbol]
            removed += 1
            log(f"[WATCHLIST] - {symbol} removido (narrativa caida: {conf['bull_score']}% bullish)")

    save_watchlist(watchlist)
    log(f"[WATCHLIST] Estado: {len(watchlist)} tokens | +{added} agregados | -{removed} removidos | {updated} actualizados")
    return watchlist


def check_watchlist_volume():
    """
    Para cada token en watchlist, analiza la tendencia de volumen usando
    el historial existente en volume_history.json (actualizado por volume_monitor).

    Niveles de alerta:
      >= 5.0x → spike confirmado (ya lo detecta volume_monitor, pero lo marcamos aqui)
      >= 2.5x → ACELERANDO  — alerta temprana fuerte
      >= 1.5x → DESPERTANDO — primera señal de interes

    Retorna: lista de dicts con los tokens que muestran movimiento.
    """
    watchlist = load_watchlist()
    if not watchlist:
        return []

    if not os.path.exists(VOLUME_HISTORY):
        return []

    with open(VOLUME_HISTORY, "r") as f:
        history = json.load(f)

    alerts = []
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    for symbol, entry in watchlist.items():
        readings = history.get(symbol, [])
        if len(readings) < 6:
            continue

        # Baseline: promedio de las ultimas 12-24 lecturas (1-2 horas)
        baseline_readings = readings[-24:] if len(readings) >= 24 else readings
        baseline = sum(baseline_readings) / len(baseline_readings)
        if baseline == 0:
            continue

        # Reciente: promedio de las ultimas 3 lecturas (15 min)
        recent = sum(readings[-3:]) / 3
        ratio  = recent / baseline

        # Determinar status
        if ratio >= 5.0:
            status = "SPIKE"
            level  = 3
        elif ratio >= 2.5:
            status = "ACELERANDO"
            level  = 2
        elif ratio >= 1.5:
            status = "DESPERTANDO"
            level  = 1
        else:
            status = "waiting"
            level  = 0

        # Actualizar status en watchlist
        prev_status = entry.get("volume_status", "waiting")
        if status != prev_status:
            watchlist[symbol]["volume_status"] = status
            watchlist[symbol]["volume_ratio"]  = round(ratio, 2)
            watchlist[symbol]["volume_alert_time"] = now_str

        if level >= 1:
            narrative_str = entry.get("narrative_strength", "")
            bull_score    = entry.get("bull_score", 0)
            alert = {
                "symbol":    symbol,
                "status":    status,
                "ratio":     round(ratio, 2),
                "narrative": narrative_str,
                "bull_score": bull_score,
                "level":     level,
            }
            alerts.append(alert)
            log(f"[WATCHLIST] {symbol}: volumen {status} {ratio:.1f}x | "
                f"narrativa {narrative_str} ({bull_score}% bullish)")

    save_watchlist(watchlist)

    # Ordenar por nivel de alerta y ratio
    alerts.sort(key=lambda x: (-x["level"], -x["ratio"]))
    return alerts


def get_today_summary():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(SUMMARIES_DIR, f"{today}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Test manual ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test Market Intelligence (con sentimiento) ===")
    print(f"CLAUDE_ENABLED = {CLAUDE_ENABLED}")
    print()

    # Limpiar news_seen para forzar re-scan en test
    import sys
    force_rescan = "--rescan" in sys.argv

    if force_rescan:
        print("Modo --rescan: limpiando news_seen.json...")
        save_news_seen({})

    print("--- Scan de prueba: PENGU, FET, ZRO, 0G ---")
    results = scan_news(symbols=["PENGU", "FET", "ZRO", "0G"])
    for sym, articles in results.items():
        print(f"  {sym}: {len(articles)} articulos nuevos")

    print()
    print("--- Narrative tracker hoy ---")
    tracker = load_tracker()
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    day = tracker.get(today, {})
    tokens = day.get("tokens", {})
    for sym in ["PENGU", "FET", "ZRO", "0G"]:
        t = tokens.get(sym, {})
        print(f"  {sym}: {t}")

    print()
    print("--- Narrative boost ---")
    for sym in ["FET", "PENGU", "ZRO", "0G"]:
        boost = get_narrative_boost(sym)
        print(f"  {sym}: boost = {boost}")
