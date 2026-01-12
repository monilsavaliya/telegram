from .amazon_api import AmazonAPI
from .context_engine import ContextEngine
from .card_renderer import ProductCardRenderer

class ShoppingBot:
    def __init__(self):
        self.api = AmazonAPI()
        self.context_engine = ContextEngine()
        self.renderer = ProductCardRenderer()
        self.sessions = {} # user_id -> {products: [], offset: 0, query: ""}

    def process_message(self, user_id, text, user_mood=None):
        """
        Main Handler.
        If text is 'next' or 'more', fetches next page from session.
        Else, treats as new search.
        """
        clean_text = text.lower().strip()
        
        # 1. Handle Pagination
        if clean_text in ["next", "more", "show more", "show me", "continue"] and user_id in self.sessions:
            return self.get_next_page(user_id)
            
        # 2. New Search
        return self.new_search(user_id, text, user_mood)

    def new_search(self, user_id, text, user_mood):
        # Analyze Context
        ctx = self.context_engine.analyze_context(text, mood=user_mood)
        
        # [PHASE 46] Context Refinement / Session Merging
        # If user says "under 300", ContextEngine extracts budget=300, and query becomes empty/noise.
        # In this case, we should REUSE the previous product query.
        
        is_refinement = False
        if user_id in self.sessions:
            last_session = self.sessions[user_id]
            last_query = last_session.get("query", "")
            
            # Heuristic: If new query is empty (just budget) or very short/attribute-like, merge.
            # For now, strict check: if query effectively empty but budget exists.
            cleaned_new_query = ctx["query"].strip()
            
            # If ContextEngine stripped everything (e.g. "under 300"), query might be empty
            if not cleaned_new_query and ctx["budget"]:
                print(f"🔄 Refinement Detected: Reusing '{last_query}' with new budget {ctx['budget']}")
                ctx["query"] = last_query # Restore old product term
                is_refinement = True
                
            # If user adds a simple attribute "black" or "mens", we could append?
            # Let's keep it simple: Budget Refinement is the main request.

        print(f"🧠 Context Analysis: {ctx}")
        
        # Fetch Data (Fetch more to allow pagination, e.g. 20 items)
        raw_products = self.api.search_products(ctx["query"], page=1)
        
        # Rank
        ranked_products = self._rank_products(raw_products, ctx)
        
        # Save Session
        # If refinement, keep the base query as the "main" one? Or update it?
        # Update it so "under 300" state is preserved if they say "under 200" next.
        self.sessions[user_id] = {
            "products": ranked_products,
            "offset": 0,
            "query": ctx["query"]
        }
        
        return self.get_next_page(user_id, direction="current")

    def get_next_page(self, user_id, direction="next"):
        session = self.sessions.get(user_id)
        if not session:
            return "❌ No active search. Type a product name to start shopping."
            
        products = session["products"]
        offset = session["offset"]
        limit = 1 # Single Card Mode
        
        # Calculate New Offset
        if direction == "next":
            new_offset = offset + limit
        elif direction == "prev":
            new_offset = max(0, offset - limit)
        else:
            new_offset = offset
            
        # Check Bounds
        if new_offset >= len(products):
            # If next goes out of bounds, maybe fetch more? For now, loop or stop.
            # Let's stop.
            return "🏁 End of results. Try a different search?"
            
        # Update Session
        session["offset"] = new_offset
        
        # Slice batch
        batch = products[new_offset : new_offset + limit]
        
        if not batch:
             return "🏁 End of results."
        
        # Render Single Card
        product_data = self.renderer.render_card(batch[0], index=new_offset + 1)
        
        # Navigation Buttons
        nav_buttons = []
        if new_offset > 0:
            nav_buttons.append({"text": "⬅️ Prev", "callback_data": "shopping_prev"})
        
        # Always allow next (unless last item? API might have more pages, but for now we have fixed list)
        if new_offset < len(products) - 1:
            nav_buttons.append({"text": "Next ➡️", "callback_data": "shopping_next"})
        
        # Construct Response Object (Dict)
        return {
            "type": "photo_card",
            "photo": product_data["image"],
            "caption": product_data["caption"],
            "buttons": [
                [{"text": "🛍️ Buy Now", "url": product_data["url"]}],
                nav_buttons
            ]
        }

    def _rank_products(self, products, context):
        """
        Sorts products based on:
        - Budget compliance
        - Rating (Stars * Count)
        - Price/Value ratio
        """
        scored = []
        for p in products:
            price_raw = p.get("product_price")
            if not price_raw:
                price_str = "0"
            else:
                price_str = str(price_raw).replace('$', '').replace('₹', '').replace(',', '')
                
            try:
                price = float(price_str)
            except:
                price = 0
                
            # Filter by Budget
            if context["budget"] and price > context["budget"]:
                continue
                
            rating = float(p.get("product_star_rating", 0) or 0)
            reviews = int(p.get("product_num_ratings", 0) or 0)
            
            # Simple Score: Logarithmic review count boost + Star rating
            score = rating * (reviews ** 0.5) 
            
            scored.append((score, p))
            
        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored]
        
    def is_slang(self, text):
        return self.context_engine.is_slang_detected(text)
