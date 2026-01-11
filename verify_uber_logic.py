
import asyncio
from main import process_uber_request

async def test_uber_logic():
    print("🧪 --- TESTING UBER DEEP LINK LOGIC ---")
    
    # CASE 1: No Coordinates (Default User)
    print("\n[CASE 1] User Location UNKNOWN (No Coords)")
    print("Expected: Link should contain 'pickup=my_location'")
    card_html_1 = await process_uber_request("India Gate", user_coords=None)
    
    if "pickup=my_location" in card_html_1:
        print("✅ PASS: Correctly defaulted to Auto-Detect.")
    else:
        print("❌ FAIL: Did not find 'pickup=my_location'")
        
    if "pickup[latitude]" in card_html_1:
        print("❌ FAIL: Found specific coords when none were given!")
    else:
        print("✅ PASS: No leakage of fake coordinates.")

    # CASE 2: With Coordinates (Shared Location)
    print("\n[CASE 2] User Location KNOWN (Lat: 28.123, Long: 77.123)")
    print("Expected: Link should contain 'pickup[latitude]=28.123'")
    card_html_2 = await process_uber_request("India Gate", user_coords=(28.123, 77.123))
    
    if "pickup[latitude]=28.123" in card_html_2:
        print("✅ PASS: Correctly injected User Coordinates.")
    else:
        print("❌ FAIL: Did not find injected coordinates.")
        
    if "pickup=my_location" in card_html_2:
        print("❌ FAIL: Still defaulting to 'my_location' despite having coords!")
    else:
        print("✅ PASS: Correctly removed auto-detect.")

    print("\n-------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_uber_logic())
