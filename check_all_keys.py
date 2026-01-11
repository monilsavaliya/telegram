import google.generativeai as genai

# List of API Keys provided by user
API_KEYS = [
    "AIzaSyDZcgDrkUMhR9E7oyV67m7PI4RttkqvVTE",       # Key 1
    "AIzaSyD0xLiqIW2wO6Hb7Zu5aHDIG6Oqtrxla88",       # Key 2
    "AIzaSyC_e_8Nt2IGIGcsZebEd6orEvWPft2yF_4",       # Key 3
    "AIzaSyDT8Kj6V7SdN5nQ5U16W4vE3MwQIQJ3Cvw"        # Key 4
]

print("🔍 Checking API Keys & Models...\n")

for i, key in enumerate(API_KEYS):
    print(f"🔑 Testing Key {i+1}: ...{key[-5:]}")
    genai.configure(api_key=key)
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                models.append(m.name)
        
        print(f"   ✅ Active! Found {len(models)} models.")
        # Check specific ones we care about
        for desired in ['models/gemini-2.0-flash', 'models/gemini-1.5-flash', 'models/gemini-1.5-pro']:
            if desired in models:
                print(f"      - {desired} (Available)")
            else:
                print(f"      - {desired} (MISSING)")
                
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    print("-" * 40)
