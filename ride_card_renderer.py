from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class RideCardRenderer:
    def render_vehicle_options(self, options):
        """
        Renders a list of vehicles as a message with Inline Buttons.
        Format:
        Choose your ride:
        
        🚗 Uber Go - ₹150 (15 min)
        [Select Uber Go]
        
        🛺 Auto - ₹80 (20 min)
        [Select Auto]
        """
        
        text = "🚖 **Choose Your Ride**\n\n"
        buttons = []
        
        for opt in options:
            # Add details to text
            text += f"**{opt['name']}**\n⏱️ {opt['eta']} mins • ₹{opt['price']}\n\n"
            
            # Button for this specific vehicle
            buttons.append([InlineKeyboardButton(
                text=f"Book {opt['name']} - ₹{opt['price']}", 
                callback_data=f"book_taxi_{opt['id']}"
            )])
            
        keyboard = InlineKeyboardMarkup(buttons)
        return text, keyboard

    def render_driver_card(self, driver):
        """
        Renders the final driver confirmation card.
        """
        text = (
            f"✅ **Ride Confirmed!**\n\n"
            f"🚖 **{driver['car']}**\n"
            f"👤 **{driver['name']}** ⭐ {driver['rating']}\n"
            f"📍 Arriving shortly."
        )
        return text
