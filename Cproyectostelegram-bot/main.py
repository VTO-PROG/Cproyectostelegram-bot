import os
from flask import Flask
from threading import Thread

# --- INICIO DEL TRUCO PARA RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "¡Bot de Telegram en línea!"

def run():
    # Render nos asigna un puerto automáticamente
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

import os
import json
import time
import asyncio
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, PeerFloodError

# --- CONFIGURACIÓN ---
API_ID = 39968832
API_HASH = "4e34b241319e3def1dcb7dfc13803371"
BOT_TOKEN = os.environ.get(¨BOT_TOKEN¨)
ADMIN_ID = 7951708357

# --- RUTAS Y CARPETAS ---
SESSION_DIR = "sessions"
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "users.json")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# --- FUNCIONES DE USUARIOS ---
def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)

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
        if os.path.exists(session_file):
            os.remove(session_file)
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

# --- FUNCIONES DE BLACKLIST ---
def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE):
        return []
    try:
        with open(BLACKLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(blacklist, f, indent=4)

async def get_user_groups(user_client):
    dialogs = await user_client.get_dialogs()
    return [dialog for dialog in dialogs if dialog.is_group or dialog.is_channel]

# --- INICIALIZACIÓN ---
bot = TelegramClient("bot_session", API_ID, API_HASH)
user_sessions = {}
pending_sessions = {}
admin_steps = {}
scheduled_tasks = {}

# --- PANEL ADMIN ---
@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID:
        return
    await event.respond(
        "👑 **Panel de Administrador** 👑\n\nElige una opción:",
        buttons=[
            [Button.inline("➕ Añadir usuario", b"add_user")],
            [Button.inline("🗑️ Eliminar usuario", b"remove_user")],
            [Button.inline("📅 Extender acceso", b"extend_user")],
            [Button.inline("📢 Enviar anuncio", b"broadcast")]
        ]
    )

# --- ADMIN CALLBACKS ---
@bot.on(events.CallbackQuery(pattern=b'^(add_user|remove_user|extend_user|broadcast)$'))
async def admin_buttons(event):
    if event.sender_id != ADMIN_ID:
        return
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
        await event.edit("📝 Escribe el mensaje que quieres enviar a todos los usuarios con acceso:")

# --- ADMIN MENSAJES ---
@bot.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID and e.sender_id in admin_steps))
async def admin_flow(event):
    user_id = event.sender_id
    step_data = admin_steps[user_id]
    text = event.raw_text.strip()

    if step_data["step"] == "get_user_id":
        try:
            target_id = int(text)
            step_data["user_id"] = target_id
            action = step_data["action"]
            if action == "add":
                step_data["step"] = "get_phone"
                await event.respond("📱 Ingresa el número de teléfono del usuario (formato internacional, ej: +52...):")
            elif action == "remove":
                remove_user(target_id)
                await event.respond(f"🗑️ Usuario `{target_id}` eliminado correctamente.")
                del admin_steps[user_id]
            elif action == "extend":
                step_data["step"] = "get_duration_extend"
                await event.respond(f"⏳ ¿Cuántos meses quieres agregar a `{target_id}`?", buttons=[
                    [Button.inline("1 Mes", b"ext_1"), Button.inline("3 Meses", b"ext_3")]
                ])
        except ValueError:
            await event.respond("❌ ID inválido. Debe ser un número.")

    elif step_data["step"] == "get_phone":
        step_data["phone"] = text
        step_data["step"] = "get_duration_add"
        await event.respond("⏳ ¿Cuántos meses de acceso le darás?", buttons=[
            [Button.inline("1 Mes", b"add_1"), Button.inline("3 Meses", b"add_3")]
        ])

    elif step_data["step"] == "await_code":
        code = text
        target_id = step_data["user_id"]
        pending = pending_sessions.get(target_id)
        if not pending:
            await event.respond("❌ No hay ninguna sesión pendiente para este usuario.")
            del admin_steps[user_id]
            return
        try:
            await pending["client"].sign_in(pending["phone"], code)
            user_sessions[target_id] = pending["client"]
            save_access(target_id, pending["phone"], step_data["duration"])
            del pending_sessions[target_id]
            del admin_steps[user_id]
            await event.respond(f"✅ ¡Éxito! Usuario `{target_id}` añadido y sesión iniciada. 🎉")
        except Exception as e:
            await event.respond(f"❌ Error al verificar el código: {e}")
            pending_sessions.pop(target_id, None)
            del admin_steps[user_id]

    elif step_data["step"] == "await_broadcast":
        message = text
        users = load_users()
        count = 0
        for uid_str, data in users.items():
            if time.time() < data["expires"]:
                try:
                    await bot.send_message(int(uid_str), f"📢 *Anuncio del administrador:*\n\n{message}")
                    count += 1
                except Exception as e:
                    print(f"❌ No se pudo enviar a {uid_str}: {e}")
        await event.respond(f"✅ Mensaje enviado a {count} usuario(s).")
        del admin_steps[user_id]

# --- ADMIN DURACIÓN BOTONES ---
@bot.on(events.CallbackQuery(pattern=b'(add|ext)_[0-9]+'))
async def handle_duration_buttons(event):
    if event.sender_id != ADMIN_ID or event.sender_id not in admin_steps:
        return
    parts = event.data.decode().split('_')
    action_type = parts[0]
    months = int(parts[1])
    step_data = admin_steps[event.sender_id]

    if action_type == 'add' and step_data.get("action") == "add":
        step_data["duration"] = months
        phone = step_data["phone"]
        target_id = step_data["user_id"]
        client = TelegramClient(os.path.join(SESSION_DIR, str(target_id)), API_ID, API_HASH)

        try:
            await client.connect()
            await client.send_code_request(phone)
            pending_sessions[target_id] = {'client': client, 'phone': phone}
            step_data["step"] = "await_code"
            await event.edit("📨 Código de inicio enviado. Pídeselo al usuario e ingrésalo aquí.")
        except Exception as e:
            await event.edit(f"❌ Error al solicitar el código: {e}")
            del admin_steps[event.sender_id]

    elif action_type == 'ext' and step_data.get("action") == "extend":
        target_id = step_data["user_id"]
        extend_user(target_id, months)
        await event.edit(f"✅ Acceso extendido por {months} mes(es) para el usuario `{target_id}`.")
        del admin_steps[event.sender_id]

# --- COMANDO START ---
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    if uid != ADMIN_ID and not has_access(uid):
        await event.respond("⛔ No tienes acceso a este bot. Contacta al administrador.")
        return

    user_client = user_sessions.get(uid)
    
    # CAMBIO OBLIGATORIO PARA RENDER: Separar el await del 'if not'
    is_auth = False
    if user_client:
        is_auth = await user_client.is_user_authorized()

    if not user_client or not is_auth:
        status_msg = await event.respond("🔄 Recargando tu sesión, por favor espera un momento...")
        session_path = os.path.join(SESSION_DIR, str(uid))
        if not os.path.exists(f"{session_path}.session"):
            await status_msg.edit("❌ Error: Tu sesión no se encontró.")
            return

        user_client = TelegramClient(session_path, API_ID, API_HASH)
        await user_client.connect()

        if not await user_client.is_user_authorized():
            await status_msg.edit("❌ Tu sesión ha expirado o fue revocada. Contacta al administrador.")
            return

        user_sessions[uid] = user_client
        await status_msg.delete()

    buttons = [
        [Button.inline("📢 Enviar mensaje ahora", data="send_now")],
        [Button.inline("⏰ Programar spam", data="schedule_spam")],
        [Button.inline("🛑 Detener spam", data="stop_spam")],
        [Button.inline("🚫 Blacklist de grupos", data="manage_blacklist")]
    ]
    await event.respond("👋 **¡Bienvenido! Elige una opción:**", buttons=buttons)

# --- COMANDO SUB ---
@bot.on(events.NewMessage(pattern="/sub"))
async def show_subscription(event):
    uid = event.sender_id
    users = load_users()
    user_data = users.get(str(uid))
    
    if not user_data:
        await event.respond("⛔ No tienes una suscripción activa. Contacta al administrador.")
        return
    
    expires_timestamp = user_data["expires"]
    current_time = time.time()
    remaining_seconds = expires_timestamp - current_time
    
    if remaining_seconds <= 0:
        await event.respond("⚠️ Tu suscripción ha expirado. Contacta al administrador para renovar.")
        return
    
    remaining_days = int(remaining_seconds // (60 * 60 * 24))
    remaining_hours = int((remaining_seconds % (60 * 60 * 24)) // (60 * 60))
    
    phone_number = user_data.get("phone", "N/A")
    
    response = (
        "📅 **Estado de tu suscripción** 📅\n\n"
        f"📱 Número asociado: `{phone_number}`\n"
        f"⏳ Tiempo restante: `{remaining_days} días y {remaining_hours} horas`\n\n"
        f"📆 Fecha de expiración: <code>{time.strftime('%d/%m/%Y %H:%M', time.localtime(expires_timestamp))}</code>"
    )
    
    await event.respond(response, parse_mode='html')

# --- GESTIÓN DE BLACKLIST PAGINADA ---
async def show_blacklist_page(event, uid, page=0):
    try:
        user_client = user_sessions.get(uid)
        if not user_client:
            await event.respond("❌ Primero inicia sesión con /start")
            return
        
        blacklist = load_blacklist()
        all_groups = await get_user_groups(user_client)
        
        if not all_groups:
            await event.edit("ℹ️ No estás en ningún grupo o canal.")
            return
        
        # Dividir en páginas de 8 grupos cada una
        groups_per_page = 8
        total_pages = (len(all_groups) + groups_per_page - 1) // groups_per_page
        page = max(0, min(page, total_pages - 1))
        groups = all_groups[page*groups_per_page : (page+1)*groups_per_page]
        
        buttons = []
        for group in groups:
            group_id = group.id
            group_name = group.name or f"Grupo {group_id}"
            is_blacklisted = group_id in blacklist
            emoji = "✅" if not is_blacklisted else "❌"
            
            # Limitar longitud del nombre para el botón
            display_name = (group_name[:15] + '...') if len(group_name) > 15 else group_name
            buttons.append([
                Button.inline(
                    f"{emoji} {display_name}", 
                    data=f"toggle_{group_id}_{page}"  # Incluir página actual en el callback
                )
            ])
        
        # Botones de navegación
        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("⬅️ Anterior", data=f"bl_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(Button.inline("Siguiente ➡️", data=f"bl_page_{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([Button.inline("🔙 Volver al menú", data="back_to_menu")])
        
        await event.edit(
            f"🚫 **Blacklist de Grupos** (Página {page+1}/{total_pages})\n\n"
            "✅ = Recibe spam\n"
            "❌ = No recibe spam\n\n"
            "Haz clic en un grupo para cambiar su estado:",
            buttons=buttons
        )
    except Exception as e:
        print(f"Error en show_blacklist_page: {e}")
        await event.respond("⚠️ Ocurrió un error al cargar los grupos. Intenta de nuevo.")

@bot.on(events.CallbackQuery(pattern=b'manage_blacklist'))
async def manage_blacklist(event):
    await show_blacklist_page(event, event.sender_id, 0)

@bot.on(events.CallbackQuery(pattern=b'bl_page_(\d+)'))
async def blacklist_page_nav(event):
    page = int(event.pattern_match.group(1))
    await show_blacklist_page(event, event.sender_id, page)

@bot.on(events.CallbackQuery(pattern=b'toggle_(-?\d+)_(\d+)'))
async def toggle_blacklist(event):
    group_id = int(event.pattern_match.group(1))
    page = int(event.pattern_match.group(2))
    uid = event.sender_id
    blacklist = load_blacklist()
    
    if group_id in blacklist:
        blacklist.remove(group_id)
        action = "removido de"
    else:
        blacklist.append(group_id)
        action = "añadido a"
    
    save_blacklist(blacklist)
    
    # Notificación rápida
    try:
        user_client = user_sessions.get(uid)
        group = await user_client.get_entity(group_id)
        group_name = group.title if hasattr(group, 'title') else f"Grupo {group_id}"
        await event.answer(f"Grupo '{group_name[:30]}' {action} la blacklist")
    except:
        await event.answer(f"Grupo ID {group_id} {action} la blacklist")
    
    # Refrescar la página actual
    await show_blacklist_page(event, uid, page)

@bot.on(events.CallbackQuery(pattern=b'back_to_menu'))
async def back_to_menu(event):
    uid = event.sender_id
    buttons = [
        [Button.inline("📢 Enviar mensaje ahora", data="send_now")],
        [Button.inline("⏰ Programar spam", data="schedule_spam")],
        [Button.inline("🛑 Detener spam", data="stop_spam")],
        [Button.inline("🚫 Blacklist de grupos", data="manage_blacklist")]
    ]
    await event.edit("👋 **¡Bienvenido! Elige una opción:**", buttons=buttons)

# --- FUNCIONES PARA SPAM ---
async def show_saved_messages(event, mode):
    uid = event.sender_id
    user_client = user_sessions.get(uid)
    saved_messages = await user_client.get_messages('me', limit=15)
    buttons = []
    for msg in saved_messages:
        text_preview = "🖼️ Archivo multimedia"
        if msg.text:
            text_preview = msg.text[:40] + "..." if len(msg.text) > 40 else msg.text
        buttons.append([Button.inline(f"➡️ {text_preview}", data=f"{mode}_{msg.id}")])
    await event.edit(f"**Elige un mensaje para {'programar' if mode=='schedule' else 'enviar ahora'}:**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'send_now'))
async def handle_send_now(event):
    await show_saved_messages(event, mode="now")

@bot.on(events.CallbackQuery(pattern=b'schedule_spam'))
async def handle_schedule(event):
    await show_saved_messages(event, mode="schedule")

@bot.on(events.CallbackQuery(pattern=b'stop_spam'))
async def handle_stop(event):
    uid = event.sender_id
    user_tasks = scheduled_tasks.get(uid, {})
    if not user_tasks:
        await event.edit("ℹ️ No tienes mensajes programados actualmente.")
        return
    buttons = []
    for msg_id in user_tasks.keys():
        buttons.append([Button.inline(f"🛑 Detener mensaje ID {msg_id}", data=f"cancel_{msg_id}")])
    await event.edit("🛑 **Elige el mensaje que quieres detener:**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'schedule_[0-9]+'))
async def ask_interval(event):
    msg_id = int(event.data.decode().split('_')[1])
    admin_steps[event.sender_id] = {"step": "await_interval", "msg_id": msg_id}
    await event.edit("⏳ ¿Cada cuántos minutos quieres enviar este mensaje?")

@bot.on(events.NewMessage(func=lambda e: e.sender_id in admin_steps and admin_steps[e.sender_id]["step"] == "await_interval"))
async def save_interval(event):
    try:
        minutes = int(event.raw_text.strip())
        if minutes < 1:
            raise ValueError
    except:
        await event.respond("❌ Por favor ingresa un número válido de minutos (mínimo 1).")
        return
    uid = event.sender_id
    msg_id = admin_steps[uid]["msg_id"]
    del admin_steps[uid]

    async def spam_task():
        user_client = user_sessions.get(uid)
        while True:
            try:
                await send_mass_message(user_client, msg_id, uid)
            except Exception as e:
                print(f"Error en spam programado: {e}")
            await asyncio.sleep(minutes * 60)

    task = asyncio.create_task(spam_task())
    scheduled_tasks.setdefault(uid, {})[msg_id] = task
    await event.respond(f"✅ Mensaje `{msg_id}` programado cada {minutes} minuto(s). Se notificará cada envío.")

@bot.on(events.CallbackQuery(pattern=b'cancel_[0-9]+'))
async def cancel_task(event):
    uid = event.sender_id
    msg_id = int(event.data.decode().split('_')[1])
    task = scheduled_tasks.get(uid, {}).pop(msg_id, None)
    if task:
        task.cancel()
        await event.edit(f"🛑 Mensaje `{msg_id}` detenido.")
    else:
        await event.edit("⚠️ No encontré esa tarea.")

async def send_mass_message(user_client, msg_id, uid):
    success_count = 0
    fail_count = 0
    blacklist = load_blacklist()
    dialogs = await user_client.get_dialogs()
    
    status_msg = await bot.send_message(uid, f"📤 **Enviando spam masivo del mensaje ID {msg_id}...**")
    
    for dialog in dialogs:
        if (dialog.is_group or dialog.is_channel) and dialog.id not in blacklist:
            try:
                await user_client.forward_messages(entity=dialog.id, messages=msg_id, from_peer='me')
                success_count += 1
            except (FloodWaitError, UserIsBlockedError, PeerFloodError):
                fail_count += 1
            except Exception:
                fail_count += 1
    
    result_text = (
        f"✅ **Spam masivo completado** ✅\n\n"
        f"📝 Mensaje ID: `{msg_id}`\n"
        f"📊 Resultados:\n"
        f"  • Grupos alcanzados: `{success_count}`\n"
        f"  • Grupos fallidos: `{fail_count}`\n\n"
        f"Total: `{success_count + fail_count}` grupos"
    )
    await bot.edit_message(uid, status_msg.id, result_text)
    return success_count, fail_count

@bot.on(events.CallbackQuery(pattern=b'now_[0-9]+'))
async def handle_forward_now(event):
    msg_id = int(event.data.decode().split('_')[1])
    uid = event.sender_id
    user_client = user_sessions.get(uid)
    await send_mass_message(user_client, msg_id, uid)

# --- EJECUCIÓN PRINCIPAL ---
async def main():
    # CAMBIO OBLIGATORIO: Iniciar servidor web justo antes que el bot
    keep_alive()
    
    await bot.start(bot_token=BOT_TOKEN)
    users_data = load_users()
    for user_id_str, data in users_data.items():
        if time.time() < data["expires"]:
            session_path = os.path.join(SESSION_DIR, f"{user_id_str}.session")
            if os.path.exists(session_path):
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    user_sessions[int(user_id_str)] = client
    print("\n✅ Bot iniciado y escuchando eventos.")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido.")
