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
        super().__init__(store_callback_data=False)
        self.edge_config_url = os.getenv("EDGE_CONFIG")
        if not self.edge_config_url:
            raise ValueError("EDGE_CONFIG environment variable not set.")
        # The API endpoint is the connection string with /items at the end
        self.api_endpoint = f"{self.edge_config_url}/items"

    def _read_all_data(self) -> dict:
        """Helper function to read all items from Edge Config."""
        try:
            response = requests.get(self.api_endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return {}

    def _write_items(self, items: list) -> None:
        """Helper function to write items to Edge Config."""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {"items": items}
            response = requests.patch(self.api_endpoint, headers=headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to write to Edge Config: {e}")

    async def get_user_data(self) -> dict[int, dict]:
        all_data = self._read_all_data()
        user_data = {}
        for key, value in all_data.items():
            if key.startswith("user_"):
                try:
                    user_id = int(key.split("_")[1])
                    user_data[user_id] = pickle.loads(bytes.fromhex(value))
                except (ValueError, IndexError):
                    continue
        return user_data

    async def update_user_data(self, user_id: int, data: dict) -> None:
        key = f"user_{user_id}"
        # We store the pickled data as a hex string to keep it JSON-compatible
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": key, "value": value}])

    async def get_chat_data(self) -> dict[int, dict]:
        # Implement similarly if you need chat_data persistence
        return {}

    async def update_chat_data(self, chat_id: int, data: dict) -> None:
        # Implement similarly if you need chat_data persistence
        pass

    async def get_bot_data(self) -> dict:
        all_data = self._read_all_data()
        hex_data = all_data.get("bot_data")
        return pickle.loads(bytes.fromhex(hex_data)) if hex_data else {}

    async def update_bot_data(self, data: dict) -> None:
        value = pickle.dumps(data).hex()
        self._write_items([{"operation": "update", "key": "bot_data", "value": value}])

    # ... other required methods can be left as pass ...
    async def get_callback_data(self) -> dict | None: return None
    async def update_callback_data(self, data: dict) -> None: pass
    async def flush(self) -> None: pass
    async def get_conversations(self, name: str) -> dict: return {}
    async def update_conversation(self, name: str, key: tuple, new_state: object | None) -> None: pass