import requests
res = requests.get('http://localhost:8000/keyframes/L21_V008/6300.jpg')
print('Status 6300:', res.status_code)
