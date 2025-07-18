# bot_logic.py
import logging, os, random, requests, json, traceback, urllib, math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

from persistence import load_user_data, save_user_data

# --- Настройка и константы ---
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0

# --- Вспомогательные функции ---
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'; return text.translate(str.maketrans({char: f'\\{char}' for char in escape_chars}))

def get_coordinates(address: str) -> tuple | None:
    url = "https://catalog.api.2gis.com/3.0/items/geocode"; params = {"q": address, "key": os.getenv("DGIS_API_KEY"), "fields": "items.point"}
    try:
        response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
        if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"):
            point = data["result"]["items"][0]["point"]; return point['lat'], point['lon']
    except requests.RequestException: return None
    return None

def get_random_lunch_place(lat: float, lon: float, radius_meters: int) -> dict | None:
    all_places = []
    for page_num in range(1, 11):
        params = {'key': os.getenv("DGIS_API_KEY"), 'q': 'поесть', 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url,items.point_info', 'page_size': 10, 'page': page_num}
        url = "https://catalog.api.2gis.com/3.0/items";
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
    if all_places:
        place_choice = random.choice(all_places)
        point_info = place_choice.get('point_info', {}); point_coords = point_info.get('point', {})
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
        else: await update.message.reply_text(text=message_text)
        return
        
    title = "🎉 *Выбор сделан\\!* 🎉" if is_new_search else "🎉 *Новый вариант\\!* 🎉"
    name = escape_markdown_v2(place.get('name', '')); address = escape_markdown_v2(place.get('address', ''))
    message_text = f"{title}\n\n📍 *Название:* {name}\n"
    if address: message_text += f"🏠 *Адрес:* {address}\n"
    
    place_url = place.get('url')
    if place_url: url_to_send = place_url
    else:
        place_name_for_url = urllib.parse.quote_plus(place.get('name', ''))
        city_name = context.user_data.get('city', 'almaty').lower()
        url_to_send = f"https://2gis.kz/{city_name}/search/{place_name_for_url}"
        
    message_text += f"\n[Посмотреть на карте 2GIS]({url_to_send})"
    reply_markup = create_result_keyboard()
    if update.callback_query: await update.callback_query.edit_message_text(text=message_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else: await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)

# --- Обработчики ---
async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    
    start_message = (f"Привет, {update.effective_user.mention_html()}!\n\n"
                     f"Текущий радиус поиска: <b>{current_radius} км</b>.\n\n")
    if 'city' in context.user_data:
        start_message += f"Ваш сохраненный город: <b>{context.user_data['city']}</b>. Просто отправьте улицу и номер дома."
        context.user_data['state'] = 'awaiting_address'
    else:
        start_message += "Для начала, пожалуйста, напишите мне свой город."
        context.user_data['state'] = 'awaiting_city'
    
    save_user_data(user_id, context.user_data)
    await update.message.reply_html(start_message)

async def set_city_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    context.user_data['state'] = 'awaiting_city'
    save_user_data(user_id, context.user_data)
    await update.message.reply_text("Какой новый город выберем?")
    
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
        context.user_data['city'] = user_text
        context.user_data['state'] = 'awaiting_address'
        save_user_data(user_id, context.user_data)
        await update.message.reply_text(f"Город '{user_text}' сохранен. Теперь отправьте улицу и номер дома.")
        return
        
    elif state == 'awaiting_radius':
        try:
            new_radius = float(user_text.replace(',', '.'));
            if not (0.1 <= new_radius <= 10): raise ValueError()
            context.user_data['radius_km'] = new_radius; context.user_data.pop('state', None)
            save_user_data(user_id, context.user_data)
            await update.message.reply_text(f"Радиус обновлен: {new_radius} км.")
            return
        except (ValueError, TypeError):
            await update.message.reply_text("Неверный формат. Попробуйте еще раз."); return

    city = context.user_data.get('city')
    if not city: await start(update, context); return
    full_address = f"{city}, {user_text}"
    await update.message.reply_text(f"Ищу заведения рядом с {full_address}...")
    coords = await get_coordinates(full_address)
    if not coords: await update.message.reply_text("Не смог найти такой адрес."); return
    context.user_data['last_coords'] = [coords[0], coords[1]]
    save_user_data(user_id, context.user_data)
    
    await perform_search_and_reply(update, context, coords, is_new_search=True)

# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ---
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data.clear(); context.user_data.update(load_user_data(user_id))
    
    if query.data == "repeat_search":
        coords = context.user_data.get('last_coords')
        if not coords:
            await query.edit_message_text("Нет сохраненных координат. Начните с /start.")
            return
        # Просто вызываем центральную функцию, которая содержит правильную логику
        await perform_search_and_reply(update, context, coords)
    
    elif query.data == "change_radius":
        await set_radius_command(query, context)

def add_handlers(application: Application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setcity", set_city_command))
    application.add_handler(CommandHandler("radius", set_radius_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))