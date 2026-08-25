import requests, time, json

url = 'http://127.0.0.1:5000'
email = f"test+{int(time.time())}@example.com"
print('Using email:', email)

reg_payload = {
    'company_name': 'TestCo',
    'full_name': 'Tester',
    'email': email,
    'password': 'TestPass123!'
}

try:
    r = requests.post(url + '/api/auth/register', json=reg_payload, timeout=30)
    print('REGISTER', r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
except Exception as e:
    print('REGISTER ERROR', e)

try:
    s = requests.post(url + '/api/auth/login', json={'email': email, 'password': 'TestPass123!'}, timeout=30)
    print('LOGIN', s.status_code)
    try:
        print(json.dumps(s.json(), indent=2))
    except Exception:
        print(s.text)
except Exception as e:
    print('LOGIN ERROR', e)
