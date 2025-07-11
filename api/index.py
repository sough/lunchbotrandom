# api/index.py
import os
import asyncio
import logging
import json
from http.server import BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import PicklePersistence

# We are importing the setup function
from bot_logic import setup_application

# --- Global Variables & Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

application = None
init_lock = asyncio.Lock()

async def initialize_bot():
    """Creates and initializes the bot application if it hasn't been already."""
    global application
    async with init_lock:
        if application is None:
            logger.info("Performing one-time bot initialization...")
            persistence = PicklePersistence(filepath="/tmp/bot_persistence")
            bot_token = os.getenv("TELEGRAM_TOKEN")
            application = setup_application(persistence, bot_token)
            await application.initialize()
            
            webhook_url = os.getenv("VERCEL_CUSTOM_URL")
            secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
            if webhook_url:
                full_webhook_url = f"https://{webhook_url}/api/index"
                await application.bot.set_webhook(full_webhook_url, secret_token=secret_token)
                logger.info(f"Webhook set to {full_webhook_url}")
            
            logger.info("Bot initialization complete.")

# This is the Vercel handler function for Python
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Handles incoming POST requests from Telegram."""
        asyncio.run(self.process_async())
        return

    async def process_async(self):
        """The main async processing logic."""
        try:
            # Ensure the bot is initialized
            if application is None:
                await initialize_bot()
            
            # Read the request body
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            
            # --- SECRET TOKEN CHECK ---
            secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
            if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret_token:
                logger.warning("Invalid secret token received.")
                self.send_response(401) # Unauthorized
                self.end_headers()
                return

            # Process the update
            update = Update.de_json(json.loads(body), application.bot)
            logger.info(f"Received update: update_id={update.update_id}")
            await application.process_update(update)

        except Exception as e:
            logger.error(f"Error processing update: {e}", exc_info=True)
        
        finally:
            # Always send a 200 OK response to Telegram
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')