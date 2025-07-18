# bot_logic.py
import logging, os, random, requests, json, traceback, urllib.parse, math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# --- Setup & Constants ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0

# --- Helper & API Functions ---
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'; return text.translate(str.maketrans({char: f'\\{char}' for char in escape_chars}))
async def get_coordinates(address: str) -> tuple | None:
    url = "https://catalog.api.2gis.com/3.0/items/geocode"; params = {"q": address, "key": os.getenv("DGIS_API_KEY"), "fields": "items.point"}
    try:
        response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
        if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"):
            point = data["result"]["items"][0]["point"]; return point['lat'], point['lon']
        else: logger.warning(f"2GIS API не нашел координат для адреса '{address}'."); return None
    except requests.RequestException as e: logger.error(f"Ошибка сети при запросе к 2GIS Geocode API: {e}"); return None
def get_straight_line_distance(start_coords: tuple, end_coords: tuple) -> int:
    R = 6371e3; lat1, lon1 = start_coords; lat2, lon2 = end_coords; phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1); delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)); distance = R * c
    return int(distance)
async def get_random_lunch_place(lat: float, lon: float, radius_meters: int) -> dict | None:
    all_places = [];
    for page_num in range(1, 11):
        params = {'key': os.getenv("DGIS_API_KEY"), 'q': 'поесть', 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url,items.point_info', 'page_size': 10, 'page': page_num}
        url = "https://catalog.api.2gis.com/3.0/items";
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
    if all_places:
        place_choice = random.choice(all_places); point_info = place_choice.get('point_info', {}); point_coords = point_info.get('point', {})
        return {"name": place_choice.get("name", "N/A"), "address": place_choice.get("address_name", ""), "url": place_choice.get("url", ""), "lat": point_coords.get('lat'), "lon": point_coords.get('lon')}
    return None
def create_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Повторить поиск 🔁", callback_data="repeat_search"), InlineKeyboardButton("Сменить радиус 📏", callback_data="change_radius")]])
async def perform_search_and_reply(update: Update, context: CallbackContext, coords: tuple, is_new_search: bool = False):
    if update.callback_query: await update.callback_query.edit_message_text(text="_Ищу другой вариант\\.\\.\\._", parse_mode='MarkdownV2')
    radius_km = context.user_data.get('radius_km', DEFAULT_RADIUS_KM); radius_meters = int(radius_km * 1000)
    place = await get_random_lunch_place(coords[0], coords[1], radius_meters)
    if not place:
        message_text = f"К сожалению, я не нашел заведений в радиусе {radius_km} км."
        if update.callback_query: await update.callback_query.edit_message_text(text=message_text)
        elif update.message: await update.message.reply_text(text=message_text)
        return
    title = "🎉 *Выбор сделан\\!* 🎉" if is_new_search else "🎉 *Новый вариант\\!* 🎉"
    name = escape_markdown_v2(place.get('name', '')); address = escape_markdown_v2(place.get('address', ''))
    message_text = f"{title}\n\n📍 *Название:* {name}\n"
    if address: message_text += f"🏠 *Адрес:* {address}\n"
    place_coords = (place.get('lat'), place.get('lon'))
    if all(place_coords):
        distance_m = get_straight_line_distance(start_coords=coords, end_coords=place_coords)
        message_text += f"📏 *Расстояние:* примерно {distance_m} м по прямой\n"
    place_url = place.get('url')
    if place_url: url_to_send = place_url
    else:
        place_name_encoded = urllib.parse.quote_plus(place.get('name', '')); city_name = context.user_data.get('city', 'almaty').lower()
        url_to_send = f"https://2gis.kz/{city_name}/search/{place_name_encoded}"
    message_text += f"\n[Посмотреть на карте 2GIS]({url_to_send})"
    reply_markup = create_result_keyboard()
    if update.callback_query: await update.callback_query.edit_message_text(text=message_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    elif update.message: await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)
async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

# --- Handlers ---
async def start(update: Update, context: CallbackContext) -> None:
    context.user_data['next_step'] = 'set_city'
    await update.message.reply_text("Привет! Напишите город, в котором ищем (например, Алматы).")
async def set_city(update: Update, context: CallbackContext) -> None:
    context.user_data['city'] = None
    context.user_data['next_step'] = 'set_city'
    await update.message.reply_text("Хорошо, давайте сменим город.")
async def set_radius(update: Update, context: CallbackContext) -> None:
    current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    context.user_data['next_step'] = 'set_radius'
    await update.message.reply_text(f"Текущий радиус поиска: {current_radius} км. Отправьте новое значение (например, 1.5).")

async def handle_text(update: Update, context: CallbackContext) -> None:
    next_step = context.user_data.get('next_step')
    if next_step == 'set_city':
        city = update.message.text
        if "/" in city: await update.message.reply_text("Это похоже на команду. Пожалуйста, введите название города."); return
        context.user_data['city'] = city
        context.user_data['next_step'] = 'set_address'
        await update.message.reply_text(f"Город '{city}' установлен. Теперь отправьте улицу и номер дома.")
    elif next_step == 'set_radius':
        try:
            new_radius = float(update.message.text.replace(',', '.'));
            if not (0.1 <= new_radius <= 10): raise ValueError()
            context.user_data['radius_km'] = new_radius
            context.user_data.pop('next_step', None)
            await update.message.reply_text(f"Радиус обновлен: {new_radius} км.")
            if 'last_coords' in context.user_data: await perform_search_and_reply(update, context, context.user_data['last_coords'], is_new_search=True)
        except (ValueError, TypeError): await update.message.reply_text("Неверный формат. Введите число, например, 1.5.")
    else:
        city = context.user_data.get('city')
        if not city: await start(update, context); return
        full_address = f"{city}, {update.message.text}"
        await update.message.reply_text(f"Ищу заведения рядом с адресом: {full_address}...")
        coords = await get_coordinates(full_address)
        if not coords: await update.message.reply_text("Не смог найти такой адрес."); return
        context.user_data['last_coords'] = coords
        await perform_search_and_reply(update, context, coords, is_new_search=True)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query; await query.answer()
    if query.data == "repeat_search":
        coords = context.user_data.get('last_coords')
        if not coords: await query.edit_message_text(text="Что-то пошло не так. Начните поиск с /start."); return
        await perform_search_and_reply(update, context, coords)
    elif query.data == "change_radius":
        await set_radius(query, context)

def add_handlers(application: Application):
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setcity", set_city))
    application.add_handler(CommandHandler("radius", set_radius))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))