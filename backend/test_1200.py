import requests
res = requests.get('http://localhost:8000/keyframes/L22_V030/1200.jpg')
print('Status 1200:', res.status_code)
