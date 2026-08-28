import requests
import json

url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'TRAKE',
    'text': 'Nhóm 5 người đang chơi đùa bên cạnh một con vật màu vàng. Một trong số đó đã mang một vật trông như trái bí đỏ đi giấu.',
    'top_k': 5
}

try:
    res = requests.post(url, json=payload, timeout=30)
    data = res.json()
    for r in data.get('data', [])[:5]:
        print(json.dumps(r, indent=2))
except Exception as e:
    print(f"Error: {e}")
