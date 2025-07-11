# bot_logic.py
import logging
import os
import random
import requests
import asyncio
import traceback
import html
import json
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler, PicklePersistence
)
from timezonefinder import TimezoneFinder

# --- Настройки и константы ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0
ASKING_RADIUS = 1

# ... (all other functions from escape_markdown_v2 to cancel remain the same) ...
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'; return text.translate(str.maketrans({char: f'\\{char}' for char in escape_chars}))
async def get_coordinates_and_timezone(address: str) -> tuple | None:
    url = "https://catalog.api.2gis.com/3.0/items/geocode"; params = { "q": address, "key": os.getenv("DGIS_API_KEY"), "fields": "items.point" }
    try:
        response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
        if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"):
            point = data["result"]["items"][0]["point"]; lat, lon = point['lat'], point['lon']; timezone_str = TimezoneFinder().timezone_at(lng=lon, lat=lat)
            if not timezone_str: logger.warning(f"Найдены координаты для '{address}', но не удалось определить часовой пояс."); return lat, lon, None
            return lat, lon, timezone_str
        else: logger.warning(f"2GIS API не нашел координат для адреса '{address}'. Ответ: {data}"); return None
    except requests.RequestException as e: logger.error(f"Ошибка сети при запросе к 2GIS Geocode API для адреса '{address}': {e}"); return None
async def get_random_lunch_place(lat: float, lon: float, radius_meters: int) -> dict | None:
    all_places = []
    for page_num in range(1, 11):
        url = "https://catalog.api.2gis.com/3.0/items"; params = {'key': os.getenv("DGIS_API_KEY"), 'q': "кафе, ресторан, столовая", 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url', 'page_size': 10, 'page': page_num}
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
        except (KeyError, IndexError): break
    if all_places:
        place_choice = random.choice(all_places)
        return {"name": place_choice.get("name", "Н/Д"), "address": place_choice.get("address_name", "Н/Д"), "url": place_choice.get("url", "")}
    return None
def create_result_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("Повторить поиск 🔁", callback_data="repeat_search"), InlineKeyboardButton("Сменить радиус 📏", callback_data="change_radius")]]; return InlineKeyboardMarkup(keyboard)
async def perform_search_and_reply(update: Update, context: CallbackContext, coords: tuple, is_new_search: bool = False):
    radius_km = context.user_data.get('radius_km', DEFAULT_RADIUS_KM); radius_meters = int(radius_km * 1000)
    place = await get_random_lunch_place(coords[0], coords[1], radius_meters)
    if not place:
        message_text = f"К сожалению, я не нашел заведений в радиусе {radius_km} км."
        if update.callback_query: await update.callback_query.edit_message_text(text=message_text)
        elif update.message: await update.message.reply_text(text=message_text)
        return
    title = "🎉 *Выбор сделан\\!* 🎉" if is_new_search else "🎉 *Новый вариант\\!* 🎉"; name = escape_markdown_v2(place['name']); address = escape_markdown_v2(place['address'])
    message_text = f"{title}\n\n📍 *Название:* {name}\n🏠 *Адрес:* {address}\n\n"
    if place.get('url'): message_text += f"[Посмотреть на карте 2GIS]({place['url']})"
    reply_markup = create_result_keyboard()
    if update.callback_query: await update.callback_query.edit_message_text(text=message_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    elif update.message: await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)
async def daily_prompt_callback(context: CallbackContext) -> None:
    job = context.job; keyboard = [[InlineKeyboardButton("Начать поиск 🔎", callback_data="start_daily_search")]]; reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info(f"Сработала задача '{job.name}', отправляю сообщение в чат {job.chat_id}.")
    await context.bot.send_message(job.chat_id, text="Где обедаем сегодня?", reply_markup=reply_markup)
def remove_job_if_exists(name: str, context: CallbackContext) -> bool:
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs: return False
    for job in current_jobs: job.schedule_removal()
    return True
async def schedule_daily_prompt(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_message.chat_id; user_id = update.effective_user.id; job_name = f"daily_lunch_prompt_{user_id}"
    remove_job_if_exists(job_name, context)
    timezone_str = context.user_data.get('timezone')
    if not timezone_str: logger.warning(f"Не удалось запланировать задачу для user_id {user_id}, так как не найден часовой пояс."); return
    try:
        tz = ZoneInfo(timezone_str); t = time(11, 30, 0, tzinfo=tz)
        context.job_queue.run_daily(daily_prompt_callback, t, chat_id=chat_id, name=job_name, user_id=user_id)
        logger.info(f"Задача '{job_name}' запланирована на 11:30 по времени {timezone_str}.")
        await update.effective_message.reply_text("Отлично! Я буду напоминать вам об обеде каждый день в 11:30.")
    except ZoneInfoNotFoundError: logger.error(f"Некорректный часовой пояс: {timezone_str}"); await update.effective_message.reply_text("Не удалось определить ваш часовой пояс для планирования напоминаний.")
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; current_radius = context.user_data.get('radius_km', DEFAULT_RADIUS_KM)
    start_message = (f"Привет, {user.mention_html()}!\n\nЯ помогу тебе выбрать, где пообедать.\n"
                     f"Текущий радиус поиска: <b>{current_radius} км</b>. Чтобы его изменить, используй команду /radius.\n\n")
    if 'city' in context.user_data: city = context.user_data['city']; start_message += f"Ваш город: <b>{city}</b>. Просто отправьте мне улицу и номер дома."
    else: start_message += "Для начала, пожалуйста, напиши мне свой город."
    await update.message.reply_html(start_message)
async def set_city(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; job_name = f"daily_lunch_prompt_{user_id}"
    if remove_job_if_exists(job_name, context):
        logger.info(f"Задача '{job_name}' отменена из-за смены города."); await update.message.reply_text("Ежедневное напоминание отменено.")
    context.user_data.pop('city', None); context.user_data.pop('last_coords', None); context.user_data.pop('timezone', None)
    await update.message.reply_text("Хорошо, давайте сменим город. Какой теперь выберем?")
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_text = update.message.text
    if 'city' not in context.user_data:
        geo_data = await get_coordinates_and_timezone(user_text)
        if not geo_data: await update.message.reply_text("Не смог найти такой город. Попробуйте еще раз."); return
        lat, lon, timezone_str = geo_data; context.user_data['city'] = user_text; context.user_data['timezone'] = timezone_str
        escaped_city = escape_markdown_v2(user_text)
        await update.message.reply_markdown_v2(f"Отлично\\! Ваш город '{escaped_city}' сохранен\\.\nТеперь отправьте мне улицу и номер дома \\(например, 'Абая 15'\\)\\.")
        await schedule_daily_prompt(update, context)
        return
    city = context.user_data['city']; full_address = f"{city}, {user_text}"; escaped_full_address = escape_markdown_v2(full_address)
    await update.message.reply_markdown_v2(f"Ищу заведения рядом с адресом: *{escaped_full_address}*\\.\\.\\.\n_\\(Это может занять несколько секунд\\)_")
    coords_data = await get_coordinates_and_timezone(full_address)
    if not coords_data: await update.message.reply_text("Не смог найти такой адрес."); return
    lat, lon, _ = coords_data; coords = (lat, lon); context.user_data['last_coords'] = coords
    await perform_search_and_reply(update, context, coords, is_new_search=True)
async def start_daily_search_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query; await query.answer()
    await query.message.reply_text("Отлично! Отправьте мне улицу и номер дома (например, 'Абая 15').")
async def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "repeat_search":
        coords = context.user_data.get('last_coords')
        if not coords: await query.edit_message_text(text="Что-то пошло не так. Пожалуйста, отправьте адрес заново."); return
        await query.edit_message_text(text="_Ищу другой вариант\\.\\.\\._", parse_mode='MarkdownV2')
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
        if coords: await update.message.reply_text(f"Радиус обновлен: {new_radius} км. Автоматически запускаю повторный поиск..."); await perform_search_and_reply(update, context, coords, is_new_search=True)
        else: await update.message.reply_text(f"Отлично! Новый радиус поиска сохранен: {new_radius} км.")
    except ValueError: await update.message.reply_text("Это не похоже на число. Пожалуйста, введите корректное значение (от 0.1 до 10)."); return ASKING_RADIUS
    return ConversationHandler.END
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Действие отменено."); return ConversationHandler.END

async def error_handler(update: object, context: CallbackContext) -> None:
    """Логирует ошибки, вызванные обновлениями, в читаемом формате."""
    logger.error("Произошло исключение при обработке обновления:", exc_info=context.error)

    # Собираем traceback ошибки
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Собираем информацию о пользователе и чате
    update_str = update.to_json() if isinstance(update, Update) else str(update)
    
    # Формируем простое и понятное многострочное сообщение для лога
    # Мы не используем html.escape, чтобы сохранить переносы строк и отступы
    message = (
        f"--- Начало информации об ошибке ---\n"
        f"Update: {json.dumps(json.loads(update_str), indent=2, ensure_ascii=False)}\n\n"
        f"User Data: {context.user_data}\n\n"
        f"Traceback:\n{tb_string}"
        f"--- Конец информации об ошибке ---"
    )

    # Логируем как одну большую запись
    logger.error(message)


def setup_application(persistence: PicklePersistence) -> Application:
    """Настраивает и возвращает объект Application."""
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .persistence(persistence)
        .build()
    )

    application.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('radius', radius_start)],
        states={
            ASKING_RADIUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, radius_receive)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        persistent=True,
        name="radius_conversation"
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setcity", set_city))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(start_daily_search_handler, pattern='^start_daily_search$'))
    
    return application