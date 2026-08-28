import requests
import json
import urllib.parse
url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'KIS',
    'text': 'Đoạn clip bắt đầu với cảnh một người đang dùng điện thoại chụp ảnh bức tranh hình tê giác trên tường. Đoạn clip kết thúc với cảnh một người chụp ảnh các hình graffiti 3 chú khỉ trên một cây cầu',
    'top_k': 100
}
try:
    res = requests.post(url, json=payload)
    data = res.json()
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        print(f"Type returned: {data.get('type')}")
        print(f"Number of results: {len(data.get('data', []))}")
    else:
        print(data)
except Exception as e:
    print(e)
