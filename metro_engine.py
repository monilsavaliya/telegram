import heapq
import urllib.parse
import json
import ast
from metro_data import METRO_GRAPH, METRO_LANDMARKS

def get_line_color(station):
    """Returns the primary line color of a station."""
    colors = METRO_GRAPH["stations"].get(station, set())
    return list(colors)[0] if colors else "Unknown"

def get_interchange_lines(station):
    """Returns all lines available at this station."""
    return METRO_GRAPH["stations"].get(station, set())

def find_shortest_path(start, end, interchange_penalty=2):
    """
    Finds shortest path using Dijkstra.
    interchange_penalty: Extra cost (mins) for switching lines.
    """
    # Queue: (Cumulative Cost, Current Station, Line Arrived On, Path)
    # Start: Cost 0, Station Start, Line None, Path [Start]
    queue = [(0, start, None, [start])] 
    visited = {} # (Station, Line) -> Cost
    
    final_path = None
    min_cost = float('inf')

    while queue:
        cost, current, curr_line, path = heapq.heappop(queue)
        
        # Optimization: Early Exit if worse than found
        if cost > min_cost: continue
        
        # Visited Check (State = Station + Line)
        state = (current, curr_line)
        if state in visited and visited[state] <= cost:
            continue
        visited[state] = cost
        
        if current == end:
            if cost < min_cost:
                min_cost = cost
                final_path = path
            continue
            
        neighbors = METRO_GRAPH["adj"].get(current, [])
        for neighbor in neighbors:
            # Determine Line Logic
            # Determine Line Logic
            lines_curr = METRO_GRAPH["stations"].get(current, [])
            lines_next = METRO_GRAPH["stations"].get(neighbor, [])
            
            set_curr = set(lines_curr)
            set_next = set(lines_next)
            
            common_lines = set_curr.intersection(set_next)
            
            # If we don't know the line (first step), pick any valid one
            next_line = list(common_lines)[0] if common_lines else "Unknown"
            
            # Transition Cost
            move_cost = 2 # 2 mins per station
            
            # Check Interchange
            if curr_line and curr_line not in common_lines:
                # We are changing lines!
                move_cost += interchange_penalty
            
            heapq.heappush(queue, (cost + move_cost, neighbor, next_line, path + [neighbor]))
                
    return final_path

def get_platform_heuristic(stn_from, stn_to, line_color):
    """Guesses platform based on direction (Heuristic)."""
    # Real platform data is complex, using smart defaults for now.
    # Yellow: Samaypur Badli (P2) <-> Huda City Centre (P1)
    # Blue: Dwarka (P1) <-> Noida/Vaishali (P2)
    
    if line_color == "Yellow":
        return "Platform 1" if "Huda" in stn_to or stn_to < stn_from else "Platform 2"
    elif line_color == "Blue":
        return "Platform 1" if "Dwarka" in stn_to else "Platform 2"
    elif line_color == "Red":
        return "Platform 2" # Default
    return "Platform 1/2"

async def handle_metro(user_text, user_id, send_msg_func, ai_generator=None, criteria="fastest", previous_route=None):
    """
    Handles Metro Routing with Smart Station Resolution & Mood Criteria.
    criteria: 'fastest' (Penalty 2) or 'comfort' (Penalty 15)
    previous_route: (src, dest) tuple from Context
    Returns: (src, dest) found, or None
    """
    penalty = 15 if criteria == "comfort" else 2
    
    # Check for "Minimum Exchange" keywords specifically to force 'comfort' logic
    if any(x in user_text.lower() for x in ["exchange", "interchange", "change", "comfort", "easy"]):
        penalty = 15
    
    # 1. Try Simple Keyword Matching first (Fast)
    valid_stations = list(METRO_GRAPH['adj'].keys())
    found_stations = []
    text_lower = user_text.lower()
    
    for stn in valid_stations:
        if stn.lower() in text_lower:
            found_stations.append(stn)
            
    src, dest = None, None
    
    if len(found_stations) >= 2:
        # Naive Guess: First mentioned is src? Or strictly by order in string?
        # Let's trust order of appearance if possible, or just take first 2.
        # Better: find index in string.
        found_stations.sort(key=lambda s: text_lower.find(s.lower()))
        src, dest = found_stations[0], found_stations[1]
    
    # 2. Context Reuse (Refinement)
    if (not src or not dest) and previous_route:
        # If user didn't specify NEW stations, assume they want to refine the OLD route
        # e.g. "Minimum exchange" -> Reuse (IIT, CP)
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 Reusing Previous Metro Context: {previous_route}")
        src, dest = previous_route

    # 3. AI Fallback (Smart Resolution) - Only if Context didn't fill it
    if (not src or not dest) and ai_generator:
        # "IIT Gate to India Gate" -> Map to 'IIT' and 'Central Secretariat'
        context_str = f"Previous Route: {previous_route[0]} to {previous_route[1]}" if previous_route else "None"
        prompt = (
            f"Task: generic_location_to_exact_metro_station\n"
            f"User Input: '{user_text}'\n"
            f"Context: {context_str}\n"
            f"Valid Stations List: {json.dumps(valid_stations[:50])}... (Standard Delhi Metro)\n"
            "Identify the Source and Destination. If a Landmark is given, map it to the NEAREST valid station name.\n"
            "Rules:\n"
            "1. If user says 'Then to X' or 'Next X' and Context exists, make Source = Context Destination.\n"
            "2. If user assumes start is current location, try to infer or ask.\n"
            "Return valid JSON only: {\"source\": \"Valid_Station_Name\", \"destination\": \"Valid_Station_Name\"}\n"
            "Example: 'Visit India Gate' -> {\"destination\": \"Central Secretariat\"}"
        )
        
        try:
            resp = await ai_generator(prompt, tier="lightning")
            if resp and "{" in resp:
                clean_json = resp[resp.find("{"):resp.rfind("}")+1]
                try:
                    data = json.loads(clean_json)
                except json.JSONDecodeError:
                    # Fallback for Single Quotes (Common LLM error)
                    try:
                        data = ast.literal_eval(clean_json)
                    except:
                        data = {}
                        
                src = data.get("source")
                dest = data.get("destination")
        except Exception as e:
            print(f"Metro AI Fail: {e}")

    if not src or not dest or src not in valid_stations or dest not in valid_stations:
        await send_msg_func(user_id, "🚇 I couldn't identify the Metro Stations. Please try:\n*Route from Rajiv Chowk to Noida*")
        return None, None

    # 4. Calculate Path (BFS/Dijkstra)
    path = find_shortest_path(src, dest, interchange_penalty=penalty) 
    if not path:
        await send_msg_func(user_id, f"❌ No route found between *{src}* and *{dest}*.")
        return src, dest

    # 3. Generate Bullet-Point Itinerary
    # Detect Changes
    interchange_stations = []
    current_line = None
    
    # Analyze line changes
    segments = [] # (Start, End, Line)
    seg_start = path[0]
    
    # *Simplified logic for Demo: Just showing path + Changes*
    # Real logic would need line-checking per edge.
    # Assuming 'Change' if station has multiple colors in metadata
    
    msg = f"🚇 **Metro Route: {src} ➔ {dest}**\n\n"
    msg += f"🟢 **Start at {src}**\n"
    
    # Walk the path
    for i in range(len(path)-1):
        curr = path[i]
        next_stn = path[i+1]
        
        # Heuristic: If curr is major interchange, mention it
        # METRO_LANDMARKS is not defined, skipping this part for now
        # if i > 0 and len(METRO_LANDMARKS.get(curr, [])) > 0: # Using Landmarks as proxy for major stn
        #      pass # Logic placeholder

    # Formatting the output nicely
    from metro_lines import get_direction
    
    start_line = list(METRO_GRAPH['stations'].get(src, ['Unknown']))[0] 
    
    # Try to find Next Station to determine direction
    next_stn_name = path[1] if len(path) > 1 else src
    direction = get_direction(start_line, src, next_stn_name)
    
    msg += f"   └ 🚉 Take **{start_line} Line** {direction}\n"
    
    # Find interchanges (naive: stations with > 1 outgoing lines in graph or multi-color)
    changes = []
    for i, stn in enumerate(path[1:-1]):
        real_idx = i + 1
        colors = METRO_GRAPH['stations'].get(stn, [])
        if len(colors) > 1:
            # Check if line actually changes between prev and next
            prev_st = path[real_idx-1]
            next_st = path[real_idx+1]
            
            l1_set = set(METRO_GRAPH['stations'].get(prev_st, []))
            current_l_set = set(METRO_GRAPH['stations'].get(stn, []))
            l2_set = set(METRO_GRAPH['stations'].get(next_st, []))
            
            line_in = list(l1_set.intersection(current_l_set))[0] if l1_set.intersection(current_l_set) else "Unknown"
            line_out = list(l2_set.intersection(current_l_set))[0] if l2_set.intersection(current_l_set) else "Unknown"
            
            if line_in != line_out:
                new_dir = get_direction(line_out, stn, next_st)
                msg += f"🔄 **Change at {stn}** ({line_in} ➔ {line_out})\n"
                msg += f"   └ 🚉 Take **{line_out} Line** {new_dir}\n"
         
    msg += f"🏁 **Exit at {dest}**\n"
    msg += f"\n⏳ Est. Time: {len(path)*2} mins | 🛑 Stations: {len(path)}"

    await send_msg_func(user_id, msg)

def format_route(path):
    """
    Converts a list of stations into a structured itinerary with interchanges.
    """
    if not path: return None
    
    steps = []
    current_line = None
    segment_start = path[0]
    
    # Identify Line for first segment
    # Look ahead to see which line connects 0 and 1
    if len(path) > 1:
        l0 = METRO_GRAPH["stations"].get(path[0], set())
        l1 = METRO_GRAPH["stations"].get(path[1], set())
        common = l0.intersection(l1)
        current_line = list(common)[0] if common else "Unknown"
    
    steps.append({
        "type": "start",
        "station": path[0],
        "line": current_line,
        "platform": "Check Display" # Dynamic platform DB is hard, using placeholder
    })
    
    for i in range(1, len(path) - 1):
        prev = path[i-1]
        curr = path[i]
        next_st = path[i+1]
        
        # Determine lines connecting Prev->Curr and Curr->Next
        l_prev_curr = METRO_GRAPH["stations"].get(prev, set()).intersection(METRO_GRAPH["stations"].get(curr, set()))
        l_curr_next = METRO_GRAPH["stations"].get(curr, set()).intersection(METRO_GRAPH["stations"].get(next_st, set()))
        
        line_in = list(l_prev_curr)[0] if l_prev_curr else "Unknown"
        line_out = list(l_curr_next)[0] if l_curr_next else "Unknown"
        
        if line_in != line_out:
            # INTERCHANGE DETECTED
            steps.append({
                "type": "travel",
                "to": curr,
                "stations_count": "Unknown", # Could calculate details
            })
            steps.append({
                "type": "interchange",
                "station": curr,
                "from_line": line_in,
                "to_line": line_out,
                "instruction": f"Change from {line_in} Line to {line_out} Line"
            })
            current_line = line_out
            segment_start = curr

    # Final Leg
    steps.append({
        "type": "travel",
        "to": path[-1],
    })
    
    steps.append({
        "type": "end",
        "station": path[-1],
        "line": current_line
    })
    
    return steps

def generate_human_readable_response(start, end):
    path_data = find_shortest_path(start, end)
    if not path_data:
        return f"❌ Could not find a route between {start} and {end}."
    
    # Bullet points format
    msg = f"🚇 *Metro Route: {start} ➝ {end}*\n\n"
    
    for step in path_data:
        if step["type"] == "start":
            msg += f"🟢 *Start at {step['station']}* ({step['line']} Line)\n"
        elif step["type"] == "interchange":
            msg += f"🔄 *Interchange at {step['station']}*\n"
            msg += f"   └ Change to {step['to_line']} Line\n"
        elif step["type"] == "end":
             msg += f"🔴 *Exit at {step['station']}*\n"
    
    fare = 40 # Mock
    time = len(path_data) * 2 # Mock 2 min per station
    
    msg += f"\n💰 Fare: ₹{fare} | ⏱️ Time: ~{time} mins"
    return msg

def get_haversine_distance(lat1, lon1, lat2, lon2):
    import math
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def find_nearest_station(user_lat, user_lon):
    """
    Finds the single nearest metro station to the user's coordinates.
    Returns: (StationName, DistanceKm, LineColor)
    """
    nearest_station = None
    min_dist = float('inf')
    
    for station, (lat, lon) in METRO_GRAPH.get("coords", {}).items():
        dist = get_haversine_distance(user_lat, user_lon, lat, lon)
        if dist < min_dist:
            min_dist = dist
            nearest_station = station
            
    if nearest_station:
        line = get_line_color(nearest_station)
        return nearest_station, round(min_dist, 2), line
    return None, 0, "Unknown"
