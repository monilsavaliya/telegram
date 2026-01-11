import logging
import json
from datetime import datetime
from database_adapter import db # [PHASE 14] Infinite Memory DB

logger = logging.getLogger(__name__)

# [PHASE 14] Legacy JSON functions replaced by DB calls
def load_memory(user_id):
    """
    Loads user profile from Infinite Memory (Brain DB).
    """
    user_data = db.get_user(str(user_id))
    if user_data:
        # DB returns {"profile": {}, "preferences": {}}
        # But legacy code expects a merged object or specific structure.
        # Let's unify it.
        return user_data
    else:
        # Default Profile
        return {
            "profile": {
                "nickname": "Boss", 
                "mode": "FRIEND (Bro/Bestie)",
                "context": {}
            }, 
            "preferences": {}
        }

def save_memory(user_id, data):
    """
    Saves user profile to Infinite Memory (Brain DB).
    """
    # Split data back into Profile and Preferences for DB Structure
    profile = data.get("profile", {})
    preferences = data.get("preferences", {})
    
    # If data is flat (legacy), try to separate
    if "profile" not in data:
        # Assume it's mixed
        pass 
        
    db.upsert_user(str(user_id), profile, preferences)
    logger.info(f"💾 Memory Saved to Brain DB for {user_id}")

def update_preference(user_id, key, value):
    """
    Updates a specific preference (Helper).
    """
    current_data = load_memory(user_id)
    if "preferences" not in current_data:
        current_data["preferences"] = {}
        
    current_data["preferences"][key] = value
    save_memory(user_id, current_data)

# Legacy Global (Mocking the old class instance if needed, but functions are better)
# If telegram_main.py imports 'memory_db', we need to check how it's used.
# It seems telegram_main used 'memory_db' as an instance?
# Let's check previous code. It imported 'from memory_core import memory_db' usually.
# If so, we need to provide a class wrapper.


def get_recent_context(user_id, limit=5):
    """
    Fetches recent conversation history for deep context.
    """
    try:
        history = db.get_history(str(user_id), limit=limit)
        # Format as string
        context_str = "\n".join([f"{h['role']}: {h['content']}" for h in history])
        return context_str
    except Exception as e:
        logger.error(f"Context Fetch Error: {e}")
        return ""

class MemoryCoreWrapper:
    def get_all_users(self):
        return db.get_all_users()
        
    def get_pending_events(self):
        return db.get_pending_events()
        
    def complete_event(self, user, event):
        db.complete_event(user, event)
    
    # Expose DB methods through wrapper for consistency
    def get_profile(self, user_id):
        return load_memory(user_id)
        
    def update_profile(self, user_id, key, value):
        # Handle dot notation if needed, but for now simple key
        # We need a proper deep update if key is "profile.x"
        # For now, just use the load/save logic
        data = load_memory(user_id)
        if "profile" not in data: data["profile"] = {}
        data["profile"][key] = value
        save_memory(user_id, data)

    def update_psych_profile(self, user_id, reflection):
        """
        Merges nightly reflection into permanent Psych Profile.
        """
        data = load_memory(user_id)
        if "profile" not in data: data["profile"] = {}
        if "psych_profile" not in data["profile"]: 
            data["profile"]["psych_profile"] = {"values": [], "fears": [], "core_memories": []}
            
        p = data["profile"]["psych_profile"]
        
        # Merge Sets to avoid duplicates
        p["values"] = list(set(p.get("values", []) + reflection.get("values", [])))
        p["fears"] = list(set(p.get("fears", []) + reflection.get("fears", [])))
        
        # Append Core Memories (Timeseries)
        if reflection.get("core_memories"):
            for mem in reflection["core_memories"]:
                p["core_memories"].append({"date": datetime.now().isoformat(), "memory": mem})
                
        # Store Surprise for tomorrow
        if reflection.get("surprise"):
            db.add_event(user_id, "SURPRISE", datetime.now().isoformat(), "Nightly Insight", reflection["surprise"])
            
        save_memory(user_id, data)

memory_db = MemoryCoreWrapper()
