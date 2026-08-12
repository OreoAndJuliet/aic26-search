import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
model_name = os.environ.get("GEMINI_MODEL", "models/gemini-1.5-flash-latest")

if not api_key:
    print(" ERROR: API Key not found in .env")
    exit(1)

if not model_name.startswith("models/"):
    model_name = f"models/{model_name}"

client = genai.Client(api_key=api_key)
models = client.models.list()

print("Available models supporting generateContent:")
print("-" * 60)
available = []
for model in models:
    methods = getattr(model, "supported_actions", None) or getattr(
        model, "supported_generation_methods", []
    )
    if "generateContent" in methods:
        available.append(model.name)
        print(f"- {model.name}")

print("-" * 60)
if model_name in available:
    print(f" GEMINI_MODEL is available: {model_name}")
else:
    print(f" GEMINI_MODEL is not in available list: {model_name}")