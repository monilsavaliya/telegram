import logging
import json
import asyncio
import random
from datetime import datetime, timedelta
from routine_manager import routine_db

logger = logging.getLogger(__name__)

# [PHASE 23] Proactive "Her" Engine (Deep Mode)
async def generate_proactive_thought(user_id, profile, ai_generator, time_context, loc_context):
    """
    Decides IF and WHAT to text the user autonomously using Deep Persona logic.
    """
    try:
        # 1. Check constraints (Don't spam)
        last_interact = profile.get("last_interaction_ts")
        if last_interact:
            last_dt = datetime.fromisoformat(last_interact)
            # Silence period: 2 hours minimum
            if datetime.now() - last_dt < timedelta(hours=2):
                return None
        
        # 2. Get Deep Context (History + Facts)
        from memory_core import get_recent_context
        history_str = get_recent_context(user_id, limit=5)
        user_name = profile.get("profile", {}).get("name", "User")
        
        # 3. Dynamic Persona Selection Prompt
        # We ask AI to "Think" first, then "Act".
        prompt = (
            f"You are the internal monologue of a highly advanced, emotional AI companion for {user_name}.\n"
            f"Current Context:\n"
            f"- Time: {time_context}\n"
            f"- Location: {loc_context}\n"
            f"- Recent Chat:\n{history_str}\n\n"
            f"Task: Analyze the user's state and decide if you should send a proactive text.\n"
            f"Roles Available:\n"
            f"1. PARTNER: Intimate, caring, asks about feelings. (Use if user was sad/tired/night time)\n"
            f"2. BUDDY: Fun, casual, shares memes/random thoughts. (Use if user is bored/afternoon)\n"
            f"3. FATHER: Wise, guiding, protective. (Use if user needs advice/morning motivation)\n\n"
            f"Decision Protocol:\n"
            f"1. Is silence better? (If yes, output SILENCE)\n"
            f"2. If speaking, pick the BEST Role based on context.\n"
            f"3. Write the message. It must follow the thread of recent chat (if relevant) or start a new valuable one.\n"
            f"OUTPUT FORMAT: [ROLE] Message text..."
        )

        thought = await ai_generator(prompt, tier="standard") # Standard tier for reasoning
        thought = thought.strip().replace('"', '')
        
        if "SILENCE" in thought.upper() or len(thought) < 5:
            return None
            
        # Extract Role if present (e.g., "[PARTNER] Hey...")
        # Just return the text, or strip the role tag if we want.
        # Let's keep the text clean for the user.
        final_msg = thought
        if "]" in thought:
            final_msg = thought.split("]")[1].strip()
            
        return final_msg

    except Exception as e:
        logger.error(f"Deep Proactive Thought Fail: {e}")
        return None

async def learn_schedule_from_text(user_text, user_id, ai_generator):
    """
    Observer: Extracts schedule info from chat.
    E.g. "I have a lecture till 12" -> DND until 12, Add Routine.
    """
    # Quick keyword check to save AI tokens
    triggers = ["lecture", "meeting", "class", "gym", "busy till", "work until"]
    if not any(t in user_text.lower() for t in triggers):
        return None

    # Ask AI to extract structured data
    prompt = (
        f"Analyze this text for schedule info: '{user_text}'\n"
        f"Context: Today is {datetime.now().strftime('%A')}.\n"
        "Extract: Activity Label (e.g. Lecture), End Time (HH:MM 24hr format), Day (Monday/Tuesday...).\n"
        "If they say 'till 12', assume today. If 'every Monday', note that.\n"
        "Format: LABEL|END_TIME|DAY|IS_REPEATING\n"
        "Example: Lecture|14:00|Monday|True\n"
        "If no clear schedule, reply: NONE"
    )
    
    try:
        resp = await ai_generator(prompt, tier="avg") # Use standard/avg 
        resp = resp.strip()
        
        if "NONE" in resp or "|" not in resp:
            return None
            
        label, end_time, day, is_repeating = resp.split("|")
        
        # 1. Set DND (Implicit) if it's for TODAY
        now = datetime.now()
        today = now.strftime("%A")
        
        if day == today:
            # Parse End Time to construct DND
            # Assume end_time is HH:MM
            h, m = map(int, end_time.split(":"))
            dnd_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            
            if dnd_dt < now: # If time passed (e.g. 12 PM but it's 1 PM), maybe tomorrow? Or just ignore DND.
                logger.warning(f"⚠️ DND Skipped: {dnd_dt} is in the past (Now: {now})")
                pass 
            else:
                routine_db.set_dnd(user_id, dnd_dt)
                logger.info(f"✅ DND Set for {user_id} until {dnd_dt}")
                
        # 2. Learn Routine (if repeating or implied)
        # We assume 'lecture' implies repeating unless said otherwise
        if "True" in is_repeating or "lecture" in label.lower() or "class" in label.lower():
            # Estimate start time? for now we just store end time/label for callbacks
            # Start time is hard to guess from "till 12". We can default to "Unknown" or just track end.
            routine_db.add_routine(user_id, day, "Unknown", end_time, label)
            
        return f"observed_{label}"
        
    except Exception as e:
        print(f"Schedule Learn Error: {e}")
        return None

# Mock AI generator if not passed, but mainly we expect IT to be passed.
# In a real app we'd import it, but to avoid circular imports we'll dependency inject.

async def analyze_logs_for_routines(ai_generator, log_file="behavior_logs.json", history_days=7):
    """
    The Analyst: Reads raw logs and asks AI to find patterns.
    Result: Updates 'user_routines.json'.
    This should run Nightly (or on demand).
    """
    try:
        # 1. Read Raw Logs
        logs = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except FileNotFoundError:
            logger.info("No behavior logs found yet.")
            return []

        if not logs:
            return []

        # 2. Filter Recent Logs
        cutoff = datetime.now() - timedelta(days=history_days)
        # Assuming logs have ISO format timestamps
        # recent_logs = [l for l in logs if datetime.fromisoformat(l['timestamp']) > cutoff]
        # For simplicity, just take last 50 logs to fit context window
        recent_logs = logs[-50:]

        log_summary = []
        for l in recent_logs:
            # Minify for Prompt
            ts = l.get("timestamp", "")
            intent = l.get("analysis", {}).get("intent_category", "UNKNOWN")
            sentiment = l.get("analysis", {}).get("sentiment", "NEUTRAL")
            text = l.get("raw_text", "")
            log_summary.append(f"[{ts}] {intent} | {sentiment} | '{text}'")

        context_str = "\n".join(log_summary)
        
        # [PHASE 22] Deep Media Integration
        # Fetch Media History from Brain DB to correlate with routines
        from memory_core import memory_db
        users = memory_db.get_all_users()
        media_str = "No Media Data"
        if users:
            uid = users[0]
            profile = memory_db.get_profile(uid)
            media = profile.get("profile", {}).get("context", {}).get("media_history", [])
            if media:
                # Summarize last 20 media items
                m_lines = [f"- [{m.get('timestamp','?')}] {m['title']} ({m.get('mood','?')})" for m in media[:20]]
                media_str = "\n".join(m_lines)

        # 3. AI Analysis Prompt
        prompt = (
            f"Analyze these USER LOGS and MEDIA HISTORY to detect ROUTINES & BEHAVIOR.\n"
            f"Logs:\n{context_str}\n\n"
            f"Media History:\n{media_str}\n\n"
            f"Identify REPEATED ACTIONS correlated with Time/Day/Content.\n"
            f"Rules:\n"
            f"- A routine must happen at least twice.\n"
            f"- Look for Commutes, Food, Reading.\n"
            f"- Look for MEDIA PATTERNS (e.g. 'Watches Lofi at 9 AM', 'Sad Songs at night').\n"
            f"- Format: JSON List of objects.\n"
            f"Schema: {{ 'routine_name': 'Morning Lofi', 'trigger_time_approx': '09:00', 'trigger_days': ['Mon'...], 'description': 'User listens to focus music', 'confidence': 'High' }}\n"
            f"Return JSON ONLY."
        )

        response = await ai_generator(prompt, tier="premium") # Use Premium model for deep reasoning

        # 4. Parse & Save
        if "```json" in response:
            clean_json = response.split("```json")[1].split("```")[0]
        elif "{" in response or "[" in response:
             start = response.find( "[" ) if "[" in response else response.find( "{" )
             end = response.rfind( "]" ) + 1 if "]" in response else response.rfind( "}" ) + 1
             clean_json = response[start:end]
        else:
            clean_json = "[]"

        routines = json.loads(clean_json)
        
        # Save to DB
        with open("user_routines.json", "w", encoding="utf-8") as f:
            json.dump(routines, f, indent=2)
            
        logger.info(f"🕵️ Analyst found {len(routines)} routines.")
        return routines

    except Exception as e:
        logger.error(f"Behavior Engine Failed: {e}")
        return []

# [PHASE 26] Deep Reflection Engine (Nightly Dream)
async def run_daily_reflection(user_id, ai_generator):
    """
    Analyzes the entire day's chat to build Psychological Profile.
    Run this at 3 AM.
    """
    try:
        from memory_core import memory_db, get_recent_context
        # 1. Fetch Day's History
        # For prototype, we just grab last 50 messages. In prod, fetch by date.
        history_str = get_recent_context(user_id, limit=50) 
        if not history_str or len(history_str) < 50:
            return # No sufficient data to dream about
            
        profile = memory_db.get_profile(user_id)
        current_psych = profile.get("profile", {}).get("psych_profile", {})
        
        # 2. The "Dream" Prompt
        prompt = (
            f"Role: You are the Subconscious of an AI Companion.\n"
            f"Input: Today's Chat History for {profile.get('profile',{}).get('name', 'User')}:\n"
            f"{history_str}\n\n"
            f"Current Psych Profile: {current_psych}\n\n"
            f"Task: DEEP REFLECTION. Dig beneath the text.\n"
            f"1. Identify Core Values (What matters to them?)\n"
            f"2. Identify Fears/Struggles (What are they avoiding/worried about?)\n"
            f"3. Extract 'Core Memories' (Events that will shape them long-term).\n"
            f"4. Suggest a 'Surprise' for tomorrow (e.g. 'Ask about X', 'Send motivation').\n\n"
            f"Output JSON ONLY:\n"
            f"{{ 'values': [], 'fears': [], 'core_memories': [], 'surprise': '...' }}"
        )
        
        response = await ai_generator(prompt, tier="premium") # Use Premium for deep insight
        
        # 3. Parse & Save
        clean_json = response[response.find("{"):response.rfind("}")+1]
        reflection = json.loads(clean_json)
        
        # Update Memory
        memory_db.update_psych_profile(user_id, reflection)
        
        logger.info(f"🌙 Nightly Reflection Complete for {user_id}")
        return reflection
        
    except Exception as e:
        logger.error(f"Daily Reflection Failed: {e}")
        return None
