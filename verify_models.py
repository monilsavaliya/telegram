import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

KEYS = [k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k.strip()]
if not KEYS:
    print("❌ No Gemini Keys found in .env")
    exit(1)

KEY = KEYS[0] # Test with first key

async def test_generation():
    # Explicitly testing the model found in the list
    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}"
    print(f"\n🧪 Testing Generation: {model} ...")
    
    payload = {
        "contents": [{"parts": [{"text": "Explain quantum physics in 5 words."}]}]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                print(f"   ✅ SUCCESS! Output: {resp.json()['candidates'][0]['content']['parts'][0]['text']}")
            else:
                print(f"   ❌ FAILED. Status: {resp.status_code} | {resp.text}")
    except Exception as e:
        print(f"   ⚠️ Exception: {e}")

async def main():
    await test_generation()

if __name__ == "__main__":
    asyncio.run(main())
