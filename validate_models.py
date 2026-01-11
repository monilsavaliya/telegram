import asyncio
import httpx
import time

API_KEYS = [
    "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs",
    "AIzaSyAtG1fj_q-HNSp_uAx6oIElLI_WBJOHdj4",
    "AIzaSyDkb8tPcIXB7doW5OWjK79EavoMtSE9PgI",
    "AIzaSyCjEHzb76TcQx3M5sQMRura_92gJAU1pGY",
    "AIzaSyAyLunolTuQcSLLFD3O43--Cr-DgG1b0Gc",
    "AIzaSyCjEHzb76TcQx3M5sQMRura_92gJAU1pGY",
    "AIzaSyAKCSUEFr1qIw5QbricBExhhcuQ812vJHc",
    "AIzaSyDNEV7rSU-R4AshKw1S65FaUCIWnkYOssk",
    "AIzaSyDkb8tPcIXB7doW5OWjK79EavoMtSE9PgI",
]

MODELS_TO_TEST = [
    'gemini-2.0-flash-exp', # Correct name for 2.0
    'gemini-1.5-flash',
    'gemini-1.5-pro',
    'gemini-1.0-pro'
]

async def test_key(key, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                return "✅"
            elif resp.status_code == 404:
                return "❌ (404)"
            elif resp.status_code == 429:
                return "⚠️ (429)"
            else:
                return f"❌ ({resp.status_code})"
        except Exception as e:
            return "ERR"

async def main():
    print(f"{'KEY':<10} | " + " | ".join([f"{m:<15}" for m in MODELS_TO_TEST]))
    print("-" * 100)
    
    for key in API_KEYS:
        results = []
        for model in MODELS_TO_TEST:
            res = await test_key(key, model)
            results.append(f"{res:<15}")
        
        key_masked = f"...{key[-4:]}"
        print(f"{key_masked:<10} | " + " | ".join(results))

if __name__ == "__main__":
    asyncio.run(main())
