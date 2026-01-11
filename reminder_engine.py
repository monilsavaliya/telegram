import dateparser
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def parse_reminder(text: str):
    """
    Parses natural language text to find a future datetime.
    Returns (datetime_object, clean_message) or (None, None).
    """
    # 1. Clean text to help dateparser
    # remove "remind me to", "wake me up at", etc.
    # checking for common prefixes
    triggers = ["remind me to", "remind me", "wake me up at", "wake up at", "text me at", "ping me at", "alarm at"]
    
    context_text = text.lower()
    
    # 1.5 Hinglish Pre-processing
    intent_map = {
        " ke bad": "", # Remove suffix, we will prepend 'in' if needed
        " bad me": "",
        " yad dilana": "",
        " uthana": "", 
        " msg krna": ""
    }
    for k, v in intent_map.items():
        time_str = time_str.replace(k, v)
        
    for t in triggers:
        if t in time_str:
            time_str = time_str.replace(t, "").strip()
            
    # 2. Try Regex First (Fast & Accurate for "2 mins")
    import re
    # Match: "2 min", "10 minutes", "1 hour"
    regex = r"(\d+)\s*(m|min|minute|h|hr|hour|d|day)s?"
    match = re.search(regex, time_str)
    
    dt = None
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        
        now = datetime.now()
        if unit in ['m', 'min', 'minute']:
            dt = now + timedelta(minutes=val)
        elif unit in ['h', 'hr', 'hour']:
            dt = now + timedelta(hours=val)
        elif unit in ['d', 'day']:
            dt = now + timedelta(days=val)
            
    # 3. Fallback to Dateparser
    if not dt:
        settings = {
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now()  
        }
        dt = dateparser.parse(time_str, settings=settings)
    
    if not dt and "in " not in time_str and re.match(r"\d", time_str):
        # Try prepending "in" for simple numbers like "20 min"
        dt = dateparser.parse(f"in {time_str}", settings=settings)
    
    if not dt:
        return None, None
        
    # Ensure it's in the future
    if dt < datetime.now():
        dt += timedelta(days=1)
        
    # Clean Message Logic...
    clean_msg = text
    for t in triggers:
        clean_msg = clean_msg.replace(t, "")
        
    # Remove Hinglish artifacts from note
    for k in [ "ke bad", "bad me", "yad dilana", "uthana"]:
         clean_msg = clean_msg.replace(k, "")
         
    return dt, clean_msg.strip() or "Here is your reminder! ⏰"
