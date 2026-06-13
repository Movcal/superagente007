# Aclaraciones del equipo organizador
> Este archivo se actualiza conforme el equipo responde preguntas o flexibiliza condiciones.
> Formato: [fecha] pregunta -> respuesta + impacto en las condiciones

---

## Aclaraciones pendientes de agregar

_(Pega aqui las respuestas que te hayan dado en el Telegram o DoraHacks)_

---

## Aclaraciones confirmadas

### [2026-06-12] Venue de trading - Track 1
- **Aclaracion:** El Track 1 opera en tokens spot. Todos los tokens de la lista aparecen en PancakeSwap.
- **Impacto:** Las compras/ventas del agente se ejecutan en PancakeSwap (BSC). No es trading de perpetuos ni derivados.

### [2026-06-12] Como se evalua el PnL - Track 1
- **Aclaracion:** El agente se enfrenta a una ventana de mercado retenida (held-out) despues del cierre de entregas. Los jueces puntuan en base a:
  1. Retornos (returns)
  2. Drawdowns (caidas maximas)
  3. Rendimiento ajustado al riesgo (risk-adjusted performance)
  4. Cumplimiento de las normas (rule compliance)
- **Impacto:** No basta con ganar mucho, el agente debe hacerlo de forma controlada. Un agente que gana poco pero con drawdown bajo puede superar a uno que gana mas pero con drawdown alto. El cumplimiento de reglas es un criterio de puntuacion, no solo de descalificacion.

### [2026-06-12] Doble participacion en ambos tracks
- **Aclaracion:** Si se puede participar en ambos tracks, PERO cada entrega necesita su propio agente funcionando. Los equipos ganadores generalmente se enfocan en una sola pista.
- **Impacto:** Si competimos en Track 1 y Track 2 al mismo tiempo, necesitamos dos agentes separados. Dado el tiempo limitado (9 dias), lo mas inteligente es enfocarse en Track 1 (mayor premio) y documentar la estrategia para Track 2 sin construir un segundo agente separado.
