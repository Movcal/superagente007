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

# Contratos BSC verificados contra PancakeSwap (fuente primaria) y CMC
# Actualizados: 2026-06-16 | Cubiertos: 137/149 tokens de la competencia
# Pendientes sin contrato BSC confirmado: TON, WLFI, LAB, HTX, CTM, BEAM, REAL, BRETT, APR
KNOWN_CONTRACTS = {
    # ── Wrappers / nativos ────────────────────────────────────────────────────
    "BNB":       "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "WBNB":      "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",

    # ── Stablecoins ───────────────────────────────────────────────────────────
    "USDT":      "0x55d398326f99059fF775485246999027B3197955",
    "USDC":      "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "DAI":       "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3",
    "BUSD":      "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    "TUSD":      "0x40af3827F39D0EAcBF4A168f8D4ee67c121D11c9",
    "FDUSD":     "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409",
    "FRAX":      "0x90C97F71E18723b0Cf0dfa30ee176Ab653E89F40",
    "FRXUSD":    "0x80Eede496655FB9047dd39d9f418d5483ED600df",
    "USDD":      "0x45E51bc23D592EB2DBA86da3985299f7895d66Ba",
    "USD1":      "0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d",
    "USDe":      "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",
    "USDf":      "0xb3b02E4A9Fb2bD28CC2ff97B0aB3F6B3Ec1eE9D2",
    "USDF":      "0xb3b02E4A9Fb2bD28CC2ff97B0aB3F6B3Ec1eE9D2",
    "DUSD":      "0xaf44A1E76F56eE12ADBB7ba8acD3CbD474888122",
    "XUSD":      "0xF81aC2E1A0373ddE1BcE01E2Fe694a9b7E3bfcB9",
    "EURI":      "0x9d1a7a3191102e9f900faa10540837ba84dcbae7",
    "lisUSD":    "0x0782b6d8c4551B9760e74c0545a9bCD90bdc41E5",
    "STABLE":    "0x011EBe7d75E2C9D1E0bD0be0bEf5C36f0A90075F",

    # ── Layer 1s ──────────────────────────────────────────────────────────────
    "ETH":       "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BTC":       "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    "XRP":       "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE",
    "TRX":       "0xCE7de646e7208a4Ef112cb6ed5038FA6cC6b12e3",
    "DOGE":      "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
    "ZEC":       "0x1Ba42e5193dfA8B03D15dd1B86a3113bbBEF8Eeb",
    "ADA":       "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47",
    "BCH":       "0x8fF795a6F4D97E7887C79beA79aba5cc76444aDf",
    "LTC":       "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94",
    "AVAX":      "0x1CE0c2827e2eF14D5C4f29a091d735A204794041",
    "DOT":       "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402",
    "ETC":       "0x3d6545b08693daE087E957cb1180ee38B9e3c25E",
    "ATOM":      "0x0Eb3a705fc54725037CC9e008bDede697f62F335",
    "FIL":       "0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153",
    "ZIL":       "0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787",
    "KAVA":      "0x9BAFC8d4b487cEBff201721702507a3E2C67ad79",
    "ROSE":      "0xF00600eBC7633462BC4F9C61eA2cE99F5AAEBd4a",
    "ZETA":      "0x0000028a2eB8346cd5c0267856aB7594B7a55308",
    "XPR":       "0x5de3939b2f811a61d830e6f52d13b066881412ab",
    "ZIG":       "0x8C907e0a72C3d55627E853f4ec6a96b0C8771145",
    "PLUME":     "0x5aFadCd1E8E3CA78Ee2D37100102f2aec8Bc0Aa8",
    "ZIL":       "0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787",

    # ── DeFi ──────────────────────────────────────────────────────────────────
    "CAKE":      "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "LINK":      "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    "UNI":       "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    "AAVE":      "0xfb6115445Bff7b52FeB98650C87f44907E58f802",
    "COMP":      "0x52CE071Bd9b1C4B00A0b92D298c512478CaD67e8",
    "SUSHI":     "0x947950BcC74888a40Ffa2593C5798F11Fc9124C4",
    "SNX":       "0x9Ac983826058b8a9C7Aa1C9171441191232E8404",
    "YFI":       "0x88f1A5ae2A3BF98AEAF342D26B30a79438c9142e",
    "1INCH":     "0x111111111117dc0aa78b770fa6a738034120c302",
    "STG":       "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
    "PENDLE":    "0xb3Ed0A426155B79B898849803E3B36552f7ED507",
    "LDO":       "0x986854779804799C1d68867F5E03e601E781e41b",
    "DEXE":      "0x6E88056E8376Ae7709496Ba64d37fa2f8015ce3e",
    "AXS":       "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0",
    "LUNC":      "0x156ab3346823B651294766e23e6Cf87254d68962",
    "ZRO":       "0x6985884C4392D348587B19cb9eAAf157F13271cd",
    "INJ":       "0xa2B726B1145A4773F68593CF171187d8EBe4d495",
    "FET":       "0x031b41e504677879370e9DBcF937283A8691Fa7f",
    "PEAQ":      "0x8b9Ee39195eA99d6ddD68030F44131116bc218F6",
    "MYX":       "0xD82544bf0dfe8385eF8FA34D67e6e4940CC63e16",
    "WFI":       "0x90c48855bb69f9d2c261efd0d8c7f35990f2dd6f",
    "KOGE":      "0xe6DF05CE8C8301223373CF5B969AFCb1498c5528",
    "ALE":       "0x9dCE13E71B11eb5Df66ca269bD657696587Fd4E2",
    "HUMA":      "0x92516e0DDf1dDBF7FAB1b79CaC26689fDC5ba8e6",
    "FORM":      "0x5b73A93b4E5e4f1FD27D8b3F8C97D69908b5E284",

    # ── BNB Ecosystem ─────────────────────────────────────────────────────────
    "TWT":       "0x4B0F1812e5Df2A09796481Ff14017e6005508003",
    "SFP":       "0xD41FDb03Ba84762dD66a0af1a6C8540FF1ba5dfb",
    "ASTER":     "0x000Ae314E2A2172a039B26378814C252734f556A",
    "FLOKI":     "0xfb5B838b6cfEEdC2873aB27866079AC55363D37E",
    "BONK":      "0xA697e272a73744b343528C3Bc4702F2565b2F422",
    "BTT":       "0x352Cb5E19b12FC216548a2677bD0fce83BaE434B",
    "NFT":       "0x20eE7B720f4E4c4FFcB00C4065cdae55271aECCa",
    "SHIB":      "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D",
    "BabyDoge":  "0xc748673057861a797275CD8A068AbB95A902e8de",
    "CHEEMS":    "0x0DF0587216a4a1bB7d5082fdc491d93d2dD4B413",
    "BANANAS31": "0x3d4f0513e8a29669b960f9dbca61861548a9a760",

    # ── Memes / gaming / otros ────────────────────────────────────────────────
    "PENGU":     "0x6418c0dd099a9FDA397C766304CDd918233E8847",
    "APE":       "0x8f86a15EC17cb3369d8b3E666dAdBC11daA82b79",
    "RAVE":      "0x97693439EA2f0ecdeb9135881E49f354656a911c",
    "DUSK":      "0xB2BD0749DBE21f623d9BABa856D3B0f0e1BFEc9C",
    "BAT":       "0x101d82428437127bF1608F699CD651e6Abf9766E",
    "ELF":       "0xa3f020a5c92e15be13caf0ee5c95cf79585eecc9",
    "ACH":       "0xBc7d6B50616989655AfD682fb42743507003056D",
    "AXL":       "0x8b1f4432F943c465A973FeDC6d7aa50Fc96f1f65",
    "BDX":       "0x6ad12E761b438beA3EA09F6C6266556Bb24C2181",
    "AIOZ":      "0x33d08D8C7a168333a85285a68C0042b39fC3741D",
    "NILA":      "0x00f8Da33734FeB9b946fEC2228C25072D2e2E41f",
    "LUR":       "0xc66B6f38aE5053A109cfd8639E0Ee17EC69cf788",

    # ── Tokens de competencia (PancakeSwap) ───────────────────────────────────
    "XAUt":      "0x21cAef8A43163Eea865baeE23b9C2E327696A3bf",
    "H":         "0x44F161aE29361E332dEA039DFA2F404E0bC5B5Cc",
    "M":         "0x22b1458e780F8fA71E2F84502cEe8B5A3cc731Fa",
    "U":         "0xcE24439F2D9C6a2289F741120FE202248B666666",
    "NIGHT":     "0xFe930c2d63AeD9b82fC4DBC801920dD2c1a3224F",
    "SIREN":     "0x997A58129890bBdA032231A52eD1ddC845fc18e1",
    "KITE":      "0x904567252D8F48555b7447c67dCA23F0372E16be",
    "BEAT":      "0xcf3232B85b43BCa90E51D38cc06Cc8bB8C8A3E36",
    "PIEVERSE":  "0x0E63B9C287E32A05E6b9AB8ee8dF88A2760225A9",
    "EDGE":      "0x70f2EADf1CA1969FF42b0c78e9DA519e8937cbaF",
    "B":         "0x6bdcCe4A559076e37755a78Ce0c06214E59e4444",
    "FF":        "0xAC23B90A79504865D52B49B327328411a23d4dB2",
    "NEX":       "0x365DE036A1F7dcCb621530d517133521debB2013",
    "HOME":      "0x4BfAa776991E85e5f8b1255461cbbd216cFc714f",
    "RAY":       "0x13b6A55662f6591f8B8408Af1C73B017E32eEdB8",
    "GWEI":      "0x30117E4bC17d7B044194b76A38365C53b72F7D49",
    "XCN":       "0x7324c7C0d95CEBC73eEa7E85CbAac0dBdf88a05b",
    "GENIUS":    "0x1F12B85aAC097E43Aa1555b2881E98a51090e9A6",
    "XPL":       "0x405FBc9004D857903bFD6b3357792D71a50726b0",
    "SKYAI":     "0x92aa03137385F18539301349dcfC9EbC923fFb10",
    "IP":        "0x4d6394bc3031f751edce368c189b0e060b527107",
    "TAG":       "0x208bF3E7dA9639f1Eaefa2DE78c23396B0682025",
    "NXPC":      "0xf2b51CC1850fEd939658317a22d73d3482767591",
    "AB":        "0x95034f653D5D161890836Ad2B6b8cc49D14e029a",
    "SAHARA":    "0xFDFfB411C4A70AA7C95D5C981a6Fb4Da867e1111",
    "RIVER":     "0xdA7AD9dea9397cffdDAE2F8a052B82f1484252B3",
    "UB":        "0x40b8129B786D766267A7a118cF8C07E31CDB6Fde",
    "SLX":       "0x02bcC4C181B83a8c0A342BC003389CbEcb4BC54D",
    "BILL":      "0xDf24f8c21Cb404B3031a450D8e049D6E39FC1fA5",
    "GOMINING":  "0x7Ddc52c4De30e94Be3A6A0A2b259b2850f421989",
    "VCNT":      "0xc6BDFC4f2E90196738873E824a9eFa03F7c64176",
    "GUA":       "0xA5C8e1513B6A08334b479fe4D71F1253259469BE",
    "SMILEK":    "0x4f9d3AdbfAF4579518b1Ca7E06468A363897B997",
    "0G":        "0x4B948d64dE1F71fCd12fB586f4c776421a35b3eE",
    "SOON":      "0xb9E1Fd5A02D3A33b25a14d661414E6ED6954a721",
    "MY":        "0xf0ebb572643336834d516c485ad31d3299999999",
    "Q":         "0xc07e1300dc138601FA6B0b59f8D0FA477e690589",
    "TAC":       "0x1219c409faBe2C27Bd0D1A565daeed9Bd9f271dE",
    "CYS":       "0x0C69199C1562233640e0Db5Ce2c399A88eB507C7",
    "ZAMA":      "0x6907A5986C4950Bdaf2F81828Ec0737ce787519f",
    "TRIA":      "0xb0b92de23bAa85fB06208277E925ceD53edab482",
    "VELO":      "0xf486ad071f3bEE968384D2E39e2D8aF0fCf6fd46",
    "UAI":       "0x3E5d4f8aee0D9B3082d5f6DA5D6e225D17ba9ea0",
    "OPEN":      "0xA227Cc36938f0c9E09CE0e64dfab226cad739447",
    "BSB":       "0x595dEaad1eB5476Ff1E649fDb7EFC36F1E4679cc",
    "TOSHI":     "0x6a2608Dabe09bc1128EEC7275B92DFB939D5Db3f",
    "BAS":       "0x0F0df6cB17ee5E883eddFEf9153fC6036BDB4e37",
    "IRYS":      "0x91152B4Ef635403efBAe860edD0F8c321d7c035d",
    "BARD":      "0xd23A186A78c0B3B805505E5f8ea4083295ef9f3a",
    "COAI":      "0x0A8D6C86e1bcE73fE4D0bD531e1a567306836EA5",
    "BDCA":      "0x0c8382719ef242cae2247e4decb2891fbf699818",
    "XAUM":      "0x23AE4fd8E7844cdBc97775496eBd0E8248656028",
    "GOMINING":  "0x7Ddc52c4De30e94Be3A6A0A2b259b2850f421989",

    # ── Verificados manualmente ───────────────────────────────────────────────
    # Pendientes: WLFI, LAB, HTX, CTM, BEAM, REAL, BRETT, APR
    "TON":       "0x76a797a59ba2c17726896976b7b3747bfd1d220f",
    "WLFI":      "0x47474747477b199288bF72a1D702f7Fe0Fb1DEeA",
    "BRETT":     "0xa7440029eca41deabd8775ef1d6086b37d4df8d6",
    "LAB":       "0x7ec43Cf65F1663F820427C62A5780b8f2E25593A",
    "HTX":       "0x61ec85ab89377db65762e234c946b5c25a56e99e",
    "CTM":       "0xc8Fb80fCc03f699C70ff0CC08C09106288888888",
    "DUCKY":     "0xaDB50D6a3f931E5b4A14D06A4A77fe71171A462f",
    "BEAM":      "0x62D0A8458eD7719FDAF978fe5929C6D342B0bFcE",
    "APR":       "0x299AD4299Da5b2b93Fba4c96967B040C7F611099",
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
            contract_map = token_data.get("contract_address", [])
            for entry in contract_map:
                platform = entry.get("platform", {}).get("coin", {}).get("slug", "")
                pname = entry.get("platform", {}).get("name", "").lower()
                if platform in ["bnb-smart-chain", "binance-smart-chain", "binancecoin"] \
                        or "bnb" in pname or "bsc" in pname or "binance smart" in pname:
                    return entry.get("contract_address")
            # Fallback: si el token vive en BSC como plataforma principal
            platforms = token_data.get("platform", {})
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
    test_tokens = ["CAKE", "BNB", "FET", "ASTER", "BONK", "FLOKI", "TWT", "KOGE", "DUCKY"]
    print("=== Verificando contratos BSC ===\n")
    for symbol in test_tokens:
        contract = get_contract(symbol)
        if contract:
            print(f"{symbol}: {contract}")
        else:
            print(f"{symbol}: NO ENCONTRADO")
