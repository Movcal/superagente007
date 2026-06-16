import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
CMC_MCP_URL = "https://pro-api.coinmarketcap.com/v1"

# Tokens del ecosistema BNB prioritarios
PRIORITY_TOKENS = ["BNB", "CAKE", "ASTER", "FLOKI"]

# Categorias de narrativa por token
NARRATIVES = {
    "privacidad": ["ZEC", "ROSE", "AXL"],
    "ia": ["FET", "SKYAI", "COAI", "AIOZ", "UAI", "0G", "PEAQ"],
    "defi": ["AAVE", "UNI", "CAKE", "SUSHI", "COMP", "PENDLE", "STG", "1INCH"],
    "meme": ["BONK", "FLOKI", "CHEEMS", "BANANAS31", "BabyDoge", "DOGE", "SHIB"],
    "bnb_ecosistema": ["BNB", "CAKE", "ASTER", "FLOKI"],
}


def get_cmc_headers():
    return {"X-CMC_PRO_API_KEY": CMC_API_KEY}


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [SENTIMENT] {msg}"
    print(line)
    with open("logs/sentiment_analyzer.log", "a") as f:
        f.write(line + "\n")


def get_token_narrative(symbol):
    """Devuelve la narrativa/categoria del token."""
    for narrative, tokens in NARRATIVES.items():
        if symbol in tokens:
            return narrative
    return "general"


def fetch_price_data(symbol):
    """
    Consulta precio, cambio 24h, cambio 1h y volumen del token.
    Retorna dict con los datos o None si falla.
    """
    url = f"{CMC_MCP_URL}/cryptocurrency/quotes/latest"
    try:
        r = requests.get(
            url,
            headers=get_cmc_headers(),
            params={"symbol": symbol, "convert": "USD"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            token_data = data.get(symbol)
            if isinstance(token_data, list):
                token_data = token_data[0]
            if token_data:
                quote = token_data.get("quote", {}).get("USD", {})
                return {
                    "price": quote.get("price", 0),
                    "change_1h": quote.get("percent_change_1h", 0),
                    "change_24h": quote.get("percent_change_24h", 0),
                    "change_7d": quote.get("percent_change_7d", 0),
                    "volume_24h": quote.get("volume_24h", 0),
                    "market_cap": quote.get("market_cap", 0),
                }
    except Exception as e:
        log(f"Error obteniendo precio de {symbol}: {e}")
    return None


def fetch_trending():
    """Obtiene los tokens mas visitados/trending en CMC ahora mismo."""
    url = f"{CMC_MCP_URL}/cryptocurrency/trending/most-visited"
    try:
        r = requests.get(
            url,
            headers=get_cmc_headers(),
            params={"limit": 20, "convert": "USD"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            return [item.get("symbol") for item in data]
    except Exception as e:
        log(f"Error obteniendo trending: {e}")
    return []


def fetch_fear_greed():
    """Obtiene el Fear & Greed Index actual."""
    url = f"{CMC_MCP_URL}/fear-and-greed/latest"
    try:
        r = requests.get(url, headers=get_cmc_headers(), timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            return {
                "value": data.get("value", 50),
                "classification": data.get("value_classification", "Neutral")
            }
    except Exception as e:
        log(f"Error obteniendo Fear & Greed: {e}")
    return {"value": 50, "classification": "Neutral"}


def fetch_token_info(symbol):
    """Obtiene metadata basica del token: descripcion, categoria, links."""
    url = f"{CMC_MCP_URL}/cryptocurrency/info"
    try:
        r = requests.get(
            url,
            headers=get_cmc_headers(),
            params={"symbol": symbol},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            token_data = list(data.values())[0] if data else {}
            return {
                "name": token_data.get("name", symbol),
                "category": token_data.get("category", ""),
                "description": token_data.get("description", "")[:300],
                "tags": token_data.get("tags", [])[:5],
            }
    except Exception as e:
        log(f"Error obteniendo info de {symbol}: {e}")
    return {}


def score_price_sentiment(price_data, symbol, trending_list, volume_ratio=1.0):
    """
    Calcula score de sentimiento basado en:
    - Cambio de precio 1h y 24h
    - Si el token esta en trending
    - Spike de volumen (señal anticipada — el volumen precede al precio)
    Retorna: score (-1.0 a 1.0), razon
    """
    if not price_data:
        return 0.0, "Sin datos de precio disponibles"

    score = 0.0
    reasons = []

    change_1h = price_data.get("change_1h", 0)
    change_24h = price_data.get("change_24h", 0)
    change_7d = price_data.get("change_7d", 0)

    # Score por cambio 1h (peso alto — señal reciente)
    if change_1h >= 5:
        score += 0.4
        reasons.append(f"+{change_1h:.1f}% en 1h (fuerte alza)")
    elif change_1h >= 2:
        score += 0.2
        reasons.append(f"+{change_1h:.1f}% en 1h (alza moderada)")
    elif change_1h <= -5:
        score -= 0.4
        reasons.append(f"{change_1h:.1f}% en 1h (fuerte caida)")
    elif change_1h <= -2:
        score -= 0.2
        reasons.append(f"{change_1h:.1f}% en 1h (caida moderada)")

    # Score por cambio 24h (peso medio)
    if change_24h >= 10:
        score += 0.3
        reasons.append(f"+{change_24h:.1f}% en 24h")
    elif change_24h >= 5:
        score += 0.15
        reasons.append(f"+{change_24h:.1f}% en 24h")
    elif change_24h <= -10:
        score -= 0.3
        reasons.append(f"{change_24h:.1f}% en 24h")
    elif change_24h <= -5:
        score -= 0.15
        reasons.append(f"{change_24h:.1f}% en 24h")

    # Score por tendencia 7d (peso bajo — contexto)
    if change_7d >= 20:
        score += 0.1
        reasons.append(f"+{change_7d:.1f}% en 7d (tendencia alcista)")
    elif change_7d <= -20:
        score -= 0.1
        reasons.append(f"{change_7d:.1f}% en 7d (tendencia bajista)")

    # Bonus si esta en trending
    if symbol in trending_list:
        score += 0.15
        reasons.append("en trending CMC ahora mismo")

    # Bonus por spike de volumen (el volumen precede al precio — señal anticipada)
    if volume_ratio >= 20:
        score += 0.35
        reasons.append(f"volumen {volume_ratio:.0f}x (spike extremo)")
    elif volume_ratio >= 10:
        score += 0.25
        reasons.append(f"volumen {volume_ratio:.0f}x (spike alto)")
    elif volume_ratio >= 5:
        score += 0.15
        reasons.append(f"volumen {volume_ratio:.1f}x (spike detectado)")

    reason = " | ".join(reasons) if reasons else "Movimiento de precio neutral"
    return round(max(-1.0, min(1.0, score)), 2), reason


def analyze(symbol, volume_ratio=1.0):
    """
    Analisis completo de sentimiento para un token.
    Retorna dict con: sentiment (POSITIVO/NEGATIVO/NEUTRO), score, razon, datos de contexto.
    volume_ratio: ratio de volumen detectado (el volumen precede al precio, es señal anticipada).
    """
    log(f"Analizando sentimiento de {symbol}...")

    # 1. Precio y cambios
    price_data = fetch_price_data(symbol)

    # 2. Trending
    trending_list = fetch_trending()
    in_trending = symbol in trending_list

    # 3. Score de precio + volumen
    price_score, price_reason = score_price_sentiment(price_data, symbol, trending_list, volume_ratio)

    # 4. Info del token
    token_info = fetch_token_info(symbol)
    narrative = get_token_narrative(symbol)
    is_priority = symbol in PRIORITY_TOKENS

    # Score final — solo precio, volumen y trending (sin modificador macro F&G)
    final_score = round(max(-1.0, min(1.0, price_score)), 2)

    # Clasificacion
    if final_score >= 0.2:
        sentiment = "POSITIVO"
    elif final_score <= -0.2:
        sentiment = "NEGATIVO"
    else:
        sentiment = "NEUTRO"

    result = {
        "symbol": symbol,
        "sentiment": sentiment,
        "score": final_score,
        "price_score": price_score,
        "price_reason": price_reason,
        "in_trending": in_trending,
        "narrative": narrative,
        "is_priority": is_priority,
        "token_name": token_info.get("name", symbol),
        "tags": token_info.get("tags", []),
        "price_data": price_data,
        "timestamp": datetime.utcnow().isoformat()
    }

    log(f"{symbol} -> {sentiment} (score: {final_score}) | {price_reason}")
    return result


if __name__ == "__main__":
    # Prueba con algunos tokens
    test_tokens = ["BNB", "CAKE", "ZEC", "FET"]
    for token in test_tokens:
        result = analyze(token)
        print(f"\n{'='*50}")
        print(f"Token: {result['symbol']} ({result['token_name']})")
        print(f"Sentimiento: {result['sentiment']} (score: {result['score']})")
        print(f"Fear & Greed: {result['fear_greed']} ({result['fear_greed_value']})")
        print(f"Narrativa: {result['narrative']}")
        print(f"Razon: {result['price_reason']}")
        if result.get('price_data'):
            pd = result['price_data']
            print(f"Precio: ${pd['price']:.4f} | 1h: {pd['change_1h']:.2f}% | 24h: {pd['change_24h']:.2f}%")
        print(f"En trending: {result['in_trending']}")
        print(f"{'='*50}")
