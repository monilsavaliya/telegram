import logging
import random
from metro_data import METRO_GRAPH
from metro_engine import generate_human_readable_response, find_nearest_station, get_line_color
from network_utils import safe_get

logger = logging.getLogger(__name__)

# ==========================================
# 1. INTENT CLASSIFICATION (HIVE MIND)
# ==========================================
async def decide_intent_ai(text: str, ai_generator=None) -> str:
    """
    Hybrid Classifier: Fast Regex -> Fallback to AI Router.
    """
    text_lower = text.lower().strip()
    
    # --- LAYER 1: FAST REGEX (High Confidence Only) ---
    # We restrict this layer to ONLY very explicit commands. 
    # Everything else falls to the AI Router for "Mood Analysis".
    
    # 1. METRO (Explicit Command)
    if "metro" in text_lower or "route from" in text_lower:
        return "METRO"
    if any(k in text_lower for k in ["fastest route", "shortest route", "min exchange", "minimum exchange"]):
        return "METRO"
        
    # 2. SHOPPING (Explicit Command)
    # Only if user says "buy" or "price of". "I need shoes" goes to AI.
    if text_lower.startswith(("buy ", "price of ", "cost of ")):
        return "SHOPPING"
        
    # 3. BOOKS (Explicit Command)
    if "read book" in text_lower or "find book" in text_lower:
        return "BOOK"
        
    # 4. CAB (Explicit Command)
    if "book uber" in text_lower or "book cab" in text_lower or text_lower.startswith("uber "):
        return "CAB"

    # 5. REMINDER (Explicit Command)
    if any(k in text_lower for k in ["remind me", "wake me up", "text me at", "alarm at", "ping me at"]):
        return "REMINDER"

    # --- LAYER 2: AI ROUTER (Hive Mind) ---
    # Only use AI if regex failed (GENERAL) and we have a generator
    if ai_generator:
        try:
            prompt = (
                f"Classify this User Message into one of these INTENTS:\n"
                f"[METRO, SHOPPING, BOOK, CAB, MOVIE, REMINDER, GENERAL]\n\n"
                f"Message: '{text}'\n\n"
                f"Rules:\n"
                f"- If asking for travel/route/navigation OR preferences like 'fastest', 'min exchange' -> METRO\n"
                f"- If wanting to buy/check price -> SHOPPING\n"
                f"- If wanting to reading/find book -> BOOK\n"
                f"- If asking for taxi/uber OR generic travel (e.g. 'go to start', 'take me to X', 'I want to go to Y') -> CAB\n"
                f"- If asking to set an alarm/reminder/wake up -> REMINDER\n"
                f"- If casual chat/greeting -> GENERAL\n"
                f"Reply ONLY with the Intent Word."
            )
            # Use 'lightning' tier (Groq) for speed
            ai_verdict = await ai_generator(prompt, tier="lightning")
            ai_verdict = ai_verdict.upper().strip().replace(".", "")
            
            valid_intents = ["METRO", "SHOPPING", "BOOK", "CAB", "MOVIE", "REMINDER", "GENERAL"]
            if ai_verdict in valid_intents:
                logger.info(f"🧠 AI Router: '{text}' -> {ai_verdict}")
                return ai_verdict
                
        except Exception as e:
            logger.error(f"AI Router Fail: {e}")

    # Fallback
    return "GENERAL"

# ==========================================
# 2. METRO LOGIC HANDLER
# ==========================================
async def handle_metro(text: str, user_phone: str, send_msg_func, ai_generator=None, criteria="fastest"):
    """Specialized Agent for Metro Logic."""
    logger.info(f"🚇 Handling Metro Request: {text}")
    text_lower = text.lower()
    
    # A. NEAREST STATION (Local DB Logic)
    if "nearest" in text_lower or "near" in text_lower:
        loc_query = text_lower.replace("nearest", "").replace("near", "").replace("metro", "").strip()
        if not loc_query: loc_query = "current location"
        
        target_coords = None
        
        # 1. Internal DB Match
        for name, coords in METRO_GRAPH.get("coords", {}).items():
            if name.lower() in loc_query:
                target_coords = coords
                break
        
        if target_coords:
            st_name, dist, color = find_nearest_station(*target_coords)
            await send_msg_func(user_phone, f"📍 Nearest to {loc_query.title()}: *{st_name}* ({dist}km, {color} Line)")
        else:
            await send_msg_func(user_phone, f"📍 Please share your Live Location for precise 'Nearest Station' info.")
        return

    # B. ROUTE FINDING
    if " to " in text_lower or " se " in text_lower:
        try:
            # Flexible parsing for "X to Y" or "X se Y" (Hinglish)
            if " to " in text_lower:
                parts = text_lower.split(" to ")
            else:
                parts = text_lower.split(" se ") # Hinglish
                
            start_raw = parts[0].replace("route", "").replace("from", "").replace("bta", "").strip()
            end_raw = parts[1].replace("tk", "").replace("ka", "").replace("route", "").strip()
            
            # Fuzzy Logic (Simple Substring)
            all_stations = list(METRO_GRAPH["stations"].keys())
            
            start_match = next((s for s in all_stations if start_raw in s.lower()), None)
            end_match = next((s for s in all_stations if end_raw in s.lower()), None)
            
            # AI Fallback for Typos/Landmarks (e.g. "India Get")
            if (not start_match or not end_match) and ai_generator:
                prompt = (
                    f"Map these locations to EXACT Delhi Metro Station names from the official list.\n"
                    f"Start Input: '{start_raw}'\n"
                    f"End Input: '{end_raw}'\n"
                    f"Official Stations Sample: Rajiv Chowk, Kashmere Gate, Hauz Khas, India Gate (Wait, India Gate is arguably Central Secretariat/Khan Market, but let's map closest).\n"
                    f"Reply STRICTLY in format: StartStation|EndStation\n"
                    f"If unknown, reply: UNKNOWN|UNKNOWN"
                )
                try:
                    ai_resp = await ai_generator(prompt, tier="lightning")
                    if "|" in ai_resp and "UNKNOWN" not in ai_resp:
                        s, e = ai_resp.split("|")
                        if not start_match: start_match = s.strip()
                        if not end_match: end_match = e.strip()
                except Exception as ex:
                    logger.error(f"AI Metro Res Error: {ex}")

            if start_match and end_match:
                 # Use the Human Readable Generator from Engine
                 path_str = generate_human_readable_response(start_match, end_match) # Pass criteria if engine supported it
                 await send_msg_func(user_phone, path_str)
            else:
                 missing = []
                 if not start_match: missing.append(f"Start ({start_raw})")
                 if not end_match: missing.append(f"End ({end_raw})")
                 await send_msg_func(user_phone, f"⚠️ Unknown Station: {', '.join(missing)}. Try exact names.")
                 
        except Exception as e:
            logger.error(f"Route Error: {e}")
            await send_msg_func(user_phone, "⚠️ Could not calculate route. Try 'Route from Dwarka to Rajiv Chowk'.")
        return

    # Default Metro Message
    await send_msg_func(user_phone, "🚇 Metro System Online. Ask me: 'Route from X to Y' or 'Nearest station to Z'.")
