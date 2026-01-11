import urllib.parse
import logging

logger = logging.getLogger(__name__)

async def handle_multimedia(user_text, user_id, send_msg_func, mood_context=None, ai_generator=None, user_location=None, time_context=None):
    """
    Suggests YouTube/Music content based on User Input + Mood + Context.
    """
    query = user_text.lower().replace("play", "").replace("watch", "").replace("listen to", "").replace("suggest", "").strip()
    
    # 1. AI Refinement (If query is vague or empty, use Mood + Memory)
    if not query or len(query) < 3:
        # [PHASE 24] Personalization Injection
        from memory_core import memory_db
        try:
            profile = memory_db.get_profile(user_id)
            # Default to pop if no preferences
            prefs = profile.get("preferences", {}).get("music_genres", "Pop, Lofi") 
            history = profile.get("profile", {}).get("media_history", [])[-3:] # Last 3 songs
            
            history_str = ", ".join([h.get('title', 'Unknown') for h in history])
            
            if mood_context and ai_generator:
                prompt = (
                    f"User Mood: '{mood_context}'. "
                    f"Location: '{user_location}'. Time: '{time_context}'. "
                    f"User Tastes: {prefs}. "
                    f"Recent History: {history_str}. "
                    "Task: Suggest a SPECIFIC song or mix that fits the mood, location, time, and taste. "
                    "Examples: 'Rainy Day Jazz in Mumbai', 'Late Night LoFi', 'Morning Workout Pop'. "
                    "Output ONLY the search query. No quotes."
                )
                query = await ai_generator(prompt, tier="lightning")
                query = query.strip().replace('"', '')
            else:
                query = f"Best {prefs} Mix"
        except Exception as e:
            logger.error(f"Media Personalization Fail: {e}")
            query = "Trending Music"

    # 2. Generate Links
    enc_query = urllib.parse.quote(query)
    yt_url = f"https://www.youtube.com/results?search_query={enc_query}"
    music_url = f"https://music.youtube.com/search?q={enc_query}"
    
    # 3. Construct Message
    msg = f"🎬 **Multimedia Suggestion**\n\n"
    msg += f"🎵 **Vibe**: *{query.title()}*\n"
    msg += f"Based on your mood." if mood_context else ""
    
    # 4. Buttons (We need InlineKeyboardMarkup, but we pass it via kwargs to send_msg_func)
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Watch on YouTube", url=yt_url)],
        [InlineKeyboardButton("🎧 Listen on Music", url=music_url)]
    ])
    
    await send_msg_func(user_id, msg, reply_markup=keyboard)
    logger.info(f"🎬 Multimedia served: {query}")

# [PHASE 19] Real-Time Link Listener
async def analyze_shared_content(url, user_id, send_msg_func, ai_generator):
    """
    Analyzes a shared link (YouTube/Amazon) to update User Profile/Mood.
    """
    # 1. Identity Content Type
    domain = "Unknown"
    if "youtube" in url or "youtu.be" in url: domain = "YouTube"
    elif "amazon" in url or "amzn" in url: domain = "Amazon"
    elif "spotify" in url: domain = "Spotify"
    
    # 2. AI Analysis of the SIGNAL
    prompt = (
        f"User just shared this link: {url} ({domain}). "
        "Analyze what this action implies about their current mood or interest. "
        "Output a short, witty, 1-sentence comment to verify you 'saw' it. "
        "Example: 'Oho, romantic songs? Missing someone? 😉' or 'New gadget? Nice choice!'"
    )
    
    comment = await ai_generator(prompt, tier="speed")
    comment = comment.strip().replace('"', '')
    
    # 3. Reply
    await send_msg_func(user_id, f"👀 **I see you.**\n{comment}")
    
    logger.info(f"🔗 Link Analyzed: {url} | Comment: {comment}")
    
    # [PHASE 20] Save to Permanent Memory
    from memory_core import memory_db
    # We infer mood from the comment or just pass 'Detected'
    memory_db.log_media(user_id, url, f"{domain} Usage", mood="Interested")
