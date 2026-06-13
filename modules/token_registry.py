import requests
import json
import os
import sys
import pathlib
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
CONTRACTS_FILE = "data/token_contracts.json"

# Contratos conocidos en BSC (hardcoded para los mas importantes)
KNOWN_CONTRACTS = {
    "USDT":  "0x55d398326f99059fF775485246999027B3197955",
    "USDC":  "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "BNB":   "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
    "CAKE":  "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "ETH":   "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BUSD":  "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "DAI":   "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
    "DOGE":  "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
    "ADA":   "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47",
    "XRP":   "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE",
    "DOT":   "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402",
    "LINK":  "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    "UNI":   "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    "ATOM":  "0x0Eb3a705fc54725037CC9e008bDede697f62F335",
    "LTC":   "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94",
    "AVAX":  "0x1CE0c2827e2eF14D5C4f29a091d735A204794041",
    "SHIB":  "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D",
    "MATIC": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD",
    "TRX":   "0xCE7de646e7208a4Ef112cb6ed5038FA6cC6b12e3",
    "FIL":   "0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153",
    "ETC":   "0x3d6545b08693daE087E957cb1180ee38B9e3c25E",
    "AAVE":  "0xfb6115445Bff7b52FeB98650C87f44907E58f802",
    "SUSHI": "0x947950BcC74888a40Ffa2593C5798F11Fc9124C",
    "COMP":  "0x52CE071Bd9b1C4B00A0b92D298c512478CaD67e8",
    "FLOKI": "0xfb5B838b6cfEEdC2873aB27866079AC55363D37A",
    "BONK":  "0xA697e272a73744b343528C3Bc4702F2565b2F422",
    "FET":   "0x031b41e504677879370e9DBcF937283A8691Fa7f",
    "PENDLE":"0xb3Ed0A426155B79B898849803E3B36552f7ED507",
    "ZEC":   "0x1Ba42e5193dfA8B03D15dd1B86a3113bbBEF8Eeb",
    "ROSE":  "0x0b7958F8190De6D6B4b83C7a5EF0aA98A6df6Fd",
    "AXL":   "0x8b1f4432F943c465A973FeDC6d7aa50Fc96f1f65",
    "AIOZ":  "0x33f289d91286535c47270C8479f6776Fb3Bc84E3",
    "PEAQ":  "0x02f4A3A00e2a8B47fD5513e4B389c8c280DCe34B",
    "STG":   "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
    "ZIG":   "0x0f5d854B9b878CA6391C4D8a5F2c7d8E49E8F636",
    "LUNC":  "0x156ab3346823B651294766e23e6Cf87254d68962",
    "TWT":   "0x4B0F1812e5Df2A09796481Ff14017e6005508003",
    "1INCH": "0x111111111117dC0aa78b770fA6A738034120C302",
    "KAVA":  "0x5F88AB06e8dfe89DF127B2430Bba4Af600866035",
    "ZIL":   "0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787",
    "DUSK":  "0xB2BD0749DBE21f623d9BABa856D3B0f0e1BFEc9C",
    "ACH":   "0xBC7d6B50616989655AfD682fb42743507003056D",
    "ELF":   "0xa3F020a5C92e15Be13CAF0Ee5C95cF79585EeCC9",
    "BAT":   "0x101d82428437127bF1608F699CD651e6Abf9766A",
    "INJ":   "0xa2B726B1145A4773F68593CF171187d8EBe4d495",
    "YFI":   "0x88f1A5ae2A3BF98AEAF342D26B30a79438c9142e",
    "SNX":   "0x9Ac983826058b8a9C7Aa1C9171441191232E8404",
    "APE":   "0xC762043E211571eB34f1ef377e5e8e76914962f9",
    "BCH":   "0x8fF795a6F4D97E7887C79beA79aba5cc76444aDf",
    "LDO":   "0x986854779804799C1d68867F5E03e601E781e41b",
    "FDUSD": "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409",
    "TUSD":  "0x14016E85a25aeb13065688cAFB43044C2ef86784",
    "BTT":   "0x352Cb5E19b12FC216548a2677bD0fce83BaE434B",
    "FRAX":  "0x90C97F71E18723b0Cf0dfa30ee176Ab653E89F40",
}

def get_contract(symbol):
    """Retorna el contrato BSC de un token. Busca en cache primero, luego en CMC."""
    # 1. Buscar en conocidos hardcoded
    if symbol in KNOWN_CONTRACTS:
        return KNOWN_CONTRACTS[symbol]

    # 2. Buscar en cache local
    cache = load_cache()
    if symbol in cache:
        return cache[symbol]

    # 3. Buscar en CMC
    contract = fetch_from_cmc(symbol)
    if contract:
        cache[symbol] = contract
        save_cache(cache)
        return contract

    return None


def fetch_from_cmc(symbol):
    """Busca el contrato BSC de un token en CMC."""
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/info"
    try:
        r = requests.get(
            url,
            headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
            params={"symbol": symbol},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            token_data = list(data.values())[0] if data else {}
            platforms = token_data.get("platform", {})
            # Buscar en plataformas BSC
            contract_map = token_data.get("contract_address", [])
            for entry in contract_map:
                platform = entry.get("platform", {})
                if platform.get("slug") in ["bnb-smart-chain", "binance-smart-chain", "bsc"]:
                    return entry.get("contract_address")
            # Fallback: si el token vive en BSC como plataforma principal
            if platforms and platforms.get("slug") in ["bnb-smart-chain", "binance-smart-chain"]:
                return platforms.get("token_address")
    except Exception as e:
        print(f"Error buscando contrato de {symbol} en CMC: {e}")
    return None


def load_cache():
    if os.path.exists(CONTRACTS_FILE):
        with open(CONTRACTS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CONTRACTS_FILE, "w") as f:
        json.dump(cache, f, indent=2)


if __name__ == "__main__":
    test_tokens = ["CAKE", "BNB", "FET", "ASTER", "BONK"]
    print("=== Verificando contratos BSC ===\n")
    for symbol in test_tokens:
        contract = get_contract(symbol)
        if contract:
            print(f"{symbol}: {contract}")
        else:
            print(f"{symbol}: NO ENCONTRADO")
