
import google.generativeai as genai

KEY = "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs" # Taking one valid key

def list_models():
    genai.configure(api_key=KEY)
    print("📋 Listing Available Models:")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"  - {m.name}")
    except Exception as e:
        print(f"❌ Error Listing Models: {e}")

if __name__ == "__main__":
    list_models()
