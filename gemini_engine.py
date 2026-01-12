import httpx
import base64
import logging
import asyncio

# Configure Logger
logger = logging.getLogger(__name__)

# CONSTANTS
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

async def generate_gemini_text(prompt, key, model="gemini-1.5-flash"):
    """
    Pure REST Text Generation.
    Includes Auto-Downgrade for 404s (Model Not Found).
    """
    url = f"{BASE_URL}/{model}:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800
        }
    }
    
    # [DEBUG] Log Request Details
    logger.info(f"🚀 Sending Gemini Request: Model={model}, PromptLen={len(prompt)}")
    # logger.debug(f"Payload: {json.dumps(payload)}") # Uncomment for full payload dump
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
            
            # [Smart Fallback] If 404 (Model Not Found), try 1.5-flash
            if resp.status_code == 404:
                logger.warning(f"⚠️ Model {model} not found (404). Attempting fallback to gemini-1.5-flash.")
                fallback_url = f"{BASE_URL}/gemini-1.5-flash:generateContent?key={key}"
                resp = await client.post(fallback_url, json=payload, headers=headers, timeout=15.0)

            # Check for non-200 status after potential fallback
            if resp.status_code != 200:
                logger.error(f"Gemini REST Error ({resp.status_code}): {resp.text}")
                return None

            data = resp.json()
            
            # Safety checks for response structure
            if "candidates" in data and len(data["candidates"]) > 0:
                content = data["candidates"][0].get("content")
                if content and "parts" in content:
                    return content["parts"][0]["text"].strip()
            
            logger.warning(f"Gemini response valid but contained no text: {data}")
            return None
            
    except httpx.RequestError as e:
        logger.error(f"Gemini Network Exception: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini General Exception: {e}")
        return None

async def generate_gemini_vision(prompt, image_bytes, key, model="gemini-2.5-flash", mime_type="image/jpeg"):
    """
    Pure REST Vision Generation.
    Supports dynamic mime_type (image/png, image/jpeg, image/webp).
    """
    url = f"{BASE_URL}/{model}:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    
    # Base64 Encode
    try:
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to encode image bytes: {e}")
        return None
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": b64_img
                    }
                }
            ]
        }]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
            
            if resp.status_code != 200:
                logger.error(f"Gemini Vision REST Error ({resp.status_code}): {resp.text}")
                return None

            data = resp.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                content = data["candidates"][0].get("content")
                if content and "parts" in content:
                    return content["parts"][0]["text"].strip()
            
            return None
            
    except Exception as e:
        logger.error(f"Gemini Vision Exception: {e}")
        return None
