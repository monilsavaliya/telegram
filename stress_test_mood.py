import re

def test_mood_parser():
    print("🧪 Testing Mood Parser...")
    
    # 1. Simulate AI Response with Mood Tag
    ai_reply = "Bro, tension mat le. [SEARCH: relaxing music]"
    print(f"📥 AI Output: '{ai_reply}'")
    
    # 2. Parse Logic (Copied from telegram_main.py)
    search_tag = None
    if "[SEARCH:" in ai_reply:
        match = re.search(r'\[SEARCH:\s*(.*?)\]', ai_reply)
        if match:
            search_tag = match.group(1)
            ai_reply = ai_reply.replace(match.group(0), "").strip()
            
    # 3. Assertions
    if search_tag == "relaxing music":
        print(f"✅ Tag Extracted: '{search_tag}'")
    else:
        print(f"❌ Failed to extract tag. Got: {search_tag}")
        
    if "[SEARCH" not in ai_reply:
        print(f"✅ Cleaned Text: '{ai_reply}'")
    else:
        print(f"❌ Text still has tag: '{ai_reply}'")

if __name__ == "__main__":
    test_mood_parser()
