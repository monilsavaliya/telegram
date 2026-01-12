import re

class ContextEngine:
    def __init__(self):
        # Comprehensive Slang Mapping (Source: Reddit, Indian Internet, GenZ)
        self.slang_map = {
            # --- Explicit / Intimate (Amazon Specific) ---
            "sex toys": "personal body wand massager vibration",
            "vibrator": "cordless body massager for women",
            "dildo": "silicone body massager tool",
            "fleshlight": "male stimulation sleeve",
            "fuck my date": "condoms and massage oil", 
            "i wanna fuck": "condoms and lubricants",
            "horny": "adult pleasure accessories",
            "masturbate": "personal massager vibration",
            "sex": "intimate wellness products",
            "toys": "personal body massager",
            "lubricant": "personal lubricant gel",
            "oil": "sensual massage oil",
            "condom": "durex condoms for men",
            
            # --- Indian Locality / Desi Internet Slang ---
            "chapri": "neon sunglasses and skinny jeans",  # Stereotypical fashion
            "nibba": "large teddy bear gift",             # "Couple" gifts
            "nibbi": "chocolates and heart pillow",
            "jugaad": "diy repair tool kit",
            "systumm": "loud bass speakers",              # Elvish Yadav / Car culture
            "system": "smartwatches and gadgets",
            "mahaul": "party speakers and disco lights",
            "scene": "party wear clothes",                # "Kya scene hai?" -> Party
            "shag": "energy drinks",                      # Indian context: "Too tired/shagged" -> Energy
            "bt": "headache balm and stress relief",      # "Bad Trip" -> Stress relief
            "bhasad": "fidget toys for stress",
            "kalti": "travel bags",                       # "Kalti maar" -> Travel/Escape
            "pataka": "ethnic party wear for women",
            "tot": "crop tops and trendy fashion",        # "Totta"
            "kadak": "premium intense coffee",
            "bawa": "leather jackets and accessories",    # Parsi/Mumbai slang
            "dhinchak": "sequin shiny clothing",
            "timepass": "snacks and munchies",
            
            # --- Reddit / Global GenZ / Internet Culture ---
            "drip": "streetwear aesthetics",
            "riz": "men's grooming kit",
            "rizz": "men's grooming and perfume",
            "gymrat": "creatine and whey protein",
            "touch grass": "hiking gear and camping",
            "based": "gigachad meme merch",
            "delulu": "manifestation journal",
            "aesthetic": "sunset lamp and vines",
            "coquette": "bows and lace dresses",
            "cottagecore": "floral dresses and tea sets",
            "dark academia": "tweed blazers and fountain pens",
            "goblincore": "mushroom decor and earthy clothes",
            "normcore": "plain white tees and denim",
            "old money": "polo shirts and linen trousers",
            "y2k": "baggy jeans and baby tees",
            "simp": "bouquets and chocolates",
            "girl math": "sale items under 500",
            "boy math": "expensive gaming consoles",
            "cap": "baseball caps",
            "no cap": "authentic branded shoes",
            "slay": "party heels and dresses",
            "main character": "sunglasses and statement jewelry",
            "npc": "grey hoodies and plain cargo pants",
            "sus": "spy cameras",
            "yeet": "throwing frisbee",
            "uwu": "kawaii plushies and anime merch",
            "waifu": "anime body pillow",
            "ick": "cleaning supplies and hygiene",
            "mid": "budget earphones",                    # "Mid" -> Average/Budget
            
            # --- Trendy / Viral / Aesthetics ---
            "trendy": "viral trending products instagram",
            "viral": "tiktok made me buy it products",
            "hot": "bestsellers current month",
            "cool": "newest tech gadgets",
            "latest": "new launch products 2024",
            "fyp": "trending aesthetically pleasing items",
            "aesthetic": "pinterest room decor",
            "pinterest": "aesthetic room decor and outfits",
            "instagramable": "photogenic props and lighting",
            "influencer": "ring lights and tripods",
            
            # --- Rich / Luxury / Status ---
            "rich": "luxury branded watches and perfumes",
            "classy": "minimalist old money outfits",
            "premium": "high end electronics",
            "lux": "luxury home decor gold accents",
            "expensive": "branded designer accessories",
            "flex": "apple products and accessories",
            "status": "premium leather goods",
            "boujee": "high end fashion accessories",
            
            # --- Tech / Gaming Specific ---
            "pc mr": "rtx graphic cards",                 # PC Master Race
            "console peasant": "playstation 5 games",
            "keeb": "mechanical keyboard",
            "battlestation": "rgb led strips",
            "setup": "monitor arms and desk mats",
        }
    def analyze_context(self, text, mood=None, past_history=None):
        """
        Extracts:
        1. Refined Search Query (handling slang)
        2. Budget (Capacity)
        3. Intent (Gift vs Self, etc - basic heuristic)
        """
        analysis = {
            "query": text,
            "budget": None,
            "is_slang": False,
            "mood_influence": mood,
            "filters": {}
        }

        # 0. User Behavior / History Integration
        # If the user has a history of "expensive" taste, default budget might be higher.
        # If they often buy "tech", we might bias vague queries to tech.
        if past_history:
             if past_history.get("purchase_capacity") == "high":
                 analysis["filters"]["min_price"] = 1000
             if past_history.get("interest") == "tech":
                 pass # Logic to bias vague terms

        # 1. Slang Detection & Mapping
        # Sort by length to match longer phrases first (e.g. "fuck my date" before "fuck")
        cleaned = text.lower()
        sorted_keys = sorted(self.slang_map.keys(), key=len, reverse=True)
        
        for slang in sorted_keys:
            if slang in cleaned:
                # If specific slang found, override query or append
                analysis["query"] = self.slang_map[slang]
                analysis["is_slang"] = True
                break

        # 1.5 Clean Noise/Fillers
        # Remove common non-search words to avoid generic searches
        noise_words = ["suggest", "show", "me", "find", "search", "looking", "for", "please", "can", "you", "give", "recommend", "no", "and", "some", "a", "an", "the"]
        
        # Only clean if it's not a slang term (slang is specific)
        if not analysis["is_slang"]:
            tokens = cleaned.split()
            filtered = [t for t in tokens if t not in noise_words]
            if filtered:
                cleaned = " ".join(filtered)
                analysis["query"] = cleaned
            
        # 2. Budget Extraction (e.g., "under 500", "below 2k", "price 1000")
        budget_match = re.search(r'(?:under|below|price|budget)\s?(?:of)?\s?(\d+(?:k)?)', cleaned)
        if budget_match:
            val_str = budget_match.group(1)
            full_match = budget_match.group(0) # Get the full "under 500" string
            
            if 'k' in val_str:
                budget = int(val_str.replace('k', '')) * 1000
            else:
                budget = int(val_str)
            analysis["budget"] = budget
            
            # Remove budget params from query to clean it up for search
            # Only remove the matched part
            cleaned = cleaned.replace(full_match, "").strip()
            analysis["query"] = cleaned
            
        # 3. Mood Injection (if query is vague)
        if len(analysis["query"].split()) < 2 and mood:
            if mood == "Sad":
                analysis["query"] = f"comfort {analysis['query']}"
            elif mood == "Excited":
                analysis["query"] = f"party {analysis['query']}"

        return analysis

    def is_slang_detected(self, text):
        """Public check for slang existence."""
        cleaned = text.lower()
        # Fast generic check first
        for s in self.slang_map:
             if s in cleaned: return True
        return False
