
import asyncio
from main import process_tmdb_request

async def test_tmdb():
    print("🎬 --- TESTING TMDB LOGIC ---")
    
    query = "Inception"
    print(f"Searching for: {query}...")
    
    html = await process_tmdb_request(query)
    
    if "Inception" in html and "Christopher Nolan" in html or "Inception" in html:
        print("✅ PASS: Found 'Inception' in output.")
    else:
        print(f"❌ FAIL: Output was: {html[:100]}...")

    if "background-image: url('https://image.tmdb.org" in html:
        print("✅ PASS: Poster URL found.")
    else:
        print("❌ FAIL: No poster URL.")
        
    print("\n-------------------------")

if __name__ == "__main__":
    asyncio.run(test_tmdb())
