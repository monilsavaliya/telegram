import requests
import json

url = "http://localhost:8000/simulate/send"
payload = {
    "object": "whatsapp_business_account",
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "919328552413",
                    "id": "wamid.test_local",
                    "timestamp": 12345678,
                    "type": "text",
                    "text": {"body": "hauz khas to rajiv chowk"}
                }]
            }
        }]
    }]
}

try:
    print(f"Sending to {url}...")
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")
except Exception as e:
    print(f"Error: {e}")
