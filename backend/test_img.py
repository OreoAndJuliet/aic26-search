import requests
res = requests.get('http://localhost:8000/keyframes/L21_V008/6097.jpg')
print('Status:', res.status_code)
