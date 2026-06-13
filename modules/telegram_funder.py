import asyncio
import os
import sys
import pathlib
from telethon import TelegramClient
from telethon.tl.types import KeyboardButtonCallback, ReplyInlineMarkup, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
BOT_USERNAME = os.getenv("STABLECOINS_BOT_USERNAME", "@stablecoins_demo_bot")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
AGENT_WALLET = "0xABC819c3aeE6419333d2D7df365484E5CC833222"
DELAY = 5.5  # segundos entre cada interaccion con el bot

# Ruta absoluta fija para el archivo de sesion (fuera del proyecto)
SESSION_PATH = str(pathlib.Path.home() / ".superagente007_session")

# Cooldown: minimo de horas entre fondeos
FUNDING_COOLDOWN_HOURS = 24


def log(msg):
    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] [FUNDER] {msg}"
    print(line.encode('ascii', errors='replace').decode('ascii'))
    with open("logs/telegram_funder.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def click_button(client, message, text):
    """Busca y hace click en un boton por texto."""
    if message.reply_markup:
        markup = message.reply_markup
        if hasattr(markup, 'rows'):
            for row in markup.rows:
                for button in row.buttons:
                    btn_text = ""
                    if hasattr(button, 'text'):
                        btn_text = button.text
                    if text.lower() in btn_text.lower():
                        log(f"Clickeando boton: '{btn_text}'")
                        await message.click(text=btn_text)
                        await asyncio.sleep(DELAY)
                        return True
    log(f"Boton '{text}' no encontrado")
    return False


async def get_last_msg_id(client, bot):
    """Devuelve el ID del mensaje mas reciente en el chat con el bot."""
    messages = await client.get_messages(bot, limit=1)
    if messages:
        return messages[0].id
    return 0


async def wait_inline_message(client, bot, after_id, timeout=30):
    """Espera un mensaje nuevo del bot (ID > after_id) con botones inline."""
    import time
    start = time.time()
    while time.time() - start < timeout:
        messages = await client.get_messages(bot, limit=10)
        for msg in messages:
            if msg.out is False and msg.id > after_id and isinstance(msg.reply_markup, ReplyInlineMarkup):
                return msg
        await asyncio.sleep(1)
    log("Timeout esperando mensaje con botones inline")
    return None


async def wait_bot_message(client, bot, after_id, timeout=30):
    """Espera cualquier mensaje nuevo del bot (ID > after_id)."""
    import time
    start = time.time()
    while time.time() - start < timeout:
        messages = await client.get_messages(bot, limit=10)
        for msg in messages:
            if msg.out is False and msg.id > after_id:
                return msg
        await asyncio.sleep(1)
    log("Timeout esperando mensaje del bot")
    return None


def _check_cooldown():
    """Retorna True si ya paso el cooldown desde el ultimo fondeo."""
    import json
    from datetime import datetime, timedelta
    history_file = "data/funding_history.json"
    if not os.path.exists(history_file):
        return True
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    if not history:
        return True
    last = history[-1].get("timestamp_utc", "")
    try:
        last_dt = datetime.fromisoformat(last)
        elapsed = datetime.utcnow() - last_dt
        if elapsed < timedelta(hours=FUNDING_COOLDOWN_HOURS):
            horas = (timedelta(hours=FUNDING_COOLDOWN_HOURS) - elapsed).seconds // 3600
            log(f"Cooldown activo: ultimo fondeo hace {elapsed.seconds // 3600}h. Faltan ~{horas}h.")
            return False
    except Exception:
        pass
    return True


def _save_funding_record(amount_ars, mp_link):
    """Guarda un registro permanente de cada fondeo exitoso."""
    import json
    from datetime import datetime
    history_file = "data/funding_history.json"
    history = []
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    record = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "amount_ars": amount_ars,
        "wallet": AGENT_WALLET,
        "network": "BNB Chain",
        "token": "USDT",
        "mp_link": mp_link,
        "note": "Fondeo automatico via Superagente007 — rampa fiat MercadoPago"
    }
    history.append(record)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    log(f"Registro guardado en {history_file} (total: {len(history)} fondeos)")


async def fund_agent(amount_ars):
    """
    Ejecuta el flujo completo de fondeo via el bot de stablecoins.
    Retorna el link de MercadoPago o None si falla.
    """
    log(f"Iniciando fondeo de {amount_ars} ARS...")

    if not _check_cooldown():
        log("Fondeo bloqueado por cooldown. Abortando.")
        return None

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start(phone=PHONE)

    try:
        bot = await client.get_entity(BOT_USERNAME)

        # Paso 1: Iniciar el bot
        log("Paso 1: Iniciando bot...")
        last_id = await get_last_msg_id(client, bot)
        await client.send_message(bot, "/start")
        await wait_bot_message(client, bot, last_id)
        await asyncio.sleep(DELAY)

        # Paso 2: Configurar wallet
        log("Paso 2: Configurando wallet del agente...")
        last_id = await get_last_msg_id(client, bot)
        await client.send_message(bot, "👛 Mi wallet")
        await wait_bot_message(client, bot, last_id)
        await asyncio.sleep(DELAY)

        # Paso 3: Enviar direccion del agente
        log(f"Paso 3: Enviando direccion del agente: {AGENT_WALLET}")
        last_id = await get_last_msg_id(client, bot)
        await client.send_message(bot, AGENT_WALLET)
        await wait_bot_message(client, bot, last_id)
        await asyncio.sleep(DELAY)

        # Paso 4: Ir a Comprar
        log("Paso 4: Tocando Comprar...")
        last_id = await get_last_msg_id(client, bot)
        await client.send_message(bot, "🛒 Comprar")

        # Paso 5: Seleccionar BNB Chain - esperar mensaje nuevo con botones inline
        log("Paso 5: Esperando botones de cadena...")
        msg = await wait_inline_message(client, bot, last_id)
        if not msg:
            log("No se recibio el menu de cadenas")
            return None
        log("Paso 5: Seleccionando BNB Chain - USDT...")
        last_id = msg.id
        await msg.click(data=b"cadena:bnb")
        await asyncio.sleep(DELAY)

        # Paso 6: Ingresar monto
        log(f"Paso 6: Ingresando monto: {amount_ars} ARS...")
        last_id2 = await get_last_msg_id(client, bot)
        await client.send_message(bot, str(amount_ars))

        # Paso 7: Confirmar - esperar mensaje nuevo con botones inline
        log("Paso 7: Esperando resumen de compra...")
        msg = await wait_inline_message(client, bot, last_id2)
        if not msg:
            log("No se recibio el resumen de compra")
            return None
        log("Paso 7: Confirmando compra...")
        last_id = msg.id
        await msg.click(data=b"confirmar")

        # Paso 8: Obtener link de MercadoPago
        log("Paso 8: Esperando link de MercadoPago...")
        msg = await wait_bot_message(client, bot, last_id)

        # Buscar el link en el mensaje
        mp_link = None
        if msg and msg.text:
            import re
            links = re.findall(r'https://www\.mercadopago\.com[^\s]+', msg.text)
            if links:
                mp_link = links[0]

        # Buscar en entidades del mensaje
        if not mp_link and msg and msg.entities:
            for entity in msg.entities:
                if hasattr(entity, 'url') and entity.url and 'mercadopago' in entity.url:
                    mp_link = entity.url
                    break

        if mp_link:
            log(f"Link de MercadoPago obtenido: {mp_link}")
            # Registrar en historial de fondeos
            _save_funding_record(amount_ars, mp_link)
            # Notificar a Jorge
            if ADMIN_CHAT_ID:
                await client.send_message(
                    ADMIN_CHAT_ID,
                    f"Superagente007 necesita fondos.\n\n"
                    f"Monto: {amount_ars} ARS\n"
                    f"Wallet destino: {AGENT_WALLET}\n\n"
                    f"Paga aqui:\n{mp_link}"
                )
                log("Notificacion enviada a Jorge")
            return mp_link
        else:
            log("No se encontro el link de MercadoPago en la respuesta")
            return None

    except Exception as e:
        log(f"Error en el flujo de fondeo: {e}")
        return None
    finally:
        await client.disconnect()


async def main():
    print("=== Prueba del Modulo de Fondeo ===\n")
    print("Iniciando flujo de fondeo con 1000 ARS (prueba)...")
    link = await fund_agent(1800)
    if link:
        print(f"\nLink de pago generado:\n{link}")
    else:
        print("\nNo se pudo generar el link de pago.")


if __name__ == "__main__":
    asyncio.run(main())
