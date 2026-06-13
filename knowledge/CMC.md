# CoinMarketCap AI Agent Hub - Documentacion
> Fuente: https://coinmarketcap.com/api/agent y https://coinmarketcap.com/api/documentation/
> Actualizado: 2026-06-12

---

## Que es
El CMC AI Agent Hub convierte datos de mercado en informacion lista para agentes de IA.
Funciona como la capa de datos del agente: precios, señales tecnicas, sentimiento, noticias, todo en un formato que un LLM puede consumir directamente.

---

## Datos disponibles
- Precios en vivo, market cap, volumen (CEX y DEX)
- Datos de exchanges (pares, liquidez, rankings)
- Datos on-chain (tokens, pares DEX, historico)
- Señales pre-calculadas: MACD, RSI, EMA, Fear & Greed Index
- Noticias, sentimiento social, KOLs, wallets
- Historico: 14 años de datos, 51M+ assets, 947+ exchanges, 72+ endpoints
- Datos actualizados cada 1 minuto

---

## Formas de integracion

### 1. MCP (Model Context Protocol)
- Se agrega el MCP de CMC al agente
- Compatible con: Claude Code, Cursor, VS Code, Codex, Hermes, Openclaw
- 2 pasos: agregar MCP -> ejecutar Skills de prueba

### 2. x402 Protocol
- Acceso por micropago: $0.01 USDC por request
- NO requiere API key
- El agente paga por cada llamada directamente
- Importante para el premio especial "Mejor uso de Agent Hub"

### 3. CLI
- Comandos de terminal para interactuar con CMC

### 4. Skills Library
- Pipelines de computo estructurado pre-construidos
- El hub selecciona y ensambla automaticamente los Skills correctos segun el contexto
- Ejecucion en la nube (reduce costos de procesamiento)
- Outputs en formato Markdown/YAML compacto y con timestamps

---

## Autenticacion
- **Con API key:** registrarse en pro.coinmarketcap.com
- **Con x402:** sin API key, pago de $0.01 USDC por request

---

## Planes y precios

| Plan | Precio | Endpoints | Creditos/mes | Historico | Uso |
|---|---|---|---|---|---|
| Basic | Gratis | 35+ | 15,000 | Sin historico | Personal |
| Hobbyist | $29/mes ($348/año) | 40+ | 150,000 | 3 años | Personal |
| Startup | $79/mes ($948/año) | 50+ | 450,000 | Todo el tiempo | Comercial |
| Standard | $299/mes ($3,588/año) | Todos | 2,000,000 | Todo el tiempo | Comercial |
| Professional | $699/mes ($8,388/año) | Todos | 5,000,000 | Todo el tiempo | Comercial |

---

## Links
- Documentacion API: https://coinmarketcap.com/api/documentation/
- Agent Hub: https://coinmarketcap.com/api/agent
- Registro API key: https://pro.coinmarketcap.com

---

---

## Como funciona el Agent Hub (filosofia)

### Sin Agent Hub vs Con Agent Hub
| Sin Agent Hub | Con Agent Hub |
|---|---|
| API -> JSON masivo -> fallo de parseo / quema de tokens -> fallo del LLM | Prompt -> Ruteo a Skills -> Computo en nube -> Analisis profundo -> Insights estructurados |
| Responde "que paso hoy?" | Responde "es buen dia para tomar riesgos?, cuales oportunidades primero?, que invalidaria la tesis?" |

### Ventajas clave
- **Pre-calculado:** indicadores (MACD, RSI, EMA, Fear & Greed) ya calculados, sin computo pesado en el agente
- **Multi-fuente:** CEX + derivados + on-chain + noticias + social + KOL + wallets en una sola llamada
- **Listo para agentes:** output en Markdown/YAML compacto, reduce alucinaciones y sobrecarga de JSON
- **Enrutamiento inteligente:** el motor de intencion IA selecciona los skills correctos automaticamente
- **Ejecucion en nube:** reduce miles de tokens a señales de alta calidad

### Configuracion en 2 pasos
1. Agregar MCP al agente (compatible con Claude Code, Cursor, VS Code, Codex, Hermes, Openclaw)
2. Ejecutar un skill de ejemplo para verificar que funciona

---

## x402 - Detalle tecnico completo
> Fuente: https://pro.coinmarketcap.com/api/documentation/ai-agent-hub/x402

### Que es
Protocolo de pago por request desarrollado por Coinbase. Reemplaza el API key con micropagos en USDC automaticos via HTTP.

### Flujo de pago (3 pasos)
1. El agente hace un request al endpoint x402 sin autenticacion
2. El servidor responde HTTP 402 con los detalles de pago en el header `Payment-Required`
3. El agente firma un mensaje USDC `transferWithAuthorization` (EIP-3009) y reintenta el request con el header `PAYMENT-SIGNATURE`
   - Solo se cobra si el servidor entrega los datos exitosamente
   - Las firmas expiran en ~30 segundos (sin uso no llegan al blockchain)

### Precio y red
- Costo: $0.01 USDC por request (todos los endpoints)
- Red: Base (Chain ID 8453)
- Token: USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- Metodo: EIP-3009 `transferWithAuthorization`

### Endpoints disponibles via x402
| Endpoint | Metodo | Path |
|---|---|---|
| DEX Search | GET | /x402/v1/dex/search |
| Crypto Quotes Latest | GET | /x402/v3/cryptocurrency/quotes/latest |
| Crypto Listings Latest | GET | /x402/v3/cryptocurrency/listings/latest |
| DEX Pairs Quotes Latest | GET | /x402/v4/dex/pairs/quotes/latest |

### MCP via x402
- Endpoint MCP: `https://mcp.coinmarketcap.com/x402/mcp`
- Permite a Claude y otros LLM llamar herramientas CMC con pago automatico por request

### Ejemplo de codigo (TypeScript)
```typescript
import { createX402AxiosClient } from "@x402/axios";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount("0xYOUR_PRIVATE_KEY");
const signer = toClientEvmSigner(account, publicClient);
const client = createX402AxiosClient({ schemes: [new ExactEvmScheme(signer)] });

const response = await client.get(
  "https://pro-api.coinmarketcap.com/x402/v1/dex/search",
  { params: { q: "bnb" } }
);
```

---

## Skills Marketplace - Catalogo completo (193 skills)
> Total skills disponibles: 193 | Star Skills: 23

### Skills MAS RELEVANTES para nuestro agente de trading spot (Track 1)

| Skill | Categoria | Usos | Descripcion corta |
|---|---|---|---|
| daily market overview | market/macro | 8.2K | Panorama diario: macro, liquidez, BTC ETF, sentimiento, candidatos spot/perp |
| altcoin breakout scanner spot | market | 4.6K | Rankea candidatos de breakout en spot por precio, volumen y tendencia |
| altcoin token profile | asset | 4.1K | Perfil del token: mercado, protocolo, holders, gaps fundamentales |
| kline pattern recognition | asset | 4.1K | Detecta patrones de velas y clasicos (flags, wedges, H&S, doble techo/piso) |
| altcoin kol sentiment | asset | 3.9K | Sentimiento social y KOL para un token, separa ruido de señal real |
| altcoin sector analysis | asset | 3.8K | Rotacion sectorial: momentum relativo vs BTC, concentracion de flujo |
| crypto macro overview | market | 3.8K | Sintesis macro: pulso de mercado, liquidez, ETF, sentimiento |
| macro news aggregator | market | 3.8K | Noticias macro actuales con nivel de frescura y relevancia |
| btc cross asset correlation | asset | 5.1K | Regimen BTC vs activos de riesgo, DXY, Gold. Contexto macro diario |
| btc etf institutional demand | asset | 4.3K | Flujo ETF de BTC con confirmacion de absorcion spot y holders de largo plazo |
| altcoin deep research | asset | 3.1K | Memo de investigacion profunda: perfil, estructura de mercado, sector, sentimiento |
| Monitor Market Sentiment Shift | market | 2.4K | Monitorea si el sentimiento va a euforia, panico, recuperacion o rango |
| Detect Market Regime | market | 1.7K | Clasifica el regimen: trend_expansion, liquidation_stress, range_chop |
| Analyze Multi Timeframe Trend Alignment | asset | 1.9K | Alineacion de tendencia en multiples timeframes (bullish/bearish/mixto) |
| altcoin official dynamics | asset | 3.4K | Actualizaciones oficiales, catalizadores y calidad de contenido del proyecto |
| Assess Volatility Expansion Risk | asset | 1.8K | Detecta si la volatilidad esta contenida, expandiendose, o en squeeze |
| price probability forecaster | asset | 1.2K | Bandas de probabilidad de precio para un horizonte dado |
| Scan Spot Altcoin Breakout With Social Confirmation | market | 1.8K | Candidatos de breakout spot con confirmacion de narrativa social |
| Classify Kline Pattern Quality | asset | 2.5K | Clasifica calidad del ultimo patron de velas con contexto multi-timeframe |
| Review Support Resistance Confluence | asset | 1.5K | Lee soporte/resistencia con niveles clave y fuerza de confluencia |
| onchain token scanner | universe | 4K | Escanea tokens on-chain nuevos con traccion temprana, filtra rugs |
| macro liquidity monitor | market | 3.9K | Condiciones macro de liquidez: sopportivo, neutral o restrictivo |
| Macro Financial Conditions | market | 3.4K | Tasas, yields, curva, inflacion, politica Fed: sopportivo o restrictivo |
| Build Daily Market Brief | market | 2.1K | Brief diario: tono, macro, ETF, amplitud sectorial, titulares |
| Detect Funding Rate Regime Shift | market | 1.6K | Cambio de regimen en funding rate de perpetuos |
| detect accumulation breakout transition | asset | 1.6K | Detecta transicion de acumulacion a breakout en un mercado perp |
| Assess Altcoin Sector Relative Position | asset | 2K | Posicion relativa del token en su sector: liderando, siguiendo, rezagado |

### Skills adicionales utiles (segundo nivel)

| Skill | Categoria | Descripcion corta |
|---|---|---|
| Analyze Cross Asset Risk Regime | asset | Clasifica si crypto esta en risk-on, deleveraging defensivo o estres macro |
| Detect ETF Flow Price Absorption | asset | Detecta si flujos ETF tienen absorcion real en spot |
| Screen Spot Breakout Candidates | asset | Candidatos de breakout spot rankeados |
| Build Altcoin Market Context Profile | asset | Perfil de contexto de mercado para un altcoin |
| Analyze Taker Flow Imbalance | asset | Compara flujo taker spot vs perp (compra/venta activa confirmada) |
| Detect Spot Perp Flow Divergence | market | Detecta divergencia entre flujo spot y perp |
| Track Social Price Divergence | asset | Detecta divergencia entre atencion social y precio |
| Track Narrative Rotation | asset | Detecta si el liderazgo narrativo esta rotando o concentrandose |
| Build Indicator Trade Watchlist | asset | Watchlist rankeado con tipo de setup y condiciones de trigger |

### Categorias del marketplace
- **All:** 193 skills
- **Star Skills:** 23 (los mas probados y confiables)
- **defi:** 24
- **research:** 77
- **market-data:** 6
- **risk:** 21
- **on-chain:** 3
- **cex:** 49
- **portfolio:** 13
