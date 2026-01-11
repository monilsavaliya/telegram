import sqlite3
import json
import logging
import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
DB_FILE = "brain.db"

class DatabaseAdapter:
    """
    Unified Interface for Infinite Memory.
    Currently uses SQLite (Robust Local DB).
    Ready for Firebase migration (Adapter Pattern).
    """
    def __init__(self):
        self.conn = None
        self._init_db()

    def _get_conn(self):
        # Thread-safe connection handling
        return sqlite3.connect(DB_FILE, check_same_thread=False)

    def _init_db(self):
        """Initialize Tables if not exist."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # 1. Users Table (Profile)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        profile_json TEXT,
                        preferences_json TEXT,
                        created_at TEXT
                    )
                ''')
                
                # 2. History Table (Conversations)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        role TEXT,
                        content TEXT,
                        timestamp TEXT,
                        embedding TEXT
                    )
                ''')
                
                # 3. Behavior Table (Logs)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS behavior_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        timestamp TEXT,
                        log_json TEXT
                    )
                ''')
                
                # 4. Events Table (Timeline) - [BUG FIX: Missing Table]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        type TEXT,
                        start_time TEXT,
                        desc TEXT,
                        follow_up_msg TEXT,
                        status TEXT, -- pending/completed
                        created_at TEXT
                    )
                ''')
                
                conn.commit()
            logger.info("🧠 Brain DB (SQLite) Initialized.")
        except Exception as e:
            logger.error(f"DB Init Failed: {e}")

    # --- SCHEDULER SUPPORT METHODS ---
    def get_all_users(self) -> List[str]:
        """Fetch all user IDs for the scheduler."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users")
                rows = cursor.fetchall()
                return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"DB Get Users Error: {e}")
            return []

    def get_pending_events(self) -> List[tuple]:
        """
        Fetch all pending events. 
        Returns list of (user_id, event_dict).
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                # Find events where status is 'pending'
                # Note: We compare ISO strings which works for basic ordering, 
                # but here we just want status='pending'
                cursor.execute("SELECT * FROM events WHERE status='pending'")
                rows = cursor.fetchall()
                
                pending = []
                # ID, USER_ID, TYPE, START_TIME, DESC, FOLLOW_UP, STATUS, CREATED
                for r in rows:
                    event_dict = {
                        "id": r[0],
                        "type": r[2],
                        "start_time": r[3],
                        "desc": r[4],
                        "follow_up_msg": r[5],
                        "status": r[6],
                        "created_at": r[7]
                    }
                    pending.append((r[1], event_dict))
                return pending
        except Exception as e:
            logger.error(f"DB Pending Events Error: {e}")
            return []
            
    def add_event(self, user_id, event_type, start_time, desc, follow_up_msg):
        """Add event to DB."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO events (user_id, type, start_time, desc, follow_up_msg, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                ''', (user_id, event_type, start_time, desc, follow_up_msg, datetime.datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            logger.error(f"DB Add Event Error: {e}")

    def complete_event(self, user_id, event):
        """Mark event as completed. Event dict must have 'id' (DB ID) or we match by desc/time."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                if "id" in event:
                    cursor.execute("UPDATE events SET status='completed' WHERE id=?", (event["id"],))
                else:
                    # Fallback match
                    cursor.execute("UPDATE events SET status='completed' WHERE user_id=? AND start_time=? AND desc=?", 
                                   (user_id, event.get("start_time"), event.get("desc")))
                conn.commit()
        except Exception as e:
            logger.error(f"DB Complete Event Error: {e}")

    # --- USER PROFILE METHODS ---
    def get_profile(self, user_id: str) -> Dict:
        """
        Legacy Compatibility Method.
        Ensures user exists and returns full data dict including 'profile'.
        """
        user = self.get_user(user_id)
        if not user:
            # Initialize Default
            default_profile = {
                "nickname": "Boss", 
                "mode": "FRIEND (Bro/Bestie)",
                "aliases": {},
                "context": {}
            }
            default_prefs = {}
            self.upsert_user(user_id, default_profile, default_prefs)
            return {"profile": default_profile, "preferences": default_prefs, "user_id": user_id}
        
        # Ensure 'profile' key exists and has defaults if empty
        if "profile" not in user or not user["profile"]:
            user["profile"] = {"nickname": "Boss", "mode": "FRIEND (Bro/Bestie)", "aliases": {}}
            
        return user

    def update_profile(self, user_id: str, key: str, value: Any):
        """
        Legacy Compatibility Method.
        Updates a specific field in the user's profile.
        """
        user = self.get_profile(user_id)
        user["profile"][key] = value
        self.upsert_user(user_id, user["profile"], user["preferences"])

    def update_routine(self, user_id, day, item):
        """Legacy Routine Learning."""
        # Ideally this should use the new Behavior Engine, but for compatibility:
        # We might store it in preferences or just log it?
        # The new engine uses 'user_routines.json' or creates them from logs.
        # Let's map this to a preference or ignore to prevent crash, 
        # or better, store in a 'legacy_routines' field in preferences.
        user = self.get_profile(user_id)
        if "legacy_routines" not in user["preferences"]:
            user["preferences"]["legacy_routines"] = {}
        
        routines = user["preferences"]["legacy_routines"]
        if day not in routines: routines[day] = []
        if item not in routines[day]:
            routines[day].append(item)
            
        self.upsert_user(user_id, user["profile"], user["preferences"])

    def get_user(self, user_id: str) -> Dict:
        """Fetch full user object."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT profile_json, preferences_json FROM users WHERE user_id=?", (user_id,))
                row = cursor.fetchone()
                
                if row:
                    profile = json.loads(row[0]) if row[0] else {}
                    prefs = json.loads(row[1]) if row[1] else {}
                    return {"profile": profile, "preferences": prefs, "user_id": user_id}
                else:
                    return None
        except Exception as e:
            logger.error(f"DB Read Error: {e}")
            return None

    def upsert_user(self, user_id: str, profile: Dict = None, preferences: Dict = None):
        """Create or Update User."""
        try:
            current = self.get_user(user_id) or {"profile": {}, "preferences": {}}
            
            new_profile = {**current["profile"], **(profile or {})}
            new_prefs = {**current["preferences"], **(preferences or {})}
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (user_id, profile_json, preferences_json, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        profile_json=excluded.profile_json,
                        preferences_json=excluded.preferences_json
                ''', (
                    user_id, 
                    json.dumps(new_profile), 
                    json.dumps(new_prefs), 
                    datetime.datetime.now().isoformat()
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB Write Error: {e}")

    # --- HISTORY METHODS ---
    def add_history_item(self, user_id: str, role: str, content: str):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO history (user_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, role, content, datetime.datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            logger.error(f"DB History Write Error: {e}")

    def get_history(self, user_id: str, limit=20) -> List[Dict]:
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT role, content, timestamp FROM history 
                    WHERE user_id=? 
                    ORDER BY id DESC LIMIT ?
                ''', (user_id, limit))
                rows = cursor.fetchall()
                # Reverse to get chronological order
                return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
        except Exception as e:
            logger.error(f"DB History Read Error: {e}")
            return []

# Singleton Global Instance
db = DatabaseAdapter()
