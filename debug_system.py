import os
import asyncio
from dotenv import load_dotenv
import httpx
from groq import Groq

load_dotenv()

# 1. Check Key Counts
groq_keys = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]
gemini_keys = [k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k.strip()]

print(f"DTO: Loaded {len(groq_keys)} Groq Keys.")
print(f"DTO: Loaded {len(gemini_keys)} Gemini Keys.")

# 2. Test Groq
print("\n--- TEST GROQ ---")
if groq_keys:
    try:
        client = Groq(api_key=groq_keys[0])
        print("Sending request to Groq...")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": "Explain 42"}],
            model="llama-3.3-70b-versatile",
        )
        print("✅ Groq Success:", chat_completion.choices[0].message.content[:50])
    except Exception as e:
        print("❌ Groq Failed:", e)
else:
    print("❌ No Groq Keys found.")

# 3. Test Gemini
print("\n--- TEST GEMINI ---")
if gemini_keys:
    async def test_gemini():
        key = gemini_keys[0]
        # Trying explicit 001 model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-001:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            print(f"Gemini Status: {resp.status_code}")
            if resp.status_code == 200:
                 print("✅ Gemini Success:", resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")[:50])
            else:
                 print("❌ Gemini Failed:", resp.text)
    
    asyncio.run(test_gemini())
else:
    print("❌ No Gemini Keys found.")
