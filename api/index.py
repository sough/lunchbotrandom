# api/index.py
import os
import asyncio
import logging
from fastapi import FastAPI, Request, Response, HTTPException

from telegram import Update
from telegram.ext import PicklePersistence

from bot_logic import setup_application

# --- Global Variables & Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
persistence = PicklePersistence(filepath="/tmp/bot_persistence")
application = setup_application(persistence)

# Get the secret token from environment variables
SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN")

is_initialized = False

async def initialize_bot():
    """Creates, initializes the bot, and sets the webhook with a secret token."""
    global is_initialized
    if not is_initialized:
        logger.info("Performing one-time bot initialization...")
        await application.initialize()
        
        webhook_url = os.getenv("VERCEL_URL")
        if webhook_url:
            full_webhook_url = f"https://{webhook_url}/api"
            # Set the webhook and include the secret token
            await application.bot.set_webhook(full_webhook_url, secret_token=SECRET_TOKEN)
            logger.info(f"Webhook set to {full_webhook_url} with secret token.")
            
        is_initialized = True
        logger.info("Bot initialization complete.")

@app.on_event("startup")
async def startup_event():
    """Initializes the bot when the application starts."""
    await initialize_bot()

@app.post("/api")
async def telegram_webhook(request: Request):
    """Handles incoming updates from Telegram after verifying the secret token."""
    # --- ADDED SECURITY CHECK ---
    # Check if the secret token from Telegram matches ours
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET_TOKEN:
        logger.warning("Invalid secret token received.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        logger.info(f"Received update: update_id={update.update_id}")
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
    
    return Response(status_code=200)

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}