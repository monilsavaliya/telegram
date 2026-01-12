import requests
import json
import os

# User's Key
UBER_SERVER_TOKEN = os.getenv("UBER_SERVER_TOKEN", "YOUR_KEY_HERE")

# Dummy Coordinates (New Delhi)
# Start: IIT Delhi, End: Connaught Place
start_lat, start_lng = 28.5438, 77.1906
end_lat, end_lng = 28.6304, 77.2177

url = f"https://api.uber.com/v1.2/estimates/price?start_latitude={start_lat}&start_longitude={start_lng}&end_latitude={end_lat}&end_longitude={end_lng}"

headers = {
    'Authorization': f'Token {UBER_SERVER_TOKEN}',
    'Accept-Language': 'en_US',
    'Content-Type': 'application/json'
}

print(f"🔍 Testing Uber API Key: {UBER_SERVER_TOKEN[:5]}...")
print(f"📡 Endpoint: {url}")

try:
    response = requests.get(url, headers=headers)
    
    print(f"\n✅ Status Code: {response.status_code}")
    print("📄 Response Content:")
    
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
        
        if response.status_code == 200:
            print("\n🎉 SUCCESS: Key is Valid! estimates received.")
        else:
            print("\n❌ API Error: Key might be invalid or lacks 'estimates' scope.")
            
    except Exception as e:
        print(f"Raw Text: {response.text}")

except Exception as e:
    print(f"❌ Connection Error: {e}")
