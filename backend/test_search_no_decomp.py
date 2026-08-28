import requests
import json
import os

url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'KIS',
    'text': 'A yellow lion (or dragon/lion dance costume?) jumps or falls from above, near a small blue model ship.',
    'top_k': 20
}
res = requests.post(url, json=payload)
data = res.json()
print("Search results (No Concept Decomposition):")
for idx, r in enumerate(data.get('data', [])[:5]):
    print(f"{idx+1}. {r.get('video_id')}_{r.get('frame_id')} - Score: {r.get('score')}")
