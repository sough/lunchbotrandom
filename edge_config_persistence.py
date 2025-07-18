# edge_config_persistence.py
import os
import requests
import pickle
import logging
from urllib.parse import urlparse
from telegram.ext import BasePersistence

logger = logging.getLogger(__name__)

class EdgeConfigPersistence(BasePersistence):
    """
    A persistence class that uses Vercel Edge Config via its REST API.
    It uses the read-only EDGE_CONFIG for reads and a VERCEL_API_TOKEN for writes.
    """
    def __init__(self):
        super().__init__()
        # Read-only connection string from Vercel
        self.edge_config_url = os.getenv("EDGE_CONFIG")
        if not self.edge_config_url:
            raise ValueError("EDGE_CONFIG environment variable not set.")
        
        # Vercel API token with write permissions
        self.api_token = os.getenv("VERCEL_API_TOKEN")
        if not self.api_token:
            raise ValueError("VERCEL_API_TOKEN environment variable for writing is not set.")

        # Extract Edge Config ID from the connection string
        try:
            parsed_url = urlparse(self.edge_config_url)
            self.edge_config_id = parsed_url.path.split('/')[-1]
        except (IndexError, AttributeError):
            raise ValueError("Could not parse Edge Config ID from EDGE_CONFIG URL.")

        # Construct the correct API endpoints
        self.read_endpoint = f"{self.edge_config_url}/items"
        self.write_endpoint = f"https://api.vercel.com/v1/edge-config/{self.edge_config_id}/items"
        self.write_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

    def _read_all_data(self) -> dict:
        try:
            response = requests.get(self.read_endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to read from Edge Config: {e}")
            return {}

    def _write_items(self, items: list) -> None:
        try:
            payload = {"items": items}
            response = requests.patch(self.write_endpoint, headers=self.write_headers, json=payload, timeout=5)
            response.raise_for_status()
            logger.info(f"Successfully wrote {len(items)} item(s) to Edge Config.")
        except requests.RequestException as e:
            logger.error(f"Failed to write to Edge Config: {e}. Response: {e.response.text if e.response else 'No response'}")

    # ... The rest of the methods remain the same ...
    async def get_user_data(self) -> dict[int, dict]:
        all_data = self._read_all_data()
        user_data = {}
        for key, value in all_data.items():
            if key.startswith("user_"):
                try:
                    user_id = int(key.split("_")[1])
                    user_data[user_id] = pickle.loads(bytes.fromhex(value))
                except (ValueError, IndexError, TypeError):
                    continue
        return user_data

    async def update_user_data(self, user_id: int, data: dict) -> None:
        key = f"user_{user_id}"
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": key, "value": value}])

    async def get_bot_data(self) -> dict:
        all_data = self._read_all_data()
        hex_data = all_data.get("bot_data")
        return pickle.loads(bytes.fromhex(hex_data)) if hex_data else {}
    async def update_bot_data(self, data: dict) -> None:
        value = pickle.dumps(data).hex(); self._write_items([{"operation": "update", "key": "bot_data", "value": value}])
    async def get_chat_data(self) -> dict[int, dict]: return {}
    async def update_chat_data(self, chat_id: int, data: dict) -> None: pass
    async def get_conversations(self, name: str) -> dict: return {}
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None: pass
    async def drop_chat_data(self, chat_id: int) -> None: pass
    async def drop_user_data(self, user_id: int) -> None: self._write_items([{"operation": "delete", "key": f"user_{user_id}"}])
    async def refresh_bot_data(self, bot_data: dict) -> None: bot_data.update(await self.get_bot_data())
    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None: pass
    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        # For simplicity, we assume the initial fetch in get_user_data is sufficient for a single request
        pass
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass