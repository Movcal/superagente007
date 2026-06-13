# Trust Wallet Agent Kit (TWAK) - Documentacion
> Fuente: https://portal.trustwallet.com
> Actualizado: 2026-06-12

---

## Que es
MCP server + CLI + SDK que le da a los agentes IA la capacidad de leer, transaccionar y automatizar en 25+ cadenas, sin que el agente tenga las llaves del usuario. Self-custody siempre.

---

## 6 Primitivos principales

| Primitivo | Descripcion |
|---|---|
| Wallet & Identity | Modo autonomo (wallet dedicada con reglas) o WalletConnect (conecta Trust Wallet existente del usuario) |
| Trade & Swap | Swaps cross-chain con mejor ruta en EVM, Solana, Bitcoin, Cosmos, TON, Aptos, Tron, NEAR, Sui |
| Market Data | Precios en tiempo real, metricas on-chain, señales de riesgo de tokens, resolucion ENS |
| Payments (x402) | Micropagos por llamada via protocolo x402 |
| Automation | DCA, limit orders, alertas de precio, ejecucion programada |
| Fiat On/Off-Ramp | Comprar/vender crypto con tarjeta, transferencia bancaria, pagos regionales |

---

## Cadenas soportadas (25+)
Ethereum, Solana, Bitcoin, Arbitrum, Base, Polygon, **BNB Chain**, Optimism, Avalanche, Cosmos, TON, Aptos, Tron, NEAR, Sui, y otras.

---

## Modos de operacion

### Modo A - Autonomous Agent Wallet (para el hackathon)
- Wallet dedicada con reglas y limites de activos pre-configurados
- No requiere aprobacion por transaccion
- Ideal para: DCA, limit orders, ejecucion programada, trading autonomo
- El agente firma y ejecuta solo dentro de los guardrails definidos

### Modo B - WalletConnect User-in-Loop
- El agente propone transacciones al Trust Wallet existente del usuario
- El usuario aprueba cada transaccion
- Ideal para: advisory, copilots, UX retail

---

## Instalacion

```bash
curl -fsSL https://agent-kit.trustwallet.com/install.sh | bash
```

El instalador hace:
- Instala el CLI (v0.12.0+)
- Verifica credenciales de API
- Auto-conecta a Claude Code, Cursor y otros harnesses
- Crea opcionalmente una HD wallet para 25+ cadenas

---

## Formas de integracion

### Opcion A - MCP Server (conversacional)
- Compatible con: Claude, Cursor, Windsurf, GitHub Copilot, Cline, Codex
- Configuracion via `claude_desktop_config.json` con comando `twak serve`

### Opcion B - CLI (programatico)
- Ejecucion directa en shell o dentro de loops del agente, scripts, CI jobs, cron

---

## Comandos CLI

```bash
twak price ETH                              # precio en tiempo real
twak swap 100 USDC ETH --quote-only         # cotizacion de swap
twak alert create --token BTC --above 75000 # crear alerta de precio
twak wallet portfolio                        # ver portfolio

# Comandos del hackathon (Track 1)
twak compete register                        # registrar agente on-chain en el contrato de competencia
```

---

## Registro en el hackathon (obligatorio antes del 22 junio)

```bash
twak compete register
```
O via MCP: accion `competition_register`

Ambos resuelven la wallet del agente y envian la transaccion de registro.
Contrato: `0x212c61b9b72c95d95bf29cf032f5e5635629aed5` (BSC)

---

## Seguridad y self-custody
- Las llaves NUNCA salen del usuario
- Self-custody siempre mantenido
- Llaves dedicadas con scope y revocables
- x402 para micropagos seguros

---

## Relevancia para el premio especial TWAK ($2,000)
Para ganar el premio "Mejor uso de Trust Wallet Agent Kit" el agente debe:
- Usar TWAK como UNICA capa de ejecucion (no solo un swap aislado)
- Usar mas de una superficie: signing + autonomous mode + x402
- Mantener self-custody en todo el loop de trading
- Tener guardrails reales: drawdown caps, allowlists de tokens, limites por trade/dia, slippage protection
- Usar x402 para pagar por datos o inferencia dentro del loop de trading
- Mostrar en el demo el loop completo con prueba on-chain (contrato o tx hash en BSC)

---

---

## Detalle tecnico del SDK (developer.trustwallet.com/developer/agent-sdk)

### Instalacion
```bash
npx @trustwallet/cli --version
# o global:
npm install -g @trustwallet/cli
```

### Autenticacion
1. Obtener credenciales en portal.trustwallet.com (Access ID + HMAC Secret)
2. Inicializar:
```bash
twak init --api-key your_access_id --api-secret your_hmac_secret
twak auth status   # verificar
```
3. Credenciales guardadas en `~/.twak/credentials.json` (permisos 0600)

### Servidores MCP disponibles
| Servidor | Uso | Endpoint |
|---|---|---|
| API Gateway MCP | Datos blockchain en vivo | https://mcp.trustwallet.com/tws |
| Docs MCP | Buscar documentacion del developer | (Integrado) |

Headers requeridos para API Gateway MCP:
- `X-TW-CREDENTIAL`: Access ID
- `X-TW-SECRET-KEY`: HMAC Secret Key

### Comandos CLI completos
```bash
twak price ETH --json                          # precio en tiempo real
twak chains                                    # info de cadenas disponibles
twak balance --address <addr> --coin 60        # balance de cuenta (coin 60 = ETH)
twak serve                                     # modo MCP
twak serve --rest --port 3000                  # modo REST API
twak serve --watch                             # modo automatizacion + watcher activo

# Swaps
twak swap ... --chain <chain>                  # ejecutar swap en cadena especifica
twak swap ... --prefer-network bsc             # preferir BSC/BNB Chain
twak swap ... --quote-only                     # solo cotizacion, no ejecuta

# Automatizacion
twak automate --interval <tiempo>              # DCA automatico
twak automate --price <precio> --condition ... # limit order

# x402
twak x402 quote <url>                          # cotizar pago x402
twak x402 request <url> --max-payment <amt>    # ejecutar request con pago x402

# Hackathon
twak compete register                          # registrar agente en contrato del hack
```

### Modo autonomo
- Las automatizaciones solo corren mientras hay un watcher activo
- Lanzar: `twak serve --watch`
- Soporta: DCA con `--interval`, limit orders con `--price`

### Configuracion compatible
- Claude Code, Claude Desktop, Cursor, VS Code, Windsurf, GitHub Copilot, Cline, Codex

### Identificadores de cadena
- BNB Chain: `--prefer-network bsc` o con CAIP-2 identifiers

---

## TW Agent Skills - Repo de skills open source
> Fuente: https://github.com/trustwallet/tw-agent-skills
> Licencia: MIT | 60 stars | 41 forks

### Que es
Skills de agente IA para Trust Wallet — endpoints REST, CLI y librerias open-source para 100+ cadenas.
Arquitectura eficiente: 3 descripciones siempre disponibles, 21 documentos de referencia que cargan bajo demanda.

### Instalacion de los skills
```bash
# Auto-detecta el agente:
npx skills add trustwallet/tw-agent-skills

# Para agente especifico:
npx skills add trustwallet/tw-agent-skills -a claude-code
npx skills add trustwallet/tw-agent-skills -a cursor
npx skills add trustwallet/tw-agent-skills -a github-copilot

# Un solo skill:
npx skills add trustwallet/tw-agent-skills -s api
```

### Variables de entorno requeridas
```bash
TWAK_ACCESS_ID=your_access_id
TWAK_HMAC_SECRET=your_hmac_secret
```
IMPORTANTE: agregar `.env` al `.gitignore` — nunca subir credenciales al repo.

### Los 3 Skills disponibles

#### 1. API Skill
Acceso REST a:
- Busqueda de tokens
- Precios
- Cotizaciones de swap
- Datos de mercado
- Validacion de seguridad de tokens

#### 2. Wallet Skill (CLI twak)
- Gestion de wallet
- Consulta de balances
- Swaps de tokens
- Transferencias
- Monitoreo de actividad
- Operaciones ERC-20
- Evaluacion de riesgo de tokens
- Soporte x402

#### 3. SDK Skill (librerias open-source)
- Wallet Core
- Web3 Provider integration
- Deep linking
- Gestion de assets
- Barz protocol

### Estadisticas
- 14 acciones API en 3 skills
- 21 documentos de referencia
- 100+ blockchains soportadas

### Agentes compatibles
Claude Code, Cursor, Codex, Windsurf, GitHub Copilot, Cline, OpenCode, Roo

### Pendiente
- Configuracion de guardrails especifica (drawdown caps, token allowlists)
- Integracion con LangChain
- Integracion con PancakeSwap especificamente
