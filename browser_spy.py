import os
import shutil
import sqlite3
import datetime
import logging
import time
import asyncio
import threading
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default Chrome History Path (Windows)
# Dynamic User Path
# Default Chrome History Path (Windows)
# Dynamic User Path
USER_PROFILE = os.environ.get("USERPROFILE")

if USER_PROFILE:
    BASE_CHROME_PATH = os.path.join(USER_PROFILE, r"AppData\Local\Google\Chrome\User Data")
else:
    # On Linux/Server (PythonAnywhere), this path usually doesn't exist or is different.
    # We will disable functionality if path is invalid.
    BASE_CHROME_PATH = None

TEMP_DB_PATH = "chrome_history_temp.db"

def find_history_path():
    """
    Intelligently finds the active Chrome History file.
    Checks 'Default' and 'Profile 1' to 'Profile 10'.
    Returns the path with the most recent modification time.
    """
    if not BASE_CHROME_PATH:
        return None
        
    candidates = ["Default"] + [f"Profile {i}" for i in range(1, 10)]
    best_path = None
    newest_mtime = 0
    
    for profile in candidates:
        try:
             path = os.path.join(BASE_CHROME_PATH, profile, "History")
        except: continue
        
        if os.path.exists(path):
            try:
                mtime = os.path.getmtime(path)
                if mtime > newest_mtime:
                    newest_mtime = mtime
                    best_path = path
            except:
                pass
                
    return best_path

class BrowserSpy:
    def __init__(self, callback_async_func, loop, interval=60):
        self.callback = callback_async_func
        self.loop = loop
        self.interval = interval
        self.running = False
        self.seen_urls = set()
        self.history_path = None

    def start(self):
        # Auto-Discover Path
        self.history_path = find_history_path()
        
        if not self.history_path:
            logger.warning(f"❌ Chrome History not found in {BASE_CHROME_PATH}")
            return
            
        logger.info(f"🕵️ Browser Spy Locked Target: {self.history_path}")
            
        self.running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _monitor_loop(self):
        while self.running:
            try:
                self._check_history()
            except Exception as e:
                logger.error(f"Browser Spy Error: {e}")
            time.sleep(self.interval)

    def _check_history(self):
        if not self.history_path: return
        
        # 1. Copy DB to temp to avoid lock
        try:
            if os.path.exists(TEMP_DB_PATH):
                os.remove(TEMP_DB_PATH)
            shutil.copy2(self.history_path, TEMP_DB_PATH)
        except (PermissionError, FileNotFoundError):
            # Browser might be writing heavily, or path wrong
            return

        # 2. Query
        try:
            conn = sqlite3.connect(TEMP_DB_PATH)
            cursor = conn.cursor()
            
            # Get last 15 visits
            cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 15")
            rows = cursor.fetchall()
            conn.close()

            # 3. Filter & Notify
            new_items = []
            for url, title, count, visit_time in reversed(rows): # Oldest to Newest of the batch
                if not url: continue
                if url in self.seen_urls: continue
                
                self.seen_urls.add(url)
                
                # Interesting Domains Only
                if any(x in url.lower() for x in ["youtube.com/watch", "amazon.in", "amazon.com", "google.com/search"]):
                    new_items.append((url, title))

            # 4. Dispatch
            if new_items:
                for url, title in new_items:
                    logger.info(f"🕵️ Browser Spy saw: {title}")
                    asyncio.run_coroutine_threadsafe(self.callback(url, title), self.loop)
        except Exception as e:
            logger.error(f"History Read Error: {e}")

# Usage: spy = BrowserSpy(callback, loop) -> spy.start()
