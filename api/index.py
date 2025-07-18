# api/index.py
import os, asyncio, logging, random, requests, math, urllib.parse, json
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# --- Setup & Constants ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
DEFAULT_RADIUS_KM = 1.0

app = FastAPI(docs_url=None, redoc_url=None)

# --- Helper Functions ---
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
        params = {'key': os.getenv("DGIS_API_KEY"), 'q': 'поесть', 'point': f'{lon},{lat}', 'radius': radius_meters, 'type': 'branch', 'fields': 'items.name,items.address_name,items.url', 'page_size': 10, 'page': page_num}
        url = "https://catalog.api.2gis.com/3.0/items";
        try:
            response = requests.get(url, params=params); response.raise_for_status(); data = response.json()
            if data.get("meta", {}).get("code") == 200 and data.get("result", {}).get("items"): all_places.extend(data["result"]["items"])
            else: break
        except requests.RequestException: break
    if all_places: return random.choice(all_places)
    return None

# --- Main Handler Logic (replaces bot_logic.py) ---
async def start(update: Update, context: CallbackContext) -> None:
    context.user_data['state'] = 'awaiting_city'
    await update.message.reply_text("Привет! Напишите город и адрес, где ищем (например, Алматы, Абая 15).")

async def handle_text(update: Update, context: CallbackContext) -> None:
    full_address = update.message.text
    await update.message.reply_text(f"Ищу заведения рядом с адресом: {full_address}...")
    
    coords = get_coordinates(full_address)
    if not coords:
        await update.message.reply_text("Не смог найти такой адрес. Попробуйте еще раз, указав город и улицу."); return

    context.user_data['last_coords'] = coords
    context.user_data['last_address'] = full_address
    
    place = get_random_lunch_place(coords[0], coords[1], int(DEFAULT_RADIUS_KM * 1000))
    if not place:
        await update.message.reply_text(f"К сожалению, я не нашел заведений в радиусе {DEFAULT_RADIUS_KM} км."); return

    name = escape_markdown_v2(place.get('name', 'N/A'))
    address = escape_markdown_v2(place.get('address_name', ''))
    
    message_text = f"🎉 *Выбор сделан\\!* 🎉\n\n📍 *Название:* {name}\n"
    if address: message_text += f"🏠 *Адрес:* {address}\n"
    
    url = place.get('url') or f"https://2gis.kz/search/{urllib.parse.quote_plus(full_address)}"
    message_text += f"\n[Посмотреть на карте 2GIS]({url})"
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("Повторить поиск 🔁", callback_data="repeat_search")]])
    await update.message.reply_markdown_v2(message_text, reply_markup=markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query; await query.answer()
    if query.data == "repeat_search":
        coords = context.user_data.get('last_coords')
        address = context.user_data.get('last_address', 'ваше последнее местоположение')
        if not coords: await query.edit_message_text(text="Что-то пошло не так. Начните новый поиск с /start."); return
        
        await query.edit_message_text(text=f"_Ищу другой вариант рядом с {escape_markdown_v2(address)}\\.\\.\\._", parse_mode='MarkdownV2')
        
        place = get_random_lunch_place(coords[0], coords[1], int(DEFAULT_RADIUS_KM * 1000))
        if not place:
            await query.edit_message_text(text=f"Больше ничего не нашел в радиусе {DEFAULT_RADIUS_KM} км."); return

        name = escape_markdown_v2(place.get('name', 'N/A'))
        address = escape_markdown_v2(place.get('address_name', ''))
        message_text = f"🎉 *Новый вариант\\!* 🎉\n\n📍 *Название:* {name}\n"
        if address: message_text += f"🏠 *Адрес:* {address}\n"
        
        url = place.get('url') or f"https://2gis.kz/search/{urllib.parse.quote_plus(context.user_data.get('last_address', ''))}"
        message_text += f"\n[Посмотреть на карте 2GIS]({url})"
        
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Повторить поиск 🔁", callback_data="repeat_search")]])
        await query.edit_message_text(text=message_text, parse_mode='MarkdownV2', reply_markup=markup)

async def main_handler(data: dict):
    """
    Creates, initializes, and processes an update with one application instance.
    This is the single entry point for all bot logic.
    """
    bot_token = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Process the update
    async with application:
        await application.initialize()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        await application.shutdown()

# --- FastAPI Endpoints ---
@app.post("/api")
async def telegram_webhook(request: Request):
    """Endpoint to receive updates from Telegram."""
    try:
        data = await request.json()
        await main_handler(data)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
    return Response(status_code=200)

@app.get("/")
def health_check():
    return {"status": "ok"}