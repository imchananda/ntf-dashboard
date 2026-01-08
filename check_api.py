import requests

# Check dashboard.py API
print("Checking dashboard.py API (port 8080):")
try:
    r = requests.get('http://localhost:8080/api/votes', timeout=5)
    data = r.json()
    for item in data.get('latest_summary', []):
        if item['code'] in ['YND06', 'YND10']:
            print(f"  {item['code']}: {item['points']}")
except Exception as e:
    print(f"  Error: {e}")

print()

# Check dashboard_two.py API
print("Checking dashboard_two.py API (port 5001):")
try:
    r = requests.get('http://localhost:5001/api/data', timeout=5)
    data = r.json()
    for item in data.get('summary', []):
        if item['code'] in ['YND06', 'YND10']:
            print(f"  {item['code']}: {item['votes']}")
except Exception as e:
    print(f"  Error: {e}")
