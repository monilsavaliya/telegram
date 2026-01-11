import requests
import json

# Keys to test
API_KEYS = [
    "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs",
    "AIzaSyAtG1fj_q-HNSp_uAx6oIElLI_WBJOHdj4",
    "AIzaSyDkb8tPcIXB7doW5OWjK79EavoMtSE9PgI",
    "AIzaSyCjEHzb76TcQx3M5sQMRura_92gJAU1pGY",
    "AIzaSyAyLunolTuQcSLLFD3O43--Cr-DgG1b0Gc",
    "AIzaSyAKCSUEFr1qIw5QbricBExhhcuQ812vJHc",
    "AIzaSyDNEV7rSU-R4AshKw1S65FaUCIWnkYOssk",
]

# Test with gemini-2.0-flash-exp (experimental model)
MODEL = "gemini-2.0-flash-exp"

print(f"Testing {len(API_KEYS)} keys with model: {MODEL}")
print("=" * 80)

for idx, key in enumerate(API_KEYS, 1):
    key_short = f"...{key[-6:]}"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": "Say hello in one word"}]
        }]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        status = response.status_code
        
        if status == 200:
            data = response.json()
            if "candidates" in data and data["candidates"]:
                reply = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Key {idx} {key_short}: ✅ SUCCESS - Reply: {reply.strip()}")
            else:
                print(f"Key {idx} {key_short}: ⚠️  200 OK but no reply")
        elif status == 429:
            print(f"Key {idx} {key_short}: ⚠️  RATE LIMITED (429) - Key works but quota exceeded")
        elif status == 404:
            print(f"Key {idx} {key_short}: ❌ NOT FOUND (404) - Model not accessible")
        elif status == 403:
            print(f"Key {idx} {key_short}: ❌ FORBIDDEN (403) - Invalid or expired key")
        else:
            print(f"Key {idx} {key_short}: ❌ ERROR ({status}) - {response.text[:100]}")
            
    except Exception as e:
        print(f"Key {idx} {key_short}: ❌ EXCEPTION - {str(e)[:80]}")

print("=" * 80)
print("\nTest complete!")
