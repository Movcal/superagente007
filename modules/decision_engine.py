import json
import os
from datetime import datetime
from dotenv import load_dotenv
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from modules.sentiment_analyzer import analyze as analyze_sentiment
from modules.news_analyzer import get_market_bias
from modules.market_intelligence import get_narrative_boost, get_narrative_confirmation

load_dotenv()

CAPITAL_TOTAL = float(os.getenv("CAPITAL_TOTAL", 100))
CAPITAL_POR_POSICION = float(os.getenv("CAPITAL_POR_POSICION", 50))
MAX_POSICIONES = int(os.getenv("MAX_POSICIONES", 2))
POSITIONS_FILE = "data/open_positions.json"
DECISIONS_LOG = "logs/decisions.log"


def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [DECISION] {msg}"
    print(line)
    with open(DECISIONS_LOG, "a") as f:
        f.write(line + "\n")


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return []


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def get_available_capital():
    """Calcula el capital disponible segun posiciones abiertas."""
    positions = load_positions()
    capital_usado = sum(p.get("capital", 0) for p in positions)
    return max(0, CAPITAL_TOTAL - capital_usado)


def calculate_position_size(volume_ratio, sentiment_score, is_priority, symbol=""):
    """
    El agente decide cuanto capital usar segun la calidad de la oportunidad.
    - Oportunidad fuerte: hasta CAPITAL_POR_POSICION
    - Oportunidad media: 50% de CAPITAL_POR_POSICION
    - Oportunidad debil: 25% de CAPITAL_POR_POSICION
    """
    available = get_available_capital()
    if available <= 0:
        return 0

    # Score de oportunidad (0 a 1)
    volume_score = min(1.0, (volume_ratio - 5) / 10 + 0.5)  # 5x = 0.5, 10x = 1.0
    sentiment_normalized = (sentiment_score + 1) / 2  # -1..1 -> 0..1
    opportunity_score = (volume_score * 0.6) + (sentiment_normalized * 0.4)

    if is_priority:
        opportunity_score = min(1.0, opportunity_score + 0.1)

    # Boost por narrativa acumulada (market intelligence)
    if symbol:
        try:
            narrative_boost = get_narrative_boost(symbol)
            if narrative_boost > 0:
                opportunity_score = min(1.0, opportunity_score + narrative_boost)
        except Exception:
            pass  # no bloquear la decision si market_intelligence falla

    # Tamano de posicion
    if opportunity_score >= 0.7:
        size = CAPITAL_POR_POSICION
    elif opportunity_score >= 0.5:
        size = CAPITAL_POR_POSICION * 0.5
    else:
        size = CAPITAL_POR_POSICION * 0.25

    return round(min(size, available), 2)


def estimate_hold_time(volume_ratio, sentiment_score, narrative):
    """Estima cuanto tiempo mantener la posicion."""
    if volume_ratio >= 10 and sentiment_score >= 0.4:
        hours_min, hours_max = 4, 12
        reason = "señal muy fuerte, movimiento rapido esperado"
    elif volume_ratio >= 7 or sentiment_score >= 0.3:
        hours_min, hours_max = 2, 6
        reason = "señal moderada-fuerte"
    else:
        hours_min, hours_max = 1, 4
        reason = "señal moderada, monitorear de cerca"

    # Ajuste por narrativa
    if narrative in ["meme"]:
        hours_min = max(1, hours_min // 2)
        hours_max = hours_max // 2
        reason += " (meme: salida rapida)"
    elif narrative in ["defi", "bnb_ecosistema"]:
        hours_max = int(hours_max * 1.5)
        reason += " (narrativa solida, puede durar mas)"

    return hours_min, hours_max, reason


def generate_reasoning(symbol, volume_alert, sentiment_result, capital, hold_min, hold_max, hold_reason, narrative_conf=None):
    """Genera el texto de razonamiento del agente."""
    pd = sentiment_result.get("price_data", {}) or {}
    change_1h = pd.get("change_1h", 0)
    change_24h = pd.get("change_24h", 0)
    price = pd.get("price", 0)
    in_trending = sentiment_result.get("in_trending", False)
    narrative = sentiment_result.get("narrative", "general")
    is_priority = sentiment_result.get("is_priority", False)

    lines = [
        f"ENTRADA en {symbol} | ${capital:.2f} USDT",
        f"",
        f"SEÑALES DE ENTRADA:",
        f"  Volumen: {volume_alert['ratio']}x su promedio (threshold: 5x) — confirmado",
        f"  Sentimiento: {sentiment_result['sentiment']} (score: {sentiment_result['score']})",
        f"  Precio actual: ${price:.4f} | 1h: {change_1h:+.2f}% | 24h: {change_24h:+.2f}%",
        f"  Narrativa: {narrative}",
        f"  En trending CMC: {'Si' if in_trending else 'No'}",
    ]

    if is_priority:
        lines.append(f"  Token prioritario del ecosistema BNB: Si")

    # Confirmacion narrativa pre-spike
    if narrative_conf:
        strength = narrative_conf.get("strength", "ninguna")
        confirmed = narrative_conf.get("confirmed", False)
        bull_score = narrative_conf.get("bull_score", 0)
        pos_days = narrative_conf.get("positive_days", 0)
        if confirmed:
            lines.append(f"")
            lines.append(f"DOBLE CONFIRMACION NARRATIVA + VOLUMEN:")
            lines.append(f"  {narrative_conf['message']}")
        else:
            lines.append(f"")
            lines.append(f"ADVERTENCIA NARRATIVA: {narrative_conf['message']}")

    lines += [
        f"",
        f"PERIODO ESTIMADO: {hold_min}-{hold_max} horas ({hold_reason})",
        f"",
        f"CONDICIONES DE SALIDA:",
        f"  - Precio sube +15% desde entrada (toma de ganancias)",
        f"  - Precio baja -8% desde entrada (stop loss)",
        f"  - Volumen vuelve a promedio (señal agotada)",
        f"  - BTC cae mas de 3% (proteccion macro)",
        f"  - Tiempo maximo: {hold_max} horas sin importar el precio",
    ]

    return "\n".join(lines)


def evaluate(volume_alert, path="B"):
    """
    Evalua si entrar en un trade dado una alerta de volumen.
    path: "A" = sentimiento primero, "B" = volumen primero
    Retorna: decision dict o None si no se debe entrar.
    """
    symbol = volume_alert["symbol"]
    volume_ratio = volume_alert["ratio"]

    log(f"Evaluando {symbol} (volumen: {volume_ratio}x, camino: {path})")

    # Verificar si ya tenemos posicion en este token
    positions = load_positions()
    if any(p["symbol"] == symbol for p in positions):
        log(f"{symbol} ya tiene posicion abierta, ignorando")
        return None

    # Verificar limite de posiciones
    if len(positions) >= MAX_POSICIONES:
        log(f"Maximo de posiciones alcanzado ({MAX_POSICIONES}), ignorando {symbol}")
        return None

    # Analizar sentimiento (se pasa volume_ratio para que el spike sea señal anticipada)
    sentiment = analyze_sentiment(symbol, volume_ratio=volume_ratio)

    # REGLA PRINCIPAL: doble confirmacion obligatoria
    # Volumen confirmado (ya lo tenemos por la alerta)
    # Sentimiento debe ser POSITIVO — excepto en breaking news BULLISH_ALTO
    is_breaking = volume_alert.get("breaking_news", False)
    if sentiment["sentiment"] != "POSITIVO" and not is_breaking:
        log(f"{symbol} rechazado: sentimiento {sentiment['sentiment']}, se necesita POSITIVO")
        return None
    if is_breaking and sentiment["sentiment"] != "POSITIVO":
        log(f"{symbol} [BREAKING] override de sentimiento: noticia alto impacto, entrando aunque precio aun no confirma")

    # Confirmacion narrativa pre-spike: el volumen confirma lo que las noticias ya anunciaban
    narrative_conf = get_narrative_confirmation(symbol)
    if narrative_conf["confirmed"]:
        log(f"{symbol} DOBLE CONFIRMACION: volumen {volume_ratio}x + narrativa {narrative_conf['strength'].upper()} "
            f"({narrative_conf['bull_score']}% bullish, {narrative_conf['positive_days']} dias)")
    else:
        log(f"{symbol} narrativa: {narrative_conf['strength']} ({narrative_conf['bull_score']}% bullish) — "
            f"spike sin respaldo previo de noticias")

    # Analisis de noticias y KOLs via Claude
    # Si CLAUDE_ENABLED=false -> market_bias=None y este bloque no hace nada
    market_bias = get_market_bias(symbol)
    if market_bias:
        if market_bias["action_modifier"] == "SKIP":
            log(f"{symbol} rechazado por Claude: {market_bias['reason']}")
            return None
        if market_bias["action_modifier"] == "REDUCE_SIZE":
            log(f"{symbol} capital reducido por Claude: {market_bias['reason']}")
            # Se aplica el 50% de reduccion despues de calculate_position_size

    # Calcular capital
    capital = calculate_position_size(volume_ratio, sentiment["score"], sentiment["is_priority"], symbol)
    if capital <= 0:
        log(f"{symbol} rechazado: sin capital disponible")
        return None

    # Aplicar reduccion de Claude si corresponde
    if market_bias and market_bias["action_modifier"] == "REDUCE_SIZE":
        capital = round(capital * 0.5, 2)
        log(f"{symbol} capital ajustado a ${capital} (50% por señal de cautela de Claude)")

    # Estimar tiempo de hold
    hold_min, hold_max, hold_reason = estimate_hold_time(
        volume_ratio, sentiment["score"], sentiment["narrative"]
    )

    # Generar razonamiento
    reasoning = generate_reasoning(
        symbol, volume_alert, sentiment, capital, hold_min, hold_max, hold_reason,
        narrative_conf=narrative_conf
    )

    decision = {
        "action": "BUY",
        "symbol": symbol,
        "capital": capital,
        "entry_time": datetime.utcnow().isoformat(),
        "hold_min_hours": hold_min,
        "hold_max_hours": hold_max,
        "volume_ratio": volume_ratio,
        "sentiment": sentiment["sentiment"],
        "sentiment_score": sentiment["score"],
        "narrative": sentiment["narrative"],
        "is_priority": sentiment["is_priority"],
        "reasoning": reasoning,
        "path": path
    }

    log(f"DECISION: COMPRAR {symbol} con ${capital} | Hold: {hold_min}-{hold_max}h")
    log(f"\n{reasoning}\n")

    return decision


if __name__ == "__main__":
    # Prueba simulando una alerta de volumen en CAKE
    fake_alert = {
        "symbol": "CAKE",
        "ratio": 6.5,
        "current_volume": 15000000,
        "avg_volume": 2300000,
        "timestamp": datetime.utcnow().isoformat(),
        "priority": True
    }

    print("=== Prueba del Motor de Decision ===\n")
    decision = evaluate(fake_alert, path="B")

    if decision:
        print("\n--- DECISION TOMADA ---")
        print(decision["reasoning"])
    else:
        print("\n--- NO SE ENTRA ---")
        print("El agente decidio no entrar en este trade.")
