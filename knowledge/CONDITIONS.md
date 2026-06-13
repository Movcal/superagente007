# Condiciones del Hackathon: BNB Hack AI Trading Agent Edition
> Fuente: https://dorahacks.io/hackathon/bnbhack-twt-cmc/detail
> Ultima actualizacion: 2026-06-12

---

## Fechas clave
| Evento | Fecha |
|---|---|
| Inicio registro | 3 junio 2026 (12pm UTC) |
| Ventana de construccion | 3-21 junio 2026 |
| **Deadline entrega** | **21 junio 2026 09:00** |
| Trading en vivo (Track 1) | 22-28 junio 2026 |
| Evaluacion | 29 junio - 5 julio 2026 |
| Anuncio ganadores | Semana del 6 julio 2026 |

---

## Premio total: $36,000 USD

### Track 1 - Autonomous Trading Agents ($24,000)
| Lugar | Premio |
|---|---|
| 1 | $10,000 |
| 2 | $6,000 |
| 3 | $4,000 |
| 4 | $2,000 |
| 5 | $2,000 |

### Track 2 - Strategy Skills ($6,000)
| Lugar | Premio |
|---|---|
| 1 | $3,000 |
| 2 | $2,000 |
| 3 | $1,000 |

### Premios especiales ($2,000 cada uno, acumulables con el main)
1. Mejor uso de Trust Wallet Agent Kit (solo Track 1)
2. Mejor uso de Agent Hub CMC (ambos tracks)
3. Mejor uso de BNB AI Agent SDK (ambos tracks)

---

## Track 1 - Autonomous Trading Agents

### Que construir
Un agente que:
- Lee datos de mercado via CoinMarketCap AI Agent Hub
- Toma decisiones automaticas
- Firma y ejecuta sus propias transacciones via Trust Wallet Agent Kit (TWAK)
- Opera en vivo en BSC durante la semana de trading

### Requisitos obligatorios
- Registrar wallet del agente on-chain ANTES del 22 junio via:
  - CLI: twak compete register
  - MCP: accion competition_register
- Contrato de competencia: 0x212c61b9b72c95d95bf29cf032f5e5635629aed5 (BSC)
- Minimo 1 trade por dia durante los 7 dias de trading (7 trades totales)
- Mantener balance mayor a $1 en todo momento
- Operar SOLO con tokens de la lista aprobada (149 tokens BEP-20)
- Registrar direccion del agente en DoraHacks + explicar la estrategia

### Lista de tokens permitidos (149 tokens BEP-20)
ETH, USDT, USDC, XRP, TRX, DOGE, ZEC, ADA, LINK, BCH, DAI, TON, USD1, USDe, M, LTC, AVAX, SHIB, XAUt, WLFI, H, DOT, UNI, ASTER, DEXE, USDD, ETC, AAVE, ATOM, U, STABLE, FIL, INJ, NIGHT, FET, TUSD, BONK, PENGU, CAKE, SIREN, LUNC, ZRO, KITE, FDUSD, BEAT, PIEVERSE, BTT, NFT, EDGE, FLOKI, LDO, B, FF, PENDLE, NEX, STG, AXS, TWT, HOME, RAY, COMP, GWEI, XCN, GENIUS, XPL, BAT, SKYAI, APE, IP, SFP, TAG, NXPC, AB, SAHARA, 1INCH, CHEEMS, BANANAS31, RIVER, MYX, RAVE, SNX, FORM, LAB, HTX, USDf, CTM, BDX, SLX, UB, DUCKY, FRAX, BILL, WFI, KOGE, ALE, FRXUSD, USDF, GOMINING, VCNT, GUA, DUSD, SMILEK, 0G, BEAM, MY, SOON, REAL, Q, AIOZ, ZIG, YFI, TAC, lisUSD, CYS, ZAMA, TRIA, HUMA, PLUME, ZIL, XPR, ZETA, BabyDoge, NILA, ROSE, VELO, UAI, BRETT, OPEN, BSB, TOSHI, BAS, ACH, AXL, LUR, ELF, KAVA, APR, IRYS, EURI, XUSD, BARD, DUSK, SUSHI, PEAQ, COAI, BDCA, XAUM

### Como se evalua Track 1
- Metrica principal: PnL total (retorno %) durante la semana de trading
- Gate de riesgo: Drawdown maximo 30% -> si se supera = DESCALIFICADO
- Ranking = mayor ganancia sin explotar el drawdown
- Se aplican costos de transaccion simulados

---

## Track 2 - Strategy Skills

### Que construir
Un CMC Skill que convierte datos de mercado en una estrategia de trading.
- Entregable: spec de estrategia backtestable (no agente en vivo)
- No requiere ejecucion on-chain
- No requiere registro on-chain
- Se entrega por DoraHacks antes del 21 junio

### Como se evalua Track 2
Panel discrecional con 4 criterios:
1. Ejecucion tecnica - funciona? la parte on-chain es real?
2. Originalidad - es un enfoque nuevo a un problema real?
3. Relevancia real - hay un usuario claro y camino plausible a adopcion?
4. Demo y presentacion - el demo es claro?

---

## Premio especial: Mejor uso de Trust Wallet Agent Kit (solo Track 1)
| Criterio | Puntos |
|---|---|
| Profundidad de integracion TWAK (unica capa de ejecucion, multiples superficies) | 30 |
| Self-custody integridad (llaves del usuario, firma local en todo el loop) | 25 |
| Ejecucion autonoma + guardrails (drawdown caps, allowlists, limites por trade/dia) | 20 |
| Uso nativo de x402 (pago por request en el trade loop) | 10 |
| Originalidad y relevancia real | 10 |
| Demo y presentacion (prueba on-chain: contrato o tx hash en BSC) | 5 |

Penalizacion de self-custody:
- Totalmente self-custodial -> 20-25 puntos
- Componente custodial parcial -> 8-15 puntos
- Loop principal depende de custodia -> 0-7 puntos

---

## Stack tecnologico requerido
| Herramienta | Uso |
|---|---|
| CoinMarketCap AI Agent Hub | Datos de mercado (MCP, x402, CLI, Skills) |
| Trust Wallet Agent Kit (TWAK) | Firma y ejecucion on-chain self-custody |
| BNB AI Agent SDK | SDK para construir agentes en BSC |
| BNB Chain (BSC) | Blockchain donde opera el agente |

---

## Requisitos de entrega (ambos tracks)
- Repo publico (GitHub/GitLab/Bitbucket)
- Demo link o video, O instrucciones claras de setup
- Para Track 1: direccion del agente en BSC + descripcion de estrategia en DoraHacks
- PROHIBIDO: lanzar tokens, abrir liquidez, o hacer airdrop pumping antes de los resultados
- AI tooling permitido

---

## Causas de descalificacion
- Drawdown mayor al 30% en Track 1
- Trades fuera de la lista de 149 tokens
- Menos de 1 trade/dia durante la semana de trading
- Lanzar token / fundraising durante el evento
- Repo no publico o sin demo

---

## Contacto
- Telegram del hackathon: https://t.me/+MhiOLT0YUnlmNWFk
