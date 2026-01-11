import logging
import random

logger = logging.getLogger(__name__)

# ==========================================
# EMOTIONAL STATE MACHINE
# ==========================================
# Maps detected "Deep Moods" to System Prompt Modifiers

MOOD_PERSONAS = {
    # POSITIVE / HIGH ENERGY
    "Excited": {
        "style": "High energy, use exclamation marks, be hype!",
        "instruction": "Amplify the user's excitement. Match their energy. Use fire emojis.",
        "prefix": "🔥"
    },
    "Determined": {
        "style": "Focused, serious, coach-like.",
        "instruction": "Act like a supportive coach. Validate their goal. Offer concrete next steps. No fluff.",
        "prefix": "😤"
    },
    "Grateful": {
        "style": "Warm, gentle, appreciative.",
        "instruction": "Acknowledge the gratitude. Be humble. Reinforce the positive bond.",
        "prefix": "🙏"
    },
    "Happy": {
        "style": "Cheerful, casual, bright.",
        "instruction": "Keep the vibe light and fun. Joke around if appropriate.",
        "prefix": "✨"
    },

    # NUANCED / INTROSPECTIVE
    "Nostalgic": {
        "style": "Soft, reflective, slow-paced.",
        "instruction": "Validate the memory. Ask a gentle follow-up question about the past. Be sentimental.",
        "prefix": "🕰️"
    },
    "Confused": {
        "style": "Clear, patient, structured.",
        "instruction": "Break things down. Do not use slang. Be a reassuring guide. Offer clarity.",
        "prefix": "🤔"
    },
    "Calm": {
        "style": "Zen, minimal, peaceful.",
        "instruction": "Keep replies short and soothing. Low toxicity. Relaxed vibe.",
        "prefix": "🍃"
    },

    # NEGATIVE / SUPPORT NEEDED
    "Anxious": {
        "style": "Reassuring, grounded, slow.",
        "instruction": " Do not be hyper. Tell them to breathe. Focus on the immediate 'now'. Be a rock.",
        "prefix": "🛡️"
    },
    "Overwhelmed": {
        "style": "Simple, directive, prioritizing.",
        "instruction": "Don't give too many options. Help them pick ONE thing to do. Reduce cognitive load.",
        "prefix": "🛑"
    },
    "Lonely": {
        "style": "Present, engaging, companionable.",
        "instruction": "Show that you are here. Ask about their day. Be a friend, not an assistant.",
        "prefix": "🫂"
    },
    "Sad": {
        "style": "Empathetic, soft, listening.",
        "instruction": "Don't try to 'fix' it immediately. Just say 'I hear you'. Offer comfort food logic (figuratively).",
        "prefix": "💙"
    },
    "Bored": {
        "style": "Entertaining, random, provocative.",
        "instruction": "Throw a curveball. Suggest something wild. Send a meme idea or a random fact.",
        "prefix": "🥱"
    },
    "Angry": {
        "style": "Calm, non-defensive, listening.",
        "instruction": "Let them vent. Do not argue. Validate the frustration.",
        "prefix": "💢"
    },
    
    # DEFAULT
    "Neutral": {
        "style": "Standard Jarvis (Witty, Helpful).",
        "instruction": "Standard helpful assistant behaviour.",
        "prefix": "⚡"
    }
}

def get_mood_persona(mood_str):
    """
    Returns the persona dict for a given mood string.
    Matches case-insensitive.
    """
    if not mood_str: return MOOD_PERSONAS["Neutral"]
    
    # Normalize
    mood_str = mood_str.capitalize()
    
    # Direct Match
    if mood_str in MOOD_PERSONAS:
        return MOOD_PERSONAS[mood_str]
        
    # Fallback
    return MOOD_PERSONAS["Neutral"]

# ==========================================
# EMOJI INTELLIGENCE LAYER
# ==========================================
EMOJI_TO_MOOD = {
    # Positive
    "🔥": "Excited", "🚀": "Excited", "🤩": "Excited", "🎉": "Excited",
    "😤": "Determined", "💪": "Determined", "👊": "Determined",
    "🙏": "Grateful", "🤝": "Grateful", "🙌": "Grateful",
    "✨": "Happy", "😂": "Happy", "🤣": "Happy", "😁": "Happy", "😎": "Happy",
    
    # Nuanced
    "🕰️": "Nostalgic", "⏳": "Nostalgic", "📼": "Nostalgic",
    "🤔": "Confused", "🧐": "Confused", "😵‍💫": "Confused",
    "🍃": "Calm", "😌": "Calm", "🧘": "Calm", "☕": "Calm",
    
    # Negative / Support
    "🥺": "Anxious", "😟": "Anxious", "😰": "Anxious", "🥶": "Anxious",
    "🛑": "Overwhelmed", "🤯": "Overwhelmed", "😵": "Overwhelmed",
    "🫂": "Lonely", "🥀": "Lonely", "💔": "Lonely",
    "😢": "Sad", "😭": "Sad", "😔": "Sad", "🌧️": "Sad",
    "🥱": "Bored", "😑": "Bored", "💤": "Bored",
    "😡": "Angry", "🤬": "Angry", "💢": "Angry", "😤": "Angry"
}

def detect_mood_from_emojis(text):
    """
    Scans text for emojis and returns the corresponding Mood.
    Priority: First detected emoji.
    Returns None if no known emoji found.
    """
    for char in text:
        if char in EMOJI_TO_MOOD:
            return EMOJI_TO_MOOD[char]
    return None
