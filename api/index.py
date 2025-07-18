import os, asyncio, logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application
from edge_config_persistence import EdgeConfigPersistence
from bot_logic_v2 import add_handlers

app = FastAPI(docs_url=None, redoc_url=None)
application = None

@app.on_event("startup")
async def startup_event():
    global application
    logging.info("Starting up and initializing application...")
    persistence = EdgeConfigPersistence()
    bot_token = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(bot_token).persistence(persistence).build()
    add_handlers(application)
    await application.initialize()
    webhook_url = os.getenv("VERCEL_URL")
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if webhook_url:
        full_webhook_url = f"https://{webhook_url}/api"
        await application.bot.set_webhook(full_webhook_url, secret_token=secret_token)
    logging.info("Startup complete.")

@app.post("/api")
async def telegram_webhook(request: Request):
    if not application: return Response(content="Application not initialized", status_code=500)
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