import os, asyncio, logging, random, requests, math, urllib.parse, json, redis
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# --- Setup & Constants ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
DGIS_API_KEY = os.getenv("DGIS_API_KEY")

app = FastAPI(docs_url=None, redoc_url=None)

# --- Database (Vercel KV / Redis) ---
try:
    redis_client = redis.from_url(os.getenv("KV_URL"))
except Exception as e:
    logger.error(f"Could not connect to Redis: {e}")
    redis_client = None

def load_user_data(user_id: int) -> dict:
    if not redis_client: return {}
    try:
        data = redis_client.get(f"user:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"Failed to load data for user {user_id}: {e}"); return {}

def save_user_data(user_id: int, data: dict) -> None:
    if not redis_client: return
    try:
        # Convert tuple to list for JSON compatibility
        if 'last_coords' in data and isinstance(data['last_coords'], tuple):
            data['last_coords'] = list(data['last_coords'])
        redis_client.set(f"user:{user_id}", json.dumps(data))
    except Exception as e:
        logger.error(f"Failed to save data for user {user_id}: {e}")

# --- Helper Functions ---
def get_coordinates(address: str) -> tuple | None:
    url = "https://catalog.api.2gis.com/3.0/items/geocode"; params = {"q": address, "key": DGIS_API_KEY, "fields": "items.point"}
    try:
        response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
        if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"):
            point = data["result"]["items"][0]["point"]; return point['lat'], point['lon']
    except requests.RequestException: return None
    return None
def get_random_lunch_place(lat: float, lon: float, radius_meters: int) -> dict | None:
    all_places = []
    for page_num in range(1, 11):
        params = {'key': DGIS_API_KEY, 'q': 'поесть', 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url', 'page_size': 10, 'page': page_num}
        url = "https://catalog.api.2gis.com/3.0/items";
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
    if all_places: return random.choice(all_places)
    return None
def create_result_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("Искать снова 🔁", callback_data="repeat_search")],[InlineKeyboardButton("Другой адрес 🏠", callback_data="change_address"),InlineKeyboardButton("Сменить радиус 📏", callback_data="change_radius"),InlineKeyboardButton("Сменить город 🏙️", callback_data="change_city")]]
    return InlineKeyboardMarkup(keyboard)

async def perform_search_and_reply(update: Update, context: CallbackContext):
    query = update.callback_query
    if query: await query.edit_message_text("_Ищу...")
    coords = context.user_data.get('last_coords')
    full_address = context.user_data.get('last_address')
    radius_km = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    if not coords or not full_address:
        await update.effective_message.reply_text("Недостаточно данных для поиска. Начните с /start.")
        return
    place = get_random_lunch_place(coords[0], coords[1], int(radius_km * 1000))
    if not place:
        message_text = f"К сожалению, я не нашел заведений в радиусе {radius_km} км."
        if query: await query.edit_message_text(text=message_text)
        else: await update.message.reply_text(text=message_text)
        return
    name = place.get('name', 'N/A'); address = place.get('address_name', '')
    url = place.get('url') or f"https://2gis.kz/search/{urllib.parse.quote_plus(full_address)}"
    title = "🎉 Новый вариант!" if query else "🎉 Выбор сделан!"
    message_text = f"{title}\n\n📍 **Название:** {name}\n"
    if address: message_text += f"🏠 **Адрес:** {address}\n"
    message_text += f"\n[Посмотреть на карте 2GIS]({url})"
    reply_markup = create_result_keyboard()
    if query: await query.edit_message_text(message_text, parse_mode='Markdown', reply_markup=reply_markup)
    else: await update.message.reply_text(message_text, parse_mode='Markdown', reply_markup=reply_markup)

# --- Bot Handlers ---
async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    if context.user_data.get('city') and context.user_data.get('last_address'):
        await update.message.reply_html(f"С возвращением! Ваш город: <b>{context.user_data['city']}</b>. Последний адрес: <b>{context.user_data['last_address']}</b>. Искать по нему? (отправьте 'да' или новый адрес)")
        context.user_data['state'] = 'confirm_address'
    elif context.user_data.get('city'):
        await update.message.reply_html(f"Ваш город: <b>{context.user_data['city']}</b>. Отправьте улицу и номер дома для поиска.")
        context.user_data['state'] = 'awaiting_address'
    else:
        await update.message.reply_html("Привет! Пожалуйста, напишите ваш город (например, <b>Алматы</b>).")
        context.user_data['state'] = 'awaiting_city'
    save_user_data(user_id, context.user_data)

async def set_city_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    context.user_data['state'] = 'awaiting_city'
    save_user_data(user_id, context.user_data)
    await update.message.reply_text("Какой новый город выберем?")

async def set_address_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    context.user_data['state'] = 'awaiting_address'
    save_user_data(user_id, context.user_data)
    city = context.user_data.get('city', 'вашем городе')
    await update.message.reply_text(f"Какой адрес ищем в городе {city}?")

async def set_radius_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    context.user_data['state'] = 'awaiting_radius'
    save_user_data(user_id, context.user_data)
    current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    await update.message.reply_text(f"Текущий радиус: {current_radius} км. Введите новое значение.")

async def handle_text(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    state = context.user_data.get('state')
    user_text = update.message.text

    if state == 'awaiting_city':
        context.user_data['city'] = user_text; context.user_data['state'] = 'awaiting_address'
        save_user_data(user_id, context.user_data)
        await update.message.reply_text(f"Город '{user_text}' сохранен. Теперь отправьте улицу и номер дома.")
    elif state == 'awaiting_radius':
        try:
            new_radius = float(user_text.replace(',', '.'));
            if not (0.1 <= new_radius <= 10): raise ValueError()
            context.user_data['radius_km'] = new_radius; context.user_data.pop('state', None)
            save_user_data(user_id, context.user_data)
            await update.message.reply_text(f"Радиус обновлен: {new_radius} км. Теперь можете искать по адресу.")
        except (ValueError, TypeError):
            await update.message.reply_text("Неверный формат. Попробуйте еще раз.");
    elif state == 'confirm_address' and user_text.lower() in ['да', 'yes', 'ок']:
        context.user_data.pop('state', None)
        save_user_data(user_id, context.user_data)
        await perform_search_and_reply(update, context)
    else:
        city = context.user_data.get('city')
        if not city: await start(update, context); return
        full_address = f"{city}, {user_text}"
        await update.message.reply_text(f"Ищу заведения рядом с адресом: {full_address}...")
        coords = get_coordinates(full_address)
        if not coords: await update.message.reply_text("Не смог найти такой адрес."); return
        
        # --- FIX IS HERE ---
        context.user_data['last_coords'] = coords
        context.user_data['last_address'] = full_address
        context.user_data.pop('state', None)
        save_user_data(user_id, context.user_data) # This line was missing
        
        await perform_search_and_reply(update, context)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query; await query.answer()
    if query.data == "repeat_search": await perform_search_and_reply(update, context)
    elif query.data == "change_address": await set_address_command(query, context)
    elif query.data == "change_radius": await set_radius_command(query, context)
    elif query.data == "change_city": await set_city_command(query, context)

# --- FastAPI Webhook ---
app = FastAPI(docs_url=None, redoc_url=None)

@app.post("/api")
async def telegram_webhook(request: Request):
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    try:
        async with application:
            await application.initialize()
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            await application.shutdown()
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
    return Response(status_code=200)