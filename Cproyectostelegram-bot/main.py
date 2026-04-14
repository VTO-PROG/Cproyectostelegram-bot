import os
import json
import time
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, PeerFloodError

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "¡Bot en línea! By Mateoz"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# Iniciar Flask antes de todo
t = Thread(target=run_flask)
t.daemon = True
t.start()

# --- CONFIGURACIÓN ---
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

# --- FUNCIONES ---
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
    u_str = str(user_id)
    if u_str in users:
        sf = os.path.join(SESSION_DIR, f"{u_str}.session")
        if os.path.exists(sf): os.remove(sf)
        del users[u_str]
        save_users(users)

def extend_user(user_id, months):
    users = load_users()
    u_str = str(user_id)
    if u_str in users:
        base = max(time.time(), users[u_str]["expires"])
        users[u_str]["expires"] = int(base) + 60*60*24*30*months
        save_users(users)

def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE): return []
    try:
        with open(BLACKLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_blacklist(bl):
    with open(BLACKLIST_FILE, "w") as f: json.dump(bl, f, indent=4)

async def get_user_groups(user_client):
    dialogs = await user_client.get_dialogs()
    return [d for d in dialogs if d.is_group or d.is_channel]

# --- INICIALIZACIÓN ---
bot = TelegramClient("bot_session", API_ID, API_HASH)
user_sessions = {}
pending_sessions = {}
admin_steps = {}
scheduled_tasks = {}

@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    await event.respond("👑 **Panel Admin**", buttons=[
        [Button.inline("➕ Añadir", b"add_user"), Button.inline("🗑️ Eliminar", b"remove_user")],
        [Button.inline("📅 Extender", b"extend_user"), Button.inline("📢 Anuncio", b"broadcast")]
    ])

@bot.on(events.CallbackQuery(pattern=b'^(add_user|remove_user|extend_user|broadcast)$'))
async def admin_buttons(event):
    if event.sender_id != ADMIN_ID: return
    data = event.data.decode()
    admin_steps[event.sender_id] = {"step": "get_user_id", "action": data}
    if data == "broadcast":
        admin_steps[event.sender_id]["step"] = "await_broadcast"
        await event.edit("📝 Escribe el mensaje:")
    else:
        await event.edit(f"📥 Ingresa el ID para {data}:")

@bot.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID and e.sender_id in admin_steps))
async def admin_flow(event):
    uid = event.sender_id
    step_data = admin_steps[uid]
    text = event.raw_text.strip()
    
    if step_data["step"] == "get_user_id":
        try:
            target = int(text)
            step_data["user_id"] = target
            if step_data["action"] == "add":
                step_data["step"] = "get_phone"
                await event.respond("📱 Teléfono (+52...):")
            elif step_data["action"] == "remove":
                remove_user(target)
                await event.respond("✅ Eliminado."); del admin_steps[uid]
            elif step_data["action"] == "extend":
                step_data["step"] = "get_duration_extend"
                await event.respond("⏳ Meses:", buttons=[[Button.inline("1 Mes", b"ext_1"), Button.inline("3 Meses", b"ext_3")]])
        except: await event.respond("❌ ID inválido.")
    elif step_data["step"] == "get_phone":
        step_data["phone"] = text
        step_data["step"] = "get_duration_add"
        await event.respond("⏳ Meses:", buttons=[[Button.inline("1 Mes", b"add_1"), Button.inline("3 Meses", b"add_3")]])
    elif step_data["step"] == "await_code":
        pending = pending_sessions.get(step_data["user_id"])
        try:
            await pending["client"].sign_in(pending["phone"], text)
            user_sessions[step_data["user_id"]] = pending["client"]
            save_access(step_data["user_id"], pending["phone"], step_data["duration"])
            await event.respond("✅ Usuario activo."); del admin_steps[uid]
        except Exception as e: await event.respond(f"❌ Error: {e}")
    elif step_data["step"] == "await_broadcast":
        users = load_users()
        for u_id in users:
            try: await bot.send_message(int(u_id), f"📢 {text}")
            except: pass
        await event.respond("✅ Enviado."); del admin_steps[uid]

@bot.on(events.CallbackQuery(pattern=b'(add|ext)_[0-9]+'))
async def handle_duration(event):
    parts = event.data.decode().split('_')
    step_data = admin_steps[event.sender_id]
    months = int(parts[1])
    if parts[0] == 'add':
        step_data["duration"] = months
        client = TelegramClient(os.path.join(SESSION_DIR, str(step_data["user_id"])), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(step_data["phone"])
        pending_sessions[step_data["user_id"]] = {'client': client, 'phone': step_data["phone"]}
        step_data["step"] = "await_code"
        await event.edit("📨 Ingresa el código:")
    else:
        extend_user(step_data["user_id"], months)
        await event.edit("✅ Extendido."); del admin_steps[event.sender_id]

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    if uid != ADMIN_ID and not has_access(uid):
        await event.respond("⛔ Sin acceso.")
        return
    
    # CORRECCIÓN DE LA LÍNEA QUE DIO ERROR:
    user_client = user_sessions.get(uid)
    authorized = False
    if user_client:
        authorized = await user_client.is_user_authorized()

    if not user_client or not authorized:
        sp = os.path.join(SESSION_DIR, str(uid))
        if os.path.exists(f"{sp}.session"):
            user_client = TelegramClient(sp, API_ID, API_HASH)
            await user_client.connect()
            user_sessions[uid] = user_client
        else:
            await event.respond("❌ No hay sesión activa."); return

    btns = [[Button.inline("📢 Enviar ahora", b"send_now")], [Button.inline("⏰ Programar", b"schedule_spam")], [Button.inline("🚫 Blacklist", b"manage_blacklist")]]
    await event.respond("👋 Bienvenido", buttons=btns)

# --- SPAM LÓGICA ---
async def send_mass(uc, mid, uid):
    bl = load_blacklist()
    dialogs = await uc.get_dialogs()
    sc, fc = 0, 0
    for d in dialogs:
        if (d.is_group or d.is_channel) and d.id not in bl:
            try: await uc.forward_messages(d.id, mid, 'me'); sc += 1
            except: fc += 1
    await bot.send_message(uid, f"✅ Fin. Éxito: {sc} | Error: {fc}")

@bot.on(events.CallbackQuery(pattern=b'send_now'))
async def now(event):
    uc = user_sessions.get(event.sender_id)
    msgs = await uc.get_messages('me', limit=1)
    if msgs: await send_mass(uc, msgs[0].id, event.sender_id)

@bot.on(events.CallbackQuery(pattern=b'manage_blacklist'))
async def ml(event):
    uc = user_sessions.get(event.sender_id)
    bl = load_blacklist()
    grps = await get_user_groups(uc)
    btns = [[Button.inline(f"{'✅' if g.id not in bl else '❌'} {g.name[:15]}", f"tog_{g.id}")] for g in grps[:10]]
    await event.edit("🚫 Blacklist", buttons=btns)

@bot.on(events.CallbackQuery(pattern=b'tog_(-?\d+)'))
async def tog(event):
    gid = int(event.pattern_match.group(1))
    bl = load_blacklist()
    if gid in bl: bl.remove(gid)
    else: bl.append(gid)
    save_blacklist(bl)
    await event.answer("Cambiado")

# --- EJECUCIÓN ---
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot iniciado")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
