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
def home(): return "¡Bot en línea! By Mateoz"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

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

# --- PERSISTENCIA ---
def load_json(path, default):
    if not os.path.exists(path): return default
    with open(path, "r") as f: return json.load(f)

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=4)

# --- INICIALIZACIÓN ---
bot = TelegramClient("bot_session", API_ID, API_HASH)
user_sessions = {}
pending_sessions = {}
admin_steps = {}
scheduled_tasks = {}

# --- UTILIDADES ---
async def get_client(uid):
    if uid in user_sessions: return user_sessions[uid]
    sp = os.path.join(SESSION_DIR, str(uid))
    if os.path.exists(f"{sp}.session"):
        client = TelegramClient(sp, API_ID, API_HASH)
        await client.connect()
        if await client.is_user_authorized():
            user_sessions[uid] = client
            return client
    return None

# --- COMANDOS ---
@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    await event.respond("👑 **Panel Admin**", buttons=[
        [Button.inline("➕ Añadir", b"add_user"), Button.inline("🗑️ Eliminar", b"remove_user")],
        [Button.inline("📅 Extender", b"extend_user"), Button.inline("📢 Anuncio", b"broadcast")]
    ])

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    users = load_json(DATA_FILE, {})
    if event.sender_id != ADMIN_ID and (str(event.sender_id) not in users or time.time() > users[str(event.sender_id)]["expires"]):
        return await event.respond("⛔ Sin acceso.")
    
    btns = [
        [Button.inline("📢 Enviar ahora", b"send_now")],
        [Button.inline("⏰ Programar spam", b"schedule_spam")],
        [Button.inline("🛑 Detener spam", b"stop_spam")],
        [Button.inline("🚫 Blacklist", b"manage_blacklist")]
    ]
    await event.respond("👋 **¡Bienvenido! Elige una opción:**", buttons=btns)

# --- MANEJO DE CALLBACKS (BOTONES) ---
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    uid = event.sender_id
    data = event.data.decode()
    
    # IMPORTANTE: Confirmar el click de inmediato para quitar el relojito
    await event.answer()

    if data == "back_to_menu":
        btns = [[Button.inline("📢 Enviar ahora", b"send_now")], [Button.inline("⏰ Programar spam", b"schedule_spam")], [Button.inline("🛑 Detener spam", b"stop_spam")], [Button.inline("🚫 Blacklist", b"manage_blacklist")]]
        await event.edit("👋 **Elige una opción:**", buttons=btns)

    elif data == "manage_blacklist":
        await show_blacklist_page(event, uid, 0)

    elif data.startswith("bl_page_"):
        await show_blacklist_page(event, uid, int(data.split("_")[2]))

    elif data.startswith("toggle_"):
        _, gid, pg = data.split("_")
        bl = load_json(BLACKLIST_FILE, [])
        gid = int(gid)
        if gid in bl: bl.remove(gid)
        else: bl.append(gid)
        save_json(BLACKLIST_FILE, bl)
        await show_blacklist_page(event, uid, int(pg))

    elif data == "send_now":
        uc = await get_client(uid)
        if not uc: return await event.respond("❌ Usa /start para conectar tu sesión.")
        msgs = await uc.get_messages('me', limit=15)
        btns = [[Button.inline(f"➡️ {m.text[:30] if m.text else 'Multimedia'}", f"now_{m.id}")] for m in msgs]
        await event.edit("🎯 **Selecciona mensaje para enviar ahora:**", buttons=btns)

    elif data.startswith("now_"):
        mid = int(data.split("_")[1])
        uc = await get_client(uid)
        asyncio.create_task(send_mass_message(uc, mid, uid))

    # --- Lógica de Admin ---
    elif data in ["add_user", "remove_user", "extend_user", "broadcast"]:
        if uid != ADMIN_ID: return
        admin_steps[uid] = {"step": "get_user_id", "action": data}
        if data == "broadcast":
            admin_steps[uid]["step"] = "await_broadcast"
            await event.edit("📝 Escribe el mensaje para el anuncio:")
        else:
            await event.edit(f"📥 Ingresa el ID para {data}:")

# --- SPAM MASIVO ---
async def send_mass_message(uc, mid, uid):
    bl = load_json(BLACKLIST_FILE, [])
    dialogs = await uc.get_dialogs()
    status = await bot.send_message(uid, "📤 **Iniciando envío masivo...**")
    sc, fc = 0, 0
    for d in dialogs:
        if (d.is_group or d.is_channel) and d.id not in bl:
            try:
                await uc.forward_messages(d.id, mid, 'me')
                sc += 1
                await asyncio.sleep(1) # Evitar Flood
            except: fc += 1
    await bot.edit_message(uid, status.id, f"✅ **Completado**\nÉxito: `{sc}` | Fallido: `{fc}`")

# --- BLACKLIST PAGINADA ---
async def show_blacklist_page(event, uid, page):
    uc = await get_client(uid)
    if not uc: return await event.respond("❌ Sesión no iniciada.")
    bl = load_json(BLACKLIST_FILE, [])
    dialogs = [d for d in await uc.get_dialogs() if d.is_group or d.is_channel]
    
    per_page = 8
    total_pages = (len(dialogs) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    current_dialogs = dialogs[page*per_page : (page+1)*per_page]
    
    btns = []
    for g in current_dialogs:
        emoji = "✅" if g.id not in bl else "❌"
        btns.append([Button.inline(f"{emoji} {g.name[:20]}", f"toggle_{g.id}_{page}")])
    
    nav = []
    if page > 0: nav.append(Button.inline("⬅️", f"bl_page_{page-1}"))
    if page < total_pages - 1: nav.append(Button.inline("➡️", f"bl_page_{page+1}"))
    if nav: btns.append(nav)
    btns.append([Button.inline("🔙 Menú Principal", b"back_to_menu")])
    
    await event.edit(f"🚫 **Gestión de Blacklist** ({page+1}/{total_pages})", buttons=btns)

# --- FLUJO DE TEXTO (ADMIN Y CÓDIGOS) ---
@bot.on(events.NewMessage)
async def handle_text(event):
    uid = event.sender_id
    if uid not in admin_steps: return
    
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
                # Lógica de borrar usuario...
                del admin_steps[uid]
                await event.respond(f"🗑️ `{target}` eliminado.")
        except: await event.respond("❌ ID inválido.")
    
    elif step_data["step"] == "get_phone":
        step_data["phone"] = text
        step_data["step"] = "get_duration_add"
        await event.respond("⏳ ¿Meses?", buttons=[[Button.inline("1 Mes", b"add_1"), Button.inline("3 Meses", b"add_3")]])

# --- EJECUCIÓN ---
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot By Mateoz Online")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
