# api/index.py
import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

# Импортируем нашу логику
from bot_logic import setup_application

# --- Настройка логирования, чтобы видеть вывод в Vercel ---
# Это важно для отладки!
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# --- Инициализация ---
app = Flask(__name__)

# Vercel предоставляет временную файловую систему в /tmp
persistence = PicklePersistence(filepath="/tmp/bot_persistence")

logger.info("Инициализация приложения Telegram...")
application = setup_application(persistence)
logger.info("Приложение Telegram успешно инициализировано.")

@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    """Главная функция, которая обрабатывает входящие запросы от Telegram."""
    logger.info("Получен входящий POST-запрос от Telegram.")
    
    try:
        # Получаем данные из тела запроса
        update_data = request.get_json(force=True)
        
        # Преобразуем JSON в объект Update
        update = Update.de_json(update_data, application.bot)
        logger.info(f"Десериализовано обновление: update_id={update.update_id}")

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
        # Вместо помещения в очередь, напрямую обрабатываем обновление.
        # Это более надежный метод для serverless-окружения.
        # Запускаем асинхронную обработку в синхронном контексте Flask.
        asyncio.run(application.process_update(update))
        
        logger.info("Обработка обновления успешно завершена.")
        return 'ok'

    except Exception as e:
        # Логируем любую ошибку, которая произошла во время обработки
        logger.error(f"Произошла ошибка при обработке обновления: {e}", exc_info=True)
        # Возвращаем 'ok', чтобы Telegram не пытался отправить обновление повторно
        return 'ok'

@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    """Проверка, что сервис жив."""
    return 'ok'