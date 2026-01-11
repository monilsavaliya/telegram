import shutil
import os
import datetime
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# Config
BACKUP_DIR = "backups"
FILES_TO_BACKUP = ["brain.db", "behavior_logs.json", "user_routines.json"]

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def create_backup():
    """
    Copies critical data files to backup/ directory with timestamp.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    
    for filename in FILES_TO_BACKUP:
        if os.path.exists(filename):
            try:
                # Backup Name: backups/brain_20240112_0125.db
                name, ext = os.path.splitext(filename)
                target = os.path.join(BACKUP_DIR, f"{name}_{timestamp}{ext}")
                shutil.copy2(filename, target)
                
                # Also keep a "latest" copy for easy restore
                latest_target = os.path.join(BACKUP_DIR, f"{name}_latest{ext}")
                shutil.copy2(filename, latest_target)
                
            except Exception as e:
                logger.error(f"Backup Failed for {filename}: {e}")
    
    logger.info(f"💾 Backup Complete at {timestamp}")

def start_backup_scheduler():
    """
    Runs backup every 6 hours and on startup.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(create_backup, 'interval', hours=6)
    scheduler.start()
    
    # Run one immediately
    create_backup()
    return scheduler

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_backup_scheduler()
