# api/index.py
import os
import asyncio
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import PicklePersistence

# We are importing the setup function, not a pre-built application object
from bot_logic import setup_application

# --- Global Variables ---
# We create a placeholder for our application object
application = None
# A flag to ensure initialization happens only once per cold start
is_initialized = False

# --- FastAPI App ---
app = FastAPI()

async def initialize_bot():
    """Creates and initializes the bot application."""
    global application, is_initialized
    if not is_initialized:
        logging.info("Performing one-time bot initialization...")
        persistence = PicklePersistence(filepath="/tmp/bot_persistence")
        application = setup_application(persistence)
        await application.initialize()
        
        # Automatically set the webhook
        webhook_url = os.getenv("VERCEL_URL")
        if webhook_url:
            full_webhook_url = f"https://{webhook_url}/api/"
            await application.bot.set_webhook(full_webhook_url)
            logging.info(f"Webhook set to {full_webhook_url}")
            
        is_initialized = True
        logging.info("Bot initialization complete.")
    else:
        logging.info("Bot already initialized, skipping setup.")

@app.post("/api")
async def telegram_webhook(request: Request):
    """Handles incoming updates from Telegram by initializing the bot if necessary."""
    global application
    
    # Ensure the bot is initialized before processing any updates
    if not application or not is_initialized:
        await initialize_bot()
        
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        logging.info(f"Received update: update_id={update.update_id}")
        await application.process_update(update)
    except Exception as e:
        logging.error(f"Error processing update: {e}", exc_info=True)
    
    return Response(status_code=200)

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}