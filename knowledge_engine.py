import logging
import feedparser
import yfinance as yf
import requests
import random
import urllib.parse
from datetime import datetime

logger = logging.getLogger(__name__)

# ==========================================
# 1. GEN Z NEWS (Google RSS + AI Rewrite)
# ==========================================
async def get_genz_news(location, ai_generator, tier="speed", style="CASUAL", persona=None):
    """
    Fetches local news via RSS. 
    Styles: 'CASUAL' (Tea/Gossip) or 'SERIOUS' (Briefing).
    Now supports Deep Persona Injection and URGENCY FILTER.
    """
    try:
        # 1. Fetch RSS (Google News)
        # Fallback to 'India' if no location
        raw_query = location if location else "India"
        query = urllib.parse.quote(raw_query)
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        feed = feedparser.parse(rss_url)
        
        # [FALLBACK] If local/specific news is dry, fetch broad 'India' news
        if not feed.entries:
             logger.info(f"News: No entries for '{query}'. Trying fallback 'India'.")
             fallback_url = "https://news.google.com/rss/search?q=India&hl=en-IN&gl=IN&ceid=IN:en"
             feed = feedparser.parse(fallback_url)

        if not feed.entries:
            return "No news found. The world is quiet. 🌍" if style=="SERIOUS" else "Bestie, the news is dry today 🌵"
            
        # 2. Pick Top Stories (Fetch more to filter)
        stories = feed.entries[:7] 
        headlines = [f"- {s.title}" for s in stories]
        headlines_str = "\n".join(headlines)
        
        # 3. AI Rewrite 
        if ai_generator:
            # Construct dynamic instruction based on Persona
            persona_instr = ""
            if persona:
                persona_instr = f"CURRENT MOOD: {persona.get('prefix', '')} \nSTYLE GUIDE: {persona.get('instruction', '')}"
            
            if style == "SERIOUS":
                 prompt = (
                    f"Summarize these headlines professionally.\n"
                    f"{persona_instr}\n"
                    f"Headlines:\n{headlines_str}\n\n"
                    f"Rules:\n"
                    f"- PRIORITIZE URGENT EVENTS (War, Disasters, Attacks) FIRST.\n"
                    f"- Professional, concise tone.\n"
                    f"- header: '📰 **Briefing for {location}**'\n"
                 )
            else:
                 # Gen Z / Casual Mode
                 prompt = (
                    f"Rewrite these news headlines based on your current Persona.\n"
                    f"{persona_instr}\n"
                    f"Headlines:\n{headlines_str}\n\n"
                    f"CRITICAL RULE: Check for MAJOR GLOBAL/LOCAL EMERGENCIES (War, Earthquakes, riots). If found, DROP the slang and be SERIOUS/WARNING.\n"
                    f"OTHERWISE (Normal News):\n"
                    f"- Use Gen Z slang (no cap, slay, wild, tea, bestie).\n"
                    f"- Gossip tone: 'Did you hear...', 'Omg...'.\n"
                    f"- Keep it under 100 words.\n"
                    f"- Format: '☕ **Tea Time ({location})** ☕\n...'\n"
                )
                
            response = await ai_generator(prompt, tier=tier)
            return response
        else:
            return f"📰 **News (Raw)**:\n{headlines_str[:300]}..."

    except Exception as e:
        logger.error(f"News Error: {e}")
        return "News system offline."

# ==========================================
# 2. WEATHER (Open-Meteo)
# ==========================================
def get_weather(location_coords):
    """
    Fetches weather from Open-Meteo.
    Requires (lat, lon) tuple.
    """
    if not location_coords:
        return "I need your location to check the vibes outside! 📍"
        
    lat, lon = location_coords
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        current = data.get("current_weather", {})
        
        temp = current.get("temperature")
        code = current.get("weathercode")
        
        # WMO Weather Codes to Emojis
        # 0=Clear, 1-3=Cloudy, 50-60=Rain, 95=Storm
        cond = "Sunny ☀️"
        if code > 3: cond = "Cloudy ☁️"
        if code >= 50: cond = "Raining 🌧️"
        if code >= 95: cond = "Stormy ⛈️"
        
        # Gen Z Comment
        comment = "Perfect weather for a slay day!"
        if temp > 35: comment = "It's literally boiling, don't forget SPF! 🥵"
        if temp < 15: comment = "Sweater weather vibes! 🥶"
        if "Rain" in cond: comment = "Mood: LoFi & Chill. ☔"
        if "Storm" in cond: comment = "Stay inside bestie, it's wild out there! 🌪️"
        
        return f"🌡️ **{temp}°C & {cond}**\n{comment}"
        
    except Exception as e:
        logger.error(f"Weather Error: {e}")
        return "Clouds are hiding the data. ☁️"

# ==========================================
# 3. FINANCE (Yahoo Finance)
# ==========================================
def get_stock_price(symbol):
    """
    Fetches live price using yfinance.
    Symbol must be valid (e.g. RELIANCE.NS, BTC-USD).
    """
    # Quick Map for common terms
    symbol = symbol.upper().replace(" PRICE", "").strip()
    
    # Common Crypto
    if "BITCOIN" in symbol: symbol = "BTC-USD"
    if "ETHEREUM" in symbol: symbol = "ETH-USD"
    if "DOGE" in symbol: symbol = "DOGE-USD"
    
    # Indian Stocks (Default .NS if missing)
    # Heuristic: If it looks like an Indian company name, append .NS
    indian_companies = ["RELIANCE", "TATA", "ZOMATO", "HDFC", "ICICI", "INFY", "WIPRO", "ADANI"]
    if any(x in symbol for x in indian_companies) and ".NS" not in symbol and ".BO" not in symbol:
        symbol += ".NS"
        
    if "TATA" in symbol and "MOTORS" not in symbol and "POWER" not in symbol and "STEEL" not in symbol:
         # Ambiguous 'Tata', default to Motors or Power? User asked for Tata Power in prompt.
         # Let's just append .NS and hope, or if it says TATA POWER it becomes TATA POWER.NS which needs underscore?
         # Yahoo expects 'TATAPOWER.NS' usually.
         symbol = symbol.replace(" ", "") # Remove spaces for ticker

    try:
        ticker = yf.Ticker(symbol)
        
        # Try Fast Info
        price = None
        try:
            price = ticker.fast_info.last_price
        except: pass
        
        # Fallback to History
        if not price or str(price) == "nan":
             hist = ticker.history(period="1d")
             if not hist.empty:
                 price = hist["Close"].iloc[-1]
        
        if not price or str(price) == "nan":
            return f"Couldn't find price for {symbol}. Try specific ticker like 'RELIANCE.NS'"
            
        emoji = "📈" 
        return f"💰 **{symbol}**: ₹{price:,.2f} {emoji}\nStonks or not? You decide. 🚀"
        
    except Exception as e:
        logger.error(f"Finance Error: {e}")
        return f"Market is ghosting me on {symbol}. 👻"
