# api/index.py
import os
import asyncio
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application
from bot_logic import add_handlers

# --- FastAPI Boilerplate ---
app = FastAPI(docs_url=None, redoc_url=None)
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

@app.post("/api")
async def telegram_webhook(request: Request):
    """This function is the single entry point for all incoming Telegram updates."""
    
    # Create a new application instance for each request
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add all the handlers from bot_logic.py
    add_handlers(application)
    
    try:
        async with application:
            # Initialize the application
            await application.initialize()
            
            # Process the single update
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            
            # Shut down cleanly
            await application.shutdown()
            
    except Exception as e:
        logging.error(f"Error processing update: {e}", exc_info=True)
        
    return Response(status_code=200)

@app.get("/")
def health_check():
    """A simple endpoint to check if the service is alive."""
    return {"status": "ok"}