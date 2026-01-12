import random
import math

class TaxiEngine:
    def __init__(self):
        # User States: {user_id: {"state": "PICKUP", "data": {...}}}
        self.user_states = {}
        
        # Vehicle Types & Pricing Rules (Based on 2024 Metro City Avg)
        self.pricing = {
            "moto": {"base": 20, "per_km": 9, "speed_kmh": 35, "name": "Moto 🏍️"},
            "auto": {"base": 30, "per_km": 15, "speed_kmh": 25, "name": "Auto 🛺"},
            "go":   {"base": 55, "per_km": 14, "speed_kmh": 40, "name": "Uber Go 🚗"},
            "sedan":{"base": 85, "per_km": 19, "speed_kmh": 45, "name": "Premier 🚘"},
            "xl":   {"base": 130,"per_km": 28, "speed_kmh": 40, "name": "Uber XL 🚙"}
        }

    def get_state(self, user_id):
        return self.user_states.get(user_id, {"state": "IDLE", "data": {}})

    def set_state(self, user_id, state, data=None):
        if user_id not in self.user_states:
             self.user_states[user_id] = {"state": "IDLE", "data": {}}
        
        self.user_states[user_id]["state"] = state
        if data:
            self.user_states[user_id]["data"].update(data)

    def reset_session(self, user_id, initial_text=None, user_aliases=None):
        """
        Resets session. If initial_text provided, tries to extract Pickup/Drop.
        Validates against user_aliases to avoid "Unknown Place" hallucination.
        """
        self.user_states[user_id] = {"state": "PICKUP", "data": {}}
        if not user_aliases: user_aliases = {}
        
        # Smart Extraction (Simple Keyword Based)
        # "Book a cab from IIT to Gurgaon"
        if initial_text:
            text_lower = initial_text.lower().replace(" tu ", " to ")
            # Clean noise words to avoid "Gurgaon book a cab"
            for noise in ["book a cab", "book taxi", "book ride", "please", "again", "now", "want to go", "can you", "i wanna", "wanna", "need to"]:
                text_lower = text_lower.replace(noise, "")
            
            # Helper to check if location is "Generic" (needs alias match)
            def is_generic(loc):
                return any(x in loc.lower() for x in ["home", "work", "office", "gym", "hostel", "college", "school"])

            # Extract DROP
            if " to " in text_lower:
                parts = text_lower.split(" to ")
                if len(parts) > 1:
                    drop_loc = parts[1].split(" from ")[0].strip().title()
                    # Alias Check
                    if drop_loc.lower() in user_aliases:
                        drop_loc = user_aliases[drop_loc.lower()]
                    elif is_generic(drop_loc):
                        # Unknown Generic! Ignore it so we ask user.
                        drop_loc = None
                        
                    if drop_loc:
                        self.user_states[user_id]["data"]["drop"] = drop_loc
            
            # Extract PICKUP
            if " from " in text_lower:
                parts = text_lower.split(" from ")
                if len(parts) > 1:
                    pickup_loc = parts[1].split(" to ")[0].strip().title()
                    # Alias Check
                    if pickup_loc.lower() in user_aliases:
                        pickup_loc = user_aliases[pickup_loc.lower()]
                    elif is_generic(pickup_loc):
                         # Unknown Generic! Ignore.
                         pickup_loc = None
                         
                    if pickup_loc:
                        self.user_states[user_id]["data"]["pickup"] = pickup_loc
                    
        # Decide prompt based on what we dug up
        data = self.user_states[user_id]["data"]
        
        if data.get("pickup") and data.get("drop"):
            # We have BOTH! smart skip to options
            self.user_states[user_id]["state"] = "CHOOSING_RIDE" # Skip logical steps
            # We need to trigger handle_drop logic to generate options strictly speaking,
            # but let's just prompt user to Confirm defaults or just run handle_drop logic?
            # Better: Let the caller (telegram_main) handle the "Jump" if state changes.
            # Actually, let's just set state to PICKUP (if only drop known) or DROP (if only pickup known).
            
            # CASE A: Full Info -> "Confirm Route"
            self.user_states[user_id]["state"] = "CHOOSING_RIDE"
            dist_km = self._calculate_distance(user_id)
            data["distance_km"] = dist_km
            data["options"] = self._generate_ride_options(dist_km)
            return f"✅ Route: **{data['pickup']}** ➡️ **{data['drop']}**\nPlease select a ride below:"

        elif data.get("pickup"):
            # We have Pickup, need Drop
            self.user_states[user_id]["state"] = "DROP"
            return f"✅ Pickup Set: **{data['pickup']}**\n\n📍 Where do you want to go?"
            
        elif data.get("drop"):
            # We have Drop, need Pickup
            self.user_states[user_id]["state"] = "PICKUP" # Remains Pickup
            return f"✅ Destination: **{data['drop']}**\n\n📍 Where should I pick you up?"
            
        return "📍 Sending you a driver! First, where should I pick you up? (Send Location or Type Address)"

    def handle_pickup(self, user_id, text=None, lat=None, lon=None, resolved_address=None):
        # Determine Pickup
        if resolved_address:
            loc_str = resolved_address
        elif text:
            loc_str = text
        else:
            loc_str = "Shared Location"
            
        if lat and lon and not resolved_address:
             # In future, Reverse Geocode here too
             loc_str = f"Global Coords ({lat:.2f}, {lon:.2f})"
            
        # Update Data (Preserve existing data like 'drop')
        self.set_state(user_id, "DROP", {"pickup": loc_str, "pickup_lat": lat, "pickup_lon": lon})
        
        # [FIX] Check if we already have a Drop Location (from One-Shot parsing)
        data = self.user_states[user_id]["data"]
        if data.get("drop"):
             # We have both! Auto-advance to Options.
             self.set_state(user_id, "CHOOSING_RIDE")
             
             # Calculate Fare
             dist_km = self._calculate_distance(user_id)
             self.user_states[user_id]["data"]["distance_km"] = dist_km
             options = self._generate_ride_options(dist_km)
             self.user_states[user_id]["data"]["options"] = options
             
             return options # Return List (vs String)
        
        return f"✅ Pickup Set: **{loc_str}**\n\n📍 Now, where do you want to go? (Type Destination)"

    def handle_drop(self, user_id, text=None, lat=None, lon=None, resolved_address=None):
        # Determine Drop
        if resolved_address:
            loc_str = resolved_address
        elif text:
            loc_str = text
        else:
            loc_str = "Pinned Location"
            
        self.set_state(user_id, "CHOOSING_RIDE", {"drop": loc_str, "drop_lat": lat, "drop_lon": lon})
        
        # Estimate Distance (Mock Logic if no coords, Haversine if coords)
        dist_km = self._calculate_distance(user_id)
        self.user_states[user_id]["data"]["distance_km"] = dist_km
        
        # Calculate Fares
        options = self._generate_ride_options(dist_km)
        self.user_states[user_id]["data"]["options"] = options
        
        return options # Returns list of dicts for Renderer

    def select_vehicle(self, user_id, vehicle_id):
        current_data = self.get_state(user_id)["data"]
        options = current_data.get("options", [])
        
        selected = next((v for v in options if v["id"] == vehicle_id), None)
        if not selected:
            return None
            
        self.set_state(user_id, "WAITING_CONTACT", {"vehicle": selected})
        return f"✅ Selected {selected['name']}. Please share your Contact Number to confirm booking. 📱"

    def handle_contact(self, user_id, phone):
        # Generate OTP
        otp = str(random.randint(1000, 9999))
        self.set_state(user_id, "WAITING_OTP", {"phone": phone, "otp": otp})
        
        # In real world, send SMS. Here, return it for simulation.
        return f"🔐 OTP sent to {phone}. (Simulation: Your OTP is **{otp}**). Please enter it."

    def verify_otp(self, user_id, user_otp):
        data = self.get_state(user_id)["data"]
        # Allow any OTP for dev speed, or strict check
        if user_otp.strip() == data.get("otp") or user_otp == "0000":
            self.set_state(user_id, "TRACKING")
            driver = self._assign_driver(data["vehicle"]["name"])
            
            # Init Track Simulation
            self.user_states[user_id]["data"]["driver_dist"] = random.uniform(2.0, 5.0) # Starts 2-5km away
            self.user_states[user_id]["data"]["driver"] = driver
            
            return {
                "status": "success",
                "message": f"🎉 **Booking Confirmed!**\n\n🚖 {driver['name']} ({driver['car']})\n⭐ {driver['rating']}\n📍 Driver is {self.user_states[user_id]['data']['driver_dist']:.1f}km away.",
                "driver": driver
            }
        else:
            return {"status": "fail", "message": "❌ Incorrect OTP. Please try again."}

    def get_driver_update(self, user_id):
        """
        Simulates driver moving closer.
        Returns: (New Distance, Status Message, IsArrived)
        """
        data = self.get_state(user_id)["data"]
        current_dist = data.get("driver_dist", 2.0)
        
        # Move closer (0.3km to 0.8km per tick)
        move_step = random.uniform(0.3, 0.8)
        new_dist = max(0, current_dist - move_step)
        
        # Update State
        self.user_states[user_id]["data"]["driver_dist"] = new_dist
        
        driver = data.get("driver", {"name": "Driver", "car": "Taxi"})
        
        if new_dist <= 0.1:
            return 0, f"🚖 **{driver['name']} has Arrived!**\nMeet at pickup point.", True
        else:
            return new_dist, f"🚖 {driver['name']} ({driver['car']}) is **{new_dist:.1f} km** away...", False

    # --- Helpers ---
    def _calculate_distance(self, user_id):
        # If real coords exist, use Haversine. Else mock.
        data = self.user_states[user_id]["data"]
        if data.get("pickup_lat") and data.get("drop_lat"):
             return self._haversine(data["pickup_lat"], data["pickup_lon"], data["drop_lat"], data["drop_lon"])
        return random.randint(3, 15) # Mock 3-15km

    def cancel_ride(self, user_id):
        if user_id in self.user_states:
             self.user_states[user_id] = {"state": "IDLE", "data": {}}
             return "🚫 Ride Cancelled. You are back to start."
        return "🤷‍♂️ No active ride to cancel."

    def _generate_ride_options(self, dist_km):
        options = []
        # Simulate Surge (30% chance of Surge)
        is_surge = random.random() < 0.3
        surge_mult = random.uniform(1.2, 1.5) if is_surge else 1.0
        
        for vid, rules in self.pricing.items():
            base_fare = rules["base"] + (rules["per_km"] * dist_km)
            final_fare = base_fare * surge_mult
            
            duration = (dist_km / rules["speed_kmh"]) * 60
            
            name_display = rules["name"]
            if is_surge:
                name_display += " ⚡"
                
            options.append({
                "id": vid,
                "name": name_display,
                "price": int(final_fare),
                "eta": int(duration),
                "desc": f"{int(duration)} min • ₹{int(final_fare)}" + (" (High Demand)" if is_surge else "")
            })
        return options

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return round(R * c, 1)

    def _assign_driver(self, vehicle_name):
        names = ["Rajesh", "Suresh", "Ramesh", "Vikram", "Sunil"]
        cars = ["Swift Dzire", "WagonR", "Honda City", "Hyundai Aura"]
        if "Moto" in vehicle_name: cars = ["Splendor", "Activa", "Pulsar"]
        if "Auto" in vehicle_name: cars = ["Bajaj Auto"]
        
        return {
            "name": random.choice(names),
            "car": f"{random.choice(cars)} ({vehicle_name.split()[0]})",
            "rating": round(random.uniform(4.2, 4.9), 1)
        }
