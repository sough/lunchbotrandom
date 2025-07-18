# edge_config_persistence.py
import os
import requests
import json
import logging
from telegram.ext import BasePersistence

logger = logging.getLogger(__name__)

class EdgeConfigPersistence(BasePersistence):
    def __init__(self):
        super().__init__()
        self.api_token = os.getenv("VERCEL_API_TOKEN")
        self.edge_config_id = os.getenv("EDGE_CONFIG_ID_ONLY")
        
        if not all([self.api_token, self.edge_config_id]):
            raise ValueError("Required environment variables VERCEL_API_TOKEN or EDGE_CONFIG_ID_ONLY are not set.")

        self.api_endpoint = f"https://api.vercel.com/v1/edge-config/{self.edge_config_id}/items"
        self.item_endpoint = f"https://api.vercel.com/v1/edge-config/{self.edge_config_id}/item"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _write_item(self, key: str, value) -> None:
        """Writes a single key-value pair to Edge Config."""
        try:
            payload = {"items": [{"operation": "update", "key": key, "value": value}]}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to write item '{key}': {e}. Response: {e.response.text if e.response else 'No response'}")

    def _read_item(self, key: str):
        """Reads a single item from Edge Config."""
        try:
            response = requests.get(f"{self.item_endpoint}/{key}", headers={"Authorization": f"Bearer {self.api_token}"}, timeout=5)
            if response.status_code == 404: return None
            response.raise_for_status()
            return response.json() if response.text else None
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Failed to read item '{key}': {e}")
            return None

    def _delete_item(self, key: str) -> None:
        """Deletes a single item from Edge Config."""
        self._write_item(key, None) # Setting value to null can also work for deletion

    # --- Implemented Abstract Methods ---
    async def get_user_data(self) -> dict[int, dict]:
        data_str = self._read_item("user_data")
        return json.loads(data_str) if isinstance(data_str, str) else {}

    async def update_user_data(self, user_id: int, data: dict) -> None:
        current_data = await self.get_user_data()
        current_data[user_id] = data
        self._write_item("user_data", json.dumps(current_data))
    
    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        fresh_data = await self.get_user_data()
        user_data.update(fresh_data.get(user_id, {}))

    async def drop_user_data(self, user_id: int) -> None:
        current_data = await self.get_user_data()
        current_data.pop(user_id, None)
        self._write_item("user_data", json.dumps(current_data))

    # --- Other required methods ---
    async def get_bot_data(self) -> dict:
        data_str = self._read_item("bot_data")
        return json.loads(data_str) if isinstance(data_str, str) else {}
    async def update_bot_data(self, data: dict) -> None:
        self._write_item("bot_data", json.dumps(data))
    async def refresh_bot_data(self, bot_data: dict) -> None:
        bot_data.update(await self.get_bot_data())
    async def get_chat_data(self) -> dict[int, dict]: return {}
    async def update_chat_data(self, chat_id: int, data: dict) -> None: pass
    async def drop_chat_data(self, chat_id: int, data: dict) -> None: pass
    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None: pass
    async def get_conversations(self, name: str) -> dict:
        # Conversation persistence with pickle is problematic, we'll store as simple JSON
        data_str = self._read_item(f"conversation_{name}")
        return json.loads(data_str) if isinstance(data_str, str) else {}
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None:
        # This simplified handler may not support complex conversation states
        # but will prevent crashes.
        pass
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass