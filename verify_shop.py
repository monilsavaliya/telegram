
import asyncio
from main import process_amazon_request

async def test_shopping_flow():
    print("🛒 --- VERIFYING AMAZON SHOPPING ---")
    
    query = "Wireless Headphones"
    chat_context = "Here are some great headphones for you! 🎧"
    
    print(f"\n[TEST] Searching for: '{query}'")
    html = await process_amazon_request(query, chat_context=chat_context)
    print(f"[DEBUG] Raw Output: {html[:300]}...") # Print first 300 chars
    
    # 1. Check for Merged UI
    if f'<div class="card-context-text">{chat_context}</div>' in html:
        print("✅ PASS: UI Merged (Text + Card).")
    else:
        print("❌ FAIL: UI Split! Text missing from card.")

    # 2. Check for Affiliate Tag
    target_tag = "tag=shopsy05-21"
    if target_tag in html:
        print(f"✅ PASS: Affiliate Tag '{target_tag}' found in Buy Link.")
    else:
        print(f"❌ FAIL: Affiliate Tag missing from HTML.")
        
    # 3. Check for Product Data
    if "product-card" in html and "shopsy05-21" in html:
         print("✅ PASS: Product Card HTML generated successfully.")
    else:
         print("❌ FAIL: Product Card HTML is malformed.")
         
    print("\n-------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_shopping_flow())
