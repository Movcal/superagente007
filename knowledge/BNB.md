# BNB AI Agent SDK - Documentacion
> Fuente: https://github.com/bnb-chain/bnbagent-sdk
> Actualizado: 2026-06-12
> Estado: en desarrollo activo, puede tener cambios que rompan compatibilidad

---

## Que es
Toolkit Python para construir agentes IA autonomos en BNB Chain.
Implementa dos estandares:
- **ERC-8004 (Agent Identity):** registrar al agente on-chain con identidad unica y wallet
- **ERC-8183 (Agentic Commerce):** protocolo de comercio trustless — el agente negocia trabajos, entrega resultados y recibe pago via escrow on-chain

---

## Instalacion

```bash
pip install bnbagent

# Con extras:
pip install "bnbagent[server,ipfs]"   # FastAPI server + IPFS
pip install "bnbagent[server]"         # Solo server
pip install "bnbagent[ipfs]"           # Solo IPFS
```

Requisitos: Python 3.10+

---

## Variables de entorno

| Variable | Requerida | Default | Uso |
|---|---|---|---|
| WALLET_PASSWORD | Si | — | Password del keystore |
| PRIVATE_KEY | Recomendada | Auto-genera | Llave del wallet del agente |
| NETWORK | No | bsc-testnet | Red a usar |
| ERC8183_SERVICE_PRICE | Si (server) | — | Precio minimo de job |
| ERC8183_AGENT_URL | Si (server) | — | Endpoint del agente |
| STORAGE_API_KEY | No | — | JWT para IPFS pinning |
| ERC8183_FUNDED_POLL_INTERVAL | No | 30 | Intervalo de polling en segundos |

---

## Paso 1: Registrar el agente (ERC-8004)

```python
from bnbagent import ERC8004Agent, AgentEndpoint, EVMWalletProvider
import os
from dotenv import load_dotenv

load_dotenv()
wallet = EVMWalletProvider(
    password=os.getenv("WALLET_PASSWORD"),
    private_key=os.getenv("PRIVATE_KEY"),
)

sdk = ERC8004Agent(network="bsc-testnet", wallet_provider=wallet)
agent_uri = sdk.generate_agent_uri(
    name="my-ai-agent",
    description="AI agent for document processing",
    endpoints=[
        AgentEndpoint(
            name="ERC-8183",
            endpoint="https://my-agent.example.com/erc8183/status",
            version="0.1.0",
        ),
    ],
)

result = sdk.register_agent(agent_uri=agent_uri)
print(f"Agent registered! ID: {result['agentId']}")
```

Nota: registro de identidad es **gratuito** en BSC Testnet via MegaFuel paymaster sponsorship.

---

## Paso 2: Correr un servidor de agente (ERC-8183)

```python
from bnbagent.erc8183.server import create_erc8183_app

def execute_job(job: dict) -> str:
    return f"Processed: {job['description']}"

app = create_erc8183_app(on_job=execute_job)
```

```bash
uvicorn agent:app --port 8003
```

---

## Cliente ERC-8183 (crear y fondear jobs)

```python
from bnbagent.erc8183 import ERC8183Client, JobStatus
from bnbagent.wallets import EVMWalletProvider
import time

wallet = EVMWalletProvider(password="your-password", private_key="0x...")
erc8183 = ERC8183Client(wallet, network="bsc-testnet")

budget = 1 * (10 ** erc8183.token_decimals())
expired_at = int(time.time()) + 3900  # 65 minutos

res = erc8183.create_job(provider="0x...", expired_at=expired_at, description="task")
job_id = res["jobId"]

erc8183.register_job(job_id)
erc8183.set_budget(job_id, budget)
erc8183.fund(job_id, budget)
erc8183.settle(job_id)

assert erc8183.get_job_status(job_id) == JobStatus.COMPLETED
```

---

## Ciclo de vida de un job

| Estado | Descripcion |
|---|---|
| OPEN | Creado, sin fondos |
| FUNDED | Escrow depositado |
| SUBMITTED | Proveedor entrego el trabajo |
| COMPLETED | Aprobado (silencio = aprobacion implicita) |
| REJECTED | Cliente o votantes lo rechazaron |
| EXPIRED | Vencio sin settlement |

---

## Endpoints del servidor

| Metodo | Path | Uso |
|---|---|---|
| POST | /erc8183/negotiate | Negociacion de precio (rate-limited) |
| GET | /erc8183/job/{id} | Detalles del job desde blockchain |
| GET | /erc8183/job/{id}/response | Resultado entregado |
| GET | /erc8183/job/{id}/verify | Verificar elegibilidad del job |
| GET | /erc8183/status | Info del wallet y contrato del agente |

---

## Disputas y reembolsos

```python
erc8183.dispute(job_id)       # Solo cliente, dentro de la ventana de disputa
erc8183.vote_reject(job_id)   # Votantes en whitelist
erc8183.claim_refund(job_id)  # Cualquiera, despues de vencimiento
```

---

## Redes soportadas
- **BSC Testnet** (default): entorno principal de pruebas, registro gratuito
- RPC personalizado via variable `RPC_URL`

---

## Conceptos clave
- **Escrow:** tokens bloqueados hasta completar o rechazar el job
- **Optimistic Settlement:** politica default = aprobacion si no hay disputa
- **Quorum Voting:** votantes en whitelist deben llegar a consenso para rechazar
- **Platform Fee:** se descuenta en puntos base al completar
- **Dispute Window:** periodo de gracia despues del submit para impugnar

---

## Relevancia para el hackathon
El BNB AI Agent SDK se usa principalmente para:
1. Darle identidad on-chain al agente (ERC-8004) — lo hace descubrible
2. Si queremos que el agente sea contratado por otros agentes (ERC-8183)
3. Premio especial "Mejor uso de BNB AI Agent SDK" ($2,000)

Para el Track 1, lo mas relevante es ERC-8004 para registrar la identidad del agente en BSC.
