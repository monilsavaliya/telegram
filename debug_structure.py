
import requests
import json

def debug_structure():
    print("🔍 Inspecting Data Structure...")
    RAPID_KEY = "e4f1b7dd57msh696dd83ac691748p1e205cjsnc9400622fd1e"
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    querystring = {"query": "iphone", "page": "1", "country": "US", "sort_by": "RELEVANCE"}
    headers = {
        "x-rapidapi-key": RAPID_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=querystring)
        data = res.json()
        
        if 'data' in data:
            d = data['data']
            print(f"Type of data['data']: {type(d)}")
            if isinstance(d, dict):
                print(f"Keys in data['data']: {d.keys()}")
            elif isinstance(d, list):
                print(f"Length of data['data']: {len(d)}")
                if len(d) > 0:
                    print(f"First item keys: {d[0].keys()}")
        else:
            print("No 'data' key found.")
            print(f"Top level keys: {data.keys()}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_structure()
