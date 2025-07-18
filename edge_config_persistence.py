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
        # Pre-fetch all data on initialization
        self.user_data = self._get_all_user_data()
        self.chat_data = {} # Assuming not used
        self.bot_data = {}  # Assuming not used
        self.conversations = {} # Assuming not used


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
            
    def _get_all_user_data(self) -> dict[int, dict]:
        """Fetches and deserializes all user data on startup."""
        all_data = self._read_all_data()
        user_data = {}
        for key, value in all_data.items():
            if key.startswith("user_"):
                try:
                    user_id = int(key.split("_")[1])
                    user_data[user_id] = pickle.loads(bytes.fromhex(value))
                except (ValueError, IndexError, TypeError):
                    continue
        print(f"Loaded {len(user_data)} user data records.")
        return user_data

    # --- Implemented Abstract Methods ---
    async def get_user_data(self) -> dict[int, dict]:
        return self.user_data.copy()

    async def update_user_data(self, user_id: int, data: dict) -> None:
        self.user_data[user_id] = data
        key = f"user_{user_id}"
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": key, "value": value}])

    async def drop_user_data(self, user_id: int) -> None:
        self.user_data.pop(user_id, None)
        self._write_items([{"operation": "delete", "key": f"user_{user_id}"}])
    
    # --- Other required methods ---
    async def get_bot_data(self) -> dict: return self.bot_data.copy()
    async def update_bot_data(self, data: dict) -> None: self.bot_data = data
    async def get_chat_data(self) -> dict[int, dict]: return self.chat_data.copy()
    async def update_chat_data(self, chat_id: int, data: dict) -> None: self.chat_data[chat_id] = data
    async def drop_chat_data(self, chat_id: int) -> None: self.chat_data.pop(chat_id, None)
    async def get_conversations(self, name: str) -> dict: return self.conversations.get(name, {}).copy()
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None:
        if name not in self.conversations: self.conversations[name] = {}
        if new_state is None: self.conversations[name].pop(key, None)
        else: self.conversations[name][key] = new_state
    async def flush(self) -> None:
        # This is where we would write all data to Edge Config if we were batching.
        # Since we write on each update, we can just save bot_data here.
        value = pickle.dumps(self.bot_data).hex()
        self._write_items([{"operation": "update", "key": "bot_data", "value": value}])