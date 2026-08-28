import requests

url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'TRAKE',
    'text': 'A yellow lion (or dragon/lion dance costume?) jumps or falls from above, near a small blue model ship.',
    'top_k': 100
}

try:
    res = requests.post(url, json=payload, timeout=30)
    data = res.json()
    for r in data.get('data', []):
        if r.get('frame_id') in [6300, 6678, 1200]:
            print(f"Video: {r.get('video_id')} Frame: {r.get('frame_id')}")
            print("Thumbnail:", r.get('thumbnail_url'))
except Exception as e:
    print(f"Error: {e}")
