# bot_logic.py
import logging
import os
import random
import requests
import json
import traceback
import math
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler
)

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0
ASKING_RADIUS = 1

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
    R = 6371e3
    lat1, lon1 = start_coords; lat2, lon2 = end_coords
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1); delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) * math.sin(delta_phi / 2) + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) * math.sin(delta_lambda / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return int(distance)

async def get_random_lunch_place(lat: float, lon: float, radius_meters: int) -> dict | None:
    all_places = []
    for page_num in range(1, 11):
        params = {'key': os.getenv("DGIS_API_KEY"), 'q': 'поесть', 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url,items.point_info', 'page_size': 10, 'page': page_num}
        url = "https://catalog.api.2gis.com/3.0/items"
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
    
    if all_places:
        found_places_names = [place.get('name', 'N/A') for place in all_places]
        logger.info(f"Found {len(found_places_names)} places: {found_places_names}")
        place_choice = random.choice(all_places)
        point_info = place_choice.get('point_info', {}); point_coords = point_info.get('point', {})
        return {
            "name": place_choice.get("name", "N/A"), 
            "address": place_choice.get("address_name", ""), # Return empty string if no address
            "url": place_choice.get("url", ""),
            "lat": point_coords.get('lat'), "lon": point_coords.get('lon')
        }
    return None

def create_result_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("Повторить поиск 🔁", callback_data="repeat_search"), InlineKeyboardButton("Сменить радиус 📏", callback_data="change_radius")]]; return InlineKeyboardMarkup(keyboard)

async def perform_search_and_reply(update: Update, context: CallbackContext, coords: tuple, is_new_search: bool = False):
    """Выполняет поиск и отправляет результат, проверяя наличие адреса."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text="_Ищу другой вариант\\.\\.\\._", parse_mode='MarkdownV2')
    
    radius_km = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    radius_meters = int(radius_km * 1000)
    place = await get_random_lunch_place(coords[0], coords[1], radius_meters)
    
    if not place:
        message_text = f"К сожалению, я не нашел заведений в радиусе {radius_km} км."
        if update.callback_query: await update.callback_query.edit_message_text(text=message_text)
        elif update.message: await update.message.reply_text(text=message_text)
        return
        
    title = "🎉 *Выбор сделан\\!* 🎉" if is_new_search else "🎉 *Новый вариант\\!* 🎉"
    name = escape_markdown_v2(place.get('name', ''))
    address = escape_markdown_v2(place.get('address', '')) # Get address from place dict

    # Начинаем формировать сообщение
    message_text = f"{title}\n\n📍 *Название:* {name}\n"

    # Добавляем строку с адресом, только если он не пустой
    if address:
        message_text += f"🏠 *Адрес:* {address}\n"
    
    place_coords = (place.get('lat'), place.get('lon'))
    if all(place_coords):
        distance_m = get_straight_line_distance(start_coords=coords, end_coords=place_coords)
        message_text += f"📏 *Расстояние:* примерно {distance_m} м по прямой\n"

    place_url = place.get('url')
    if place_url:
        url_to_send = place_url
    else:
        place_name_encoded = urllib.parse.quote_plus(place.get('name', ''))
        city_name = context.user_data.get('city', 'almaty').lower()
        url_to_send = f"https://2gis.kz/{city_name}/search/{place_name_encoded}"

    message_text += f"\n[Посмотреть на карте 2GIS]({url_to_send})"
    
    reply_markup = create_result_keyboard()
    if update.callback_query: await update.callback_query.edit_message_text(text=message_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    elif update.message: await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Произошло исключение при обработке обновления:", exc_info=context.error); tb_list = traceback.format_exception(None, context.error, context.error.__traceback__); tb_string = "".join(tb_list)
    update_dict = update.to_dict() if isinstance(update, Update) else str(update); update_str = json.dumps(update_dict, indent=2, ensure_ascii=False)
    message = (f"--- Начало информации об ошибке ---\nUpdate: {update_str}\n\nUser Data: {context.user_data}\n\nTraceback:\n{tb_string}--- Конец информации об ошибке ---"); logger.error(message)

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    start_message = (f"Привет, {user.mention_html()}!\n\nЯ помогу тебе выбрать, где пообедать.\n"
                     f"Текущий радиус поиска: <b>{current_radius} км</b>. Чтобы его изменить, используй команду /radius.\n\n"
                     "Для начала, пожалуйста, напиши мне свой город.")
    await update.message.reply_html(start_message)

async def set_city(update: Update, context: CallbackContext) -> None:
    context.user_data.pop('city', None); context.user_data.pop('last_coords', None)
    await update.message.reply_text("Хорошо, давайте сменим город. Какой теперь выберем?")

async def handle_message(update: Update, context: CallbackContext) -> None:
    user_text = update.message.text
    if 'city' not in context.user_data:
        coords = await get_coordinates(user_text)
        if not coords: await update.message.reply_text("Не смог найти такой город. Попробуйте еще раз."); return
        context.user_data['city'] = user_text
        escaped_city = escape_markdown_v2(user_text)
        await update.message.reply_markdown_v2(f"Отлично\\! Ваш город '{escaped_city}' сохранен\\.\nТеперь отправьте мне улицу и номер дома \\(например, 'Абая 15'\\)\\.")
        return
    city = context.user_data['city']; full_address = f"{city}, {user_text}"
    escaped_full_address = escape_markdown_v2(full_address)
    await update.message.reply_markdown_v2(f"Ищу заведения рядом с адресом: *{escaped_full_address}*\\.\\.\\.\n_\\(Это может занять несколько секунд\\)_")
    coords = await get_coordinates(full_address)
    if not coords: await update.message.reply_text("Не смог найти такой адрес."); return
    context.user_data['last_coords'] = coords
    await perform_search_and_reply(update, context, coords, is_new_search=True)

async def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "repeat_search":
        coords = context.user_data.get('last_coords')
        if not coords: await query.edit_message_text(text="Что-то пошло не так."); return
        await perform_search_and_reply(update, context, coords)
        return
    elif query.data == "change_radius":
        current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
        await query.message.reply_text(f"Текущий радиус поиска: {current_radius} км.\nОтправьте новое значение в километрах (например, 0.5 или 3).\n\nЧтобы отменить, введите /cancel.")
        return ASKING_RADIUS

async def radius_start(update: Update, context: CallbackContext) -> int:
    current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM); await update.message.reply_text(f"Текущий радиус поиска: {current_radius} км.\nОтправьте новое значение в километрах (например, 0.5 или 3).\n\nЧтобы отменить, введите /cancel."); return ASKING_RADIUS

async def radius_receive(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.replace(',', '.');
    try:
        new_radius = float(user_text)
        if not (0.1 <= new_radius <= 10): raise ValueError("Радиус вне допустимого диапазона.")
        context.user_data['radius_km'] = new_radius
        coords = context.user_data.get('last_coords')
        if coords:
            await update.message.reply_text(f"Радиус обновлен: {new_radius} км. Запускаю повторный поиск...")
            await perform_search_and_reply(update, context, coords, is_new_search=True)
        else:
            await update.message.reply_text(f"Отлично! Новый радиус поиска сохранен: {new_radius} км.")
    except ValueError:
        await update.message.reply_text("Это не похоже на число. Пожалуйста, введите корректное значение (от 0.1 до 10)."); return ASKING_RADIUS
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Действие отменено."); return ConversationHandler.END

def add_handlers(application: Application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('radius', radius_start)],
        states={ASKING_RADIUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, radius_receive)]},
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False, persistent=True, name="radius_conversation"
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setcity", set_city))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)