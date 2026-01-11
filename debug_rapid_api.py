
import requests
import json

def test_rapid_api():
    print("🔍 Testing RapidAPI Amazon Data...")
    
    RAPID_KEY = "e4f1b7dd57msh696dd83ac691748p1e205cjsnc9400622fd1e"
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    querystring = {"query": "iphone", "page": "1", "country": "US", "sort_by": "RELEVANCE"}
    headers = {
        "x-rapidapi-key": RAPID_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        print(f"Status Code: {response.status_code}")
        
        data = response.json()
        print("\nJSON Response Keys:", data.keys())
        
        # Dump partial JSON to see structure
        print(json.dumps(data, indent=2)[:1000]) 
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_rapid_api()
