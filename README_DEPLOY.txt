🚀 DEPLOYMENT GUIDE (RENDER.COM)

1. CODE SETUP
   - Extract this zip.
   - Upload the files to a PRIVATE GitHub Repository.
   - NOTE: The '.env' file will NOT be uploaded (for safety). This is good!

2. CREATE SERVICE
   - Go to Render.com -> New -> Web Service.
   - Connect your GitHub Repo.

3. SETTINGS
   - Name: Jarvis-Bot
   - Runtime: Python 3
   - Build Command: pip install -r requirements.txt
   - Start Command: python telegram_main.py

4. 🔐 SECURE KEYS (Crucial)
   - Go to "Environment" tab in Render.
   - Add these variables (Copy values from your local .env file):
     - TELEGRAM_TOKEN
     - GEMINI_KEYS
     - GROQ_KEYS
     - LOCATION_NAME
     - LATITUDE
     - LONGITUDE

5. KEEP IT ALIVE (Free Tier)
   - Render spins down after 15 mins of inactivity.
   - Go to cron-job.org (free).
   - Create a job to visit "https://your-app-name.onrender.com/" every 10 minutes.
   - This keeps Jarvis awake 24/7!
