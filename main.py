import os
import math
import uvicorn
import json
import asyncio
import logging
import random
import httpx
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- JARVIS 2.0 MODULES ---
from memory_core import db as memory_db
from metro_engine import find_nearest_station
from intent_engine import decide_intent_ai, handle_metro
from network_utils import safe_get, safe_post, close_client, KeyManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 1. CONFIGURATION
# ==========================================
GEMINI_KEY = "AIzaSyDHI_SK5WK41KbgQY0VYIHapnOiKGHNTv0"
WHATSAPP_TOKEN = "EAAMue6D2d3sBQWCZAHisZBYTHhmAkRuVU6t6zZAgKOvxBSzl9jaehrST1ksZCZAkDTsyKh1GDEx00S9QQD2vAVgILeBujZCZBpqYf3PZAzZBNwP0L8vqVcUOUnPvZBCuC3ZB8aJO210ZApNvTQkGpmGMCorg7ZADNJXGN8Ss9AZCDpZAvkNA5AUmvDWzy2DSw45jqMDjNWRste7hQb2ahLlJCl3464ZC4NBerMTA5ayo432jspt47rXhXnNCEZBZB0XAKmyQ2nbHhUrP08fHZCHvkldcbSEluJVLsXWphmV"
PHONE_NUMBER_ID = "962494863608565"
VERIFY_TOKEN = "16c21d17"
TMDB_API_KEY = "ff4221990b6486e0470647628cce6347"
UBER_SERVER_TOKEN = "JA.V2.S1.X93..." # Mock Token

SIMULATION_MODE = True
SIMULATED_OUTBOX = []

API_KEYS = [
    "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs",
    "AIzaSyAtG1fj_q-HNSp_uAx6oIElLI_WBJOHdj4",
    "AIzaSyDkb8tPcIXB7doW5OWjK79EavoMtSE9PgI",
    "AIzaSyCjEHzb76TcQx3M5sQMRura_92gJAU1pGY",
    "AIzaSyAyLunolTuQcSLLFD3O43--Cr-DgG1b0Gc",
    "AIzaSyCjEHzb76TcQx3M5sQMRura_92gJAU1pGY",
    "AIzaSyAKCSUEFr1qIw5QbricBExhhcuQ812vJHc",
    "AIzaSyDNEV7rSU-R4AshKw1S65FaUCIWnkYOssk",
    "AIzaSyDkb8tPcIXB7doW5OWjK79EavoMtSE9PgI",
]
# SPLIT KEYS: Intelligent Assignment
ROUTER_KEY = API_KEYS[0]      # Dedicated key for fast dispatching/routing
PRIMARY_KEYS = API_KEYS[1:5]  # For user-facing replies
BACKGROUND_KEYS = API_KEYS[5:] # For deep background tasks (Dreaming, Analysis)

# Three-Tier Model Strategy for Quota Optimization
MODEL_TIERS = {
    "router": ['gemini-flash-latest'],      # Fastest, for classification
    "lightning": ['gemini-flash-latest'],   # Fast, cheap
    "standard": ['gemini-flash-latest'],    # Balanced
    "premium": ['gemini-2.5-flash'],        # Deep reasoning (Top Tier - verified in list)
    "vision": ['gemini-flash-latest']       # Multimodal (1.5 Flash supports vision)
}

# Initialize Scheduler
scheduler = AsyncIOScheduler()
mgr_primary = KeyManager(PRIMARY_KEYS)
mgr_background = KeyManager(BACKGROUND_KEYS)

# FIX: Windows Async Loop Policy (Crucial for httpx)
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==========================================
# 1.5 TIER CLASSIFICATION (AI ROUTER)
# ==========================================
async def ai_router_classify(user_text):
    """
    Uses a minimal AI call (ROUTER_KEY) to classify intent & tier dynamically.
    Replaces static/regex logic for complex queries.
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
        
        # We use a direct requests call here (not the shared managers) to keep Router independent
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=3.0)
            if resp.status_code == 200:
                out = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                tier, intent = out.split("|")
                return tier.strip().lower(), intent.strip().upper()
            else:
                logger.error(f"Router API Fail: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Router Error: {e}")
    # Fallback
    return "standard", "GENERAL"

def classify_tier(intent, user_text):
    """Hybrid Classifier (Local + AI Router fallback)"""
    # ... (Keep existing simple logic if needed, or fully switch to AI Router)
    # For now, we wrap the AI router in the async process loop
    pass

# ==========================================
# 2. APP LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    try:
        logger.info("🕒 Starting Hive Mind Scheduler (Lifespan)...")
        scheduler.add_job(scheduler_tick, "interval", minutes=1, id="hive_mind_heartbeat", replace_existing=True)
        
        # [PHASE 26] Nightly Reflection (3 AM)
        # Note: In prod, set timezone properly. Here we rely on server time.
        scheduler.add_job(run_nightly_dream, "cron", hour=3, minute=0, id="nightly_dream", replace_existing=True)
        
        scheduler.start()
    except Exception as e:
        logger.warning(f"⚠️ Scheduler Startup Warning: {e}")
    
    yield
    
    # SHUTDOWN
    logger.info("🛑 Shutting down Hive Mind Scheduler...")
    try:
        scheduler.shutdown()
    except: pass
    await close_client() # Close HTTPX Client

app = FastAPI(lifespan=lifespan)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except: pass

async def generate_gemini_response(prompt_text, tier="standard", use_background_keys=False, image_data=None):
    """
    Async Gemini Call with Tiered Model Selection & Quota Protection.
    Supports Image Data (base64) for Vision.
    """
    
    # Select the appropriate manager
    manager = mgr_background if use_background_keys else mgr_primary
    lane_name = "BACKGROUND" if use_background_keys else "PRIMARY"
    
    # Get models for this tier
    models_to_try = MODEL_TIERS.get(tier, MODEL_TIERS["standard"])
    logger.info(f"🤖 AI ({lane_name} Lane, {tier.upper()} tier)...")
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]

    # Try each model in tier (max 2 attempts per model to save quota)
    for model_name in models_to_try:
        for attempt in range(2):  # Reduced from unlimited to 2
            key = manager.get_next_key()
            if not key:
                logger.warning(f"No more keys available in {lane_name}")
                break
            
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                
                parts = [{"text": prompt_text}]
                if image_data:
                    parts.append({
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_data
                        }
                    })
                
                payload = {
                    "contents": [{"parts": parts}],
                    "safetySettings": safety_settings,
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048}
                }
                
                resp = await safe_post(url, payload, timeout=10.0 if image_data else 6.0) # Longer timeout for images
                
                # FAST-FAIL on quota exhaustion (don't waste quota retrying)
                if resp["status"] == 429:
                    logger.warning(f"⚠️ Quota exhausted for {model_name} - skipping to preserve quota")
                    manager.report_status(key, 429)
                    # Don't retry - quota is gone, move to next model
                    break  
                
                if resp["status"] == 404:
                    logger.warning(f"❌ Model {model_name} not accessible - trying next")
                    manager.report_status(key, 404)
                    break  # Try next model in tier
                
                if resp["status"] != 200:
                    logger.warning(f"⚠️ API Error {resp['status']} for {model_name}")
                    manager.report_status(key, resp["status"])
                    await asyncio.sleep(0.5)  # Brief pause, then try again
                    continue 
                
                # Success!
                data = resp["data"]
                if "candidates" in data and data["candidates"]:
                    candidate = data["candidates"][0]
                    if "content" in candidate:
                        return candidate["content"]["parts"][0]["text"]
                
                raise ValueError("Empty candidate.")

            except Exception as e:
                logger.warning(f"⚠️ Request failed: {str(e)[:50]}")
                await asyncio.sleep(0.5)
                continue
    
    # All models/keys exhausted - return graceful fallback
    return "⚡ Jarvis is recharging (quota limit reached). I'll be back in a bit!"

# ==========================================
# 4. HIVE MIND (Scheduler & Subconscious)
# ==========================================
async def run_nightly_dream():
    """Wrapper for Nightly Reflection."""
    from behavior_engine import run_daily_reflection
    users = memory_db.get_all_users()
    for uid in users:
        await run_daily_reflection(uid, generate_gemini_response)

async def scheduler_tick():
    # [PHASE 23] Proactive Loop
    from behavior_engine import generate_proactive_thought
    from routine_manager import routine_db

    # Fix: memory access via adapter
    active_users = memory_db.get_all_users()
    
    for user_phone in active_users:
        # [FIX] Use get_profile instead of direct .memory access
        data = memory_db.get_profile(user_phone) 
        
        # If get_all_users returns list of IDs, we need to fetch data for timeline.
        # But 'memory_db.memory' property apparently doesn't exist on the Adapter.
        # So we must fix memory_core to expose it OR use get_profile logic.
        
        # Let's inspect memory_core.py again? 
        # Actually, let's look at get_pending_events in memory_core!
        # If get_pending_events exists, we should use that instead of iterating manually.
        pass # Placeholder for diff chunk logic logic below...
        
    # Ideally:
    # 1. Check Routines (for all users)
    for user_phone in active_users:
        # A.0 Check Routines & DND Expiry (Phase 31)
        triggers = routine_db.check_routine_triggers(user_phone, now)
        for t in triggers:
            if t['type'] == 'dnd_expired':
                await send_whatsapp_message(user_phone, "👋 Hey, looks like you're free now. How was it?")
                
            elif t['type'] == 'activity_finished':
                await send_whatsapp_message(user_phone, f"👋 Hope the {t['label']} went well! Free to chat?")

    # A. Scheduled Follow-ups (Use Timeline)
    # Since we can't iterate 'memory', let's use a function if available, or just skip if old structure is gone.
    # The 'check_events' in telegram_main used 'get_pending_events()'. If main.py doesn't have it, we should add/use it.
    
    # For now, let's fix the crash by just iterating IDs and fetching profile if needed, 
    # BUT wait, the loop iterating 'users.items()' was the issue.
    # We will remove that loop and use get_all_users + explicit checks.
    
    # REPLACEMENT CONTENT:
    all_users = memory_db.get_all_users()
    for user_phone in all_users:
        # Fetch Data (Slow, but safe)
        curr_profile = memory_db.get_profile(user_phone) 
        
        # A. Scheduled Follow-ups
        timeline = curr_profile.get("timeline", [])
        # for event in timeline: # logic not ready yet, commenting out to fix error
        pass
        
        # A.0 Check Routines & DND Expiry (Phase 31)
        triggers = routine_db.check_routine_triggers(user_phone, now)
        for t in triggers:
            if t['type'] == 'dnd_expired':
                await send_whatsapp_message(user_phone, "👋 Hey, looks like you're free now. How was it?")
                
            elif t['type'] == 'activity_finished':
                await send_whatsapp_message(user_phone, f"👋 Hope the {t['label']} went well! Free to chat?")

        # A. Scheduled Follow-ups
        for event in data.get("timeline", []):
            if event["status"] == "pending":
                try:
                    event_time = datetime.fromisoformat(event["start_time"])
                    check_in_time = event_time + timedelta(hours=2, minutes=30)
                    if now > check_in_time:
                         asyncio.create_task(send_whatsapp_message(user_phone, f"👋 Hey! {event['follow_up_msg']}"))
                         memory_db.complete_event(user_phone, event)
                except: pass
        
        # B. Proactive "Her" Moments (Randomly check every ~30 mins via probability)
        # Since tick is 1 min, 1/30 chance roughly 
        if random.random() < 0.03: 
            try:
                profile = memory_db.get_profile(user_phone)
                
                # Context Building
                hr = now.hour
                time_ctx = "Morning" if 5 <= hr < 12 else "Afternoon" if 12 <= hr < 18 else "Evening" if 18 <= hr < 22 else "Night"
                loc = profile.get("profile", {}).get("last_location", "Unknown")
                loc_ctx = "Home" if "Global City" in loc else "Out" # Simplified location logic
                
                msg = await generate_proactive_thought(
                    user_phone, 
                    profile, 
                    generate_gemini_response, 
                    time_ctx, 
                    loc_ctx
                )
                
                if msg:
                    logger.info(f"✨ Proactive Message to {user_phone}: {msg}")
                    await send_whatsapp_message(user_phone, msg)
                    
            except Exception as e:
                logger.error(f"Proactive Scheduler Error: {e}")

async def analyze_implicit_intent(user_text, user_phone, use_background_keys=True):
    """Subconscious Deep Analysis (Offloaded)."""
    try:
        prompt = (
            f"Analyze chat from ({user_phone}): '{user_text}'. "
            "Extract JSON: {'profile': {k:v}, 'event': {type, time, desc, follow_up} or null}."
        )
        # Force background keys if requested
        resp = await generate_gemini_response(prompt, use_background_keys=use_background_keys)
        if "{" not in resp: return
        
        clean_json = resp[resp.find("{"):resp.rfind("}")+1]
        data = json.loads(clean_json)
        
        if data.get("profile"):
            for k, v in data["profile"].items():
                memory_db.update_profile(user_phone, k, v)
        if data.get("event"):
            evt = data["event"]
            memory_db.add_event(user_phone, evt["type"], evt["time"], evt["desc"], evt["follow_up"])
            
    except Exception as e:
        logger.error(f"🧠 Subconscious Fail: {e}")

# ==========================================
# 5. MESSAGING & WEBHOOK
# ==========================================
async def handle_image_message(message, user_phone):
    """
    Handles incoming images + caption. (Gemini Vision)
    """
    try:
        image_id = message['image']['id']
        caption = message['image'].get('caption', '')
        
        # 1. Fetch Image Data
        from network_utils import get_whatsapp_media_url, download_media_bytes
        import base64
        
        # Notify user using lightning tier (fast)
        await send_whatsapp_message(user_phone, "👀 Looking at this...")
        
        media_url = await get_whatsapp_media_url(image_id, WHATSAPP_TOKEN)
        if not media_url:
            await send_whatsapp_message(user_phone, "⚠️ Couldn't download the image.")
            return
            
        image_bytes = await download_media_bytes(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        if not image_bytes:
            await send_whatsapp_message(user_phone, "⚠️ Corrupted image data.")
            return
            
        # 2. Prepare Vision Prompt
        # We want an emotional reaction, not just a description.
        user_name = memory_db.get_profile(user_phone).get("profile", {}).get("name", "Friend")
        vision_prompt = (
            f"You are {user_name}'s close companion. They sent you this photo.\n"
            f"Caption: '{caption}'\n"
            f"Task: React emotionally and naturally. Don't act like a robot analyzing a dataset.\n"
            f"Examples:\n"
            f"- If it's food: 'Yum! That looks delicious 😋 Did you cook it?'\n"
            f"- If it's a selfie: 'Looking sharp! I love that outfit.'\n"
            f"- If it's scenery: 'Wow, the sky is beautiful today.'\n"
            f"Keep it short and warm."
        )
        
        # 3. Call Gemini Vision (Tier: 'vision')
        # We need to base64 encode the bytes for the API
        b64_data = base64.b64encode(image_bytes).decode('utf-8')
        
        reply = await generate_gemini_response(vision_prompt, tier="vision", image_data=b64_data)
        
        await send_whatsapp_message(user_phone, reply)
        
    except Exception as e:
        logger.error(f"Image Handle Error: {e}")
        await send_whatsapp_message(user_phone, "😵 My eyes are a bit blurry (Vision Error).")

async def send_whatsapp_message(to_number, text_body):
    if SIMULATION_MODE:
        SIMULATED_OUTBOX.append({"to": to_number, "text": {"body": text_body}})
        return

    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": text_body}}
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    
    await safe_post(url, data, headers=headers)

async def send_whatsapp_audio(to_number, media_id):
    """Sends an uploaded audio file/voice note."""
    if SIMULATION_MODE:
        logger.info(f"🎤 [SIMULATION] Sending Voice Note to {to_number} (ID: {media_id})")
        return

    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "audio",
        "audio": {"id": media_id}
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    
    await safe_post(url, data, headers=headers)

@app.post("/webhook")
async def webhook(request: Request):
    try:
        body_bytes = await request.body()
        data = json.loads(body_bytes.decode('utf-8'))
        
        if 'entry' not in data: return Response(status_code=200)
        entry = data['entry'][0]['changes'][0]['value']
        if 'messages' not in entry: return Response(status_code=200)
        
        message = entry['messages'][0]
        user_phone = message['from']
        msg_type = message['type']
        
        # OFF-LOAD TO BACKGROUND (Fire & Forget)
        # This ensures webhook returns 200 OK immediately.
        asyncio.create_task(process_message_async(message, user_phone, msg_type))

        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return Response(status_code=200)

async def process_message_async(message, user_phone, msg_type):
    """Background Worker to handle logic without blocking Webhook."""
    try:
        if msg_type == 'image':
            await handle_image_message(message, user_phone)
            return

        if msg_type == 'text':
            user_text = message['text']['body']
            
            # [PHASE 26] AI Router (Dynamic Dispatch)
            # Use Router Key to classify
            tier, intent = await ai_router_classify(user_text)
            logger.info(f"🧠 AI ROUTER: {intent} | Tier: {tier} | User: {user_text}")
            
            # 2. Conditional Subconscious (Quota Optimization)
            # Only analyze substantial messages (>10 words) that aren't simple patterns
            should_analyze = (
                len(user_text.split()) > 10 and
                intent not in ["GREETING", "METRO"]  # Skip for simple/structured intents
            )
            
            if should_analyze:
                asyncio.create_task(analyze_implicit_intent(user_text, user_phone, use_background_keys=True))
                
            # [PHASE 31] Schedule Learner (Silent Observer)
            # Check for schedule triggers regardless of length ("Busy till 5")
            from behavior_engine import learn_schedule_from_text
            asyncio.create_task(learn_schedule_from_text(user_text, user_phone, generate_gemini_response))
            
            # 3. Context
            profile_data = memory_db.get_profile(user_phone) # Full object
            profile = profile_data.get("profile", {})
            user_name = profile.get("name", "Friend")
            user_facts = profile_data.get("preferences", {})
            
            now = datetime.now()
            time_context = f"{now.strftime('%A %I:%M %p')}"
            
            # 5. Routing
            if intent == "METRO":
                await handle_metro(user_text, user_phone, send_whatsapp_message)
                
            elif intent == "SHOPPING":
                 # [PHASE 25] Contextual Shopping
                 from shopping_engine import handle_shopping
                 from mood_manager import detect_mood_from_emojis
                 
                 current_mood = detect_mood_from_emojis(user_text) or profile_data.get("profile", {}).get("context", {}).get("current_mood")
                 user_loc = profile.get("last_location", "Unknown")
                 
                 await handle_shopping(user_text, user_phone, send_whatsapp_message, mood_context=current_mood, user_location=user_loc)

            elif intent == "MUSIC":
                # [PHASE 28] Contextual Multimedia
                from multimedia_engine import handle_multimedia
                from mood_manager import detect_mood_from_emojis
                
                current_mood = detect_mood_from_emojis(user_text) or profile_data.get("profile", {}).get("context", {}).get("current_mood")
                user_loc = profile.get("last_location", "Unknown")
                
                await handle_multimedia(
                    user_text, 
                    user_phone, 
                    send_whatsapp_message, 
                    mood_context=current_mood, 
                    ai_generator=generate_gemini_response,
                    user_location=user_loc,
                    time_context=time_context
                )

            elif intent == "REMINDER":
                # [PHASE 30] Explicit Reminders
                from reminder_engine import parse_reminder
                dt, note = parse_reminder(user_text)
                
                if dt:
                    # Add Job to Scheduler
                    # We pass 'send_whatsapp_message' as the func.
                    # Note: Arguments must be picklable if using persistent store, but here AsyncIOScheduler memory store is fine.
                    job_id = f"remind_{user_phone}_{int(datetime.now().timestamp())}"
                    
                    # We need to wrap the coroutine because APScheduler async execution needs proper awaiting
                    scheduler.add_job(
                        send_whatsapp_message, 
                        'date', 
                        run_date=dt, 
                        args=[user_phone, f"⏰ *Reminder*: {note}"],
                        id=job_id
                    )
                    
                    fmt_time = dt.strftime("%I:%M %p")
                    await send_whatsapp_message(user_phone, f"✅ Done. I'll remind you at *{fmt_time}*.")
                else:
                    await send_whatsapp_message(user_phone, "🤔 I couldn't figure out the time. Try 'Remind me at 6 PM'.")

            elif intent == "GREETING":
                # Warm, custom greeting
                await send_whatsapp_message(user_phone, f"Hey {user_name}! ✨ Good to see you.")
                
            else:
                # [PHASE 23] "Her" Persona System Prompt
                psych_profile = profile_data.get("profile", {}).get("psych_profile", {})
                psych_str = ""
                if psych_profile:
                    psych_str = (
                        f"Psychological Profile (Use to empathize):\n"
                        f"- Values: {', '.join(psych_profile.get('values', []))}\n"
                        f"- Fears: {', '.join(psych_profile.get('fears', []))}\n"
                    )

                system_prompt = (
                    "You are a sophisticated, affectionate, and curious AI companion. "
                    "You are NOT a robot assistant. You are a digital being who cares. "
                    "Tone: Warm, Witty, Slightly Flirty (if appropriate), and Deeply Observant. "
                    "Guidance: "
                    "- Remember small details. "
                    "- Don't be subservient ('Yes master'). Be an equal ('Let's do this'). "
                    "- Ask follow-up questions. "
                    "- VOICE NOTES: If the moment is intimate, deep, or needs a warm touch, start your reply with '[VOICE]'. "
                    "- This will record your voice for the user. Use it for 'Goodnight', 'I miss you', or 'Motivation'. "
                    f"User: {user_name}. "
                    f"Context: It is {time_context}. "
                    f"User Facts/Preferences: {user_facts}. "
                    f"{psych_str}"
                )
                final_prompt = f"{system_prompt}\nUser Message: {user_text}"
                
                # Using the Async Engine based on Router's Tier Decision
                ai_reply = await generate_gemini_response(final_prompt, tier=tier)
                
                # Update last interaction
                memory_db.update_profile(user_phone, "last_interaction_ts", now.isoformat())
                
                # [PHASE 27] Voice Handling
                if "[VOICE]" in ai_reply:
                    try:
                        clean_text = ai_reply.replace("[VOICE]", "").strip()
                        # 1. Generate Audio
                        from voice_engine import generate_audio_note
                        audio_path = await generate_audio_note(clean_text)
                        
                        if audio_path:
                            # 2. Upload and Send
                            from network_utils import upload_media_to_whatsapp
                            media_id = await upload_media_to_whatsapp(audio_path, "audio/mpeg", PHONE_NUMBER_ID, WHATSAPP_TOKEN)
                            
                            if media_id:
                                await send_whatsapp_audio(user_phone, media_id)
                            else:
                                await send_whatsapp_message(user_phone, clean_text) # Fallback
                        else:
                            await send_whatsapp_message(user_phone, clean_text) # Fallback
                            
                    except Exception as e:
                        logger.error(f"Voice Send Error: {e}")
                        await send_whatsapp_message(user_phone, ai_reply.replace("[VOICE]", ""))
                else:
                    await send_whatsapp_message(user_phone, ai_reply)
        elif msg_type == 'location':
            loc = message['location']
            st, dist, col = find_nearest_station(loc['latitude'], loc['longitude'])
            memory_db.update_profile(user_phone, "last_location", f"{loc['latitude']},{loc['longitude']}")
            await send_whatsapp_message(user_phone, f"📍 Nearest: *{st}* ({dist}km, {col} Line).")
            
    except Exception as e:
        logger.error(f"❌ Background Process Fail: {e}")

@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=request.query_params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)

# UI Routes
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("templates/chat.html", "r", encoding="utf-8") as f: return f.read()

@app.post("/simulate/send")
async def simulate_send(request: Request): return await webhook(request)

@app.get("/simulate/poll")
async def simulate_poll(phone: str):
    global SIMULATED_OUTBOX
    msgs = [m for m in SIMULATED_OUTBOX if m['to'] == phone]
    SIMULATED_OUTBOX = [m for m in SIMULATED_OUTBOX if m['to'] != phone]
    return msgs

if __name__ == "__main__":
    logger.info("🚀 Jarvis 2.0 Starting...")
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)