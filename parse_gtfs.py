import csv
import os
import math

# PATHS
DIR_PRIMARY = r"c:\Users\Monil\OneDrive\Desktop\projects\lyrics\wp bot\improved-gtfs-delhi-metro"
DIR_SECONDARY = r"c:\Users\Monil\OneDrive\Desktop\projects\lyrics\wp bot\DMRC_GTFS"

# MANUAL COORDINATE FIXES (For known errors/missing)
MANUAL_FIXES = {
    "Rajiv Chowk": (28.6327, 77.2195),
    "Kashmere Gate": (28.6675, 77.2285),
    "New Delhi": (28.6431, 77.2223),
    "Huda City Centre": (28.4595, 77.0726),
    "IGI Airport": (28.5562, 77.0999),
    "Noida Electronic City": (28.6287, 77.3752)
}

def normalize_name(name):
    """Normalize station names for matching (e.g. 'Dwarka Sec 21' == 'Dwarka Sector 21')."""
    n = name.lower().replace("sector", "sec").replace("-", " ").replace(".", "").strip()
    return " ".join(n.split())

def load_stops(directory):
    """Loads stops from a GTFS stops.txt file."""
    stops = {}
    path = os.path.join(directory, "stops.txt")
    if not os.path.exists(path): return {}
    
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops[row['stop_id']] = {
                "name": row['stop_name'],
                "lat": float(row['stop_lat']),
                "lon": float(row['stop_lon'])
            }
    return stops

def load_routes(directory):
    routes = {}
    path = os.path.join(directory, "routes.txt")
    if not os.path.exists(path): return {}
    
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('route_long_name', '') + " " + row.get('route_short_name', '')
            color = "Unknown"
            if "Red" in name: color = "Red"
            elif "Yellow" in name: color = "Yellow"
            elif "Blue" in name: color = "Blue"
            elif "Violet" in name: color = "Violet"
            elif "Green" in name: color = "Green"
            elif "Pink" in name: color = "Pink"
            elif "Magenta" in name: color = "Magenta"
            elif "Orange" in name or "Airport" in name: color = "Airport"
            elif "Rapid" in name: color = "Rapid"
            
            routes[row['route_id']] = color
    return routes

def load_trips(directory):
    trips = {}
    path = os.path.join(directory, "trips.txt")
    if not os.path.exists(path): return {}
    
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trips[row['trip_id']] = row['route_id']
    return trips

def process_edges(directory, stops, routes, trip_adj, station_lines, coords):
    """Process stop_times to build edges."""
    path = os.path.join(directory, "stop_times.txt")
    if not os.path.exists(path): return

    trip_route_map = load_trips(directory)
    
    current_trip_id = None
    trip_stops = []
    
    print(f"  > Parsing stop_times in {directory}...")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # We rely on file order being grouped by trip. Sorting is safest but SLOW for large files.
        # GTFS spec usually implies grouping. 
        
        for row in reader:
            t_id = row['trip_id']
            s_id = row['stop_id']
            
            if t_id != current_trip_id:
                # Flush previous trip
                if current_trip_id and len(trip_stops) > 1:
                    route_id = trip_route_map.get(current_trip_id)
                    line_color = routes.get(route_id, "Unknown")
                    
                    for i in range(len(trip_stops) - 1):
                        u_id, v_id = trip_stops[i], trip_stops[i+1]
                        if u_id not in stops or v_id not in stops: continue
                        
                        u_name = stops[u_id]['name']
                        v_name = stops[v_id]['name']
                        
                        # Save Data
                        coords[u_name] = (stops[u_id]['lat'], stops[u_id]['lon'])
                        coords[v_name] = (stops[v_id]['lat'], stops[v_id]['lon'])
                        
                        if u_name not in station_lines: station_lines[u_name] = set()
                        if v_name not in station_lines: station_lines[v_name] = set()
                        station_lines[u_name].add(line_color)
                        station_lines[v_name].add(line_color)
                        
                        if u_name not in trip_adj: trip_adj[u_name] = set()
                        if v_name not in trip_adj: trip_adj[v_name] = set()
                        trip_adj[u_name].add(v_name)
                        trip_adj[v_name].add(u_name)
                
                current_trip_id = t_id
                trip_stops = []
            
            trip_stops.append(s_id)

def merge_datasets():
    print("🚀 Starting Smart Merge...")
    
    # Shared Data Structures
    final_adj = {}
    final_lines = {}
    final_coords = {}
    
    # 1. PROCESS PRIMARY (Improved GTFS)
    # We trust its connectivity (Edges)
    print(f"📦 Loading Primary: {DIR_PRIMARY}")
    stops1 = load_stops(DIR_PRIMARY)
    routes1 = load_routes(DIR_PRIMARY)
    process_edges(DIR_PRIMARY, stops1, routes1, final_adj, final_lines, final_coords)
    
    # 2. PROCESS SECONDARY (DMRC) - Only for missing coordinates
    # We do NOT trust its edges to merge blindly, as it might create duplicates.
    # We primarily look for unique station names that Primary missed.
    print(f"📦 Scanning Secondary: {DIR_SECONDARY}")
    stops2 = load_stops(DIR_SECONDARY)
    
    count_new = 0
    for s_id, s_data in stops2.items():
        name = s_data['name']
        # Check against existing (Attempt Normalized Match)
        is_known = False
        norm_name = normalize_name(name)
        
        for k in final_coords.keys():
            if normalize_name(k) == norm_name:
                is_known = True
                break
        
        if not is_known:
            # New Station found in Secondary! Add it.
            # We can't add edges easily, but we can add it to Coords for "Nearest Station"
            final_coords[name] = (s_data['lat'], s_data['lon'])
            final_lines[name] = {"Unknown"} # We don't know line without edge parsing
            count_new += 1
            
    print(f"✅ Added {count_new} unique stations from Secondary source.")

    # 3. APPLY MANUAL FIXES
    print("🛠️ Applying Manual Precision Fixes...")
    for name, (lat, lon) in MANUAL_FIXES.items():
        final_coords[name] = (lat, lon)
        # Ensure it exists in lines/adj if we forced it? 
        # Usually manual fixes are just correcting coords of existing stations.
    
    # 4. WRITE OUTPUT
    # Convert sets to lists
    out_stations = {k: list(v) for k, v in final_lines.items()}
    out_adj = {k: list(v) for k, v in final_adj.items()}
    
    with open("metro_data.py", "w", encoding="utf-8") as f:
        f.write("METRO_GRAPH = {\n")
        f.write('    "stations": ' + repr(out_stations) + ",\n")
        f.write('    "adj": ' + repr(out_adj) + ",\n")
        f.write('    "coords": ' + repr(final_coords) + "\n")
        f.write("}\n")
        
    print(f"🎉 SUCCESS: Generated `metro_data.py` with {len(final_coords)} total stations.")

if __name__ == "__main__":
    merge_datasets()
