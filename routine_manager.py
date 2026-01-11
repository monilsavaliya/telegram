import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

ROUTINE_FILE = "user_routines.json"

class RoutineManager:
    def __init__(self):
        self.routines = self._load_routines()
        
    def _load_routines(self):
        if not os.path.exists(ROUTINE_FILE):
            return {}
        try:
            with open(ROUTINE_FILE, 'r') as f:
                data = json.load(f)
                
                # [FIX] Handle Corrupted Data (List vs Dict)
                if isinstance(data, list):
                     logger.warning("⚠️ Routine File is a LIST (Corrupted). Resetting to empty dict.")
                     # Try to salvage if list contains dicts, otherwise wipe
                     return {} # Safest to reset if schema is wrong
                     
                # Validation: Ensure all values are dicts
                valid_data = {}
                for k, v in data.items():
                    if isinstance(v, dict):
                        valid_data[k] = v
                    else:
                        valid_data[k] = {"dnd_until": None, "weekly": {}}
                return valid_data
        except Exception as e:
            logger.error(f"Routine Load Error: {e}")
            return {}

    def _save_routines(self):
        with open(ROUTINE_FILE, 'w') as f:
            json.dump(self.routines, f, indent=2)

    def add_routine(self, user_phone, day_of_week, start_time, end_time, label):
        """
        Adds a learned routine.
        day_of_week: "Monday", "Tuesday", etc.
        start_time: "HH:MM" (item start)
        end_time: "HH:MM" (item end)
        label: "Lecture", "Gym", "Meeting"
        """
        if user_phone not in self.routines:
            self.routines[user_phone] = {"dnd_until": None, "weekly": {}}
            
        user_weekly = self.routines[user_phone].setdefault("weekly", {})
        day_routines = user_weekly.setdefault(day_of_week, [])
        
        # Check duplicates
        for r in day_routines:
            if r['start'] == start_time and r['label'] == label:
                return # Already exists
                
        day_routines.append({
            "start": start_time,
            "end": end_time,
            "label": label,
            "confidence": 1  # Can increment this for reinforcement
        })
        self._save_routines()
        logger.info(f"📅 Added Routine for {user_phone}: {day_of_week} {start_time}-{end_time} ({label})")

    def set_dnd(self, user_phone, until_dt):
        """Sets extensive Do Not Disturb until specific datetime."""
        if user_phone not in self.routines:
            self.routines[user_phone] = {"dnd_until": None, "weekly": {}}
            
        self.routines[user_phone]["dnd_until"] = until_dt.isoformat()
        self._save_routines()
        logger.info(f"🤫 DND Set for {user_phone} until {until_dt}")

    def check_routine_triggers(self, user_phone, current_dt):
        """
        Checks if:
        1. DND just finished (Welcome Back).
        2. A routine is about to start or just finished.
        """
        triggers = []
        user_data = self.routines.get(user_phone)
        if not user_data: return []
        
        # 1. Check DND
        dnd_str = user_data.get("dnd_until")
        if dnd_str:
            dnd_dt = datetime.fromisoformat(dnd_str)
            if current_dt > dnd_dt:
                # DND Expired!
                triggers.append({"type": "dnd_expired", "context": "User is free now via DND expiry"})
                user_data["dnd_until"] = None # Clear it
                self._save_routines()

        # 2. Check Weekly Routines
        day_name = current_dt.strftime("%A")
        time_str = current_dt.strftime("%H:%M")
        
        daily_items = user_data.get("weekly", {}).get(day_name, [])
        for item in daily_items:
            # POST-ACTIVITY CHECK (e.g. Lecture just finished)
            # Simple check: if current time matches end time
            if item['end'] == time_str:
                triggers.append({
                    "type": "activity_finished", 
                    "label": item['label']
                })
        
        return triggers

routine_db = RoutineManager()
