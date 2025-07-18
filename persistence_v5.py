# persistence.py
import os
import json
import logging
import redis

logger = logging.getLogger(__name__)

# --- Database (Vercel KV / Redis) ---
try:
    redis_client = redis.from_url(os.getenv("KV_URL"))
except Exception as e:
    logger.error(f"Could not connect to Redis: {e}")
    redis_client = None

def load_user_data(user_id: int) -> dict:
    """Loads user data from Redis."""
    if not redis_client: return {}
    try:
        data = redis_client.get(f"user:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"Failed to load data for user {user_id}: {e}"); return {}

def save_user_data(user_id: int, data: dict) -> None:
    """Saves user data to Redis."""
    if not redis_client: return
    try:
        redis_client.set(f"user:{user_id}", json.dumps(data))
    except Exception as e:
        logger.error(f"Failed to save data for user {user_id}: {e}")