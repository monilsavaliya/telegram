
import google.generativeai as genai

# MOCK DATA
API_KEYS = [
    "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs",
    "AIzaSyAtG1fj_q-HNSp_uAx6oIElLI_WBJOHdj4",
    "AIzaSyCC7mpkE7ANsVUfbFkapwBKGaTvkjRJKfA"
]

MODEL_ROTATION = [
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-pro'
]

def test_rotation():
    print("🔄 Testing Rotation Logic...")
    for key in API_KEYS:
        print(f"\n🔑 Testing Key: ...{key[-4:]}")
        genai.configure(api_key=key)
        
        for model_name in MODEL_ROTATION:
            print(f"  🤖 Model: {model_name}")
            try:
                model = genai.GenerativeModel(model_name)
                # Simple prompt
                res = model.generate_content("Say hi")
                print(f"    ✅ Success: {res.text.strip()}")
                return # Stop if one works
            except Exception as e:
                print(f"    ❌ Failed: {e}")

if __name__ == "__main__":
    test_rotation()
