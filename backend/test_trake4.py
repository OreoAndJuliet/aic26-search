import requests

url = 'http://localhost:8000/api/v1/search'
payload = {
    'query_type': 'TRAKE',
    'text': 'Nhóm 5 người đang chơi đùa bên cạnh một con vật màu vàng. Một trong số đó đã mang một vật trông như trái bí đỏ đi giấu.',
    'top_k': 100
}

try:
    res = requests.post(url, json=payload, timeout=30)
    data = res.json()
    for r in data.get('data', []):
        if r.get('frame_id') == 6300:
            print("Thumbnail for 6300:", r.get('thumbnail_url'))
            print("Image URL for 6300:", r.get('image_url'))
            print("Image path for 6300:", r.get('image_path'))
except Exception as e:
    print(f"Error: {e}")
