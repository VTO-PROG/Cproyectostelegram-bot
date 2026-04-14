import os
import json
import time
import asyncio
from flask import Flask
from threading import Thread
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, PeerFloodError

# ==========================================
# CAMBIO MÍNIMO 1: SERVIDOR PARA RENDER
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot Online"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# Iniciar Flask en un hilo separado para que no bloquee al bot
t = Thread(target=run_flask)
t.daemon = True
t.start()

# ==========================================
# TU CÓDIGO ORIGINAL (CONFIGURACIÓN)
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

# --- TUS FUNCIONES ORIGINALES ---
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
    u_id_str = str(user_id)
    if u_id_str in users:
        session_file = os.path.join(SESSION_DIR, f"{u_id_str}.session")
        if os.path.exists(session_file): os.remove(session_file)
        del users[u_id_str]
        save_users(users)

def extend_user(user_id, months):
    users = load_users()
    u_id_str = str(user_id)
    if u_id_str in users:
        current_expiry = users[u_id_str]["expires"]
        base_time = max(time.time(), current_expiry)
        users[u_id_str]["expires"] = int(base_time) + 60*60*24*30*months
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

# --- PANEL ADMIN Y TUS BOTONES ---
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
    admin_steps[event.sender_id] = {"step": "get_user_id", "action": data}
    if data == "broadcast":
        admin_steps[event.sender_id]["step"] = "await_broadcast"
        await event.edit("📝 Escribe el mensaje para el anuncio:")
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
                await event.respond("📱 Ingresa número (+52...):")
            elif step_data["action"] == "remove":
                remove_user(target)
                await event.respond(f"🗑️ `{target}` eliminado.")
                del admin_steps[uid]
            elif step_data["action"] == "extend":
                step_data["step"] = "get_duration_extend"
                await event.respond(f"⏳ Meses:", buttons=[[Button.inline("1 Mes", b"ext_1"), Button.inline("3 Meses", b"ext_3")]])
        except: await event.respond("❌ ID inválido.")
    elif step_data["step"] == "get_phone":
        step_data["phone"] = text
        step_data["step"] = "get_duration_add"
        await event.respond("⏳ ¿Meses?", buttons=[[Button.inline("1 Mes", b"add_1"), Button.inline("3 Meses", b"add_3")]])
    elif step_data["step"] == "await_code":
        pending = pending_sessions.get(step_data["user_id"])
        if not pending: return
        try:
            await pending["client"].sign_in(pending["phone"], text)
            user_sessions[step_data["user_id"]] = pending["client"]
            save_access(step_data["user_id"], pending["phone"], step_data["duration"])
            await event.respond("✅ Sesión activa."); del admin_steps[uid]
        except Exception as e: await event.respond(f"❌ Error: {e}")
    elif step_data["step"] == "await_broadcast":
        users = load_users()
        for u_id in users:
            try: await bot.send_message(int(u_id), f"📢 {text}")
            except: pass
        await event.respond("✅ Anuncio enviado."); del admin_steps[uid]

@bot.on(events.CallbackQuery(pattern=b'(add|ext)_[0-9]+'))
async def handle_durations(event):
    parts = event.data.decode().split('_')
    months = int(parts[1])
    step_data = admin_steps[event.sender_id]
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

# --- COMANDO START ---
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    if uid != ADMIN_ID and not has_access(uid):
        await event.respond("⛔ No tienes acceso.")
        return
    
    # CAMBIO MÍNIMO 2: Corrección de sintaxis para evitar el error de Render
    user_client = user_sessions.get(uid)
    is_auth = False
    if user_client:
        is_auth = await user_client.is_user_authorized()

    if not user_client or not is_auth:
        sp = os.path.join(SESSION_DIR, str(uid))
        if os.path.exists(f"{sp}.session"):
            user_client = TelegramClient(sp, API_ID, API_HASH)
            await user_client.connect()
            user_sessions[uid] = user_client
        else:
            if uid != ADMIN_ID: await event.respond("❌ Sesión no encontrada."); return

    buttons = [
        [Button.inline("📢 Enviar mensaje ahora", data="send_now")],
        [Button.inline("⏰ Programar spam", data="schedule_spam")],
        [Button.inline("🛑 Detener spam", data="stop_spam")],
        [Button.inline("🚫 Blacklist de grupos", data="manage_blacklist")]
    ]
    await event.respond("👋 **¡Bienvenido! Elige una opción:**", buttons=buttons)

# --- TUS FUNCIONES DE SPAM Y BLACKLIST EXACTAS ---
@bot.on(events.CallbackQuery(pattern=b'manage_blacklist'))
async def m_bl(event): await show_blacklist_page(event, event.sender_id, 0)

@bot.on(events.CallbackQuery(pattern=b'bl_page_(\d+)'))
async def bl_nav(event): await show_blacklist_page(event, event.sender_id, int(event.pattern_match.group(1)))

@bot.on(events.CallbackQuery(pattern=b'toggle_(-?\d+)_(\d+)'))
async def bl_tog(event):
    gid, pg = int(event.pattern_match.group(1)), int(event.pattern_match.group(2))
    bl = load_blacklist()
    if gid in bl: bl.remove(gid)
    else: bl.append(gid)
    save_blacklist(bl)
    await show_blacklist_page(event, event.sender_id, pg)

async def show_blacklist_page(event, uid, page=0):
    user_client = user_sessions.get(uid)
    blacklist = load_blacklist()
    all_groups = await get_user_groups(user_client)
    g_per_p = 8
    total_pages = (len(all_groups) + g_per_p - 1) // g_per_p
    groups = all_groups[page*g_per_p : (page+1)*g_per_p]
    buttons = [[Button.inline(f"{'✅' if g.id not in blacklist else '❌'} {g.name[:15]}", f"toggle_{g.id}_{page}")] for g in groups]
    nav = []
    if page > 0: nav.append(Button.inline("⬅️", f"bl_page_{page-1}"))
    if page < total_pages - 1: nav.append(Button.inline("➡️", f"bl_page_{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([Button.inline("🔙 Volver al menú", data="back_to_menu")])
    await event.edit(f"🚫 **Blacklist** ({page+1}/{total_pages})", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'send_now'))
async def sn(event): await show_saved_messages(event, "now")

@bot.on(events.CallbackQuery(pattern=b'schedule_spam'))
async def ss(event): await show_saved_messages(event, "schedule")

async def show_saved_messages(event, mode):
    uc = user_sessions.get(event.sender_id)
    msgs = await uc.get_messages('me', limit=15)
    btns = [[Button.inline(f"➡️ {m.text[:40] if m.text else 'Multimedia'}", f"{mode}_{m.id}")] for m in msgs]
    await event.edit(f"**Elige un mensaje:**", buttons=btns)

@bot.on(events.CallbackQuery(pattern=b'schedule_[0-9]+'))
async def ask_int(event):
    mid = int(event.data.decode().split('_')[1])
    admin_steps[event.sender_id] = {"step": "await_interval", "msg_id": mid}
    await event.edit("⏳ ¿Cada cuántos minutos?")

@bot.on(events.NewMessage(func=lambda e: e.sender_id in admin_steps and admin_steps[e.sender_id]["step"] == "await_interval"))
async def save_int(event):
    try: mins = int(event.raw_text.strip())
    except: return
    uid, mid = event.sender_id, admin_steps[event.sender_id]["msg_id"]
    del admin_steps[uid]
    async def task():
        uc = user_sessions.get(uid)
        while True:
            await send_mass(uc, mid, uid)
            await asyncio.sleep(mins * 60)
    scheduled_tasks.setdefault(uid, {})[mid] = asyncio.create_task(task())
    await event.respond(f"✅ Programado cada {mins} min.")

async def send_mass(uc, mid, uid):
    bl, sc, fc = load_blacklist(), 0, 0
    dialogs = await uc.get_dialogs()
    st = await bot.send_message(uid, "📤 Enviando...")
    for d in dialogs:
        if (d.is_group or d.is_channel) and d.id not in bl:
            try: await uc.forward_messages(d.id, mid, 'me'); sc += 1
            except: fc += 1
    await bot.edit_message(uid, st.id, f"✅ Éxito: {sc} | Fallas: {fc}")

@bot.on(events.CallbackQuery(pattern=b'now_[0-9]+'))
async def hn(event): await send_mass(user_sessions.get(event.sender_id), int(event.data.decode().split('_')[1]), event.sender_id)

@bot.on(events.CallbackQuery(pattern=b'stop_spam'))
async def st_s(event):
    tasks = scheduled_tasks.get(event.sender_id, {})
    btns = [[Button.inline(f"🛑 Detener ID {mid}", f"cancel_{mid}")] for mid in tasks.keys()]
    await event.edit("🛑 **Detener:**", buttons=btns) if btns else await event.edit("ℹ️ Sin tareas.")

@bot.on(events.CallbackQuery(pattern=b'cancel_[0-9]+'))
async def can_t(event):
    mid = int(event.data.decode().split('_')[1])
    t = scheduled_tasks.get(event.sender_id, {}).pop(mid, None)
    if t: t.cancel(); await event.edit(f"🛑 Detenido.")

@bot.on(events.CallbackQuery(pattern=b'back_to_menu'))
async def btm(event):
    btns = [[Button.inline("📢 Enviar ahora", b"send_now")], [Button.inline("⏰ Programar spam", b"schedule_spam")], [Button.inline("🛑 Detener spam", b"stop_spam")], [Button.inline("🚫 Blacklist", b"manage_blacklist")]]
    await event.edit("👋 **¡Bienvenido!**", buttons=btns)

# --- EJECUCIÓN ---
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot Online")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
