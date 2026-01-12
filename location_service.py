import httpx

class LocationService:
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.headers = {"User-Agent": "TaxiBot_Demo/1.0 (monil_project_demo)"}

    async def resolve_address(self, query):
        """
        Converts text like "iit gate" -> "IIT Delhi Main Gate, Hauz Khas..."
        Returns: (formatted_name, lat, lon) or None
        """
        if not query or len(query) < 3:
            return None

        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
                "countrycodes": "in" # Limit to India for relevance
            }
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.base_url, params=params, headers=self.headers, timeout=5.0)
                data = resp.json()
                
                if data:
                    item = data[0]
                    display_name = item.get("display_name", query)
                    # Shorten the name (OSM names are very long)
                    parts = display_name.split(",")
                    short_name = ", ".join(parts[:3]) # First 3 parts usu. enough
                    
                    return {
                        "address": short_name,
                        "full_address": display_name,
                        "lat": float(item["lat"]),
                        "lon": float(item["lon"])
                    }
        except Exception as e:
            print(f"⚠️ Geo-Resolution Failed: {e}")
            
        return None
