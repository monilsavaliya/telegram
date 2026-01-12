import sys
import os

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopping_service_dev.shopping_bot import ShoppingBot

def run():
    bot = ShoppingBot()
    user_id = "cli_user"
    
    print("🛍️  Real-Time Amazon Shopping Bot (RapidAPI Powered)")
    print("---------------------------------------------------")
    print("Type 'exit' to quit. Type 'next' to see more results.")
    
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ["exit", "quit"]:
                break
                
            # Changed to use process_message which handles pagination internally
            results = bot.process_message(user_id, user_input, user_mood="Neutral")
            print(results)
                    
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    run()
