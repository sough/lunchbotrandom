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
            raise ValueError("Required env vars VERCEL_API_TOKEN or EDGE_CONFIG_ID_ONLY are not set.")

        self.api_endpoint = f"https://api.vercel.com/v1/edge-config/{self.edge_config_id}/items"
        self.headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    def _read_all_data(self) -> dict:
        try:
            response = requests.get(self.api_endpoint, headers=self.headers, timeout=5)
            response.raise_for_status()
            return response.json().get("items", {})
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Failed to read from Edge Config: {e}"); return {}

    def _write_items(self, items: list) -> None:
        try:
            payload = {"items": items}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to write to Edge Config: {e}. Response: {e.response.text if e.response else 'No response'}")

    async def get_user_data(self) -> dict[int, dict]:
        all_data = self._read_all_data()
        user_data_str = all_data.get("user_data", "{}")
        try:
            user_data = json.loads(user_data_str)
            return {int(k): v for k, v in user_data.items()}
        except (json.JSONDecodeError, TypeError): return {}

    async def update_user_data(self, user_id: int, data: dict) -> None:
        current_data = await self.get_user_data()
        current_data[user_id] = data
        self._write_items([{"operation": "update", "key": "user_data", "value": json.dumps(current_data)}])
    
    # --- Other required methods ---
    async def get_bot_data(self) -> dict: return self._read_all_data().get("bot_data", {})
    async def update_bot_data(self, data: dict) -> None: self._write_items([{"operation": "update", "key": "bot_data", "value": data}])
    async def get_chat_data(self) -> dict[int, dict]: return {}
    async def update_chat_data(self, chat_id: int, data: dict) -> None: pass
    async def get_conversations(self, name: str) -> dict: return {}
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None: pass
    async def drop_chat_data(self, chat_id: int) -> None: pass
    async def drop_user_data(self, user_id: int) -> None:
        current_data = await self.get_user_data(); current_data.pop(user_id, None)
        self._write_items([{"operation": "update", "key": "user_data", "value": json.dumps(current_data)}])
    async def refresh_bot_data(self, bot_data: dict) -> None: bot_data.update(await self.get_bot_data())
    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None: pass
    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        all_data = await self.get_user_data(); user_data.update(all_data.get(user_id, {}))
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass