"""
Paso 1: Recolecta info cruda de CMC + CoinGecko para los 86 tokens tradeables.
Guarda en data/token_raw_info.json para procesamiento posterior con Claude.
"""
import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
CMC_API_KEY = os.getenv("CMC_API_KEY")

TOKENS = [
    "ETH","XRP","TRX","DOGE","ZEC","ADA","LINK","BCH","TON","LTC",
    "AVAX","SHIB","WLFI","DOT","UNI","ASTER","DEXE","ETC","AAVE","ATOM",
    "FIL","INJ","FET","BONK","PENGU","CAKE","SIREN","LUNC","ZRO","BTT",
    "FLOKI","PENDLE","AXS","TWT","HOME","COMP","XCN","GENIUS","XPL","SKYAI",
    "APE","SFP","TAG","AB","SAHARA","CHEEMS","BANANAS31","RIVER","MYX","FORM",
    "LAB","HTX","UB","DUCKY","WFI","KOGE","ALE","GOMINING","0G","BEAM",
    "MY","SOON","AIOZ","ZIG","TAC","HUMA","ZIL","VELO","BRETT","OPEN",
    "BSB","TOSHI","BAS","ACH","KAVA","IRYS","DUSK","SUSHI","PEAQ","COAI",
    "BDCA","BNB","Q","FF","B","BabyDoge",
]

OUTPUT_FILE = "data/token_raw_info.json"


def parse_cmc_info(info):
    """Extrae campos utiles de un objeto de info CMC."""
    if not info or not isinstance(info, dict):
        return None
    return {
        "name":        info.get("name", ""),
        "category":    info.get("category", ""),
        "description": info.get("description", "")[:500],
        "tags":        info.get("tags", [])[:10],
        "urls": {
            "website": (info.get("urls", {}).get("website") or [""])[:1],
            "twitter": (info.get("urls", {}).get("twitter") or [""])[:1],
        }
    }


def fetch_cmc_single(symbol):
    """Consulta CMC para un solo simbolo. Si hay multiples, toma el de mayor market cap."""
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/info",
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": symbol},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            info = data.get(symbol)
            if isinstance(info, list):
                # Multiples tokens con mismo simbolo: tomar el de mayor rank CMC (menor numero = mas grande)
                info = sorted(info, key=lambda x: x.get("rank") or 9999)[0]
            return parse_cmc_info(info)
    except Exception:
        pass
    return None


def fetch_cmc_batch(symbols):
    """Trae nombre, descripcion, tags, categoria, urls de CMC para un batch."""
    results = {}
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/info",
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": ",".join(symbols)},
            timeout=20
        )
        if r.status_code == 200:
            for sym, info in r.json().get("data", {}).items():
                if isinstance(info, list):
                    info = info[0]
                parsed = parse_cmc_info(info)
                if parsed:
                    results[sym] = parsed
        else:
            print(f"  CMC error {r.status_code}")
    except Exception as e:
        print(f"  CMC batch exception: {e}")
    return results


def fetch_coingecko(symbol):
    """Busca el token en CoinGecko y trae descripcion + categorias."""
    try:
        # Primero buscar el ID
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": symbol},
            timeout=15
        )
        if r.status_code != 200:
            return None
        coins = r.json().get("coins", [])
        if not coins:
            return None

        # Tomar el primer resultado con simbolo exacto
        match = None
        for coin in coins[:5]:
            if coin.get("symbol", "").upper() == symbol.upper():
                match = coin
                break
        if not match:
            match = coins[0]

        cg_id = match.get("id")
        if not cg_id:
            return None

        # Traer detalle
        r2 = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}",
            params={"localization": "false", "tickers": "false",
                    "market_data": "false", "community_data": "false",
                    "developer_data": "false"},
            timeout=15
        )
        if r2.status_code != 200:
            return None

        data = r2.json()
        desc = data.get("description", {}).get("en", "")[:400]
        categories = data.get("categories", [])[:5]
        return {
            "cg_id":       cg_id,
            "description": desc,
            "categories":  categories,
        }
    except Exception as e:
        return None


def main():
    print(f"Recolectando info para {len(TOKENS)} tokens...\n")
    raw = {}

    # ── CMC: batch primero, luego individual para los que fallen ─────────────
    print("=== CMC API ===")
    # Inicializar todos
    for sym in TOKENS:
        raw[sym] = {"symbol": sym, "cmc": None, "coingecko": None}

    # Batch
    batch_size = 50
    for i in range(0, len(TOKENS), batch_size):
        batch = TOKENS[i:i + batch_size]
        print(f"Batch CMC {i+1}-{i+len(batch)}...")
        cmc_data = fetch_cmc_batch(batch)
        for sym in batch:
            if cmc_data.get(sym):
                raw[sym]["cmc"] = cmc_data[sym]
        time.sleep(1)

    # Consulta individual para los que fallaron en el batch
    failed = [sym for sym in TOKENS if not raw[sym]["cmc"]]
    print(f"\nConsulta individual para {len(failed)} tokens sin datos...")
    for sym in failed:
        result = fetch_cmc_single(sym)
        if result:
            raw[sym]["cmc"] = result
            name = result.get('name','').encode('ascii','replace').decode()
            print(f"  {sym}: {name} | tags: {result.get('tags',[])[:3]}")
        else:
            print(f"  {sym}: sin datos CMC")
        time.sleep(0.5)

    found = sum(1 for v in raw.values() if v["cmc"])
    print(f"\nCMC: {found}/{len(TOKENS)} tokens con datos")

    # ── CoinGecko: token por token (rate limit: 10-30 req/min sin key) ────────
    print("\n=== CoinGecko API ===")
    for i, sym in enumerate(TOKENS):
        print(f"[{i+1}/{len(TOKENS)}] {sym}...", end=" ")
        cg = fetch_coingecko(sym)
        if cg:
            raw[sym]["coingecko"] = cg
            cats = str(cg.get('categories', [])).encode('ascii','replace').decode()
            print(f"OK | cats: {cats}")
        else:
            print("sin datos")
        time.sleep(2.5)  # respetar rate limit de CoinGecko free tier

    # Guardar
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)

    found_cmc = sum(1 for v in raw.values() if v.get("cmc"))
    found_cg  = sum(1 for v in raw.values() if v.get("coingecko"))
    print(f"\nGuardado en {OUTPUT_FILE}")
    print(f"CMC: {found_cmc}/{len(TOKENS)} | CoinGecko: {found_cg}/{len(TOKENS)}")


if __name__ == "__main__":
    main()
