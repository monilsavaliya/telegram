import requests
import json

# Pick first key to test
TEST_KEY = "AIzaSyACAUZNNmnUE7Ok_ljprRYonfBUJFBPMIs"

print("=" * 80)
print("STEP 1: Discovering all available models from Gemini API...")
print("=" * 80)

# List all models endpoint
list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={TEST_KEY}"

try:
    response = requests.get(list_url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        
        if "models" in data:
            models = data["models"]
            print(f"\n✅ Found {len(models)} models!\n")
            
            # Extract and categorize models
            generative_models = []
            other_models = []
            
            for model in models:
                model_name = model.get("name", "").replace("models/", "")
                supported_methods = model.get("supportedGenerationMethods", [])
                
                if "generateContent" in supported_methods:
                    generative_models.append(model_name)
                else:
                    other_models.append(model_name)
            
            print("=" * 80)
            print("GENERATIVE MODELS (Support text generation):")
            print("=" * 80)
            for m in generative_models:
                print(f"  • {m}")
            
            if other_models:
                print("\n" + "=" * 80)
                print("OTHER MODELS (Embedding/etc):")
                print("=" * 80)
                for m in other_models:
                    print(f"  • {m}")
            
            # Now test each generative model
            print("\n" + "=" * 80)
            print("STEP 2: Testing each generative model with a simple prompt...")
            print("=" * 80)
            
            for model_name in generative_models:
                test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={TEST_KEY}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": "Say hello"}]
                    }]
                }
                
                try:
                    test_response = requests.post(test_url, json=payload, timeout=5)
                    
                    if test_response.status_code == 200:
                        result_data = test_response.json()
                        if "candidates" in result_data and result_data["candidates"]:
                            reply = result_data["candidates"][0]["content"]["parts"][0]["text"]
                            print(f"✅ {model_name:40} | SUCCESS - Reply: {reply.strip()[:30]}")
                        else:
                            print(f"⚠️  {model_name:40} | 200 OK but empty response")
                    elif test_response.status_code == 429:
                        print(f"⚠️  {model_name:40} | RATE LIMITED (429) - Works but quota exceeded")
                    elif test_response.status_code == 404:
                        print(f"❌ {model_name:40} | NOT FOUND (404)")
                    elif test_response.status_code == 403:
                        print(f"❌ {model_name:40} | FORBIDDEN (403)")
                    else:
                        print(f"❌ {model_name:40} | ERROR ({test_response.status_code})")
                        
                except Exception as e:
                    print(f"❌ {model_name:40} | EXCEPTION: {str(e)[:40]}")
            
        else:
            print("❌ No 'models' field in response")
            print(f"Response: {response.text[:200]}")
    else:
        print(f"❌ Failed to list models: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Exception: {str(e)}")

print("\n" + "=" * 80)
print("Discovery complete!")
print("=" * 80)
