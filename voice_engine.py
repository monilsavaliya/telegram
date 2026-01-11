import logging
import os
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Try importing gTTS, fallback if missing
try:
    from gtts import gTTS
    HAS_TTS = True
except ImportError:
    HAS_TTS = False
    logger.warning("⚠️ gTTS not installed. Voice features disabled.")

async def generate_audio_note(text, lang='en', slow=False):
    """
    Generates an MP3 audio note from text.
    Returns: (path_to_file, duration_seconds) or None
    """
    if not HAS_TTS:
        return None
        
    try:
        # Create 'voice_notes' dir if needed
        output_dir = "static/voice_notes"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"voice_{int(datetime.now().timestamp())}.mp3"
        filepath = os.path.join(output_dir, filename)
        
        # Sync run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save_gtts, text, lang, slow, filepath)
        
        return filepath
    except Exception as e:
        logger.error(f"Voice Gen Failed: {e}")
        return None

def _save_gtts(text, lang, slow, filepath):
    tts = gTTS(text=text, lang=lang, slow=slow)
    tts.save(filepath)
