import logging
import json
import datetime
from routine_manager import routine_db

logger = logging.getLogger(__name__)

async def check_proactive_triggers(user_id, send_msg_func):
    """
    The Executor: Checks 'Routine Profile' against Current Time.
    If match found -> Fire Action.
    Expected to run every minute via Scheduler.
    """
    try:
        routines = routine_db.get_routines()
        if not routines:
            return

        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a") # Mon, Tue...

        for routine in routines:
            # 1. Check Day
            days = routine.get("trigger_days", [])
            if current_day not in days and "Everyday" not in days:
                continue

            # 2. Check Time (fuzzy match +/- 5 mins)
            # Simplified: Exact match of HH:MM for now, or use logic
            trigger_time = routine.get("trigger_time_approx", "")
            
            # Very simple string match for MVP
            if trigger_time == current_time:
                # FIRE TRIGGER!
                routine_name = routine.get("routine_name", "Routine")
                intent = routine.get("likely_intent", "GENERAL")
                
                logger.info(f"⚡ Proactive Trigger Fired: {routine_name}")
                
                # Construct Message
                msg = f"⚡ *Jarvis Proactive*\nIt's {trigger_time}. usually you do: **{routine_name}**."
                
                if intent == "METRO":
                    msg += "\nShall I find the best route?"
                elif intent == "CAB":
                    msg += "\nCheck Uber prices?"
                elif intent == "FOOD":
                    msg += "\nOrder the usual?"
                
                await send_msg_func(user_id, msg)
                
    except Exception as e:
        logger.error(f"Trigger Engine Failed: {e}")
