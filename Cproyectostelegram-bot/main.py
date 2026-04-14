import os
import json
import time
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, PeerFloodError

# ==========================================
# SERVIDOR PARA RENDER (NECESARIO)
# ==========================================
app = Flask('')
@app.route('/')
def home(): return "Bot Online"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

t = Thread(target=run_flask, daemon=True)
t.start()

# ==========================================
# CONFIGURACIÓN
# ==========================================
API_ID = 39968832
API_HASH = "4e34b241319e3def1dcb7dfc13803371"
BOT_TOKEN ="8616101954:AAG8sLd-wAmP_mXLejLqDUTMHvoJF1qooDY"
ADMIN_ID = 7951708357

SESSION_DIR = "sessions"
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "users.json")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# --- FUNCIONES DE PERSISTENCIA ---
def load_users():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_users(users):
    with open(DATA_FILE, "w") as f: json.dump(users, f, indent=4)

def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE): return []
    with open(BLACKLIST_FILE, "r") as f: return json.load(f)

def save_blacklist(bl):
    with open(BLACKLIST_FILE, "w") as f: json.dump(bl, f, indent=4)

# --- INICIALIZACIÓN ---
bot = TelegramClient("bot_session", API_ID, API_HASH)
user_sessions = {}
admin_steps = {}
scheduled_tasks = {}

# ==========================================
# MEJORA DE VELOCIDAD: RESPUESTA RÁPIDA
# ==========================================

@bot.on(events.CallbackQuery)
async def global_answer(event):
    # Esto quita el "relojito" de carga al instante
    await event.answer()

# --- PANEL ADMIN ---
@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    await event.respond("👑 **Panel Admin**", buttons=[
        [Button.inline("➕ Añadir usuario", b"add_user")],
        [Button.inline("🗑️ Eliminar usuario", b"remove_user")],
        [Button.inline("📢 Enviar anuncio", b"broadcast")]
    ])

@bot.on(events.CallbackQuery(pattern=b'^(add_user|remove_user|broadcast)$'))
async def admin_btns(event):
    data = event.data.decode()
    admin_steps[event.sender_id] = {"step": "get_id", "action": data}
    await event.edit(f"📥 Ingresa el ID para {data}:")

# --- COMANDO START ---
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    # Verificar acceso rápido
    users = load_users()
    if str(uid) not in users and uid != ADMIN_ID:
        return await event.respond("⛔ Sin acceso.")

    # Conectar sesión si no existe en memoria
    if uid not in user_sessions:
        sp = os.path.join(SESSION_DIR, str(uid))
        if os.path.exists(f"{sp}.session"):
            cl = TelegramClient(sp, API_ID, API_HASH)
            await cl.connect()
            user_sessions[uid] = cl

    btns = [
        [Button.inline("📢 Enviar mensaje ahora", b"send_now")],
        [Button.inline("⏰ Programar spam", b"schedule_spam")],
        [Button.inline("🛑 Detener spam", b"stop_spam")],
        [Button.inline("🚫 Blacklist", b"manage_blacklist")]
    ]
    await event.respond("👋 **¡Menú Principal!**", buttons=btns)

# --- BOTONES DE SPAM ---
@bot.on(events.CallbackQuery(pattern=b'send_now'))
async def sn(event):
    uc = user_sessions.get(event.sender_id)
    if not uc: return await event.respond("❌ Reconecta con /start")
    msgs = await uc.get_messages('me', limit=10)
    btns = [[Button.inline(f"➡️ {m.text[:30] if m.text else 'Media'}", f"now_{m.id}")] for m in msgs]
    await event.edit("🎯 **Elige mensaje:**", buttons=btns)

@bot.on(events.CallbackQuery(pattern=b'now_[0-9]+'))
async def send_now_handler(event):
    mid = int(event.data.decode().split('_')[1])
    uc = user_sessions.get(event.sender_id)
    # Ejecutar en segundo plano para no bloquear el bot
    asyncio.create_task(send_mass(uc, mid, event.sender_id))

async def send_mass(uc, mid, uid):
    dialogs = await uc.get_dialogs()
    bl = load_blacklist()
    sc, fc = 0, 0
    msg = await bot.send_message(uid, "📤 Enviando...")
    for d in dialogs:
        if (d.is_group or d.is_channel) and d.id not in bl:
            try:
                await uc.forward_messages(d.id, mid, 'me')
                sc += 1
                await asyncio.sleep(0.5) # Pequeño delay para no saturar
            except: fc += 1
    await bot.edit_message(uid, msg.id, f"✅ Finalizado.\nÉxito: {sc} | Error: {fc}")

# --- BOTÓN VOLVER ---
@bot.on(events.CallbackQuery(pattern=b'back_to_menu'))
async def btm(event):
    btns = [[Button.inline("📢 Enviar ahora", b"send_now")], [Button.inline("⏰ Programar", b"schedule_spam")], [Button.inline("🚫 Blacklist", b"manage_blacklist")]]
    await event.edit("👋 **Menú Principal**", buttons=btns)

# --- EJECUCIÓN ---
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot funcionando al 100%")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
