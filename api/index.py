# api/index.py
import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import PicklePersistence

# Импортируем нашу логику
from bot_logic import setup_application

# Создаем Flask-приложение
app = Flask(__name__)

# Настраиваем persistence
# Vercel предоставляет временную файловую систему в /tmp
persistence = PicklePersistence(filepath="/tmp/bot_persistence")

# Настраиваем бота один раз при старте
application = setup_application(persistence)

# Это главная функция, которая будет обрабатывать веб-хуки
@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def webhook(path):
    # Запускаем асинхронную обработку обновления
    asyncio.run(process_update())
    return 'ok'

async def process_update():
    # Получаем данные из запроса
    update_data = request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    
    # Передаем обновление в очередь для обработки
    await application.update_queue.put(update)

# Это необязательно, но полезно для отладки
@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def health_check(path):
    return 'ok'