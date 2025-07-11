# api/index.py
import os
import asyncio
import logging
import nest_asyncio
from fastapi import FastAPI, Request, Response, HTTPException

from telegram import Update
from telegram.ext import PicklePersistence

# Import the function that adds handlers
from bot_logic import add_handlers

# Apply the patch immediately when the module is loaded
nest_asyncio.apply()

# --- Global Variables & Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None)

# Global placeholder for the application and a lock to prevent race conditions
application = None
init_lock = asyncio.Lock()

async def initialize_bot():
    """
    Creates and initializes the bot application.
    The lock ensures this function runs only once, even if multiple requests
    arrive simultaneously on a cold start.
    """
    global application
    async with init_lock:
        if application is None:
            logger.info("Application not initialized. Performing one-time setup...")
            persistence = PicklePersistence(filepath="/tmp/bot_persistence")
            bot_token = os.getenv("TELEGRAM_TOKEN")
            
            # Build the application
            application = (
                Application.builder()
                .token(bot_token)
                .persistence(persistence)
                .build()
            )
            
            # Add all command/message/callback handlers
            add_handlers(application)
            
            # Initialize the application (loads persistence, etc.)
            await application.initialize()
            
            # Set the webhook to let Telegram know where to send updates
            webhook_url = os.getenv("VERCEL_URL")
            secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
            if webhook_url:
                full_webhook_url = f"https://{webhook_url}/api"
                await application.bot.set_webhook(full_webhook_url, secret_token=secret_token)
                logger.info(f"Webhook set to {full_webhook_url}")
            
            logger.info("Bot initialization complete.")
        else:
            logger.info("Application already initialized. Skipping setup.")


@app.post("/api")
async def telegram_webhook(request: Request):
    """
    This is the main endpoint that receives updates from Telegram.
    It ensures the bot is initialized before processing the update.
    """
    # On the very first request, this will trigger the initialization
    if application is None:
        await initialize_bot()
    
    # --- Security Check ---
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret_token:
        logger.warning("Invalid secret token received. Aborting.")
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # --- Process Update ---
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
    """A simple endpoint to check if the service is alive."""
    return {"status": "ok"}