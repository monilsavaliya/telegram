
import asyncio
import re
from main import process_tmdb_request, process_uber_request

# MOCK AI RESPONSE (What Gemini WOULD say now)
# We test if the webhook logic handles this correctly
mock_ai_movie_reply = "Interstellar is a masterpiece! 🌌 ||TMDB:Interstellar||"
mock_ai_uber_reply = "Cab coming up! 🚖 ||UBER:Cyber City||"

async def test_chatx_simulation():
    print("🚀 --- CHATX FULL SIMULATION ---")
    
    # TEST 1: MOVIE FLOW (Refusal Check + Merge Check)
    print("\n[SCENARIO 1] User asks: 'Best sci-fi movie?'")
    print(f"AI Says: '{mock_ai_movie_reply}'")
    
    # Parse like Webhook
    if "||TMDB:" in mock_ai_movie_reply:
        match = re.search(r"\|\|TMDB:(.*?)\|\|", mock_ai_movie_reply)
        query = match.group(1)
        text_part = mock_ai_movie_reply.replace(match.group(0), "").strip()
        
        print(f"Parsing... Query='{query}', Text='{text_part}'")
        
        # Generate Card
        html = await process_tmdb_request(query, chat_context=text_part)
        
        # VERIFY
        if f'<div class="card-context-text">{text_part}</div>' in html:
            print("✅ PASS: UI Merged (Text is inside Card).")
        else:
            print("❌ FAIL: UI Split! Text not found in HTML.")
            
        if "Interstellar" in html and "Christopher Nolan" in html:
            print("✅ PASS: TMDB API Valid.")
        else:
             print("❌ FAIL: TMDB API Error.")

    # TEST 2: UBER FLOW (Dynamic Link + Merge Check)
    print("\n[SCENARIO 2] User asks: 'Cab to Cyber City'")
    print(f"AI Says: '{mock_ai_uber_reply}'")
    
    if "||UBER:" in mock_ai_uber_reply:
        match = re.search(r"\|\|UBER:(.*?)\|\|", mock_ai_uber_reply)
        dest = match.group(1)
        text_part = mock_ai_uber_reply.replace(match.group(0), "").strip()
        
        # Simulate User Location (GPS Shared)
        user_coords = (28.4595, 77.0266) # Gurgaon
        
        # Generate Card
        html = await process_uber_request(dest, user_coords, chat_context=text_part)
        
        # VERIFY
        if f'<div class="card-context-text">{text_part}</div>' in html:
            print("✅ PASS: UI Merged (Text is inside Card).")
        else:
            print("❌ FAIL: UI Split! Text not found in HTML.")
            
        if "pickup[latitude]=28.4595" in html:
            print("✅ PASS: Dynamic GPS Injection Verified.")
        else:
             print("❌ FAIL: Deep Link Logic Broken.")

    print("\n-------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_chatx_simulation())
