import httpx
import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# Global Client (Singleton)
_client: httpx.AsyncClient = None

def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=10.0,
            headers={
                "User-Agent": "Jarvis-Bot/2.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json"
            }
        )
    return _client

async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()

async def safe_get(url: str, params: dict = None, headers: dict = None, retries: int = 1) -> dict:
    """Robust GET request (Fail Fast)."""
    client = get_client()
    merged_headers = client.headers.copy()
    if headers:
        merged_headers.update(headers)
        
    try:
        resp = await client.get(url, params=params, headers=merged_headers)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"⚠️ Network Warning: {e}")
        return None

import time

class KeyManager:
    def __init__(self, api_keys):
        self.keys = api_keys
        self.index = 0
        self.cooldowns = {} # key -> timestamp_when_available
        self.dead_keys = set()

    def get_next_key(self):
        """Returns the next healthy API Key (Round Robin)."""
        start_index = self.index
        now = time.time()
        
        while True:
            current_key = self.keys[self.index]
            self.index = (self.index + 1) % len(self.keys)
            
            # Check availability
            if current_key in self.dead_keys:
                if self.index == start_index: return None # All dead
                continue
                
            if current_key in self.cooldowns:
                if now < self.cooldowns[current_key]:
                    # Still cooling down
                    if self.index == start_index: 
                        # We cycled through ALL keys and everyone is cooling down.
                        # Wait for the one with earliest expiry?
                        # For now, just return None or wait.
                        return None
                    continue
                else:
                    # Cooldown over
                    del self.cooldowns[current_key]
            
            return current_key

    def report_status(self, key, status_code):
        """Updates health of a key based on response code."""
        if status_code in [429]: # Rate Limit -> Cool Down
            print(f"⚠️ Key Rate Limited (429). Cooling down for 2 mins.")
            self.cooldowns[key] = time.time() + 120 # 2 Minutes
            
        elif status_code in [400, 403]: # Invalid Key -> Kill
            print(f"❌ Key Invalid ({status_code}). Removing.")
            self.dead_keys.add(key)

async def safe_post(url: str, json_data: dict, headers: dict = None, timeout: float = 10.0) -> dict:
    """Robust POST request (Fail Fast)."""
    client = get_client()
    merged_headers = client.headers.copy()
    if headers:
        merged_headers.update(headers)
        
    try:
        resp = await client.post(url, json=json_data, headers=merged_headers, timeout=timeout)
        return {"status": resp.status_code, "data": resp.json() if resp.status_code != 204 else {}, "text": resp.text}
    except Exception as e:
        logger.error(f"❌ POST Failed: {e}")
        return {"status": 500, "error": str(e)}

async def download_media_bytes(url: str, headers: dict = None) -> bytes:
    """Downloads binary content (images/audio)."""
    client = get_client()
    merged_headers = client.headers.copy()
    if headers:
        merged_headers.update(headers)
    
    try:
        resp = await client.get(url, headers=merged_headers, timeout=20.0)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.error(f"❌ Download Failed: {e}")
        return None

async def get_whatsapp_media_url(media_id: str, token: str) -> str:
    """Fetches the temporary URL for a WhatsApp Media ID."""
    url = f"https://graph.facebook.com/v17.0/{media_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        data = await safe_get(url, headers=headers)
        if data and "url" in data:
            return data["url"]
        return None
    except Exception as e:
        logger.error(f"❌ Media URL Fetch Failed: {e}")
        return None

async def upload_media_to_whatsapp(file_path: str, mime_type: str, phone_id: str, token: str) -> str:
    """
    Uploads a file to WhatsApp and returns the Media ID.
    """
    url = f"https://graph.facebook.com/v17.0/{phone_id}/media"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        files = {
            'file': (file_path.split('/')[-1], open(file_path, 'rb'), mime_type),
            'type': (None, mime_type),
            'messaging_product': (None, 'whatsapp')
        }
        
        # We need a synchronous post for file handles with httpx usually, OR async with weird streaming.
        # But httpx.AsyncClient().post(files=...) works.
        # However, opening file in async function is blocking. 
        # For prototype, it's fine. In prod, use aiofiles.
        
        client = get_client()
        # Note: requests.post style 'files' kwarg works in httpx too
        resp = await client.post(url, headers=headers, files=files, timeout=30.0)
        resp.raise_for_status()
        
        data = resp.json()
        return data.get("id")
        
    except Exception as e:
        logger.error(f"❌ Media Upload Failed: {e}")
        return None
