class ProductCardRenderer:
    def __init__(self):
        pass

    def render_card(self, product, index=1):
        """
        Converts raw Amazon API product data into a rich Markdown card.
        """
        title = product.get("product_title", "Unknown Product")[:60] + "..." # Truncate long titles
        price = product.get("product_price", "N/A")
        rating = product.get("product_star_rating", "N/A")
        reviews = product.get("product_num_ratings", 0)
        
        # Affiliate Tag Integration
        # Ensure we don't break existing params if they exist (though RapidAPI usually gives clean canonicals)
        base_url = product.get("product_url", "#")
        affiliate_tag = "shopsy05-21"
        
        if "?" in base_url:
            url = f"{base_url}&tag={affiliate_tag}"
        else:
            url = f"{base_url}?tag={affiliate_tag}"
            
        image = product.get("product_photo", "")
        
        # Prime check (RapidAPI sometimes returns is_prime)
        is_prime = product.get("is_prime", False)
        prime_badge = "⚡ *Prime Delivery*" if is_prime else ""

        card_text = (
            f"*{index}. {title}*\n"
            f"💰 *Price:* {price}  |  ⭐ *Rating:* {rating}/5 ({reviews})\n"
            f"{prime_badge}\n"
        )
        
        return {
            "type": "product_card",
            "image": image,
            "caption": card_text,
            "url": url,
            "title": title
        }

    def render_list(self, products, start_index=1):
        """
        Renders a list of products.
        """
        if not products:
            return "❌ No products found matching your criteria."
            
        cards = [self.render_card(p, start_index + i) for i, p in enumerate(products)]
        
        header = f"🛍️ *Top Picks #{start_index}-{start_index + len(products) - 1}*\n\n"
        footer = "\nType 'Next' to see more results."
        return header + "\n".join(cards) + footer
