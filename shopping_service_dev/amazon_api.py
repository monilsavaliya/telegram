import requests
import urllib.parse
import json
import os

class AmazonAPI:
    def __init__(self):
        self.api_key = os.getenv("RAPID_AMAZON_KEY", "YOUR_RAPID_API_KEY")
        self.host = "real-time-amazon-data.p.rapidapi.com"
        self.base_url = "https://real-time-amazon-data.p.rapidapi.com"

    def search_products(self, query, country="IN", page=1, sort_by="RELEVANCE"):
        """
        Fetches product search results from Amazon via RapidAPI.
        """
        url = f"{self.base_url}/search"
        
        querystring = {
            "query": query,
            "page": str(page),
            "country": country,
            "sort_by": sort_by
        }

        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.host
        }

        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("products", [])
            else:
                print(f"Amazon API Error {response.status_code}: {response.text}")
                return []
        except Exception as e:
            print(f"Amazon API Exception: {e}")
            return []

    def get_product_details(self, asin, country="IN"):
        """
        Fetches detailed info for a specific ASIN.
        """
        url = f"{self.base_url}/product-details"
        querystring = {"asin": asin, "country": country}
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.host
        }
        
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", {})
            return None
        except Exception:
            return None
