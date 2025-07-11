# api/index.py
import os
import asyncio
import logging
import nest_asyncio  # <-- ШАГ 1: Импортируем библиотеку
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

from bot_logic import setup_application

# --- Настройка ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
persistence = PicklePersistence(filepath="/tmp/bot_persistence")

logger.info("Создание объекта приложения Telegram...")
application = setup_application(persistence)
logger.info("Приложение Telegram создано.")

# --- ШАГ 2: Применяем патч к asyncio ---
# Это нужно сделать один раз при старте.
nest_asyncio.apply()
logger.info("nest_asyncio применен.")


@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    """Главная функция, которая обрабатывает входящие запросы от Telegram."""
    try:
        # --- ШАГ 3: Теперь мы можем просто использовать asyncio.run ---
        # nest_asyncio позаботится о том, чтобы цикл не закрылся преждевременно.
        asyncio.run(process_update_async(request))

    except Exception as e:
        logger.error(f"Произошла ошибка при обработке обновления: {e}", exc_info=True)
        
    return 'ok'


async def process_update_async(flask_request):
    """Асинхронно обрабатывает обновление."""
    update_data = flask_request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    
    # Мы больше не инициализируем бота здесь, т.к. persistence не работает
    # в serverless так, как мы ожидаем. Просто обрабатываем.
    await application.process_update(update)

# GET-запрос для проверки работоспособности
@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    return 'ok'