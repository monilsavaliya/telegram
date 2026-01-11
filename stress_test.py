import asyncio
import time
import logging

# Configure logging to suppress noisy output during test
logging.basicConfig(level=logging.ERROR)

from telegram_main import generate_ai_response, RESPONSE_CACHE

async def run_stress_test():
    print("🚀 Starting Phase 5 Stress Test...")
    print("-----------------------------------")
    
    prompt = "Explain Quantum Computing in 1 sentence."
    
    # 1. Cold Request (API Call)
    print("1️⃣ Sending Cold Request (API - Groq)...")
    start = time.time()
    res1 = await generate_ai_response(prompt, tier="lightning")
    t1 = time.time() - start
    print(f"   ⏱️ Time: {t1:.4f}s")
    print(f"   📝 Output: {res1}")
    
    # 2. Hot Request (Cache Hit)
    print("\n2️⃣ Sending Hot Request (Cache)...")
    start = time.time()
    res2 = await generate_ai_response(prompt, tier="lightning")
    t2 = time.time() - start
    print(f"   ⏱️ Time: {t2:.4f}s")
    print(f"   📝 Output: {res2}")
    
    # 3. Verification
    print("\n-----------------------------------")
    if res1 == res2:
        print("✅ Consistency Check: PASS (Outputs match)")
    else:
        print("❌ Consistency Check: FAIL")
        
    if t2 < 0.1:
        print(f"✅ Latency Check: PASS (Cache Time {t2:.4f}s < 0.1s)")
        print("✅ Optimization: Cache is working perfectly.")
    else:
        print(f"❌ Latency Check: FAIL (Cache Time {t2:.4f}s)")
        print("⚠️ Cache might not be engaging.")

    print(f"\n📊 Cache Stats: {len(RESPONSE_CACHE)} items stored.")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
