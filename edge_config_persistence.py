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
        super().__init__()
        self.edge_config_url = os.getenv("EDGE_CONFIG")
        if not self.edge_config_url:
            raise ValueError("EDGE_CONFIG environment variable not set.")
        self.api_endpoint = f"{self.edge_config_url}/items"
        self.headers = {"Content-Type": "application/json"}
        # Pre-fetch data on initialization
        self._load_data()

    def _load_data(self):
        """Loads all data from Edge Config into memory."""
        all_data = self._read_all_data()
        self.user_data = self._deserialize_data(all_data, "user_")
        self.chat_data = self._deserialize_data(all_data, "chat_")
        self.bot_data = self._deserialize_data(all_data, "bot_data")
        self.conversations = self._deserialize_data(all_data, "conversation_")

    def _read_all_data(self) -> dict:
        try:
            response = requests.get(self.api_endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return {}

    def _write_items(self, items: list) -> None:
        try:
            payload = {"items": items}
            response = requests.patch(self.api_endpoint, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to write to Edge Config: {e}")

    def _deserialize_data(self, all_data: dict, prefix: str) -> dict:
        """Helper to filter and deserialize data based on a key prefix."""
        deserialized = {}
        for key, value in all_data.items():
            if key.startswith(prefix):
                try:
                    # Handle single items like bot_data
                    if key == prefix:
                        return pickle.loads(bytes.fromhex(value))
                    # Handle keyed items like user_data
                    item_id = int(key.split("_")[1])
                    deserialized[item_id] = pickle.loads(bytes.fromhex(value))
                except (ValueError, IndexError, TypeError):
                    continue
        return deserialized
        
    def _delete_item(self, key: str):
        self._write_items([{"operation": "delete", "key": key}])

    # --- Implemented Abstract Methods ---
    async def get_bot_data(self) -> dict:
        return self.bot_data.copy()

    async def update_bot_data(self, data: dict) -> None:
        self.bot_data = data
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": "bot_data", "value": value}])

    async def get_chat_data(self) -> dict[int, dict]:
        return self.chat_data.copy()

    async def update_chat_data(self, chat_id: int, data: dict) -> None:
        self.chat_data[chat_id] = data
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": f"chat_{chat_id}", "value": value}])

    async def get_user_data(self) -> dict[int, dict]:
        return self.user_data.copy()

    async def update_user_data(self, user_id: int, data: dict) -> None:
        self.user_data[user_id] = data
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": f"user_{user_id}", "value": value}])
        
    async def get_conversations(self, name: str) -> dict:
        return self.conversations.get(name, {}).copy()

    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None:
        if name not in self.conversations:
            self.conversations[name] = {}
        if new_state is None:
            self.conversations[name].pop(key, None)
        else:
            self.conversations[name][key] = new_state
        value = pickle.dumps(self.conversations[name]).hex()
        self._write_items([{"operation": "update", "key": f"conversation_{name}", "value": value}])

    # --- Newly Implemented Methods ---
    async def drop_chat_data(self, chat_id: int) -> None:
        self.chat_data.pop(chat_id, None)
        self._delete_item(f"chat_{chat_id}")

    async def drop_user_data(self, user_id: int) -> None:
        self.user_data.pop(user_id, None)
        self._delete_item(f"user_{user_id}")

    async def refresh_bot_data(self, bot_data: dict) -> None:
        all_data = self._read_all_data()
        fresh_bot_data = self._deserialize_data(all_data, "bot_data")
        bot_data.update(fresh_bot_data)

    async def refresh_chat_data(self, chat_id: int, chat_data: dict) -> None:
        all_data = self._read_all_data()
        fresh_chat_data = self._deserialize_data(all_data, f"chat_{chat_id}")
        chat_data.update(fresh_chat_data.get(chat_id, {}))

    async def refresh_user_data(self, user_id: int, user_data: dict) -> None:
        all_data = self._read_all_data()
        fresh_user_data = self._deserialize_data(all_data, f"user_{user_id}")
        user_data.update(fresh_user_data.get(user_id, {}))
        
    async def get_callback_data(self) -> dict | None:
        return None  # We are not storing callback data

    async def update_callback_data(self, data: dict) -> None:
        pass  # We are not storing callback data

    async def flush(self) -> None:
        pass # Data is written immediately, so no flush action is needed