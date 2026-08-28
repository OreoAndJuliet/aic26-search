import requests
import json
payload = {
    'query_type': 'KIS',
    'text': 'Nhóm 5 ngu?i dang choi dùa bên c?nh m?t con v?t màu vàng',
    'top_k': 1
}
try:
    res = requests.post('http://localhost:8000/api/v1/search', json=payload)
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f'Error: {e}')
