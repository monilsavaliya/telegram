
import json
import os
import logging
from datetime import datetime, timedelta
import dateparser

logger = logging.getLogger(__name__)
TIMETABLE_FILE = "timetable.json"

class TimetableManager:
    def __init__(self):
        self.schedule = self._load()

    def _load(self):
        if os.path.exists(TIMETABLE_FILE):
            try:
                with open(TIMETABLE_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save(self):
        with open(TIMETABLE_FILE, "w") as f:
            json.dump(self.schedule, f, indent=2)

    def is_busy(self, current_dt):
        """
        Checks if user is currently in a scheduled block (Class/Meeting).
        """
        day_name = current_dt.strftime("%A") # Monday, Tuesday...
        if day_name not in self.schedule:
            return False, None

        current_time_str = current_dt.strftime("%H:%M")
        
        for event in self.schedule[day_name]:
            start = event.get("start")
            end = event.get("end")
            label = event.get("label", "Busy")
            
            # Simple String Comparison for Time (HH:MM is comparable directly)
            if start <= current_time_str < end:
                return True, label
                
        return False, None

    def add_event(self, day, start, end, label):
        """
        Adds an event to the schedule. 
        day: "Monday"
        start: "09:00"
        end: "11:00"
        """
        day = day.title()
        if day not in self.schedule:
            self.schedule[day] = []
            
        # Remove overlaps (simple logic: just append for now)
        self.schedule[day].append({
            "start": start,
            "end": end,
            "label": label
        })
        self._save()
        logger.info(f"📅 Added Schedule: {day} {start}-{end} ({label})")

    def get_context(self, current_dt):
        busy, label = self.is_busy(current_dt)
        if busy:
            return f"BUSY ({label})"
        return "FREE"

    def get_day_events(self, day_name):
        return self.schedule.get(day_name, [])

    def get_upcoming_event(self, current_dt, buffer_minutes=15):
        """
        Returns an event that starts within buffer_minutes.
        Used for proactive reminders.
        """
        day_name = current_dt.strftime("%A")
        if day_name not in self.schedule: return None

        now_str = current_dt.strftime("%H:%M")
        future_dt = current_dt + timedelta(minutes=buffer_minutes)
        future_str = future_dt.strftime("%H:%M")

        for event in self.schedule[day_name]:
            # If event starts between NOW and NOW+BUFFER
            # AND we haven't already notified (Need state tracking in main, or simplified here)
            # For simplicity, we just return it, main loop handles "once per event" logic
            if now_str < event["start"] <= future_str:
                return event
        return None

    def remove_event(self, day, label_keyword):
        day = day.title()
        if day in self.schedule:
            original_len = len(self.schedule[day])
            self.schedule[day] = [e for e in self.schedule[day] if label_keyword.lower() not in e["label"].lower()]
            if len(self.schedule[day]) < original_len:
                self._save()
                return True
        return False

timetable_manager = TimetableManager()
