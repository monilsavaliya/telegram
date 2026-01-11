import google.generativeai as genai
import time

KEY = "AIzaSyCC7mpkE7ANsVUfbFkapwBKGaTvkjRJKfA"

print(f"🔍 Testing Key: ...{KEY[-5:]}")
genai.configure(api_key=KEY)

print("📋 Available Models:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" - {m.name}")
except Exception as e:
    print(f"❌ List Failed: {e}")

print("\n👉 Trying 'gemini-flash-latest'...")
try:
    model = genai.GenerativeModel('gemini-flash-latest')
    response = model.generate_content("Say hi")
    print(f"✅ SUCCESS")
except Exception as e:
    print(f"❌ FAIL: {e}")
