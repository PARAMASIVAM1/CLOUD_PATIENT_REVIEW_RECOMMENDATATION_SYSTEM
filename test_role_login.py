from app import app

client = app.test_client()

# 1. Test Login Page HTML elements
res = client.get('/')
assert res.status_code == 200
html = res.data.decode('utf-8')
assert 'Email Address' in html
assert 'Select Role' in html
assert 'value="user"' in html
assert 'value="doctor"' in html
assert 'value="admin"' in html
assert 'Password' in html
print('[PASS] 1. Login page renders with Email, Role select, and Password')

# 2. Test Admin login with role='admin'
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'admin@healthcare.com', 'role': 'admin', 'password': 'admin123'}, follow_redirects=False)
assert res.status_code == 302
assert res.headers['Location'].endswith('/admin/dashboard')
with client.session_transaction() as sess:
    assert sess['user_role'] == 'admin'
print('[PASS] 2. Admin login with role=admin redirects to /admin/dashboard')

# 3. Test Doctor login with role='doctor'
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'drvikrampillai243@hospital.com', 'role': 'doctor', 'password': 'doctor123'}, follow_redirects=False)
assert res.status_code == 302
assert res.headers['Location'].endswith('/doctor/dashboard')
with client.session_transaction() as sess:
    assert sess['user_role'] == 'doctor'
print('[PASS] 3. Doctor login with role=doctor redirects to /doctor/dashboard')

# 4. Test Patient login with role='user'
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'patient@example.com', 'role': 'user', 'password': 'password123'}, follow_redirects=False)
assert res.status_code == 302
assert res.headers['Location'].endswith('/patient/dashboard') or res.headers['Location'].endswith('/home')
with client.session_transaction() as sess:
    assert sess['user_role'] == 'patient'
print('[PASS] 4. Patient login with role=user redirects to /home')

# 5. Test Doctor with wrong password
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'drvikrampillai243@hospital.com', 'role': 'doctor', 'password': 'wrongpassword'}, follow_redirects=True)
assert res.status_code == 200
assert b'Invalid email, password, or role combination' in res.data or b'Incorrect password for Doctor account' in res.data
print('[PASS] 5. Doctor login with invalid password correctly rejected')

# 6. Test cross-role warning: trying to login as user with admin email
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'admin@healthcare.com', 'role': 'user', 'password': 'admin123'}, follow_redirects=True)
assert res.status_code == 200
assert b'Admin account' in res.data or b'Invalid email, password, or role combination' in res.data
print('[PASS] 6. Cross-role awareness blocks and informs user')

# 7. Backward compatibility: login without role parameter
with client.session_transaction() as sess:
    sess.clear()
res = client.post('/login', data={'email': 'admin@healthcare.com', 'password': 'admin123'}, follow_redirects=False)
assert res.status_code == 302
assert res.headers['Location'].endswith('/admin/dashboard')
print('[PASS] 7. Backward compatibility auto-detection preserved')

print('\nALL 7 ROLE LOGIN TESTS PASSED 100%!')

