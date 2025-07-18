# edge_config_persistence.py
import os
import requests
import pickle
from telegram.ext import BasePersistence

class EdgeConfigPersistence(BasePersistence):
    """
    A persistence class that uses Vercel Edge Config via its REST API.
    """
    def __init__(self):
        # The `store_callback_data` argument has been removed from this call
        super().__init__()
        self.edge_config_url = os.getenv("EDGE_CONFIG")
        if not self.edge_config_url:
            raise ValueError("EDGE_CONFIG environment variable not set.")
        self.api_endpoint = f"{self.edge_config_url}/items"
        self.headers = {"Content-Type": "application/json"}

    def _read_all_data(self) -> dict:
        """Helper to read all items from Edge Config."""
        try:
            response = requests.get(self.api_endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return {}

    def _write_items(self, items: list) -> None:
        """Helper to write items to Edge Config."""
        try:
            payload = {"items": items}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to write to Edge Config: {e}")
            
    def _read_single_item(self, key: str):
        """Helper to read a single item."""
        try:
            response = requests.get(f"{self.edge_config_url}/item/{key}", timeout=5)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None

    def _delete_item(self, key: str):
        """Helper to delete an item."""
        self._write_items([{"operation": "delete", "key": key}])

    async def get_bot_data(self) -> dict:
        data = self._read_single_item("bot_data")
        return pickle.loads(bytes.fromhex(data)) if data else {}

    async def update_bot_data(self, data: dict) -> None:
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": "bot_data", "value": value}])

    async def get_chat_data(self) -> dict[int, dict]:
        return {}

    async def update_chat_data(self, chat_id: int, data: dict) -> None:
        key = f"chat_{chat_id}"
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": key, "value": value}])

    async def get_user_data(self) -> dict[int, dict]:
        return {}

    async def update_user_data(self, user_id: int, data: dict) -> None:
        key = f"user_{user_id}"
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": key, "value": value}])
        
    async def get_conversations(self, name: str) -> dict:
        data = self._read_single_item(f"conversation_{name}")
        return pickle.loads(bytes.fromhex(data)) if data else {}

    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None:
        conversations = await self.get_conversations(name)
        if new_state is None:
            conversations.pop(key, None)
        else:
            conversations[key] = new_state
        
        redis_key = f"conversation_{name}"
        value = pickle.dumps(conversations).hex()
        self._write_items([{"operation": "update", "key": redis_key, "value": value}])

    async def drop_chat_data(self, chat_id: int) -> None:
        self._delete_item(f"chat_{chat_id}")

    async def drop_user_data(self, user_id: int) -> None:
        self._delete_item(f"user_{user_id}")

    async def refresh_bot_data(self, bot_data: dict) -> None:
        data = await self.get_bot_data()
        bot_data.update(data)

    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None:
        key = f"chat_{chat_id}"
        data_str = self._read_single_item(key)
        data = pickle.loads(bytes.fromhex(data_str)) if data_str else {}
        chat_data.update(data)

    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        key = f"user_{user_id}"
        data_str = self._read_single_item(key)
        data = pickle.loads(bytes.fromhex(data_str)) if data_str else {}
        user_data.update(data)
        
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass