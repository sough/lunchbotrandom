import os
import asyncio
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import PicklePersistence

# We are importing the setup function
from bot_logic import setup_application

# --- Global Variables & Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# A global placeholder for the application and a lock
application = None
init_lock = asyncio.Lock()

async def initialize_bot():
    """Creates and initializes the bot application if it hasn't been already."""
    global application
    # This async lock ensures that even if multiple requests come in at once on a
    # cold start, only one of them will perform the initialization.
    async with init_lock:
        if application is None:
            logger.info("Performing one-time bot initialization...")
            persistence = PicklePersistence(filepath="/tmp/bot_persistence")
            # We must pass the token directly to the builder now
            bot_token = os.getenv("TELEGRAM_TOKEN")
            application = setup_application(persistence, bot_token)
            await application.initialize()
            
            # Set the webhook, now with the secret token included
            webhook_url = os.getenv("VERCEL_URL")
            secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
            if webhook_url:
                full_webhook_url = f"https://{webhook_url}/api"
                await application.bot.set_webhook(full_webhook_url, secret_token=secret_token)
                logger.info(f"Webhook set to {full_webhook_url}")
            
            logger.info("Bot initialization complete.")

@app.post("/api")
async def telegram_webhook(request: Request):
    """Handles incoming updates from Telegram."""
    
    # Ensure the bot is initialized before processing any updates
    if application is None:
        await initialize_bot()
    
    # Verify secret token
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret_token:
        logger.warning("Invalid secret token received.")
        return Response(status_code=401)
        
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