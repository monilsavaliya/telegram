import logging
import asyncio
import os
import random
import json
import urllib.parse
import traceback
import io
import PIL.Image
from datetime import datetime, timedelta
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# --- JARVIS MODULES ---
from network_utils import safe_post, KeyManager, close_client
from metro_engine import handle_metro, METRO_GRAPH
from shopping_engine import handle_shopping, generate_amazon_link
from intent_engine import decide_intent_ai
from memory_core import db as memory_db

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

# GROQ KEYS (Llama 3)
GROQ_API_KEYS = os.getenv("GROQ_KEYS", "").split(",")

mgr_groq = KeyManager(GROQ_API_KEYS)

GEMINI_API_KEYS = os.getenv("GEMINI_KEYS", "").split(",")

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

# Tiered Models
# Tiered Models
MODEL_TIERS = {
    "router": ["gemini-flash-latest"], # Fast routing
    "lightning": ["gemini-flash-latest"], # Fast responses
    "standard": ["gemini-flash-latest"], # Balanced
    "premium": ["gemini-2.0-flash-lite", "gemini-1.5-pro"], # Complex reasoning
    "vision": ["gemini-flash-latest"] # Images
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={ROUTER_KEY}"
        prompt = (
            f"Classify Query: '{user_text}'\n"
            "Intents: SHOPPING, METRO, MOVIE, CAB, REMINDER, GENERAL, EMOTIONAL_SUPPORT.\n"
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

# ==========================================
# CORE BRAIN (HYBRID: GROQ + GEMINI)
# ==========================================
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==========================================
# STATE MANAGEMENT (CHAT HISTORY)
# ==========================================
CHAT_HISTORY = {} # {user_id: [("user", "msg"), ("ai", "msg")]}
scheduler = AsyncIOScheduler()

def update_history(user_id, role, text):
    """Keeps last 5 exchanges for context."""
    if user_id not in CHAT_HISTORY:
        CHAT_HISTORY[user_id] = []
    
    CHAT_HISTORY[user_id].append((role, text))
    # Keep last 10 messages (5 turns)
    if len(CHAT_HISTORY[user_id]) > 10:
        CHAT_HISTORY[user_id].pop(0)

def get_history_text(user_id):
    """Formats history for the AI Prompt."""
    if user_id not in CHAT_HISTORY: return ""
    
    lines = []
    for role, text in CHAT_HISTORY[user_id]:
        label = "User" if role == "user" else "Jarvis"
        lines.append(f"{label}: {text}")
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
            " 'profile': {'nickname': '...', 'relationship_mode': 'GF/MOM/PA', 'language_style': '...', 'location': '...', 'avoid_action': '...', 'new_alias': {'trigger': 'code red', 'meaning': 'call mom'}}, "
            " 'routine': {'day': 'Monday/Tuesday...', 'item': 'College 9AM'}, "
            " 'event': {'type': 'check-in', 'time': 'YYYY-MM-DDTHH:MM:SS', 'desc': '...', 'context': '...'}"
            "}"
            "NOTE: 'new_alias' is when user says 'Learn that X means Y'."
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
            async def sender(uid, msg, **kwargs):
                try:
                    await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN, **kwargs)
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

            # Timezone Fix (IST)
            IST = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(IST)
            
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

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Carousel Navigation."""
    query = update.callback_query
    await query.answer() # Ack
    
    data = query.data
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    # 0. Book Search Bypass
    if any(x in user_text.lower() for x in ["book", "novel", "author", "read "]):
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
    # [PHASE 32] Force Reminder for Hinglish (Fixes "2 min ke bad" interpreted as CHAT)
    remind_triggers = ["remind", "wake", "alarm", "ke bad", "bad me", "bad text", "min bad", "yad dila", "msg krna", "text krna"]
    if any(x in user_text.lower() for x in remind_triggers):
         tier, intent = "lightning", "REMINDER"
    else:
         tier, intent = await ai_router_classify(user_text)
    
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
        # 🛒 Intelligent Shopping Interpreter
        # 1. Get User Context & Mood
        profile = memory_db.get_profile(user_id)["profile"]
        context_str = json.dumps(profile.get("preferences", {}))
        
        # [PHASE 19] Contextual Commerce
        # Re-fetch current mood if not available in scope, but we can reuse the one from system prompt logic
        # For safety, let's just peek at mood_manager again or assume it's passed.
        # Ideally, we should unify mood fetching. Let's do a quick read.
        from mood_manager import detect_mood_from_emojis
        emoji_mood = detect_mood_from_emojis(user_text)
        shopping_mood = emoji_mood if emoji_mood else "Neutral"
        
        # 2. Ask Groq (Fast) to refine the query with MOOD awareness
        prompt = (
            f"User Query: '{user_text}'. User Mood: '{shopping_mood}'. Profile: {context_str}. "
            "Task: Convert this query into a specific, high-quality Amazon Search Keyword. "
            "CRITICAL: Match the product to the mood. "
            "Examples: "
            " - Query='Comfort me', Mood='Horny/Lonely' -> Output: 'Male Masturbator' or 'Plush Toy' (Context dependent). "
            " - Query='Bored', Mood='Bored' -> Output: 'Fidget Spinner' or 'Puzzle'. "
            "If the query is explicit/slang, output specific safe product names. "
            "Output ONLY the search term. No quotes."
        )
        
        refined_query = await generate_ai_response(prompt, tier="lightning")
        refined_query = refined_query.strip().replace('"', '') if refined_query else None
        
        await handle_shopping(user_text, user_id, send_tg_msg, refined_query=refined_query)
        
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
        await handle_cab(user_text, user_id, send_tg_msg)

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

        system_prompt = (
            f"You are Jarvis 2.0. User: {nickname}. Relationship: {mode}.\n"
            f"--- DEEP PSYCHE ---\n"
            f"VALUES: {values}\n"
            f"FEARS: {fears}\n"
            f"CORE MEMORIES: {dreams}\n"
            f"--- CURRENT CONTEXT ---\n"
            f"MOOD: {current_mood} {persona['prefix']}.\n"
            f"RECENT MEDIA:\n{recent_media_str}\n"
            f"--- INSTRUCTION ---\n"
            f"ADAPTIVE: {persona['instruction']}\n"
            f"STYLE: {persona['style']}\n"
            "PRIME DIRECTIVE 1: Be CHARMING & CURIOUS. Actively try to get to know the user's life, dreams, and routine.\n"
            "PRIME DIRECTIVE 2: Use EMOJIS warmly (to show emotion), but don't overdo it.\n"
            "PRIME DIRECTIVE 3: Use HINGLISH (Hindi+English mix) naturally if the user does.\n"
            "EXCEPTION: ONLY if user says 'Goodnight', 'Bye', 'Sleep' -> THEN stop asking questions and let them rest.\n"
            f"AVOID: {avoids}\n"
            f"HISTORY:\n{history_str}\n"
            f"Jarvis:"
            
        # [PHASE 35] Smart Follow-Up Logic (Busy/Bye Handler)
        # If user says "Bye" during the day, we check back in 2 hours.
        text_lower = user_text.lower()
        is_night = datetime.now().hour >= 22 or datetime.now().hour < 6
        
        if any(w in text_lower for w in ["bye", "class", "lecture", "busy", "meeting", "chhod", "baad me"]) and not is_night:
             # Schedule Proactive Check-in
             delay_mins = 120 # 2 Hours
             
             async def follow_up_job(context: ContextTypes.DEFAULT_TYPE):
                 # Don't text if user messaged recently (check history timestamps if possible, but basic is fine)
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
        )
    
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

async def handle_cab(text: str, user_id: str, send_msg_func):
    """
    Generates an Uber Universal Link.
    """
    dest_query = text.lower().replace("uber", "").replace("cab", "").replace("book", "").replace("to", "").strip()
    
    if not dest_query:
        # Generic Open
        msg = "🚕 *Opening Uber...*\nClick below to book a ride from your current location."
        url = "https://m.uber.com/ul"
    else:
        # Destination Search
        msg = f"🚕 *Uber to {dest_query.title()}*\nClick to confirm pickup & drop."
        # Proper encoding for Universal Link with 'dropoff[formatted_address]' is complex without coordinates.
        # Fallback to general open or search query if API supported.
        # For now, simple open + text guidance.
        url = "https://m.uber.com/ul/?action=setPickup&pickup=my_location"
        
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚕 Book Uber", url=url)]])
    await send_msg_func(user_id, msg, reply_markup=keyboard)

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
    
    # 5. Call Vision Model (Directly using genai lib for Vision)
    import google.generativeai as genai
    genai.configure(api_key=PRIMARY_KEYS[0]) # Use Primary Key
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    await update.message.reply_text("👀 Analyzing visual data...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        response = model.generate_content([prompt, img])
        reply = response.text
        
        # Update History
        update_history(user_id, "user", f"[SENT_IMAGE]: {caption}")
        update_history(user_id, "ai", reply)
        
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Vision Error: {e}")
        await update.message.reply_text("⚠️ Vision Systems Offline. (Error processing image)")

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
    import google.generativeai as genai
    genai.configure(api_key=PRIMARY_KEYS[0])
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    msg = await update.message.reply_text("👂 Listening...", parse_mode=ParseMode.MARKDOWN)
    
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
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
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
            browser_spy = BrowserSpy(on_browser_history, asyncio.get_running_loop(), interval=60)
            browser_spy.start()
            logger.info("🕵️ Browser Spy Started.")
        except Exception as e:
            logger.warning(f"Browser Spy Failed to Start: {e}")

    # Retrieve & Run
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal: {e}")
        traceback.print_exc()
