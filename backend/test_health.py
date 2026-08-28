import requests
try:
    res = requests.get('http://localhost:8000/api/health')
    print('Status:', res.status_code)
except Exception as e:
    print('Error')
