# Estrategia del Superagente007
> Definida por Jorge | Guardada: 2026-06-12

---

## Flujo de fondeo via Telegram

1. Jorge le escribe al bot de Telegram: "quiero invertir $100"
2. El bot compra USDT (capital de trading) y BNB (para gas)
3. Los envia automaticamente a la wallet del agente
4. El agente confirma la recepcion y queda listo para operar
5. Jorge puede grabar este flujo como demo para el hackathon

Nota: Jorge ya tiene un bot de Telegram para compra de stablecoins en C:\Users\Jorge\ — evaluar reutilizarlo.
Nota 2: El video del fondeo ya fue grabado pero muestra la direccion del proyecto fracasado anterior. Hay que repetirlo con la nueva wallet del Superagente007.
Nota 3: Primera prueba real sera con 1 USDT para verificar que el flujo funciona antes de escalar a $100.

---

## Concepto central
**Sentimiento + Volumen Inusual**

El agente monitorea el sentimiento del mercado (noticias, narrativas, KOLs) y lo contrasta con el volumen inusual en las monedas participantes del hackathon. La combinacion de ambas señales es lo que genera una decision de entrada o salida.

---

## Tipos de señales que monitorea el agente

### Tipo 1 - Narrativa localizada en monedas
**Descripcion:** Se detecta una narrativa fuerte en el mercado sobre una categoria de tokens.
**Ejemplo:** Noticias y discusion sobre privacidad/seguridad del usuario.
**Accion:** Monitorear las monedas de esa categoria (ej: Monero, ZEC) dentro de la lista permitida. Contrastar con volumen. Si el volumen confirma la narrativa, entrar.
**Uso:** Principalmente para ENTRAR.

### Tipo 2 - Noticias macro globales
**Descripcion:** Eventos macroeconomicos o geopoliticos que afectan el mercado global.
**Ejemplos:**
- Inicio de nuevos bombardeos o conflictos armados
- Desplome de la bolsa tradicional
**Accion:** Observar como reacciona BTC. Si BTC reacciona mal (cae fuerte), vender las alts antes de que caigan mas fuerte.
**Uso:** Principalmente para SALIR (proteccion de capital).

### Tipo 3 - Noticias micro de una moneda especifica
**Descripcion:** Evento negativo especifico sobre una sola moneda: hackeo, exploit, rug, vulnerabilidad.
**Accion:** Monitorear si el volumen comienza a subir inusualmente (gente saliendo). Si el volumen confirma el evento negativo, salir rapido.
**Uso:** Principalmente para SALIR (stop loss por evento).

---

## Como se toma una decision de entrada

### Regla principal: DOBLE CONFIRMACION obligatoria
Sentimiento y volumen tienen el mismo peso. Ninguno prevalece sobre el otro.
**Un solo señal NO es suficiente para entrar. Siempre se necesitan los dos.**

### Dos caminos de entrada:

#### Camino A — Sentimiento primero, volumen confirma
1. El agente detecta una noticia o narrativa positiva sobre una moneda
2. Busca confirmacion en el volumen de esa moneda
3. Si el volumen esta subiendo de forma inusual → ENTRA
4. Si el volumen es normal o cae → ESPERA, no entra

#### Camino B — Volumen primero, sentimiento confirma
1. El agente detecta un spike de volumen inusual en una moneda (ej: 4x o 5x en un frametime de 5 minutos)
2. Busca informacion sobre esa moneda: noticias, KOLs, narrativa
3. Si el sentimiento es positivo → ENTRA
4. Si no encuentra razon positiva o el sentimiento es negativo → NO ENTRA (puede ser una trampa o venta masiva)

### Lo que NO activa una entrada
- Solo noticias positivas sin confirmacion de volumen
- Solo volumen alto sin razon positiva identificable
- Volumen alto con sentimiento negativo (señal de salida, no entrada)

---

## Como se toma una decision de salida

El agente sale cuando detecta:
- Señal Tipo 2 (macro negativa) + BTC reaccionando mal
- Señal Tipo 3 (evento negativo en la moneda) + volumen de salida
- La moneda esta **sobrecomprada** (el agente evalua indicadores tecnicos)
- El periodo de tiempo estimado del trade expiro sin que se cumplio el objetivo

---

## Niveles de percepcion del agente

El agente opera en 3 niveles simultaneos:

| Nivel | Que monitorea |
|---|---|
| Global (macro) | BTC, bolsa tradicional, geopolitica, sentimiento general del cripto mercado |
| Local (narrativa/sector) | Categoria de tokens (ej: privacidad, IA, DeFi), noticias del sector |
| Micro (moneda individual) | Volumen de la moneda, noticias especificas, KOLs que la mencionan, indicadores tecnicos |

---

## Caracteristica especial: Razonamiento explicado

Cada vez que el agente entra o sale de un trade, genera un resumen corto que explica:
1. **Por que entra:** que señales lo llevaron a la decision
2. **Periodo estimado:** cuanto tiempo espera mantener la posicion
3. **Cuando saldra:** que condicion lo haria salir (precio objetivo, evento, sobrecompra, tiempo)

**Ejemplo de razonamiento:**
> "Entro en ZEC porque: (1) hay narrativa fuerte sobre privacidad en el mercado por [noticia X], (2) el volumen de ZEC subio 4x su promedio de las ultimas 6 horas, (3) dos KOLs con alto engagement lo mencionaron en las ultimas 2 horas. Periodo estimado: 4-12 horas. Saldre si: el volumen cae a su promedio, ZEC sube mas del 15% sin confirmacion adicional (sobrecompra), o BTC cae mas del 3%."

---

## Restricciones del hackathon que afectan la estrategia
- Solo se puede operar con los **149 tokens BEP-20 de la lista aprobada**
- Minimo **1 trade por dia** durante los 7 dias de trading
- Drawdown maximo **30%** — estrategia conservadora primero
- Todas las operaciones son **spot en PancakeSwap (BSC)**
- PnL evaluado por: retornos, drawdown, rendimiento ajustado al riesgo, cumplimiento de normas

---

## Tokens prioritarios: Ecosistema BNB (alerta maxima durante el concurso)

Durante la semana de trading (22-28 junio) estos tokens pueden subir por el simple hecho de que el hackathon genera atencion y actividad en el ecosistema BNB Chain.

### Vinculacion fuerte con Binance/BNB Chain
| Token | Razon |
|---|---|
| BNB | Token nativo de la cadena, gas token, corazon del ecosistema. 100% Binance. |
| CAKE | Token de PancakeSwap, el DEX principal de BNB Chain. Promovido historicamente por Binance. Considerado el token "oficial" del ecosistema. Ademas es donde ejecutamos los trades. |
| ASTER | DEX de perps nuevo en BNB Chain. Respaldado por YZi Labs (brazo de inversion de cofundadores de Binance incluyendo CZ). CZ lo ha mencionado publicamente. |

### Vinculacion media-alta (incubados, listados temprano o muy usados en BNB Chain)
| Token | Razon |
|---|---|
| FLOKI | Binance ha impulsado en campañas |

### Por que son importantes durante el concurso
- El hackathon genera atencion mediatica en BNB Chain
- Participantes comprando/vendiendo en BSC aumenta la actividad del ecosistema
- CZ y YZi Labs pueden hacer menciones que muevan precios
- Son los tokens con mayor liquidez en PancakeSwap = menor slippage al operar
- El agente debe tenerlos en watchlist prioritario desde el dia 1

---

## Tokens de la lista con potencial por narrativa

### Privacidad / Seguridad
ZEC (Zcash), ROSE (Oasis), AXL (Axelar)

### IA / Tecnologia
FET (Fetch.ai), SKYAI, COAI, AIOZ, UAI, 0G, PEAQ

### DeFi / Liquidez
AAVE, UNI, CAKE (PancakeSwap nativo!), SUSHI, COMP, PENDLE, STG, 1INCH

### Memecoins con volumen
BONK, FLOKI, CHEEMS, BANANAS31, BabyDoge, DOGE, SHIB

### Stablecoins (para parking de capital entre trades)
USDT, USDC, DAI, FDUSD, FRAX

---

## Regla de cumplimiento minimo (obligatoria)

El hackathon exige minimo 1 trade por dia durante los 7 dias de trading (22-28 junio).

El agente tiene dos modos de operacion:

### Modo Oportunidad (prioridad)
El agente detecta una señal real (volumen + sentimiento + narrativa) y ejecuta un trade de tamano normal segun su estrategia.

### Modo Cumplimiento (fallback)
Si llega cerca del cierre del dia (ej: 1 hora antes de medianoche UTC) y no se ejecuto ningun trade en ese dia, el agente ejecuta automaticamente un trade pequeño de bajo riesgo para cumplir la regla:
- Monto pequeño (ej: 1-2% del capital total)
- En un token estable o de alta liquidez de la lista permitida
- Puede ser una compra y venta rapida del mismo activo
- Se registra en el log con razonamiento: "Trade de cumplimiento de regla minima diaria"

Esto garantiza que nunca perdamos la calificacion por falta de actividad.

---

## Parametros definidos

| Parametro | Valor |
|---|---|
| Threshold de volumen inusual | 5x o mas en un frametime de 5 minutos |
| Capital total del agente | ~$100 USD |
| Estructura de capital | Dos posiciones de $50 cada una |
| Posiciones simultaneas maximas | 2 |
| Tamaño por trade | El agente decide segun la oportunidad (entre $1 y $50 por posicion) |
| Donde corre | PC local primero. Si hay chances de ganar se migra a servidor. |
| Credenciales CMC | Disponibles |
| Credenciales TWAK (Access ID + HMAC Secret) | Disponibles |
| Sobrecompra | Pendiente de definir |
| Timeframes adicionales | Pendiente de definir |
