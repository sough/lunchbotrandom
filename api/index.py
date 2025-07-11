# api/index.py
import os
import asyncio
import logging
from fastapi import FastAPI, Request, Response

from telegram import Update
from telegram.ext import PicklePersistence

from bot_logic import setup_application

# --- Настройка ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Используем FastAPI вместо Flask
app = FastAPI()

persistence = PicklePersistence(filepath="/tmp/bot_persistence")
application = setup_application(persistence)

@app.on_event("startup")
async def startup_event():
    """Выполняет инициализацию бота при старте FastAPI."""
    logger.info("Запускаю инициализацию бота...")
    await application.initialize()
    # Сразу регистрируем веб-хук при старте, если его нет
    # VERCEL_URL будет доступна как переменная окружения на Vercel
    webhook_url = os.getenv("VERCEL_URL")
    if webhook_url:
        await application.bot.set_webhook(f"https://{webhook_url}/api")
    logger.info("Бот успешно инициализирован.")

@app.on_event("shutdown")
async def shutdown_event():
    """Корректно останавливает бота при остановке FastAPI."""
    logger.info("Останавливаю бота...")
    await application.shutdown()
    logger.info("Бот остановлен.")

@app.post("/api")
async def telegram_webhook(request: Request):
    """Принимает обновления от Telegram."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        logger.info(f"Получено обновление: update_id={update.update_id}")
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка обработки обновления: {e}", exc_info=True)
    
    return Response(status_code=200)

@app.get("/")
def health_check():
    """Проверка, что сервис жив."""
    return {"status": "ok"}