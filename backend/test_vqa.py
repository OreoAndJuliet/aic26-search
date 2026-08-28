import requests
import json

url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'VQA',
    'text': 'A yellow lion jumps from above',
    'question': 'Is there a yellow object in this image? Answer Yes or No.',
    'top_k': 5
}

print("Running VQA Search...")
try:
    res = requests.post(url, json=payload, timeout=300)
    data = res.json()
    print("\n--- VQA Search Results ---")
    for idx, r in enumerate(data.get('data', [])):
        print(f"{idx+1}. {r.get('video_id')}_{r.get('frame_id')} - Score: {r.get('score')} - VLM Answer: {r.get('answer')}")
except Exception as e:
    print(f"Error: {e}")
