import logging

logger = logging.getLogger(__name__)

# Static Data for Major Interchanges
# This is a MVP dataset. In production, this would be a full DB.
PLATFORM_DATA = {
    "Rajiv Chowk": {
        "Yellow": {"Towards Samaypur Badli": "Platform 2", "Towards Huda City Centre": "Platform 1"},
        "Blue": {"Towards Noida/Vaishali": "Platform 3", "Towards Dwarka": "Platform 4"}
    },
    "Kashmere Gate": {
        "Red": {"Towards Rithala": "Platform 1", "Towards Shaheed Sthal": "Platform 2"},
        "Yellow": {"Towards Huda City Centre": "Platform 3", "Towards Samaypur Badli": "Platform 4"},
        "Violet": {"Towards Raja Nahar Singh": "Platform 5", "Towards Kashmere Gate": "Platform 6"}
    },
    "Hauz Khas": {
        "Yellow": {"Towards Samaypur Badli": "Platform 2", "Towards Huda City Centre": "Platform 1"},
        "Magenta": {"Towards Botanical Garden": "Platform 3", "Towards Janakpuri West": "Platform 4"}
    }
}

# General Heuristics for standard lines (Rule of Thumb, not 100% accurate but helpful)
LINE_HEURISTICS = {
    "Yellow": {"Down": "Platform 1", "Up": "Platform 2"}, # Assuming Down=Huda, Up=Badli
    "Blue": {"Down": "Platform 1", "Up": "Platform 2"},
    "Red": {"Down": "Platform 1", "Up": "Platform 2"},
}

def get_platform_info(station_name, line_color, direction):
    """
    Returns the likely platform number.
    Ex: "Platform 1"
    """
    # 1. Check Hardcoded Major Stations
    if station_name in PLATFORM_DATA:
        station_data = PLATFORM_DATA[station_name]
        if line_color in station_data:
            # Fuzzy match direction
            for dir_key, platform in station_data[line_color].items():
                if direction in dir_key or dir_key in direction:
                    return platform
                    
    # 2. Heuristic Semantic Guess (AI Lite)
    # If we don't know, we return generic "Check Display" or try to guess reasonable default
    # For now, safe fallback
    return "Check Display"

def format_station_instruction(station, line, direction, action="Board"):
    """
    Returns rich string: "Board Yellow Line (Towards Huda City Centre) | Platform 1"
    """
    plat = get_platform_info(station, line, direction)
    
    icon = "🚉"
    if action == "Change": icon = "🔄"
    elif action == "Exit": icon = "🏁"
    
    base = f"{icon} **{station}**: {action} {line} Line"
    dir_info = f"({direction})" if direction else ""
    plat_info = f" | *{plat}*" if plat and plat != "Check Display" else ""
    
    return f"{base} {dir_info}{plat_info}"
