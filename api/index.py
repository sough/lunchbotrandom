# api/index.py
import os
import asyncio
import logging
import nest_asyncio  # Импортируем библиотеку
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

# Импортируем нашу логику
from bot_logic import setup_application

# --- Настройка ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
persistence = PicklePersistence(filepath="/tmp/bot_persistence")

logger.info("Создание объекта приложения Telegram...")
application = setup_application(persistence)
logger.info("Приложение Telegram создано.")

# --- КЛЮЧЕВЫЕ ИСПРАВЛЕНИЯ ---

# 1. Применяем патч к asyncio, чтобы разрешить вложенные циклы событий.
nest_asyncio.apply()
logger.info("nest_asyncio применен.")

# 2. Определяем и запускаем асинхронную инициализацию ОДИН РАЗ при старте.
async def initialize_bot():
    """Выполняет обязательную асинхронную инициализацию бота."""
    await application.initialize()
    # Пытаемся запустить JobQueue. Его работа в Vercel не гарантирована, но этот вызов необходим.
    if application.job_queue:
        await application.job_queue.start()
    logger.info("Приложение Telegram успешно инициализировано.")

# 3. Запускаем инициализацию с помощью asyncio.run().
# Благодаря nest_asyncio, это больше не будет вызывать ошибок "Event loop is closed".
logger.info("Запускаю одноразовую инициализацию бота...")
asyncio.run(initialize_bot())
logger.info("Одноразовая инициализация бота завершена.")


@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    """Главная функция, которая обрабатывает входящие запросы от Telegram."""
    try:
        # Теперь этот вызов безопасен
        asyncio.run(process_update_async(request))
    except Exception as e:
        logger.error(f"Произошла ошибка при обработке обновления: {e}", exc_info=True)
        
    return 'ok'


async def process_update_async(flask_request):
    """Асинхронно обрабатывает обновление."""
    update_data = flask_request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)


# GET-запрос для проверки работоспособности
@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    """Проверка, что сервис жив."""
    return 'ok'