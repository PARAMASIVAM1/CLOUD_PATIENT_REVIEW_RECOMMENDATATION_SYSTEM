import requests
import re

session = requests.Session()

# 1. Login
login_resp = session.post('http://127.0.0.1:5000/login', data={
    'email': 'santhosh@gmail.com',
    'password': 'santhosh@123',
    'role': 'patient'
})
assert login_resp.status_code == 200

# 2. Check dashboard HTML for new controls
dash_resp = session.get('http://127.0.0.1:5000/patient/dashboard')
print("Dashboard status:", dash_resp.status_code)
html = dash_resp.text

assert "Select All" in html, "Select All control missing!"
assert "Delete Selected" in html, "Delete Selected button missing!"
assert "Delete All" in html, "Delete All button missing!"
assert 'form="bulkDeleteForm"' in html, "Form connection missing!"

checkbox_ids = re.findall(r'class="apt-checkbox"[^>]*value="(\d+)"', html)
print(f"Checkboxes found for {len(checkbox_ids)} appointments:", checkbox_ids[:5])

# 3. Test Bulk Delete Selected (select 2 appointments)
if len(checkbox_ids) >= 2:
    to_delete = checkbox_ids[:2]
    print(f"Testing deleting selected 2 appointments: {to_delete}...")
    res = session.post('http://127.0.0.1:5000/appointments/bulk-delete', data={
        'action': 'selected',
        'appointment_ids': to_delete
    }, headers={'Referer': 'http://127.0.0.1:5000/patient/dashboard'})
    
    print("Delete selected status:", res.status_code, "URL:", res.url)
    assert res.status_code == 200
    assert "deleted+successfully" in res.url or "deleted successfully" in res.text
    
    # Verify they are gone
    dash_after = session.get('http://127.0.0.1:5000/patient/dashboard').text
    for did in to_delete:
        assert f'value="{did}"' not in dash_after, f"Appointment {did} should have been deleted!"
    print("✓ Successfully deleted selected appointments!")

# 4. Test Single Delete on one appointment
remaining_ids = re.findall(r'class="apt-checkbox"[^>]*value="(\d+)"', session.get('http://127.0.0.1:5000/patient/dashboard').text)
if remaining_ids:
    single_target = remaining_ids[0]
    print(f"Testing individual single delete on #{single_target}...")
    s_res = session.post(f'http://127.0.0.1:5000/appointment/{single_target}/delete', headers={
        'Referer': 'http://127.0.0.1:5000/patient/dashboard'
    })
    print("Single delete status:", s_res.status_code)
    assert s_res.status_code == 200
    dash_after_single = session.get('http://127.0.0.1:5000/patient/dashboard').text
    assert f'value="{single_target}"' not in dash_after_single
    print("✓ Individual delete still works perfectly!")

print("\nALL BATCH & INDIVIDUAL DELETE TESTS PASSED 100%!")

