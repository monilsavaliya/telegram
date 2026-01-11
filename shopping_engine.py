import urllib.parse

# ==========================================
# AMAZON SHOPPING ENGINE
# ==========================================

# MAPPING: GenX/Brainrot Slang -> Real Amazon Search Terms
GENX_SLANG_MAP = {
    "horny": "adult toys",
    "sex": "adult wellness",
    "porn": "adult novelties",
    "xxx": "adult party accessories",
    "lube": "personal lubricant",
    "condom": "condoms",
    "gyat": "lingerie",
    "rizz": "grooming kit",
    "drip": "streetwear fashion",
    "sus": "among us merch",
    "sigma": "patrick bateman poster",
    "baddie": "trendy fashion women",
    "rand": "adult wellness",
    "randi": "adult wellness", 
    "chinnal": "adult wellness",
    "raand": "adult wellness",
    "gb road": "adult wellness", 
    "tharki": "adult party accessories",   # Context: "Lusty" -> Fun/Party
    "hawas": "adult wellness",            # Context: "Lust"
    "hila": "personal lubricant",         # Context: "To shake/hand solo"
    "mutth": "personal lubricant",        # Context: "Hand solo"
    "blue film": "adult novelties",
    "nude": "art & photography books",    # Safe mapping
    "nudes": "art & photography books",
    "leaked": "security software",        # Divert to safety/security
    "mms": "security software",
    "viral": "trending fashion",
    
    # --- Meme/Misspelled NSFW (Very Common in India) ---
    "bobs": "lingerie",                   # Meme spelling for "Boobs"
    "vegana": "adult wellness",           # Meme spelling for "Vagina"
    "vegna": "adult wellness",
    "sax": "adult wellness",              # Common misspelling
    "sux": "adult wellness",
    "fuddi": "adult wellness",
    "lund": "adult novelties",
    "chut": "adult wellness",
    "boob": "lingerie",
    "chooche": "lingerie",
    "saax": "adult wellness",
    # --- Existing (Preserved) ---
    "horny": "adult toys",
    "sex": "adult wellness",
    "porn": "adult novelties",
    "xxx": "adult party accessories",
    "lube": "personal lubricant",
    "condom": "condoms",
    "gyat": "shapewear & lingerie",  # Updated for accuracy (often refers to curves)
    "rizz": "grooming kit & cologne",
    "drip": "streetwear & sneakers",
    "sus": "security cameras & mystery games",
    "sigma": "gym gear & suits",
    "baddie": "trendy fashion & makeup",

    # --- Global Gen Z Slang ---
    "delulu": "manifestation journals",
    "aesthetic": "room decor & lighting",
    "slay": "party wear & high heels",
    "touch grass": "camping gear & plants",
    "cottagecore": "floral dresses & gardening tools",
    "goblincore": "thrifty fashion & mushroom decor",
    "normcore": "basic tees & jeans",
    "simp": "flowers & chocolates",
    "cap": "hats & caps", # Pun mapping
    "no cap": "authentic brands",
    "bet": "gaming consoles",
    "yeet": "sports equipment",
    "finna": "travel accessories",
    "glow up": "skincare & haircare",
    "gatekeep": "exclusive releases",
    "girl math": "sale items & bundles",
    "boy math": "investment books & tools",
    "main character": "statement jewelry & sunglasses",
    "npc": "plain t-shirts & cargo pants",
    "tea": "kettles & tea sets",
    "salty": "snacks & savory food",
    "ghost": "horror books & halloween costumes",
    "ick": "cleaning supplies",
    "mid": "budget friendly items",
    "cheugy": "vintage & retro items",
    "dank": "gaming merch & posters",
    "based": "classic literature & philosophy",

    # --- Indian Local & Internet Slang ---
    "jugaad": "DIY tools & repair kits",
    "chapri": "neon hair dye & flashy sunglasses", # Context: flashy/kitschy style
    "nibba": "couple gifts & teddy bears",
    "nibbi": "couple gifts & chocolates",
    "scene": "event tickets & party supplies",
    "sorted": "organizers & planners",
    "vella": "video games & board games",
    "timepass": "snacks & puzzle books",
    "paisa vasool": "value packs & discounts",
    "kanjoos": "piggy banks & budget planners",
    "pataka": "party poppers & festival wear",
    "dhinchak": "sequin clothing & bling",
    "bhau": "thick chains & bracelets",
    "machayenge": "speakers & sound systems",
    "bindass": "adventure gear",
    "ghanta": "alarm clocks", # Pun mapping
    "bhasad": "stress balls & fidget toys",
    "shag": "coffee & energy drinks", # Note: In India, often means 'exhausted'
    "bt": "headache balm & comfort food", # 'Bad Trip' (Bad mood/situation)
    "moye moye": "sad playlist headphones & tissues",
    "system": "smartwatches & tech gadgets", # Elvish Yadav/Systumm context
    "systumm": "loudspeakers & car accessories",
    "bawa": "mens grooming & accessories", # Parsi/Bombay slang
    "kadak": "strong coffee & premium tea",
    "kalti": "travel bags & luggage",
}

def generate_amazon_link(query):
    """Generates an Amazon Search URL with Affiliate Tag."""
    base_url = "https://www.amazon.in/s"
    params = {
        "k": query,
        "tag": "shopsy05-21"  # User's Affiliate Tag
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"

async def handle_shopping(text, user_phone, send_msg_func, refined_query=None, mood_context=None, user_location=None):
    """Handles Shopping Intents with AI Refinement + Context (Mood/Location/Trend)."""
    clean_text = text.lower().replace("buy", "").replace("price of", "").replace("amazon", "").strip()
    
    # 1. Contextual Refinement (The "Trend" Engine)
    # If the user just says "suggest something" or "buy clothes", we use context.
    search_query = clean_text
    
    # Check for slang first (overrides context if specific)
    import re
    slang_term = None
    for slang, mapped_term in GENX_SLANG_MAP.items():
        if re.search(r'\b' + re.escape(slang) + r'\b', clean_text):
            slang_term = slang
            search_query = GENX_SLANG_MAP[slang_term]
            break
            
    # If no slang and query is vague (e.g. "shoes", "gift", "clothes"), refine it.
    is_vague = len(clean_text.split()) < 3 and not slang_term
    
    if is_vague and (mood_context or user_location):
        # Apply "Trend" logic
        # e.g. "Sad" + "Food" -> "Comfort Chocolate"
        # e.g. "Mumbai" + "Shoes" -> "Rainy Season Shoes" (Mock logic for now, or AI powered)
        
        prefix = ""
        if mood_context:
            if mood_context == "Sad": prefix += "Comfort "
            elif mood_context == "Excited": prefix += "Party "
            elif mood_context == "Calm": prefix += "Minimalist "
            
        if user_location and "Mumbai" in user_location:
            # Local trend
            pass 
            
        if prefix:
            search_query = f"{prefix} {search_query}".strip()

    # 2. Refined Query Injection
    if refined_query:
        search_query = refined_query

    link = generate_amazon_link(search_query)
    
    if slang_term:
        # 🔞 Uncensored Mode Response
        msg = (
            f"🔞 *Uncensored Mode Activated*\n"
            f"Detected: _{slang_term.upper()}_\n"
            f"🎯 Personalized Pick: *{search_query.title()}*\n"
            f"👇 View Results:\n{link}"
        )
    else:
        # Standard Shopping
        suffix = f" (Based on {mood_context} mood)" if mood_context and is_vague else ""
        msg = (
            f"🛒 *Shopping Search*: {search_query.title()}{suffix}\n"
            f"👇 Click to view best prices:\n"
            f"{link}"
        )
    
    await send_msg_func(user_phone, msg)

import httpx

# ==========================================
# OPEN LIBRARY SEARCH (Book Data)
# ==========================================
async def search_open_library(query):
    """Fetches book metadata from Open Library."""
    try:
        url = "https://openlibrary.org/search.json"
        params = {"q": query, "limit": 1}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("docs"):
                    book = data["docs"][0]
                    return {
                        "title": book.get("title"),
                        "author": book.get("author_name", ["Unknown"])[0],
                        "year": book.get("first_publish_year", "N/A"),
                        "cover_id": book.get("cover_i"),
                        "found": True
                    }
    except Exception as e:
        print(f"OpenLib Error: {e}")
    return {"found": False}

async def handle_book(text, user_phone, send_msg_func):
    """Handles Book Search (Open Library + Amazon)."""
    clean_text = text.lower()
    for kw in ["book", "read", "novel", "author", "literature"]:
        clean_text = clean_text.replace(kw, "")
    clean_text = clean_text.strip()
    
    # 1. Fetch metadata from Open Library
    book_data = await search_open_library(clean_text)
    
    # 2. Generate Amazon Link
    base_url = "https://www.amazon.in/s"
    params = {
        "k": clean_text,
        "i": "stripbooks",
        "tag": "shopsy05-21"
    }
    shop_link = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    if book_data["found"]:
        cover_url = f"https://covers.openlibrary.org/b/id/{book_data['cover_id']}-M.jpg" if book_data.get('cover_id') else None
        
        caption = (
            f"📖 *{book_data['title']}*\n"
            f"✍️ by {book_data['author']} ({book_data['year']})\n\n"
            f"👇 Buy on Amazon:\n{shop_link}"
        )
        
        # If possible, send image. If not, fallback to text.
        # Note: send_msg_func in main needs to handle images or just text.
        # For simple Telegram logic, we might just send text with link if image handling isn't robust yet.
        # But let's try to send the image URL if the wrapper supports it, otherwise just text.
        
        await send_msg_func(user_phone, caption)
        if cover_url:
             await send_msg_func(user_phone, f"[Cover Image]({cover_url})") # Markdown Link for Image
            
    else:
        # Fallback to simple search
        msg = (
            f"📚 *Book Search*: {clean_text.title()}\n"
            f"👇 Browse Books on Amazon:\n"
            f"{shop_link}"
        )
        await send_msg_func(user_phone, msg)

# ==========================================
# UBER CAB ENGINE
# ==========================================
def generate_uber_deeplink(destination, pickup=None):
    """Generates an Uber Deep Link."""
    base_url = "https://m.uber.com/ul/"
    
    # URL Encode params
    dest_enc = urllib.parse.quote(destination)
    
    # Basic Universal Link
    # If pickup is None, it defaults to 'my_location' in the app
    # Format: https://m.uber.com/ul/?action=setPickup&client_id=...&pickup=my_location&dropoff[formatted_address]=Dest
    
    link = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={dest_enc}"
    return link

async def handle_cab(text, user_phone, send_msg_func):
    """Handles Cab/Uber Requests."""
    # Extract destination
    dest = text.lower()
    for kw in ["uber", "cab", "taxi", "ride to", "go to", "book"]:
        dest = dest.replace(kw, "")
    dest = dest.strip()
    
    if not dest:
        dest = "Connaught Place" # Default fallback
        
    link = generate_uber_deeplink(dest)
    
    msg = (
        f"🚖 *Uber Ride Request*\n"
        f"📍 Destination: {dest.title()}\n"
        f"👇 Tap to open Uber:\n"
        f"{link}"
    )
    await send_msg_func(user_phone, msg)
