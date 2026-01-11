import os
import pickle
import logging
import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Scopes: Read-only access to YouTube account
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
CLIENT_SECRET_FILE = 'client_secret.json'
TOKEN_FILE = 'token.pickle'

class YouTubeNeuralLink:
    def __init__(self):
        self.service = None
        self.creds = None
    
    def authenticate(self):
        """
        Handles OAuth 2.0 Flow. 
        If token.pickle exists, loads it.
        Else, opens browser for User Login.
        """
        self.creds = None
        # 1. Load existing token
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                self.creds = pickle.load(token)
        
        # 2. Refresh or Login
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}. Re-authenticating.")
                    self.creds = None
            
            if not self.creds:
                if not os.path.exists(CLIENT_SECRET_FILE):
                    logger.error("❌ client_secret.json missing!")
                    return False
                    
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                # This opens a local server for the callback
                # Fixed port 8080 is safer/easier to whitelist if using Web Credentials
                self.creds = flow.run_local_server(port=8080)
                
            # Save token
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(self.creds, token)
        
        # 3. Build Service
        try:
            self.service = build('youtube', 'v3', credentials=self.creds)
            logger.info("🔗 YouTube Neural Link Connected.")
            return True
        except Exception as e:
            logger.error(f"YouTube Service Build Error: {e}")
            return False

    def get_latest_liked_videos(self, max_results=5):
        """Fetches the most recent liked videos."""
        if not self.service: return []
        
        try:
            # 'LL' is the special ID for "Liked List" of the authenticated user
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId="LL",
                maxResults=max_results
            )
            response = request.execute()
            
            videos = []
            for item in response.get("items", []):
                snippet = item["snippet"]
                videos.append({
                    "title": snippet["title"],
                    "channel": snippet["videoOwnerChannelTitle"],
                    "url": f"https://www.youtube.com/watch?v={item['contentDetails']['videoId']}",
                    "published_at": snippet["publishedAt"] # When it was liked (approx)
                })
            return videos
        except Exception as e:
            logger.error(f"YouTube Fetch Error: {e}")
            return []

    async def analyze_and_sync_mood(self, videos, user_id, ai_generator, memory_db):
        """
        Uses AI to infer mood from video list and syncs to DB.
        """
        if not videos: return

        # Prepare Data for AI
        video_titles = [f"- {v['title']} (by {v['channel']})" for v in videos]
        video_str = "\n".join(video_titles)
        
        # AI Prompt
        prompt = (
            f"User Profile Analysis based on recently Liked YouTube Videos:\n{video_str}\n\n"
            "Task: Infer the user's current MOOD based on this music/content.\n"
            "Logic:\n"
            "- Sad/Romantic Songs (e.g. Arijit Singh) -> Nostalgic/Lonely\n"
            "- Workouts/EDM -> Energetic/Determined\n"
            "- Lofi/Ambient -> Relaxed/Focused\n"
            "- Comedy -> Happy/Bored\n"
            "Output Format: 'MOOD|Short Witty Comment'\n"
            "Example: 'Nostalgic|Missing someone? These songs hit deep.'"
        )
        
        response = await ai_generator(prompt, tier="speed")
        if "|" in response:
            mood, comment = response.split("|", 1)
        else:
            mood, comment = "Neutral", response
            
        mood = mood.strip()
        comment = comment.strip()
        
        # Update Memory
        # log_media handles the list, but we also want to set the MAIN mood
        for v in videos:
             memory_db.log_media(user_id, v['url'], v['title'], mood=mood)
             
        # Update current mood in mood_manager (handled via behavior logs usually, but let's force a log)
        # We can simulate a "User Text" event that sets the mood? 
        # Or just return the comment for the bot to say.
        
        logger.info(f"🎧 YouTube Mood: {mood} | {comment}")
        return comment

# Global Instance
youtube_link = YouTubeNeuralLink()
