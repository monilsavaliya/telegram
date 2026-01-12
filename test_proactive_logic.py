
import asyncio
import logging
from datetime import datetime, timedelta
import pytz

# Mock Objects
class MockBot:
    async def send_message(self, chat_id, text):
        print(f"🤖 [BOT SEND] To {chat_id}: {text}")

class MockContext:
    def __init__(self):
        self.bot = MockBot()

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- TEST LOGIC COPY ---
async def test_logic():
    print("--- STARTING PROACTIVE LOGIC TEST ---")
    
    # 1. Setup Data
    user_id = "12345"
    IST = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(IST)
    
    # CASE A: User just spoke (Skips)
    print("\n[TEST 1] Recent message (< 30m ago)")
    last_ts = (now_ist - timedelta(minutes=10)).isoformat()
    
    should_skip = False
    if last_ts:
        try:
            l_dt = datetime.fromisoformat(last_ts)
            if l_dt.tzinfo is None: l_dt = IST.localize(l_dt)
            if now_ist - l_dt < timedelta(minutes=30):
                should_skip = True
                print(f"✅ PASSED: Skipped because last msg was 10 mins ago.")
        except Exception as e:
            print(f"❌ FAILED: {e}")

    if not should_skip:
         print("❌ FAILED: Should have skipped!")

    # CASE B: Long time ago (Should Run)
    print("\n[TEST 2] Old message (> 4 hours ago)")
    last_ts = (now_ist - timedelta(hours=5)).isoformat()
    should_skip = False
    if last_ts:
        try:
            l_dt = datetime.fromisoformat(last_ts)
            if l_dt.tzinfo is None: l_dt = IST.localize(l_dt)
            if now_ist - l_dt < timedelta(minutes=30):
                should_skip = True
        except:
             pass
             
    if not should_skip:
         print("✅ PASSED: Proceeded to check (Cooldown expired).")
    else:
         print("❌ FAILED: Should NOT have skipped!")

if __name__ == "__main__":
    asyncio.run(test_logic())
