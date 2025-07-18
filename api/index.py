# api/index.py
import os
import asyncio
import logging
import json
from fastapi import FastAPI, Request, Response, HTTPException
from edge_config_persistence import EdgeConfigPersistence


from telegram import Update
from telegram.ext import Application, PicklePersistence

# Import the function that adds handlers
from bot_logic import add_handlers

# --- Global App ---
# We use FastAPI for its robust web handling capabilities
app = FastAPI(docs_url=None, redoc_url=None)
# The application object is now created on-demand inside the webhook
application = None

async def main_handler(request_data: dict):
    """
    The single entry point for all async operations.
    It creates, initializes, and processes updates with one application instance.
    """
    global application
    
    # Create the application object on every invocation.
    # In a serverless environment, this is safer than relying on a global instance.
    persistence = EdgeConfigPersistence()

    bot_token = os.getenv("TELEGRAM_TOKEN")
    
    application = (
        Application.builder()
        .token(bot_token)
        .persistence(persistence)
        .build()
    )
    
    # Add all command/message/callback handlers
    add_handlers(application)
    
    # Initialize the application
    await application.initialize()
    
    # Process the update
    update = Update.de_json(request_data, application.bot)
    await application.process_update(update)
    
    # Clean up the application
    await application.shutdown()

@app.post("/api")
async def telegram_webhook(request: Request):
    """Endpoint to receive updates from Telegram."""
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        data = await request.json()
        await main_handler(data)
    except Exception as e:
        logging.error(f"Error processing update: {e}", exc_info=True)

    return Response(status_code=200)

@app.get("/")
def health_check():
    """A simple endpoint to check if the service is alive."""
    return {"status": "ok"}