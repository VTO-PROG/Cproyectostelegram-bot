import os
import json
import time
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, PeerFloodError

# ==========================================
# CAMBIO 1: ARRANCAR EL SERVIDOR WEB DE INMEDIATO
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "¡Bot de Telegram en línea! By Mateoz"

def run_flask():
    # Usamos el puerto que da Render o el 10000 que es su estándar
    port = int(os.environ.get('PORT', 10000)) 
    app.run(host='0.0.0.0', port=port)

# Lanzamos el servidor en un hilo ANTES de configurar lo demás
t = Thread(target=run_flask)
t.daemon = True
t.start()
print("🚀 Servidor de desbloqueo para Render iniciado...")

# ==========================================
# TU CONFIGURACIÓN ORIGINAL (SIN CAMBIOS)
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

# --- TODAS TUS FUNCIONES ORIGINALES ---
def load_users():
    if not os.path.exists(DATA_FILE): return {}
    try:
        with open(DATA_FILE, "r") as f: return json.load(f)
    except: return {}

def save_users(users):
    with open(DATA_FILE, "w") as f: json.dump(users, f, indent=4)

def save_access(user_id, phone, months):
    users = load_users()
    expires = int(time.time()) + 60*60*24*30*months
    users[str(user_id)] = {"phone": phone, "expires": expires}
    save_users(users)

def has_access(user_id):
    users = load_users()
    user = users.get(str(user_id))
    return user and time.time() < user["expires"]

def remove_user(user_id):
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str in users:
        session_file = os.path.join(SESSION_DIR, f"{user_id_str}.session")
        if os.path.exists(session_file): os.remove(session_file)
        del users[user_id_str]
        save_users(users)

def extend_user(user_id, months):
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str in users:
        current_expiry = users[user_id_str]["expires"]
        base_time = max(time.time(), current_expiry)
        users[user_id_str]["expires"] = int(base_time) + 60*60*24*30*months
        save_users(users)

def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE): return []
    try:
        with open(BLACKLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, "w") as f: json.dump(blacklist, f, indent=4)

async def get_user_groups(user_client):
    dialogs = await user_client.get_dialogs()
    return [dialog for dialog in dialogs if dialog.is_group or dialog.is_channel]

# --- INICIALIZACIÓN ---
bot = TelegramClient("bot_session", API_ID, API_HASH)
user_sessions = {}
pending_sessions = {}
admin_steps = {}
scheduled_tasks = {}

# --- TUS EVENTOS @bot.on (START) ---
@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    await event.respond("👑 **Panel de Administrador** 👑", buttons=[
        [Button.inline("➕ Añadir usuario", b"add_user")],
        [Button.inline("🗑️ Eliminar usuario", b"remove_user")],
        [Button.inline("📅 Extender acceso", b"extend_user")],
        [Button.inline("📢 Enviar anuncio", b"broadcast")]
    ])

@bot.on(events.CallbackQuery(pattern=b'^(add_user|remove_user|extend_user|broadcast)$'))
async def admin_buttons(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode()
    if data == "add_user":
        admin_steps[event.sender_id] = {"step": "get_user_id", "action": "add"}
        await event.edit("📥 Ingresa el ID de Telegram del nuevo usuario:")
    elif data == "remove_user":
        admin_steps[event.sender_id] = {"step": "get_user_id", "action": "remove"}
        await event.edit("🗑️ Ingresa el ID del usuario a eliminar:")
    elif data == "extend_user":
        admin_steps[event.sender_id] = {"step": "get_user_id", "action": "extend"}
        await event.edit("⏳ Ingresa el ID del usuario a extender:")
    elif data == "broadcast":
        admin_steps[event.sender_id] = {"step": "await_broadcast"}
        await event.edit("📝 Escribe el mensaje para todos:")

@bot.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID and e.sender_id in admin_steps))
async def admin_flow(event):
    user_id = event.sender_id
    step_data = admin_steps[user_id]
    text = event.raw_text.strip()
    if step_data["step"] == "get_user_id":
        try:
            target_id = int(text)
            step_data["user_id"] = target_id
            if step_data["action"] == "add":
                step_data["step"] = "get_phone"
                await event.respond("📱 Ingresa el número (+52...):")
            elif step_data["action"] == "remove":
                remove_user(target_id)
                await event.respond(f"🗑️ `{target_id}` eliminado.")
                del admin_steps[user_id]
            elif step_data["action"] == "extend":
                step_data["step"] = "get_duration_extend"
                await event.respond(f"⏳ Meses para `{target_id}`:", buttons=[[Button.inline("1 Mes", b"ext_1"), Button.inline("3 Meses", b"ext_3")]])
        except: await event.respond("❌ ID inválido.")
    elif step_data["step"] == "get_phone":
        step_data["phone"] = text
        step_data["step"] = "get_duration_add"
        await event.respond("⏳ Meses de acceso:", buttons=[[Button.inline("1 Mes", b"add_1"), Button.inline("3 Meses", b"add_3")]])
    elif step_data["step"] == "await_code":
        code = text
        target_id = step_data["user_id"]
        pending = pending_sessions.get(target_id)
        if not pending: return
        try:
            await pending["client"].sign_in(pending["phone"], code)
            user_sessions[target_id] = pending["client"]
            save_access(target_id, pending["phone"], step_data["duration"])
            del pending_sessions[target_id]
            del admin_steps[user_id]
            await event.respond(f"✅ Usuario `{target_id}` activo.")
        except Exception as e: await event.respond(f"❌ Error: {e}")
    elif step_data["step"] == "await_broadcast":
        users = load_users()
        for uid_str, d in users.items():
            if time.time() < d["expires"]:
                try: await bot.send_message(int(uid_str), f"📢 {text}")
                except: pass
        await event.respond("✅ Anuncio enviado.")
        del admin_steps[user_id]

@bot.on(events.CallbackQuery(pattern=b'(add|ext)_[0-9]+'))
async def handle_duration_buttons(event):
    if event.sender_id != ADMIN_ID or event.sender_id not in admin_steps: return
    parts = event.data.decode().split('_')
    months = int(parts[1])
    step_data = admin_steps[event.sender_id]
    if parts[0] == 'add':
        step_data["duration"] = months
        phone, target_id = step_data["phone"], step_data["user_id"]
        client = TelegramClient(os.path.join(SESSION_DIR, str(target_id)), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        pending_sessions[target_id] = {'client': client, 'phone': phone}
        step_data["step"] = "await_code"
        await event.edit("📨 Ingresa el código:")
    else:
        extend_user(step_data["user_id"], months)
        await event.edit("✅ Extendido.")
        del admin_steps[event.sender_id]

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    if uid != ADMIN_ID and not has_access(uid):
        await event.respond("⛔ Sin acceso.")
        return
    user_client = user_sessions.get(uid)
    if not user_client or not await
