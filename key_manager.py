
import os
import random
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Load Keys
raw_keys = os.getenv("GEMINI_KEYS", "")
if "," in raw_keys:
    ALL_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
else:
    ALL_KEYS = [raw_keys] if raw_keys else []

class KeyManager:
    """
    Intelligent Key Rotator & Load Balancer.
    """
    def __init__(self):
        self.keys = ALL_KEYS
        self.working_keys = ALL_KEYS.copy()
        self.current_index = 0
        
        # Dedicated Lane Assignments (Virtual Sharding)
        self.lanes = {
            "chat": 0,       # Fast, Reactive
            "vision": 0,    # Heavy
            "analyst": -1,   # Background (Last key)
            "router": 0      # High Volume
        }

    def get_key(self, task="chat"):
        """
        Get the best key for the task.
        Rotates if strictly needed, or uses assigned lane.
        """
        if not self.working_keys:
            logger.error("❌ CRITICAL: No API Keys available!")
            return None

        # Logic: Simple Rotation for now to spread load
        # In 'Die Hard' mode, we rotate per request to minimize Quota per Key hits
        key = self.working_keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.working_keys)
        return key

    def mark_failed(self, key):
        """
        Temporarily disable a bad key.
        """
        if key in self.working_keys and len(self.working_keys) > 1:
            logger.warning(f"⚠️ Flagging Bad Key: {key[:8]}...")
            self.working_keys.remove(key)
            self.current_index = 0 # Reset
        else:
            logger.warning(f"⚠️ Last key failing! Cannot remove {key[:8]}...")

key_manager = KeyManager()
