import time
import threading
import logging
import asyncio

logger = logging.getLogger(__name__)

try:
    import pyperclip
except ImportError:
    logger.warning("pyperclip not found. Install via 'pip install pyperclip'. Clipboard Spy disabled.")
    pyperclip = None

class ClipboardSpy:
    def __init__(self, callback_async_func, loop):
        self.last_text = ""
        self.callback = callback_async_func
        self.loop = loop
        self.running = False

    def start(self):
        if not pyperclip: return
        self.running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        logger.info("🕵️ Clipboard Spy Started via threading.")

    def _monitor_loop(self):
        while self.running:
            try:
                text = pyperclip.paste()
                if text and text != self.last_text:
                    self.last_text = text
                    self._process_content(text)
            except Exception as e:
                pass # Clipboard might be busy
            time.sleep(1.0) # Check every second

    def _process_content(self, text):
        # Filter for relevant links
        if "http" in text.lower():
            if any(x in text.lower() for x in ["youtube.com", "youtu.be", "amazon", "amzn", "spotify"]):
                # Found a target! Schedule callback on the main event loop
                logger.info(f"🕵️ Spy detected link: {text}")
                asyncio.run_coroutine_threadsafe(self.callback(text), self.loop)

# Usage Example:
# spy = ClipboardSpy(callback_function, main_loop)
# spy.start()
