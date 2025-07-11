# api/index.py
import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

# Импортируем нашу логику
from bot_logic import setup_application

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# --- Инициализация ---
app = Flask(__name__)
persistence = PicklePersistence(filepath="/tmp/bot_persistence")
logger.info("Создание объекта приложения Telegram...")
application = setup_application(persistence)

async def initialize_bot():
    """Выполняет асинхронную инициализацию бота."""
    await application.initialize()
    if application.job_queue:
        application.job_queue.start()
    logger.info("Приложение Telegram успешно инициализировано, JobQueue запущен.")

# Запускаем инициализацию один раз при холодном старте
asyncio.run(initialize_bot())


@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    """Главная функция, которая обрабатывает входящие запросы от Telegram."""
    logger.info("Получен входящий POST-запрос от Telegram.")
    
    try:
        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Вместо asyncio.run(), мы получаем или создаем цикл событий вручную.
        # Это более стабильный подход для интеграции с синхронными фреймворками.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Запускаем нашу асинхронную задачу в этом цикле
        loop.run_until_complete(process_update_async(request))
        
        return 'ok'

    except Exception as e:
        logger.error(f"Произошла ошибка при обработке обновления: {e}", exc_info=True)
        return 'ok'


async def process_update_async(flask_request):
    """Асинхронно обрабатывает обновление."""
    update_data = flask_request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    logger.info(f"Десериализовано обновление: update_id={update.update_id}")
    
    await application.process_update(update)
    logger.info("Обработка обновления успешно завершена.")


@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    """Проверка, что сервис жив."""
    return 'ok'