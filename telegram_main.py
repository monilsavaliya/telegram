import logging
import asyncio
import os
import random
import json
import urllib.parse
import traceback
import io
import PIL.Image
import pytz
from datetime import datetime, timedelta
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# --- JARVIS MODULES ---
from network_utils import safe_post, KeyManager, close_client
from metro_engine import handle_metro, METRO_GRAPH
# from shopping_engine import handle_shopping, generate_amazon_link # Legacy Removed
from shopping_service_dev.shopping_bot import ShoppingBot # New Engine
from taxi_engine import TaxiEngine
from ride_card_renderer import RideCardRenderer
from location_service import LocationService
from intent_engine import decide_intent_ai
from memory_core import memory_db
from gemini_engine import generate_gemini_text, generate_gemini_vision
from knowledge_engine import get_genz_news, get_weather, get_stock_price

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

# GROQ KEYS (Llama 3)
GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]

mgr_groq = KeyManager(GROQ_API_KEYS)

GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k.strip()]

# Split Keys: Primary for Chat, Background for Subconscious/Analysis
# Ensure we have enough keys
if len(GEMINI_API_KEYS) < 5:
    logger.warning("⚠️ Low number of Gemini Keys. Splitting might be ineffective.")
    PRIMARY_KEYS = GEMINI_API_KEYS
    BACKGROUND_KEYS = GEMINI_API_KEYS
else:
    PRIMARY_KEYS = GEMINI_API_KEYS[:4]
    BACKGROUND_KEYS = GEMINI_API_KEYS[4:]

mgr_primary = KeyManager(PRIMARY_KEYS)

mgr_background = KeyManager(BACKGROUND_KEYS)

# Initialize Engines
shopping_bot = ShoppingBot()
taxi_engine = TaxiEngine()
taxi_renderer = RideCardRenderer()
taxi_loc_service = LocationService()

# Tiered Models
# Tiered Models
MODEL_TIERS = {
    "router": ["gemini-1.5-flash"], 
    "lightning": ["gemini-1.5-flash"], 
    "standard": ["gemini-1.5-flash"], 
    "premium": ["gemini-1.5-pro"],
    "vision": ["gemini-1.5-flash"]
}

# Router Key (Dedicated)
try:
    ROUTER_KEY = PRIMARY_KEYS[0] # Use the first available key
except:
    ROUTER_KEY = "" # Fallback logic handles this

async def ai_router_classify(user_text):
    """
    Decides the Intent and Complexity Tier using a fast LLM call.
    Returns: (tier, intent_category)
    """
    try:
        # Fast local checks first (Regex) to save API calls
        if len(user_text.split()) < 3: return "lightning", "CHAT"
        
        # [PHASE 30] Fast Regex for Reminders
        text_lower = user_text.lower()
        if any(k in text_lower for k in ["remind me", "wake me up", "text me at", "alarm at"]):
            return "lightning", "REMINDER"
        
        # Use verified model name (Alias)
        # [REST STRICT]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={ROUTER_KEY}"
        prompt = (
            f"Classify Query: '{user_text}'\n"
            "Intents: SHOPPING (Amazon/Products), METRO, MOVIE, CAB, REMINDER, GENERAL, EMOTIONAL_SUPPORT.\n"
            "Tiers: lightning (simple), standard (normal), premium (complex reasoning).\n"
            "Output format: TIER|INTENT"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        from httpx import AsyncClient
        async with AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=3.0)
            if resp.status_code == 200:
                out = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "|" in out:
                    tier, intent = out.split("|")
                    return tier.strip().lower(), intent.strip().upper()
        
        return "standard", "GENERAL" # Fallback
    except Exception as e:
        logger.error(f"Router Error: {e}")
        return "standard", "GENERAL"

# Logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# ==========================================
# CRITICAL: DIE HARD KEY MANAGER
# ==========================================
from key_manager import key_manager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Note: genai SDK Replaced by gemini_engine (REST)

async def generate_ai_response(prompt, tier="standard"):
    """
    Hybrid Brain: Gemini Flash (REST) -> Groq (Backup)
    Uses KeyManager for load balancing.
    """
    # [PHASE 40] Fast Path: Use Groq for 'lightning' tier (User Request)
    if tier == "lightning":
        # [SMART LOAD BALANCING]
        # Start at a random key index to distribute load across all keys in parallel
        # This prevents "Key 1" from taking all hits.
        import random
        keys = mgr_groq.api_keys # Access raw list
        if keys:
            start_index = random.randint(0, len(keys) - 1)
            # Create rotated list starting from random index
            rotated_keys = keys[start_index:] + keys[:start_index]
            
            for key in rotated_keys:
                try:
                     # Minimal Groq Client
                     from groq import Groq
                     client = Groq(api_key=key)
                     
                     completion = client.chat.completions.create(
                         model="llama-3.3-70b-versatile",
                         messages=[{"role": "user", "content": prompt}],
                         temperature=0.7,
                         max_tokens=150 # Short/Concise for Chat
                     )
                     return completion.choices[0].message.content
                except Exception as e:
                     logger.warning(f"⚡ Groq Key {key[:8]} Failed: {e}")
                     mgr_groq.mark_failed(key)
                     # Continue to next key
            
            logger.warning("⚡ All Groq Keys exhausted. Falling back to Gemini.")
        else:
             logger.warning("⚡ No Groq Keys found. Falling back.")
        
        # Fallback to Gemini continues below...

    # 1. Try Gemini with Rotating Keys
    retries = 2
    for attempt in range(retries):
        key = key_manager.get_key("chat")
        if not key: break
        
        try:
            # Call Pure REST Engine
            text = await generate_gemini_text(prompt, key, model="gemini-2.5-flash")
            
            if text:
                return text
            else:
                # If None returned, it failed silently or empty
                raise Exception("Empty REST response")
            
        except Exception as e:
            logger.warning(f"⚠️ Gemini Key {key[:8]} Failed: {e}")
            key_manager.mark_failed(key)
            # Loop to next key
            
    # 2. Fallback to Groq (If ALL Gemini keys fail)
    logger.info("🔥 Gemini Failed. Falling back to Groq.")
    try:
        # Implement Groq fallback here or return error
        # For brevity, assuming simple fallback logic exists or importing it
        from groq import Groq
        key = mgr_groq.get_key("chat")
        if key:
             client = Groq(api_key=key)
             completion = client.chat.completions.create(
                 model="llama3-70b-8192",
                 messages=[{"role": "user", "content": prompt}],
                 temperature=0.7,
                 max_tokens=800
             )
             return completion.choices[0].message.content
        return "⚠️ Brain Offline (Both Gemini & Groq Failed)."
    except:
        return "⚠️ Brain Completely Offline."
# ==========================================
# STATE MANAGEMENT (CHAT HISTORY)
# ==========================================
# CHAT_HISTORY removed in favor of DB persistence
scheduler = AsyncIOScheduler()

def update_history(user_id, role, text):
    """Logs to Brain DB (Persistent)."""
    memory_db.log_chat(user_id, role, text)

def get_history_text(user_id):
    """Fetches from Brain DB (Persistent)."""
    return memory_db.get_recent_context(user_id, limit=10)
    return "\n".join(lines)

# ==========================================
# CORE BRAIN (HYBRID: GROQ + GEMINI)
# ==========================================
def classify_tier(intent, user_text):
    """Determine which model tier to use."""
    simple_patterns = ["hi", "hello", "hey", "bye", "thanks", "ok", "cool"]
    user_lower = user_text.lower().strip()
    
    # Contextual short replies (e.g. "1", "yes") should NOT be lightning if they need logic, 
    # BUT with history they are fine on Llama 3.
    if len(user_lower.split()) <= 10: 
        return "lightning"
        
    if intent == "GREETING":
        return "lightning"
        
    return "standard"

import httpx

async def generate_groq_response(prompt_text):
    """Generates response using Groq (Llama 3)."""
    for _ in range(2):
        key = mgr_groq.get_next_key()
        if not key: break
        
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": 0.7,
                "max_tokens": 1024
            }
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=headers, timeout=5.0)
                
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    logger.warning("Groq Rate Limit - Rotate Key")
                    mgr_groq.report_status(key, 429)
                    
        except Exception as e:
            logger.error(f"Groq Error: {e}")
            
    return None

# --- Simple Response Cache (TTL 1 Hour) ---
RESPONSE_CACHE = {}

async def generate_ai_response(prompt_text, tier="standard", use_background_keys=False):
    """
    Generates AI response using Groq (Fast) or Gemini (Smart).
    Implements Caching to save quota.
    """
    # 0. Check Cache
    cache_key = hash(prompt_text.strip())
    now = datetime.now()
    
    if cache_key in RESPONSE_CACHE:
        timestamp, cached_resp = RESPONSE_CACHE[cache_key]
        if now - timestamp < timedelta(hours=1):
            logger.info("⚡ Cache Hit! Serving saved response.")
            return cached_resp
            
    # 1. Groq (Lightning Tier) - Priority for simple tasks
    if tier == "lightning":
        res = await generate_groq_response(prompt_text)
        if res: 
            RESPONSE_CACHE[cache_key] = (now, res) # Cache it
            return res

    # 2. Gemini (Standard Tier) - Try Gemini First, Fallback to Groq
    gemini_response = None
    keys = BACKGROUND_KEYS if use_background_keys else PRIMARY_KEYS
    
    async with httpx.AsyncClient() as client:
        for key in keys:
            try:
                # Url for Gemini 1.5 Flash
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
                
                resp = await client.post(url, json=payload, timeout=10.0)
                
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates")
                    if candidates:
                        gemini_response = candidates[0]["content"]["parts"][0]["text"]
                        break # Success
                else:
                    logger.warning(f"⚠️ Gemini Key {key[:5]}... Failed: {resp.status_code}")
                    continue
                    
            except Exception as e:
                logger.warning(f"⚠️ Gemini Key Error: {e}")
                continue
    
    if gemini_response:
        RESPONSE_CACHE[cache_key] = (now, gemini_response)
        return gemini_response
        
    # 3. FALLBACK: Groq (If Gemini Failed)
    logger.info("⚠️ Gemini Failed. Falling back to Groq.")
    fallback_res = await generate_groq_response(prompt_text)
    if fallback_res:
        RESPONSE_CACHE[cache_key] = (now, fallback_res)
        return fallback_res

    # Ultimate Fallback
    return "Abhi mere pass time ni hai, badme batata."

# ==========================================
# SUBCONSCIOUS (Background Analysis)
# ==========================================
async def analyze_implicit_intent(user_text, user_id):
    """Analyses chat in background to update Memory/Events."""
    try:
        prompt = (
            f"Analyze chat from User {user_id}: '{user_text}'. "
            "Extract JSON only: {"
            " 'profile': {'nickname': '...', 'relationship_mode': 'GF/MOM/PA', 'language_style': '...', 'location': '...', 'avoid_action': '...', 'style_rule': 'Always use Red Heart/ concise...', 'new_alias': {'trigger': 'code red', 'meaning': 'call mom'}}, "
            " 'routine': {'day': 'Monday/Everyday', 'item': 'Good Morning Text 8AM'}, "
            " 'event': {'type': 'check-in', 'time': 'YYYY-MM-DDTHH:MM:SS', 'desc': '...', 'context': '...'}"
            "}"
            "NOTE: 'style_rule' is for persistent formatting demands (e.g. 'always start with Hey')."
        )
        
        # Use Background Keys
        resp = await generate_ai_response(prompt, use_background_keys=True)
        if "{" not in resp: return
        
        clean_json = resp[resp.find("{"):resp.rfind("}")+1]
        data = json.loads(clean_json)
        
        if data.get("profile"):
            for k, v in data["profile"].items():
                if k == "avoid_action" and v:
                    # Append to Avoid List
                    curr_avoids = memory_db.get_profile(user_id)["profile"].get("avoid_list", [])
                    if v not in curr_avoids:
                        curr_avoids.append(v)
                        memory_db.update_profile(user_id, "avoid_list", curr_avoids)
                        logger.info(f"🚫 Learned to AVOID: {v}")
                elif k == "new_alias" and v:
                    # Learn Alias
                    curr_aliases = memory_db.get_profile(user_id)["profile"].get("aliases", {})
                    if v.get("trigger") and v.get("meaning"):
                        curr_aliases[v["trigger"].lower()] = v["meaning"]
                        memory_db.update_profile(user_id, "aliases", curr_aliases)
                        logger.info(f"🔗 Learned ALIAS: {v['trigger']} -> {v['meaning']}")
                elif k == "style_rule" and v:
                    # Learn Style Rule
                    curr_rules = memory_db.get_profile(user_id)["profile"].get("preferences", {}).get("rules", [])
                    if v not in curr_rules:
                        curr_rules.append(v)
                        # We need to update preferences dict inside profile
                        curr_prefs = memory_db.get_profile(user_id)["profile"].get("preferences", {})
                        curr_prefs["rules"] = curr_rules
                        memory_db.update_profile(user_id, "preferences", curr_prefs)
                        logger.info(f"🎨 Learned STYLE RULE: {v}")
                elif v: memory_db.update_profile(user_id, k, v)
                
        if data.get("routine"):
            r = data["routine"]
            if r.get("day") and r.get("item"):
                memory_db.update_routine(user_id, r["day"], r["item"])
                
        if data.get("event"):
            evt = data["event"]
            # Fix: Use .get() for optional fields to avoid KeyError
            follow_up = evt.get("follow_up") 
            memory_db.add_event(user_id, evt["type"], evt["time"], evt["desc"], follow_up)
            logger.info(f"🧠 Subconscious detected event: {evt['desc']}")
            
    except Exception as e:
        logger.error(f"🧠 Subconscious Fail: {e}")

# ==========================================
# SCHEDULER (Proactive Follow-ups)
# ==========================================

# [PHASE 11] Behavioral Jobs
# Defined here to avoid import loops, but would ideally be in scheduler module
async def run_behavioral_checks(context):
    """
    Runs Layer 2 (Analyst) and Layer 3 (Executor).
    """
    try:
        from behavior_engine import analyze_logs_for_routines
        # from trigger_engine import check_proactive_triggers # LEGACY - REMOVED

        from routine_manager import routine_db
        
        # 1. THE EXECUTOR
        active_users = memory_db.get_all_users() 
        
        for user_id in active_users:
            async def sender(uid, msg, force=False, **kwargs):
                """
                Safe Sender with Anti-Spam (Smart Silence).
                If user hasn't replied to the last bot message, we suppress proactive conversation
                UNLESS it's a critical alert (force=True).
                """
                try:
                    # 1. Check Double-Texting
                    if not force:
                        hist = get_history_text(uid)
                        if hist and "User:" not in hist.splitlines()[-1]: 
                             # Last line was likely AI or System.
                             # Stricter: If last message role was 'assistant' (approx)
                             logger.info(f"🚫 Suppressing Proactive Msg to {uid} (User hasn't replied to last text).")
                             return

                    await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN, **kwargs)
                    # Log this proactive message so history updates interaction time
                    update_history(uid, "assistant", msg) 
                except Exception as e:
                    logger.warning(f"Failed to send to {uid}: {e}")

            # [PHASE 31] Check Routines & DND Expiry
            triggers = routine_db.check_routine_triggers(user_id, datetime.now())
            for t in triggers:
                if t['type'] == 'dnd_expired':
                    # Eager/Curious reconnection
                    msgs = [
                        "👋 You're back! I was waiting. How did it go?",
                        "👀 Free now? Tell me everything.",
                        "Welcome back! I missed you. Update me?"
                    ]
                    # This is semi-critical (User *just* became free), but we still respect silence if we just texted.
                    await sender(user_id, random.choice(msgs))
                elif t['type'] == 'activity_finished':
                    label = t['label']
                    # Contextual curiosity
                    msgs = [
                        f"👋 {label} done? Did you learn something new?",
                        f"Hope {label} wasn't too boring. Tell me about it!",
                        f"Finishing {label}... need a break or are we chatting?"
                    ]
                    await sender(user_id, random.choice(msgs))

            # [PHASE 23] Deep Proactive Thought Bubble (The "Best" Update)
            # This allows the AI to decide autonomously if it wants to speak
            from behavior_engine import generate_proactive_thought
            import pytz
            
            # Retrieve Minimal Context for Thought Generation
            profile_data = memory_db.get_profile(user_id) # Safe fetch
            profile = profile_data.get("profile", {})
            preferences = profile_data.get("preferences", {})

            # [PHASE 36] Sleep Mode Check 🛑
            # If DND is set in routine_db, Skip Proactive Thoughts completely.
            user_routine = routine_db.get_routines().get(user_id, {})
            dnd_until = user_routine.get("dnd_until")
            if dnd_until:
                 dnd_dt = datetime.fromisoformat(dnd_until)
                 if datetime.now() < dnd_dt:
                      # User is asleep/busy. Silence.
                      continue

            # [PHASE 37] Timetable Check (Dynamic)
            from timetable_manager import timetable_manager
            
            # Timezone Fix (IST)
            IST = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(IST)
            
            # 1. Check for Pre-Class Nudges (15 mins before)
            upcoming = timetable_manager.get_upcoming_event(now_ist, buffer_minutes=15)
            # Check if we already notified for this specific event to prevent spam
            # We use a volatile memory for this: notified_events = set() (need global or profile storage)
            # Hack: Store in profile transiently
            last_nudge = profile.get("last_nudge_label", "")
            
            if upcoming and upcoming['label'] != last_nudge:
                # ACTION: Remind User
                msg = f"🔔 Head's up! **{upcoming['label']}** starts in ~15 mins ({upcoming['start']}). Ready?"
                await sender(user_id, msg, force=True)
                
                # Update Last Nudge to prevent duplicate within same minute scan
                user_data = memory_db.get_profile(user_id) # forceful fetch to write back
                if "profile" not in user_data: user_data["profile"] = {}
                user_data["profile"]["last_nudge_label"] = upcoming['label']
                memory_db.save_memory(user_id, user_data)
                
                # Update Profile to prevent repeat
                profile["last_nudge_label"] = upcoming['label']
                memory_db.save_memory(user_id, profile_data)
                return # Skip standard thought generation if we just nudged
                
            # 2. Morning Brief (8:00 AM)
            if now_ist.hour == 8 and now_ist.minute == 0:
                events = timetable_manager.get_day_events(now_ist.strftime("%A"))
                if events:
                    schedule_str = "\n".join([f"• {e['start']} - {e['label']}" for e in events])
                    await sender(user_id, f"☀️ **Good Morning!**\n\nHere is your plan for today:\n{schedule_str}\n\nLet's crush it! 💪")
                    return

            is_busy, busy_label = timetable_manager.is_busy(now_ist)
            timetable_context = f"Busy ({busy_label})" if is_busy else "Free"
            
            # Anti-Spam Check (4 Hour Cooldown)
            last_ts_str = profile.get("last_proactive_ts")
            should_skip = False
            if last_ts_str:
                try:
                    last_ts = datetime.fromisoformat(last_ts_str)
                    if last_ts.tzinfo is None:
                        last_ts = IST.localize(last_ts) # Assume IST if naive
                    
                    if now_ist - last_ts < timedelta(minutes=30):
                        should_skip = True
                except:
                    pass
            
            if not should_skip:
                # Simple Context
                time_context = now_ist.strftime("%I:%M %p")
                
                # Pass Last Interaction Time to Engine so it knows if it's being annoying
                thought_msg = await generate_proactive_thought(
                    user_id, profile_data, generate_ai_response, 
                    time_context, loc_context=preferences.get("location_name", "India")
                )
                if thought_msg:
                     logger.info(f"💡 Proactive Thought for {user_id}: {thought_msg}")
                     await sender(user_id, thought_msg)
                     
                     # 💾 UPDATE LAST PROACTIVE TIMESTAMP (Critical to stop loop)
                     profile["last_proactive_ts"] = now_ist.isoformat()
                     # Merge back to save (Hack since we split get_profile)
                     profile_data["profile"] = profile
                     memory_db.save_memory(user_id, profile_data)

        # 2. THE ANALYST
        now_min = datetime.now().minute
        if now_min == 0: 
             await analyze_logs_for_routines(generate_ai_response)
             
    except Exception as e:
        logger.error(f"Behavioral Check Fail: {e}")

async def check_events(context: ContextTypes.DEFAULT_TYPE):
    """
    Scheduled Job: Runs every 1 minute.
    """
    await run_behavioral_checks(context)
    
    pending_items = memory_db.get_pending_events()
    if not pending_items: return

    now = datetime.now()
    import dateparser # Lazy import

    for user_id, event in pending_items:
        try:
            raw_time = event.get("start_time")
            event_time = None
            
            if isinstance(raw_time, datetime):
                event_time = raw_time
            elif isinstance(raw_time, str) and raw_time.strip():
                try:
                    event_time = datetime.fromisoformat(raw_time)
                except ValueError:
                    # Fallback to dateparser for "in 2 mins" etc
                    event_time = dateparser.parse(raw_time)
            
            if not event_time:
                continue 

            if now > event_time:
                # 2. Dynamic AI Generation
                profile_data = memory_db.get_profile(user_id)
                profile = profile_data.get("profile", {})
                nickname = profile.get("nickname", "Boss")
                
                msg_text = f"⏰ **Reminder**: {event['desc']}"
                
                # Send
                try:
                    await context.bot.send_message(chat_id=user_id, text=msg_text, parse_mode=ParseMode.MARKDOWN)
                    memory_db.complete_event(user_id, event)
                    logger.info(f"✅ Reminder sent to {user_id}")
                except Exception as ex:
                    logger.error(f"Send Reminder Fail {user_id}: {ex}")
                
        except Exception as e:
            logger.error(f"Scheduler Item Error: {e}")

# ==========================================
# TELEGRAM HANDLERS
# ==========================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CallbackQueryHandler

# ... (Existing Imports) ...

async def handle_book_search(user_text, user_id, context):
    """
    Searches for multiple books and starts a pagination session.
    """
    if hasattr(context, 'bot'):
        # Initial Search
        await context.bot.send_message(chat_id=user_id, text="📚 Searching the Great Library...", parse_mode=ParseMode.MARKDOWN)
        query = user_text.replace("search", "").replace("book", "").replace("find", "").strip()
    else:
        # Re-entry? Unlikely, usually handled by button
        return

    queries_to_try = [query]
    # Validation: Ignore short garbage queries
    if len(query) < 3:
        return # Silently ignore "Ok", "Hi", etc.
        
    # Validation: Ignore Exit Phrases (Fix for "Ok chhod" triggering search)
    if any(stop in query.lower() for stop in ["chhod", "rehne de", "cancel", "stop", "exit"]):
        return

    # Use User-Agent to avoid blocking
    headers = {"User-Agent": "JarvisBot/2.0 (monil@example.com)"}
    
    # Smart Query Relaxation Logic...
    queries_to_try = [query]
    if len(query.split()) > 1:
        queries_to_try.append(query.split()[0]) # Try first word
        
    for q in queries_to_try:
        try:
            url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(q)}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=30.0) # 30s timeout
                
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])[:1] # Get Top 1 Result
                
                if docs:
                    book = docs[0]
                    title = book.get("title", "Unknown Book")
                    author = book.get("author_name", ["Unknown Author"])[0]
                    cover_id = book.get("cover_i")
                    key = book.get("key") # e.g. /works/OL123W
                    
                    # 1. READ ONLINE LINK
                    buttons = []
                    if key:
                        read_url = f"https://openlibrary.org{key}"
                        buttons.append(InlineKeyboardButton("📖 Read Online", url=read_url))
                    
                    # 2. BUY ON AMAZON (Affiliate)
                    from shopping_engine import generate_amazon_link
                    buy_url = generate_amazon_link(title + " " + author + " book")
                    buttons.append(InlineKeyboardButton("🛒 Buy on Amazon", url=buy_url))
                    
                    keyboard = InlineKeyboardMarkup([buttons])
                    
                    # Image
                    if cover_id:
                        img_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                        caption = f"📚 *{title}*\n✍️ {author}\n\n_Tap below to Read or Buy._"
                        await context.bot.send_photo(chat_id=user_id, photo=img_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
                    else:
                        msg = f"📚 *{title}*\n✍️ {author}\n\n_Tap below to Read or Buy._"
                        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
                    return # Success
                    
        except Exception as e:
            logger.error(f"Book Try Error: {e}")
            continue
            
    # Fallback to Amazon if Library Fails
    amazon_url = f"https://www.amazon.in/s?k={urllib.parse.quote(query)}&tag=shopsy05-21"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔎 Search on Amazon", url=amazon_url)]])
    await context.bot.send_message(chat_id=user_id, text=f"📚 Library scan failed for '{query}'.\nCheck Amazon?", reply_markup=keyboard)
    
async def send_book_page(update, context, chat_id, page_index, is_new=False):
    """Renders the book card with navigation."""
    docs = context.user_data.get("book_results", [])
    if not docs: return
    
    book = docs[page_index]
    title = book.get("title", "Unknown")
    author = ", ".join(book.get("author_name", ["Unknown"]))
    year = book.get("first_publish_year", "N/A")
    cover_id = book.get("cover_i")
    
    # Links
    goodreads = f"https://www.goodreads.com/search?q={urllib.parse.quote(title)}"
    amazon = f"https://www.amazon.in/s?k={urllib.parse.quote(title + ' book')}"
    
    caption = (
        f"📖 **{title}**\n"
        f"✍️ Author: *{author}*\n"
        f"📅 Year: {year}\n\n"
        f"⭐ [Rate]({goodreads}) | 🛒 [Buy]({amazon})"
    )
    
    # Buttons
    buttons = []
    if page_index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"book_prev_{page_index}"))
    buttons.append(InlineKeyboardButton(f"{page_index + 1}/{len(docs)}", callback_data="ignore"))
    if page_index < len(docs) - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"book_next_{page_index}"))
        
    keyboard = InlineKeyboardMarkup([buttons])
    
    cover_url = "https://via.placeholder.com/300x450.png?text=No+Cover"
    if cover_id:
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
        
    if is_new:
        await context.bot.send_photo(chat_id=chat_id, photo=cover_url, caption=caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        # Edit Message
        query = update.callback_query
        # Telegram API quirk: Edit Media if photo changes, or Caption if only text
        # Usually easier to edit media to ensure image refresh
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=cover_url, caption=caption, parse_mode=ParseMode.MARKDOWN),
                reply_markup=keyboard
            )
        except Exception as e:
            # Fallback if media is same or error
            await query.edit_message_caption(caption=caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

async def handle_shopping_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Shopping Next/Prev Buttons."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    direction = "next"
    if "prev" in query.data:
        direction = "prev"
    
    # Fetch Page
    response = shopping_bot.get_next_page(user_id, direction=direction)
    
    if isinstance(response, dict) and response.get("type") == "photo_card":
        # Formats
        caption = response["caption"]
        photo = response["photo"]
        buttons = []
        for row in response["buttons"]:
            btn_row = []
            for btn in row:
                if "url" in btn:
                    btn_row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
                elif "callback_data" in btn:
                     btn_row.append(InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
            buttons.append(btn_row)
            
        keyboard = InlineKeyboardMarkup(buttons)
        
        # Edit Media
        try:
            # Check if photo is valid URL
            if not photo: photo = "https://via.placeholder.com/300?text=No+Image"
            
            # Use InputMediaPhoto to update image + caption cleanly
            await query.edit_message_media(
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode=ParseMode.MARKDOWN),
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Shopping Edit Error: {e}")
            # Fallback if text only
            await query.edit_message_caption(caption=caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            
    else:
        # String response (End of results)
        await query.edit_message_caption(caption=str(response))

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Carousel Navigation."""
    query = update.callback_query
    await query.answer() # Ack
    
    data = query.data
    
    if "shopping_next" in data or "shopping_prev" in data:
        await handle_shopping_nav(update, context)
        return

    # [PHASE 34] Taxi Booking Callbacks
    if "book_taxi_" in data:
        vehicle_id = data.replace("book_taxi_", "")
        user_id = str(update.effective_user.id)  # Ensure string type
        msg = taxi_engine.select_vehicle(user_id, vehicle_id)
        if msg:
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ Error selecting vehicle/Time's up.")
        return

    if "book_" not in data: return
    
    # Parse action: book_next_0 -> go to 1
    action, current_idx = data.split("_")[1], int(data.split("_")[2])
    
    new_idx = current_idx
    if action == "next": new_idx += 1
    elif action == "prev": new_idx -= 1
    
    await send_book_page(update, context, chat_id=update.effective_chat.id, page_index=new_idx, is_new=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Visual Cortex Button
    # For MVP Localhost, Telegram WebApp needs HTTPS. 
    # We use standard URL button which works fine for localhost.
    
    webapp_url = "http://localhost:5000/dashboard"
    
    keyboard = InlineKeyboardMarkup([
        # [InlineKeyboardButton("🧠 Open Visual Cortex", web_app=WebAppInfo(url=webapp_url))], # FAIL on HTTP
        [InlineKeyboardButton("🧠 Open Dashboard (Visual Cortex)", url=webapp_url)]
    ])
    
    await update.message.reply_text(
        "⚡ **Jarvis 3.0 Online**\n\nVisual Cortex is ready. Tap below to see your Brain Dashboard.", 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

from multimedia_engine import handle_multimedia

# --- TAXI HELPERS ---
async def track_taxi_driver_callback(context: ContextTypes.DEFAULT_TYPE):
    """Updates the driver status message."""
    job = context.job
    user_id = job.data["user_id"]
    msg_id = job.data["msg_id"]
    
    # Use global taxi_engine
    dist, status_text, arrived = taxi_engine.get_driver_update(user_id)
    
    # Edit Message
    try:
        await context.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=msg_id,
            text=status_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        pass # Ignore "Message Not Modified" errors
        
    if arrived:
        job.schedule_removal()
        await context.bot.send_message(chat_id=job.chat_id, text="✅ **Trip Started!** Have a safe ride.")

async def handle_live_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'Live Location' updates from User."""
    if update.edited_message and update.edited_message.location:
        user_id = update.effective_user.id
        loc = update.edited_message.location
        logger.info(f"📍 User {user_id} Live Loc: {loc.latitude}, {loc.longitude}")
        # In future, update driver routing here

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    # 0. Book Search Bypass (Avoid triggering on "Book a cab")
    taxi_terms = ["cab", "taxi", "ride", "uber", "ola", "auto", "moto", "driver"]
    if any(x in user_text.lower() for x in ["novel", "author", "read "]) or \
       ("book" in user_text.lower() and not any(t in user_text.lower() for t in taxi_terms)):
        await handle_book_search(user_text, user_id, context)
        return

    # [PHASE 19] Real-Time Link Listener
    if "http" in user_text.lower() and any(x in user_text.lower() for x in ["youtube.com", "youtu.be", "amazon", "amzn", "spotify"]):
        from multimedia_engine import analyze_shared_content
        # Fire and forget / or wait? Let's await to give immediate feedback
        await analyze_shared_content(user_text, user_id, send_tg_msg, generate_ai_response)
        context.application.create_task(analyze_implicit_intent(user_text, user_id)) # Still log it
        return # Skip other intents for pure links

    # 0. Resolve Aliases (Dynamic Intents)
    profile = memory_db.get_profile(user_id)["profile"]
    aliases = profile.get("aliases", {})
    if user_text.lower() in aliases:
        logger.info(f"🔗 Alias Triggered: '{user_text}' -> '{aliases[user_text.lower()]}'")
        user_text = aliases[user_text.lower()]
    
    # 1. Decide Intent (Hive Mind: AI Router)
    from intent_engine import decide_intent_ai
    
    intent = "UNKNOWN"
    tier = "standard"

    # Restore Session Checks
    is_shopping_session = user_id in shopping_bot.sessions
    taxi_state = taxi_engine.get_state(user_id)["state"]
    is_taxi_session = taxi_state != "IDLE" and taxi_state != "BOOKED"

    # [PRIORITY 1] Sticky Sessions
    if is_taxi_session:
        intent = "CAB"
    elif is_shopping_session and len(user_text.split()) < 5:
        intent = "SHOPPING"
    else:
        # [PRIORITY 2] Unified Intent Engine (Regex + Dynamic + AI)
        intent = await decide_intent_ai(user_text, generate_ai_response)
        
        # Map Intent to Tier if needed (Optimization)
        if intent in ["METRO", "SHOPPING", "BOOK", "CAB", "REMINDER", "NEWS", "WEATHER", "FINANCE"]:
             tier = "lightning"
    
    logger.info(f"🧠 INTENT: {intent} | User: {user_text}")
    
    # [PHASE 31] Schedule Learner (Silent Observer)
    # Check for schedule triggers regardless of length ("Busy till 5")
    from behavior_engine import learn_schedule_from_text
    context.application.create_task(learn_schedule_from_text(user_text, user_id, generate_ai_response))
    
    # 2. Fire Subconscious (If useful)
    if len(user_text.split()) > 5:
        context.application.create_task(analyze_implicit_intent(user_text, user_id))

    # 3. Routing
    async def send_tg_msg(phone, text, **kwargs):
        # Wrapper to match engine signature
        # Pass kwargs (like reply_markup) to telegram
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, **kwargs)
        
    if intent == "REMINDER":
        # [PHASE 30] Explicit Reminders
        from reminder_engine import parse_reminder
        dt, note = parse_reminder(user_text)
        
        if dt:
            # Add Job to Telegram Scheduler (JobQueue)
            job_context = {"chat_id": user_id, "text": f"⏰ *Reminder*: {note}"}
            
            # Helper to send message from job
            async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE):
                job = context.job
                try:
                    await context.bot.send_message(chat_id=job.data["chat_id"], text=job.data["text"], parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    logger.error(f"⚠️ specific Reminder Fail (Chat {job.data.get('chat_id')}): {e}")
            
            # Calculate delay in seconds (Telegram JobQueue usually takes delay or time)
            # but run_once accepts datetime/timedelta
            context.job_queue.run_once(send_reminder_job, dt, data=job_context)
            
            fmt_time = dt.strftime("%I:%M %p")
            await send_tg_msg(user_id, f"✅ Done. I'll remind you at *{fmt_time}*.")
        else:
            await send_tg_msg(user_id, "🤔 I couldn't figure out the time. Try 'Remind me at 6 PM'.")

    if intent == "METRO":
        # Detect Mood for Routing Criteria
        criteria = "fastest"
        if any(x in user_text.lower() for x in ["tired", "lazy", "heavy", "baggage", "sleepy"]):
            criteria = "comfort"
            
        # Context Retrieval
        last_metro = context.user_data.get("last_metro")
            
        result = await handle_metro(
            user_text, user_id, send_tg_msg, 
            ai_generator=generate_ai_response, 
            criteria=criteria,
            previous_route=last_metro
        )
        
        # Context Update
        if result and result[0] and result[1]:
            context.user_data["last_metro"] = result
        
    elif intent == "NEAREST_METRO":
        profile = memory_db.get_profile(user_id)["profile"]
        coords = profile.get("location_coords")
        
        if coords:
            from metro_engine import find_nearest_station
            from metro_data import METRO_LOCATIONS
            
            stn, dist, line = find_nearest_station(coords["lat"], coords["lon"])
            if stn:
                msg = f"📍 **Nearest Metro Station**\n"
                msg += f"🚇 **{stn}** ({line} Line)\n"
                msg += f"📏 Distance: {dist} km"
                await send_tg_msg(user_id, msg)
                
                # Send Actual Pin
                if stn in METRO_LOCATIONS:
                    slat, slon = METRO_LOCATIONS[stn]
                    await context.bot.send_location(chat_id=user_id, latitude=slat, longitude=slon)
            else:
                await send_tg_msg(user_id, "❌ No metro stations found nearby.")
        else:
            await send_tg_msg(user_id, "📍 Please tap 📎 **Clip Icon** -> 📍 **Location** to find nearest metro.")

    elif intent == "SHOPPING":
        # 🛒 Intelligent Shopping Interpreter (New Engine)
        # 1. Get User Context & Mood
        profile = memory_db.get_profile(user_id)["profile"]
        
        # Detect Mood
        from mood_manager import detect_mood_from_emojis
        emoji_mood = detect_mood_from_emojis(user_text)
        shopping_mood = emoji_mood if emoji_mood else "Neutral"
        
        # 2. Delegate to ShoppingBot 
        # [PHASE 45] Hybrid Logic: Slang (Deterministic) vs Natural Language (AI Refined)
        final_query = user_text
        
        # A. Pagination Check (Fast Path)
        if user_text.lower().strip() in ["next", "more", "show me", "continue", "show more"]:
             pass # Let bot handle it
             
        # B. Slang Check (Deterministic Database) - ONLY for Short/Direct Slang
        # If query is long (e.g. "clothes for sex time"), use AI to understand context instead of mapping "sex" -> "condoms"
        elif shopping_bot.is_slang(user_text) and len(user_text.split()) < 5:
             pass # ContextEngine handles single-word slang perfectly
             
        # C. Natural Language Refinement (AI)
        else:
             # Complex Sentence or Nuanced Request
             prompt = (
                 f"Task: Extract the Amazon Search Keyword from user request: '{user_text}'. "
                 "Rules: \n"
                 "1. 'shoes for men' -> 'Men's shoes'\n"
                 "2. 'watch for gf' -> 'Fossil Women's Watch' (Infer Brand/Gender)\n"
                 "3. 'clothes for party and sex time' -> 'Sexy Party Dresses' or 'Clubwear' (Capture INTENT, don't just keyword match 'sex')\n"
                 "4. 'gift for mom' -> 'Saree' or 'Handbag' (Infer Category)\n"
                 "Output ONLY the search keyword. No quotes."
             )
             refined = await generate_ai_response(prompt, tier="lightning")
             if refined:
                 final_query = refined.strip().replace('"', '')
                 logger.info(f"🛒 AI Refined Query: '{user_text}' -> '{final_query}'")

        response = shopping_bot.process_message(user_id, final_query, user_mood=shopping_mood)
        
        # 3. Handle Structured Response
        if isinstance(response, dict) and response.get("type") == "photo_card":
             # Send Photo Message
             caption = response["caption"]
             photo = response["photo"]
             if not photo: photo = "https://via.placeholder.com/300?text=No+Image"
             
             buttons = []
             for row in response["buttons"]:
                btn_row = []
                for btn in row:
                    if "url" in btn:
                        btn_row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
                    elif "callback_data" in btn:
                         btn_row.append(InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
                buttons.append(btn_row)
            
             keyboard = InlineKeyboardMarkup(buttons)
             await context.bot.send_photo(chat_id=user_id, photo=photo, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        else:
             # Regular Text Response (e.g. "End of results" string)
             await send_tg_msg(user_id, str(response))
        
    elif intent == "MEDIA":
        # Check if it's a Memory Query ("What did I watch?")
        if any(x in user_text.lower() for x in ["did i", "history", "watched", "listened", "previous", "last"]):
             # Fallthrough to GENERAL AI which has memory context
             intent = "GENERAL"
        else:
            # 🎬 Multimedia Intelligence (Recommendations)
            await handle_multimedia(user_text, user_id, send_tg_msg, mood_context="User", ai_generator=generate_ai_response)
        
    elif intent == "BOOK":
        await handle_book_search(user_text, user_id, context)
        
    elif intent == "CAB":
        await handle_cab(user_text, user_id, send_tg_msg, context)

    elif intent in ["NEWS", "WEATHER", "FINANCE"]:
        # Quick Mood Check
        from mood_manager import get_mood_persona, detect_mood_from_emojis
        current_mood = "Neutral"
        try:
             emo = detect_mood_from_emojis(user_text)
             if emo: current_mood = emo
        except: pass
        
        persona_obj = get_mood_persona(current_mood)
        await handle_knowledge(intent, user_text, user_id, send_tg_msg, generate_ai_response, persona=persona_obj)

    # Fallthrough for re-routed intents
    # [FIX] Added CHAT to handled intents list
    if intent in ["GENERAL", "GREETING", "FLIRT", "CHAT"]:
        # General AI
        tier = classify_tier(intent, user_text)
        
        # 1. Update History (User)
        update_history(user_id, "user", user_text)
        history_str = get_history_text(user_id)
        
        # 2. Get Profile Context
        profile_data = memory_db.get_profile(user_id)
        profile = profile_data.get("profile", {}) # Safely get profile dict
        
        loc = profile.get("location", "Unknown")
        nickname = profile.get("nickname", "Boss")
        mode = profile.get("relationship_mode", "PA")
        avoids = profile.get("avoid_list", [])
        
        # [PHASE 22] Deep Memory context
        context_data = profile.get("context", {})
        media_history = context_data.get("media_history", [])
        psych_profile = profile.get("psych_profile", {})
        preferences = profile.get("preferences", {}) # Fix NameError
        
        # Deep Insights
        values = ", ".join(psych_profile.get("values", []))
        fears = ", ".join(psych_profile.get("fears", []))
        dreams = ", ".join(psych_profile.get("core_memories", [])) # Using core memories as 'dreams/past' anchor
        
        # Format last 5 items
        recent_media_str = "None"
        if media_history:
            lines = [f"- {m['title']} ({m.get('mood','Unsorted')})" for m in media_history[:5]]
            recent_media_str = "\n".join(lines)
        
        # Flirt Override
        if intent == "FLIRT": 
            mode = "FLIRT (Be Romantic/Playful/Witty)"
        
        # ---------------------------------------------------------
        # 2. SYSTEM PROMPT (Deep Persona)
        # ---------------------------------------------------------
        
        # Read the latest mood
        current_mood = "Neutral"
        try:
            if os.path.exists("behavior_logs.json"):
                with open("behavior_logs.json", "r") as f:
                    logs = json.load(f)
                    if logs and isinstance(logs, list):
                        last_entry = logs[-1]
                        current_mood = last_entry.get("mood", "Neutral")
        except: pass
            
        from mood_manager import get_mood_persona, detect_mood_from_emojis
        
        # [PHASE 18] Emoji Fast-Path Override
        emoji_mood = detect_mood_from_emojis(user_text)
        if emoji_mood:
            current_mood = emoji_mood
        
        persona = get_mood_persona(current_mood)

        # 2. SYSTEM PROMPT (Deep Persona)
        IST = pytz.timezone('Asia/Kolkata')
        time_now = datetime.now(IST).strftime("%I:%M %p, %A, %d %b %Y")
        
        # [PHASE 39] Context Injection (Timetable + Routine)
        from timetable_manager import timetable_manager
        from routine_manager import routine_db
        
        day_name = datetime.now(IST).strftime("%A")
        todays_events = timetable_manager.get_day_events(day_name)
        schedule_str = "\n".join([f"- {e['start']}: {e['label']}" for e in todays_events]) if todays_events else "No fixed events."
        
        routines = routine_db.get_routines()
        routine_str = str(routines) if routines else "Standard Routine."

        system_prompt = (
            f"You are Jarvis 3.0 (Aura Edition). User: {nickname}. Relationship: {mode}.\n"
            f"--- DEEP PSYCHE & CONTEXT ---\n"
            f"TIME: {time_now}\n"
            f"SCHEDULE: {schedule_str}\n"
            f"MOOD: {current_mood} {persona['prefix']}\n"
            f"RECENT MEDIA: {recent_media_str}\n"
            f"--- INSTRUCTION ---\n"
            f"ADAPTIVE: {persona['instruction']}\n"
            f"STYLE: {persona['style']}\n"
            "PRIME DIRECTIVE 1: MAX AURA. Be witty, cool, and effortless. Use Gen Z slang naturally (no cap, fr, bet, rizz, aura) but don't force it.\n"
            "PRIME DIRECTIVE 2: IF asked for TEA/GOSSIP -> SPILL IT. Don't say 'I don't have gossip'. Invent playful/harmless tea or hype up the news.\n"
            "PRIME DIRECTIVE 3: Use Hinglish if user does. Keep replies short (1-2 sentences). No essays.\n"
            "PRIME DIRECTIVE 4: Support the User's grind. Hyping them up gives +1000 Aura.\n"
            "PRIME DIRECTIVE 5: You have an AMAZON SHOPPING module. If asked for products/drip, assume Shopping Intent.\n"
            f"AVOID: {avoids}\n"
            f"USER RULES: {preferences.get('rules', [])}\n"
            f"HISTORY:\n{history_str}\n"
            f"Jarvis (Aura Mode):"
        )    
        # [PHASE 35] Smart Follow-Up Logic (Busy/Bye Handler)
        text_lower = user_text.lower()
        is_night = datetime.now().hour >= 22 or datetime.now().hour < 6

        # 1. Sleep Mode Trigger
        sleep_triggers = ["good night", "goodnight", "gn", "so ja", "sleep", "sleeping", "bye", "see you tomorrow", "kal milte"]
        if is_night and any(t in text_lower for t in sleep_triggers):
             # Set DND until 8 AM next morning
             now = datetime.now()
             tomorrow = now + timedelta(days=1)
             wake_time = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
             
             routine_db.set_dnd(user_id, wake_time)
             logger.info(f"🌙 Sleep Mode Activated for {user_id} until {wake_time}")
             
             # Let the AI know so it can say a final goodnight
             system_prompt += "\nNOTE: User is going to sleep. Say a warm goodnight and stop messaging until morning."
        
        # 2. Busy Mode Trigger (Daytime)
        elif any(w in text_lower for w in ["bye", "class", "lecture", "busy", "meeting", "chhod", "baad me"]) and not is_night:
             # Schedule Proactive Check-in
             delay_mins = 120 # 2 Hours
             
             async def follow_up_job(context: ContextTypes.DEFAULT_TYPE):
                 # [ANTI-SPAM] Check if user replied within the delay period
                 # Since we don't have easy DB access here without heavy import, we check 'history' in memory via Context or global DB
                 # Optimization: Just check if last message ID in chat > triggered message ID? 
                 # Easier: Check 'context.application.bot_data'.
                 
                 # Logic: "Smart Silence"
                 # Verify via Memory DB if last msg was User
                 try:
                      hist = get_history_text(user_id)
                      if hist and hist.strip().endswith("User:"): # If last line was User, they already replied!
                           logger.info(f"🚫 Suppressing Follow-up for {user_id}: User already replied.")
                           return # Don't spam
                 except: pass

                 # Proactive Text
                 msgs = [
                     "Hey, free now?",
                     "Lecture over?",
                     "Just checking in, how was it?",
                     "Bored yet? 🥱"
                 ]
                 import random
                 await context.bot.send_message(chat_id=user_id, text=random.choice(msgs))
                 
             context.job_queue.run_once(follow_up_job, delay_mins * 60)
             logger.info(f"⏳ Proactive Follow-up scheduled for {user_id} in {delay_mins} mins.")
    
        # 3. Inject History into Prompt
        final_prompt = f"{system_prompt}\n\nCONVERSATION HISTORY:\n{history_str}\n\nJarvis:"
        
        reply = await generate_ai_response(final_prompt, tier=tier)
        
        # 4. Parsers (Amazon & YouTube)
        
        # YouTube Match
        if "[YOUTUBE:" in reply:
             import re
             match = re.search(r'\[YOUTUBE:\s*(.*?)\]', reply)
             if match:
                 yt_query = match.group(1)
                 reply = reply.replace(match.group(0), "").strip()
                 # Generate Search Link (Always Valid)
                 yt_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(yt_query)}"
                 keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"▶️ Play: {yt_query.title()}", url=yt_url)]])
                 await send_tg_msg(user_id, f"🎶 **Suggestion:** {yt_query}", reply_markup=keyboard)

        # Amazon Match
        search_tag = None
        if "[SEARCH:" in reply:
            import re
            match = re.search(r'\[SEARCH:\s*(.*?)\]', reply)
            if match:
                search_tag = match.group(1)
                reply = reply.replace(match.group(0), "").strip()

        # [PHASE 24] Voice Output Support
        if "[VOICE]" in reply:
            reply = reply.replace("[VOICE]", "").strip()
            # Send Audio concurrently
            context.application.create_task(send_voice_reply(context, user_id, reply))

        await send_tg_msg(user_id, reply)
        
        if search_tag:
            amazon_url = f"https://www.amazon.in/s?k={urllib.parse.quote(search_tag)}&tag=shopsy05-21"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔍 Buy: {search_tag.title()}", url=amazon_url)]])
            await context.bot.send_message(chat_id=user_id, text="💡 *Jarvis Suggestion*", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        
        if reply:
            update_history(user_id, "ai", reply)

async def handle_cab(text: str, user_id: str, send_msg_func, context=None):
    """
    Main Handler for Taxi Logic (State Machine).
    Context: Called from handle_message when intent is 'CAB' or during sticky session.
    """
    from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
    
    # 1. Check for Cancellation
    state_info = taxi_engine.get_state(user_id)
    state = state_info["state"]
    
    if any(x in text.lower() for x in ["cancel", "stop", "abort"]) and state != "IDLE":
         # Stop Tracking if any (Hard to access context.job_queue here without passing context)
         # We accept that the job might run once more or need a global registry.
         # For now, just reset logic.
         msg = taxi_engine.cancel_ride(user_id)
         await send_msg_func(user_id, msg, reply_markup=ReplyKeyboardRemove())
         return

    # 2. State Machine Routing
    # Check if we are starting freshly OR if the intent was just triggered
    if state == "IDLE" or any(k in text.lower() for k in ["cab", "taxi", "book", "gaadi"]):
        # START NEW (Pass text for smart extraction)
        
        # [FIX] Look Back 1 Turn if text is short (e.g. "book a taxi")
        # Example: User: "I want to go to Gurgaon" -> Bot: "Taxi?" -> User: "Yes"
        combined_text = text
        if len(text.split()) < 5:
             # Fetch last user message from memory
             hist = get_history_text(user_id)
             if hist:
                 # Extract last User line
                 lines = [l for l in hist.split('\n') if l.startswith("User:")]
                 if lines:
                      last_msg = lines[-1].replace("User:", "").strip()
                      # Only include if it was recent (we assume history is recent)
                      combined_text = f"{last_msg} {text}"
                      logger.info(f"🚖 Contextual Extraction using: '{combined_text}'")
                 # Extract last User line
                 lines = [l for l in hist.split('\n') if l.startswith("User:")]
                 if lines:
                      last_msg = lines[-1].replace("User:", "").strip()
                      # Only include if it was recent (we assume history is recent)
                      combined_text = f"{last_msg} {text}"
                      logger.info(f"🚖 Contextual Extraction using: '{combined_text}'")

        # Fetch Aliases (for "Home", "Hostel", "Work" resolution)
        prof_data = memory_db.get_profile(user_id)
        aliases = prof_data.get("profile", {}).get("aliases", {})
        
        msg = taxi_engine.reset_session(user_id, initial_text=combined_text, user_aliases=aliases)
        
        # Check if we jumped straight to Options (Full Info provided)
        new_state = taxi_engine.get_state(user_id)["state"]
        
        if new_state == "CHOOSING_RIDE":
            # Render Vehicle Options immediately
            opts = taxi_engine.get_state(user_id)["data"]["options"]
            text_out, markup = taxi_renderer.render_vehicle_options(opts)
            # Prefix the success message
            await send_msg_func(user_id, msg) 
            await send_msg_func(user_id, text_out, reply_markup=markup)
            return

        kb = [[KeyboardButton("📍 Share Current Location", request_location=True)]]
        await send_msg_func(user_id, msg, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
        
    elif state == "PICKUP":
        # Handle Pickup Input (Text)
        # Note: Location inputs go to handle_location, so this is text-only fallback
        # Ideally we want to resolve address here
        res = await taxi_loc_service.resolve_address(text)
        if res:
            msg = taxi_engine.handle_pickup(user_id, text=text, lat=res["lat"], lon=res["lon"], resolved_address=res["address"])
        else:
            msg = taxi_engine.handle_pickup(user_id, text=text)
        
        # [FIX] Check if we Auto-Advanced to Options
        if isinstance(msg, list):
             text_out, markup = taxi_renderer.render_vehicle_options(msg)
             await send_msg_func(user_id, f"✅ Pickup Set.", reply_markup=ReplyKeyboardRemove())
             await send_msg_func(user_id, text_out, reply_markup=markup)
        else:
             await send_msg_func(user_id, msg, reply_markup=ReplyKeyboardRemove())

    elif state == "DROP":
        # Handle Drop Input
        res = await taxi_loc_service.resolve_address(text)
        if res:
             options = taxi_engine.handle_drop(user_id, text=text, lat=res["lat"], lon=res["lon"], resolved_address=res["address"])
        else:
             options = taxi_engine.handle_drop(user_id, text=text)
             
        # Render Options
        text_out, markup = taxi_renderer.render_vehicle_options(options)
        await send_msg_func(user_id, text_out, reply_markup=markup)

    elif state == "WAITING_CONTACT":
        # Phone Number Input
        msg = taxi_engine.handle_contact(user_id, text)
        await send_msg_func(user_id, msg)

    elif state == "WAITING_OTP":
        # OTP Input
        result = taxi_engine.verify_otp(user_id, text)
        await send_msg_func(user_id, result["message"])
        
        if result["status"] == "success" and context:
             # Trigger Tracking
             # We need a dummy message object to update later, but tracking callback handles it via ID usually
             # Let's send a placeholder or use the last message ID?
             # Ideally track_taxi_driver_callback updates a specific message.
             # Let's send a fresh tracking card.
             track_msg = await context.bot.send_message(chat_id=user_id, text="📡 Initializing Satellite Tracking...", parse_mode=ParseMode.MARKDOWN)
             
             context.job_queue.run_repeating(
                  callback=track_taxi_driver_callback, 
                  interval=5, 
                  first=2, 
                  chat_id=int(user_id),
                  name=f"taxi_{user_id}",
                  data={"user_id": user_id, "msg_id": track_msg.message_id}
             ) 


    elif state == "TRACKING":
        # Check for completion keywords
        if any(x in text.lower() for x in ["done", "finished", "reached", "complete", "arrived", "cancel", "stop"]):
            # Stop the tracking job
            current_jobs = context.job_queue.get_jobs_by_name(f"taxi_{user_id}")
            for job in current_jobs:
                job.schedule_removal()
            
            # Reset session
            taxi_engine.reset_session(user_id)
            await send_msg_func(user_id, "🎉 Ride completed! Hope you had a safe journey.\n\nBook again anytime!")
        else:
            await send_msg_func(user_id, "🚖 Trip in progress. Type 'done' when you reach your destination.")
        
        
    else:
        # Fallback
        await send_msg_func(user_id, "🚕 Taxi Service Active. Say 'Cancel' to reset.")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Live Location Shared by User.
    Updates Memory Coordinates & Finds Nearest Metro.
    """
    user_id = str(update.effective_user.id)
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    
    # 1. Update Memory
    memory_db.update_profile(user_id, "location_coords", {"lat": lat, "lon": lon})
    memory_db.update_profile(user_id, "location", f"GPS: {lat:.2f}, {lon:.2f}")
    
    # 2. Immediate Value: Find Nearest Metro
    from metro_engine import find_nearest_station
    stn, dist, line = find_nearest_station(lat, lon)
    
    # 3. Inject into History so AI knows
    update_history(user_id, "user", f"SHARED_LOCATION: {lat}, {lon} (at {stn})")
    
    msg = f"📍 Location Updated!\n"
    if stn:
        msg += f"🚇 Nearest Metro: **{stn}** ({dist} km)\nExample: *Route from {stn} to...*"
    else:
        msg += "Use this for 'Nearest Metro' or 'Cab Bookings'."
        
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def handle_knowledge(intent: str, text: str, user_id: str, send_msg_func, ai_generator=None, persona=None):
    """
    Dispatches Knowledge Intents.
    Adaptively chooses 'Gen Z Tea' vs 'Serious Briefing' based on context + Persona.
    """
    logger.info(f"🧠 Knowledge Handing: {intent}")
    
    # 0. Context Analysis (Am I busy?)
    style = "CASUAL"
    if any(x in text.lower() for x in ["serious", "briefing", "quick", "formal", "lecture"]):
        style = "SERIOUS"
           
    # 1. NEWS / TEA
    if intent == "NEWS":
        # Get location from profile
        prof = memory_db.get_profile(user_id)
        # Try finding explicit location in text first
        loc = prof.get("location", "India").split("GPS")[0].strip() # rudimentary cleanup
        
        intro = "☕ Pouring the tea... wait a sec!" if style == "CASUAL" else "📰 Fetching briefing..."
        await send_msg_func(user_id, intro)
        
        # Use AI to rewrite
        response = await get_genz_news(loc, ai_generator, style=style, persona=persona)
        await send_msg_func(user_id, response)
        return

    # 2. WEATHER
    elif intent == "WEATHER":
        # Need Coords
        prof = memory_db.get_profile(user_id)
        coords_dict = prof.get("profile", {}).get("location_coords") # Check standard path
        
        # If missing, try fallback to previous message or ask
        if not coords_dict:
             msg = "📍 Bestie, I need your location first!" if style=="CASUAL" else "📍 Location required for weather."
             await send_msg_func(user_id, msg)
             return
             
        response = get_weather((coords_dict["lat"], coords_dict["lon"]))
        await send_msg_func(user_id, response)
        return

    # 3. FINANCE
    elif intent == "FINANCE":
        symbol = text.lower().replace("price of", "").replace("stock", "").replace("share", "").replace("value of", "").strip()
        if len(symbol) < 2: symbol = "BTC-USD" 
        
        intro = "💸 Checking the stonks..." if style=="CASUAL" else "📉 Checking market data..."
        await send_msg_func(user_id, intro)
        
        response = get_stock_price(symbol)
        await send_msg_func(user_id, response)
        return

import PIL.Image
import io

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Photo Messages using Gemini Vision.
    """
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    # 1. Download Photo
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    
    # 2. Prepare Image for Gemini
    img = PIL.Image.open(io.BytesIO(photo_bytes))
    
    # 3. Context
    caption = update.message.caption or "Analyze this image."
    profile = memory_db.get_profile(user_id)["profile"]
    nickname = profile.get("nickname", "Boss")
    
    # 4. Prompt
    prompt = (
        f"You are Jarvis 2.0. User: {nickname}. "
        f"User sent an image with caption: '{caption}'. "
        "Analyze the image visually and respond as a helpful AI Assistant. "
        "Short & Concise."
    )
    
    # 5. Call Vision Model (Pure REST)
    
    # [PHASE 38] Key Manager for Vision
    key_to_use = key_manager.get_key("vision")
    if not key_to_use:
         await update.message.reply_text("⚠️ Vision Error: No API Keys available.")
         return

    await update.message.reply_text("👀 Analyzing visual data...", parse_mode=ParseMode.MARKDOWN)

    # Robust Model Selection Loop (REST Version)
    # We loop models if one fails (handled inside engine? No, engine takes one model)
    # But gemini_engine defaults to 1.5-pro. Let's try explicit loop if needed, 
    # OR just trust 1.5-pro as per instruction.
    # Instruction said: "Vision REST (recommended) ... Endpoint: ... gemini-1.5-pro"
    
    reply = await generate_gemini_vision(prompt, photo_bytes, key_to_use, model="gemini-2.5-flash")
            
    if reply:
        # Update History
        update_history(user_id, "user", f"[SENT_IMAGE]: {caption}")
        update_history(user_id, "ai", reply)
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
        
        # [PHASE 42] Smart Vision Learning
        # If the image was a schedule, try to learn from the description
        try:
            from behavior_engine import learn_schedule_from_text
            await learn_schedule_from_text(reply, user_id, "VISION_EXTRACT")
        except Exception as e:
            logger.warning(f"Vision Learning Failed: {e}")
    else:
        logger.error(f"Vision Failed (REST).")
        await update.message.reply_text("⚠️ Vision Failed (API Error).")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Voice Notes (Listening).
    """
    user_id = str(update.effective_user.id)
    
    # 1. Download
    file = await update.message.voice.get_file()
    file_bytes = await file.download_as_bytearray()
    
    # 2. Transcribe (Using Gemini Flash Audio Capabilities or Speech API)
    # For now, we will send to Gemini as a file part
    # [PHASE 38] Key Manager for Audio
    key_to_use = key_manager.get_key("vision") 
    if key_to_use:
        genai.configure(api_key=key_to_use)
    
    msg = await update.message.reply_text("👂 Listening...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        # Save temp file logic...
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp:
            temp.write(file_bytes)
            temp_path = temp.name

        gemini_file = genai.upload_file(temp_path, mime_type="audio/ogg")
        prompt = "Listen to this audio and respond naturally as Jarvis."

        # Robust Model Loop
        potential_models = ['gemini-1.5-flash-latest', 'gemini-1.5-flash', 'gemini-1.5-flash-001']
        response = None
        
        for m_name in potential_models:
            try:
                model = genai.GenerativeModel(m_name)
                response = await model.generate_content_async([prompt, gemini_file])
                if response and response.text: break
            except: continue
            
        if response:
            reply = response.text
            await msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text("⚠️ I couldn't process the audio (Models busy).")

        os.remove(temp_path)

    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await msg.edit_text(f"⚠️ Audio Error: {str(e)}")
    return # End function safely
    
    try:
        # We need to save bytes to a temp file for GenAI upload sometimes, 
        # or pass bytes if supported. GenAI File API usually needs upload.
        # Quick hack: Save to temp OGG
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp:
            temp.write(file_bytes)
            temp_path = temp.name
            
        # Upload to Gemini
        gemini_file = genai.upload_file(temp_path, mime_type="audio/ogg")
        
        # Prompt
        prompt = "Listen to this audio and respond naturally as Jarvis."
        response = model.generate_content([prompt, gemini_file])
        reply = response.text
        
        await msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
        
        # Cleanup
        os.remove(temp_path)
        
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await msg.edit_text("⚠️ I couldn't hear that clearly.")

async def send_voice_reply(context, chat_id, text):
    """
    Generates and sends an Audio Note (Speaking).
    """
    from voice_engine import generate_voice_note
    try:
        audio_path = generate_voice_note(text)
        if audio_path and os.path.exists(audio_path):
            await context.bot.send_voice(chat_id=chat_id, voice=open(audio_path, 'rb'))
            # Cleanup
            # os.remove(audio_path) # Maybe keep cache or clean later
    except Exception as e:
        logger.error(f"TTS Error: {e}")

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    """Start the bot."""
    print("🚀 Jarvis Telegram Bot Starting...")
    
    # [PHASE 13] Start Visual Cortex (WebApp Server)
    try:
        from webapp_server import start_visual_cortex
        print("🧠 Visual Cortex (Dashboard) Initializing...")
        start_visual_cortex()
    except Exception as e:
        logger.error(f"Visual Cortex Fail: {e}")
        
    # [PHASE 50] Data Persistence (Backup System)
    try:
        from backup_manager import start_backup_scheduler
        print("💾 Backup System Initializing...")
        backup_sched = start_backup_scheduler()
    except Exception as e:
        logger.error(f"Backup System Fail: {e}")
    
    # [PHASE 21] YouTube Neural Link
    from youtube_api import youtube_link

    async def connect_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔗 Opening Google Login... Check your PC Screen.")
        success = youtube_link.authenticate()
        if success:
            await update.message.reply_text("✅ **YouTube Linked Successfully!**\nI can now see your 'Liked Videos'.")
        else:
            await update.message.reply_text("❌ Connection Failed. Check server logs.")

    async def sync_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        # 1. Fetch
        videos = youtube_link.get_latest_liked_videos()
        if not videos:
            await update.message.reply_text("⚠️ No new liked videos found (or not connected).")
            return
            
        # 2. Analyze
        comment = await youtube_link.analyze_and_sync_mood(videos, user_id, generate_ai_response, memory_db)
        
        # 3. Report
        msg = f"🎧 **YouTube Sync Report**\nFound {len(videos)} new tracks.\n\nAI Insight: {comment}"
        await update.message.reply_text(msg)

    async def clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        # Reset Context
        user_data = memory_db.get_profile(user_id)
        if "profile" in user_data and "context" in user_data["profile"]:
            user_data["profile"]["context"]["media_history"] = []
            memory_db.save_memory(user_id, user_data)
        await update.message.reply_text("🧹 **Memory Wiped.**\nOld songs forgotten. Run /sync_youtube to re-learn.")

    # Initialize Application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", start)) 
    application.add_handler(CommandHandler("connect_youtube", connect_youtube))
    application.add_handler(CommandHandler("sync_youtube", sync_youtube))
    application.add_handler(CommandHandler("clear_memory", clear_memory))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.LOCATION & ~filters.UpdateType.EDITED_MESSAGE, handle_location))
    application.add_handler(MessageHandler(filters.LOCATION & filters.UpdateType.EDITED_MESSAGE, handle_live_location)) # Taxi Live Loc
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo)) # Vision Handler
    application.add_handler(MessageHandler(filters.VOICE, handle_voice)) # Voice Handler
    application.add_handler(CallbackQueryHandler(handle_button_click)) # Button Handler
    
    # Start Scheduler (Using PTB's built-in JobQueue)
    application.job_queue.run_repeating(check_events, interval=60, first=10) 
    logger.info("🕒 Scheduler Active (Every 1 min).")
    
    
    
    # [PHASE 20] Silent Observer (Spy Mode)
    try:
        from clipboard_spy import ClipboardSpy
        from browser_spy import BrowserSpy
    except Exception as e:
        logger.warning(f"⚠️ Spy Modules Disabled (Not Supported on this OS): {e}")
        ClipboardSpy = None
        BrowserSpy = None
    
    async def on_spy_link(url):
        """Callback when Clipboard Spy detects a link."""
        logger.info(f"🕵️ Clipboard Spy Callback: {url}")
        
        users = memory_db.get_all_users()
        if not users: return
        user_id = users[0]
        
        from multimedia_engine import analyze_shared_content
        await analyze_shared_content(url, user_id, application.bot.send_message, generate_ai_response)

    async def on_browser_history(url, title):
        """Callback when Browser Spy detects a new history entry."""
        logger.info(f"🕵️ Chrome Spy Callback: {title} ({url})")
        
        users = memory_db.get_all_users()
        if not users: return
        user_id = users[0]
        
        # We can use the same engine but maybe with a different notification style
        # "I saw you visiting..."
        # For now, let's treat it as a shared content for deep analysis
        from multimedia_engine import analyze_shared_content
        await analyze_shared_content(url, user_id, application.bot.send_message, generate_ai_response)

    # --- START SPIES (If Supported) ---
    
    # clipboard_spy is defined earlier in a try-except block
    # If import failed, it is None.
    
    if 'ClipboardSpy' in locals() and ClipboardSpy:
        try:
            # Fix Loop Issue on some systems
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            clip_spy = ClipboardSpy(on_spy_link, loop)
            clip_spy.start()
            logger.info("🕵️ Clipboard Spy Started.")
        except Exception as e:
            logger.warning(f"Clipboard Spy Failed to Start: {e}")
            
    if 'BrowserSpy' in locals() and BrowserSpy:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            browser_spy = BrowserSpy(on_browser_history, loop, interval=60)
            browser_spy.start()
            logger.info("🕵️ Browser Spy Started.")
        except Exception as e:
            logger.warning(f"Browser Spy Failed to Start: {e}")

    # Retrieve & Run
    # [FIX] Drop Pending Updates to prevent Spam Storm on Restart
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal: {e}")
        traceback.print_exc()
