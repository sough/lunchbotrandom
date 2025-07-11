# api/index.py
import os
import asyncio
import logging
import nest_asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

from bot_logic import setup_application

# --- Настройка ---
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)
persistence = PicklePersistence(filepath="/tmp/bot_persistence")

logger.info("Создание объекта приложения Telegram...")
application = setup_application(persistence)
logger.info("Приложение Telegram создано.")

nest_asyncio.apply()
logger.info("nest_asyncio применен.")

async def initialize_bot():
    """Выполняет обязательную асинхронную инициализацию бота."""
    await application.initialize()
    # Строка application.job_queue.start() удалена
    logger.info("Приложение Telegram успешно инициализировано.")

logger.info("Запускаю одноразовую инициализацию бота...")
asyncio.run(initialize_bot())
logger.info("Одноразовая инициализация бота завершена.")

@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    try:
        asyncio.run(process_update_async(request))
    except Exception as e:
        logger.error(f"Произошла ошибка при обработке обновления: {e}", exc_info=True)
    return 'ok'

async def process_update_async(flask_request):
    update_data = flask_request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)

@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    return 'ok'