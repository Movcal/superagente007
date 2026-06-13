# Bot de Telegram para Fondeo del Agente
> Bot: "Bot Stablecoins Demo"
> Guardado: 2026-06-13

---

## Flujo completo de fondeo

1. Abrir el bot → tocar **INICIAR** (o escribir "hola" si no aparece el boton)
2. Tocar **Mi wallet** → pegar la direccion del agente: `0xABC819c3aeE6419333d2D7df365484E5CC833222`
3. El bot confirma "Wallet guardada correctamente"
4. Tocar **Comprar** → seleccionar **BNB Chain — USDT**
5. Escribir el monto en pesos argentinos (minimo $100 ARS)
6. El bot muestra resumen: red, token, precio USDT en ARS, cuanto USDT recibe, cuanto BNB para gas, wallet destino
7. Tocar **Confirmar**
8. El bot genera link de MercadoPago
9. El humano paga en MercadoPago
10. El bot envia USDT + BNB automaticamente a la wallet del agente

---

## Detalle importante
- El bot envia USDT (capital de trading) Y BNB (para gas) en la misma operacion
- El BNB para gas equivale a ~$100 ARS en el ejemplo visto
- Una vez que el humano paga en MercadoPago, el bot actua automaticamente

---

## Regla tecnica para la integracion
- El bot de Telegram es lento
- El agente debe esperar **4 segundos** entre cada llamada/interaccion con el bot
- Si no espera, las respuestas se pierden o se mezclan

---

## Para el video del demo
- Repetir el flujo con la direccion nueva: `0xABC819c3aeE6419333d2D7df365484E5CC833222`
- Primera prueba: fondear con 1 USDT para verificar que llega
- Luego escalar a $100 para el trading real
