
import asyncio
from main import process_uber_request, process_tmdb_request

async def test_merged_ui():
    print("🔮 --- TESTING FUTURE-READY MERGED UI ---")
    
    # 1. Test Uber Merge
    print("\n[TEST 1] Uber Card + Context")
    ctx = "Sir, your chariot awaits."
    html_uber = await process_uber_request("Cyber Hub", chat_context=ctx)
    
    if f'<div class="card-context-text">{ctx}</div>' in html_uber:
        print("✅ PASS: Uber Card correctly merged with AI text.")
    else:
        print("❌ FAIL: Uber Card missing context.")

    # 2. Test TMDB Merge
    print("\n[TEST 2] TMDB Card + Context")
    ctx_movie = "This movie will blow your mind."
    html_movie = await process_tmdb_request("Interstellar", chat_context=ctx_movie)
    
    if f'<div class="card-context-text">{ctx_movie}</div>' in html_movie:
        print("✅ PASS: Movie Card correctly merged with AI text.")
    else:
        print("❌ FAIL: Movie Card missing context.")

    print("\n-------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_merged_ui())
