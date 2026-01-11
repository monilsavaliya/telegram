import requests
import json

URL = "https://graph.facebook.com/v22.0/962494863608565/messages"
TOKEN = "EAAMue6D2d3sBQWCZAHisZBYTHhmAkRuVU6t6zZAgKOvxBSzl9jaehrST1ksZCZAkDTsyKh1GDEx00S9QQD2vAVgILeBujZCZBpqYf3PZAzZBNwP0L8vqVcUOUnPvZBCuC3ZB8aJO210ZApNvTQkGpmGMCorg7ZADNJXGN8Ss9AZCDpZAvkNA5AUmvDWzy2DSw45jqMDjNWRste7hQb2ahLlJCl3464ZC4NBerMTA5ayo432jspt47rXhXnNCEZBZB0XAKmyQ2nbHhUrP08fHZCHvkldcbSEluJVLsXWphmV"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": "919328552413",
    "type": "template",
    "template": {
        "name": "jaspers_market_plain_text_v1",
        "language": {
            "code": "en_US"
        }
    }
}

try:
    print(f"Sending to {URL}...")
    response = requests.post(URL, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
