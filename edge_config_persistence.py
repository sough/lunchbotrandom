# edge_config_persistence.py
import os
import requests
import json
import logging
from telegram.ext import BasePersistence

logger = logging.getLogger(__name__)

class EdgeConfigPersistence(BasePersistence):
    """
    A persistence class that uses Vercel Edge Config via its REST API,
    storing each user's data under its own key.
    """
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

    def _write_item(self, key: str, value: dict) -> None:
        """Writes a single key-value pair to Edge Config."""
        try:
            # Vercel's API requires a PATCH for updates, even for a single item
            payload = {"items": [{"operation": "update", "key": key, "value": value}]}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to write item '{key}' to Edge Config: {e}. Response: {e.response.text if e.response else 'No response'}")

    def _read_item(self, key: str) -> dict | None:
        """Reads a single item from Edge Config."""
        try:
            response = requests.get(f"{self.item_endpoint}/{key}", headers={"Authorization": f"Bearer {self.api_token}"}, timeout=5)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Failed to read item '{key}' from Edge Config: {e}")
            return None

    def _delete_item(self, key: str) -> None:
        """Deletes a single item from Edge Config."""
        try:
            payload = {"items": [{"operation": "delete", "key": key}]}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to delete item '{key}' from Edge Config: {e}. Response: {e.response.text if e.response else 'No response'}")

    # --- Implemented Abstract Methods ---
    async def get_user_data(self) -> dict[int, dict]:
        # We will load user data on demand via refresh_user_data,
        # so we start with an empty dictionary.
        return {}

    async def update_user_data(self, user_id: int, data: dict) -> None:
        self._write_item(f"user_{user_id}", data)

    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        """This is now the main method for loading data for a specific user."""
        fresh_data = self._read_item(f"user_{user_id}")
        if fresh_data:
            user_data.update(fresh_data)

    async def drop_user_data(self, user_id: int) -> None:
        self._delete_item(f"user_{user_id}")
    
    # --- Other required methods (simplified) ---
    async def get_bot_data(self) -> dict:
        return self._read_item("bot_data") or {}
    async def update_bot_data(self, data: dict) -> None:
        self._write_item("bot_data", data)
    async def refresh_bot_data(self, bot_data: dict) -> None:
        bot_data.update(await self.get_bot_data())
    async def get_chat_data(self) -> dict[int, dict]: return {}
    async def update_chat_data(self, chat_id: int, data: dict) -> None: pass
    async def drop_chat_data(self, chat_id: int) -> None: pass
    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None: pass
    async def get_conversations(self, name: str) -> dict: return {}
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None: pass
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass