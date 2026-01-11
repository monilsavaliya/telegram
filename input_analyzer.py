import logging
import json
import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def analyze_input_deep(text: str, user_profile: Dict, ai_generator: Any) -> Dict[str, Any]:
    """
    The Observer: Deeply analyzes user input for Sentiment, Facts, and Context.
    Does NOT determine the bot's immediate response (that's the Router's job).
    Instead, it creates a 'Memory Log' for behavioral study.
    """
    try:
        # Prompt designed to extract subtle behavioral curs
        prompt = (
            f"Analyze this text found in a personal chat: '{text}'. "
            "Extract structured data in JSON ONLY: {"
            " 'sentiment': 'Positive/Negative/Neutral', "
            " 'mood': 'Select ONE: [Nostalgic, Anxious, Grateful, Overwhelmed, Lonely, Excited, Bored, Confused, Determined, Happy, Sad, Angry, Calm]', "
            " 'facts': ['Fact 1', 'Fact 2'], "
            " 'entities': {'people': [], 'dates': [], 'locations': []}"
            "}"
            "Be highly sensitive to subtext. 'Mood' should reflect deep psychological state."
        )

        # Use Standard tier (Gemini Flash or Pro) for depth, Lightning is too simple
        response = await ai_generator(prompt, tier="standard")
        
        # Parse JSON
        if "```json" in response:
            clean_json = response.split("```json")[1].split("```")[0]
        elif "{" in response:
            clean_json = response[response.find("{"):response.rfind("}")+1]
        else:
            clean_json = "{}"
            
        analysis_data = json.loads(clean_json)
        
        # Enriched Data Structure
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "raw_text": text,
            "analysis": analysis_data,
            "user_id": user_profile.get("user_id", "unknown")
        }
        
        logger.info(f"👁️ Observer Logged: {json.dumps(analysis_data.get('sentiment', 'Unknown'))} | Facts: {len(analysis_data.get('facts', []))}")
        return log_entry

    except Exception as e:
        logger.error(f"Input Analyzer Failed: {e}")
        return {"error": str(e), "timestamp": datetime.datetime.now().isoformat()}

def log_behavior_to_file(log_entry: Dict, filepath="behavior_logs.json"):
    """
    Appends the analysis to a local JSON line file (simulating a DB).
    """
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write behavior log: {e}")
