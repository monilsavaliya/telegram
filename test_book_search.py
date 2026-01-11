import asyncio
import httpx
import urllib.parse
import traceback

async def test_search():
    query = "Atomic Habits"
    url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(query)}"
    headers = {"User-Agent": "JarvisTelegramBot/1.0 (Educational)"}
    
    print(f"🔍 Testing Book Search for '{query}'...")
    print(f"🌐 URL: {url}")
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # Retry Logic (Simulation of the fix)
            for attempt in range(2):
                try:
                    print(f"⏳ Attempt {attempt+1}/2...")
                    resp = await client.get(url, headers=headers, timeout=30.0)
                    resp.raise_for_status()
                    print("✅ Connection Successful!")
                    break 
                except Exception as e:
                    print(f"⚠️ Attempt {attempt+1} Failed: {e}")
                    if attempt == 1: raise
                    await asyncio.sleep(1)
            
            data = resp.json()
            docs = data.get("docs", [])[:3]
            if docs:
                print(f"📚 Found {len(docs)} books!")
                print(f"📖 Top Result: {docs[0].get('title')} by {docs[0].get('author_name', ['Unknown'])[0]}")
                print("✅ **ISSUE SORTED.** The API is reachable with the new settings.")
            else:
                print("❌ No results found, but connection worked.")
                
        except Exception as e:
            print(f"❌ **TEST FAILED**: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_search())
