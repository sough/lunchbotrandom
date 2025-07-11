# api/index.py
import os
import asyncio
import logging
import nest_asyncio
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, PicklePersistence

# Импортируем нашу функцию для настройки хендлеров
from bot_logic import add_handlers

# Применяем патч ДО создания любого цикла событий
nest_asyncio.apply()

# --- Global App ---
app = FastAPI()
application = None

@app.on_event("startup")
async def startup_event():
    """Создает, инициализирует и настраивает бота при старте Vercel."""
    global application
    logging.info("Starting up...")
    
    persistence = PicklePersistence(filepath="/tmp/bot_persistence")
    bot_token = os.getenv("TELEGRAM_TOKEN")
    
    # Создаем объект Application
    application = (
        Application.builder()
        .token(bot_token)
        .persistence(persistence)
        .build()
    )
    
    # Добавляем все наши хендлеры из bot_logic.py
    add_handlers(application)
    
    # Инициализируем приложение
    await application.initialize()
    
    # Устанавливаем веб-хук
    webhook_url = os.getenv("VERCEL_CUSTOM_URL")
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if webhook_url:
        full_webhook_url = f"https://{webhook_url}/api"
        await application.bot.set_webhook(full_webhook_url, secret_token=secret_token)
        logging.info(f"Webhook set to {full_webhook_url}")
        
    logging.info("Startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    """Корректно останавливает бота."""
    if application:
        logging.info("Shutting down...")
        await application.shutdown()
        logging.info("Shutdown complete.")

@app.post("/api")
async def telegram_webhook(request: Request):
    """Принимает обновления от Telegram."""
    if not application:
        return Response(content="Application not initialized", status_code=500)

    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret_token:
        return Response(status_code=401)
        
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logging.error(f"Error processing update: {e}", exc_info=True)
    
    return Response(status_code=200)

@app.get("/")
def health_check():
    return {"status": "ok"}