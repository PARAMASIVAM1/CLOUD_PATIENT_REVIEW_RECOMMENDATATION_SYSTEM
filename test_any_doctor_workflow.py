import requests
from bs4 import BeautifulSoup
from app import app

client = app.test_client()

print("================================================================================")
print("TESTING DYNAMIC MULTI-DOCTOR APPOINTMENT & LOGIN WORKFLOW")
print("================================================================================")

# 1. Patient Login
with client.session_transaction() as sess:
    sess.clear()
login_res = client.post(
    "/login",
    data={"email": "patient@example.com", "password": "password123", "role": "user"},
    follow_redirects=True
)
assert login_res.status_code == 200
print("[PASS] 1. Patient logged in successfully as patient@example.com")

# 2. Book appointment with a distinct doctor from search (e.g. DR.Harish Rao1361, ID: 1361)
book_data = {
    "doctor_id": "1361",
    "doctor_name": "DR.Harish Rao1361",
    "hospital": "Apollo Hospitals",
    "specialization": "Cardiology",
    "appointment_date": "2026-10-15",
    "appointment_time": "11:30 AM - Morning",
    "disease": "Chest Pain & Tightness",
    "symptoms": "Chest pain, shortness of breath",
    "notes": "Testing multi-doctor appointment workflow",
    "phone": "9876543210"
}
book_res = client.post("/appointment/book", data=book_data, follow_redirects=False)
assert book_res.status_code == 302
apt_letter_url = book_res.headers["Location"]
print(f"[PASS] 2. Appointment successfully booked! Letter URL: {apt_letter_url}")

# 3. View Appointment Letter
letter_res = client.get(apt_letter_url)
assert letter_res.status_code == 200
html = letter_res.data.decode("utf-8")
assert "DR.Harish Rao1361" in html
assert "doctor123" in html
assert "/test/switch-doctor" in html
print("[PASS] 3. Appointment Letter renders with Dr. Harish Rao credentials and switch button")

# 4. Extract appointment ID
import re
apt_id_match = re.search(r'/appointment/(\d+)/letter', apt_letter_url)
assert apt_id_match is not None
apt_id = int(apt_id_match.group(1))

# 5. Use /test/switch-doctor to switch to Dr. Harish Rao
switch_res = client.post(
    "/test/switch-doctor",
    data={
        "doctor_id": "1361",
        "doctor_name": "DR.Harish Rao1361",
        "doctor_email": "drharishrao1361@hospital.com"
    },
    follow_redirects=False
)
assert switch_res.status_code == 302
assert "/doctor/dashboard" in switch_res.headers["Location"]
print("[PASS] 4. Seamlessly switched session to Dr. Harish Rao (role='doctor')")

# 6. Access Doctor Dashboard
dash_res = client.get("/doctor/dashboard")
assert dash_res.status_code == 200
dash_html = dash_res.data.decode("utf-8")
assert "Harish Rao" in dash_html
assert "Chest Pain" in dash_html
print("[PASS] 5. Dr. Harish Rao Dashboard loaded showing the pending appointment in queue")

# 7. Dr. Harish Rao Approves the Appointment
action_res = client.post(
    f"/doctor/appointment/{apt_id}/action",
    data={
        "action": "approve",
        "doctor_notes": "Consultation confirmed for Cardiology OPD. Please arrive 10 mins early."
    },
    follow_redirects=True
)
assert action_res.status_code == 200
print(f"[PASS] 6. Dr. Harish Rao approved appointment #{apt_id} successfully")

# 8. Verify status in database
from db import get_appointment_by_id
apt = get_appointment_by_id(apt_id)
assert apt["status"] == "Approved"
assert apt["doctor_email"] == "drharishrao1361@hospital.com"
print(f"[PASS] 7. Database appointment #{apt_id} confirmed 'Approved' with doctor_email: {apt['doctor_email']}")

# 9. Test direct manual login via /login with Doctor's Name and password 'doctor123'
with client.session_transaction() as sess:
    sess.clear()
doc_login_res = client.post(
    "/login",
    data={
        "email": "DR.Harish Rao1361",
        "role": "doctor",
        "password": "doctor123"
    },
    follow_redirects=False
)
assert doc_login_res.status_code == 302
assert doc_login_res.headers["Location"].endswith("/doctor/dashboard")
print("[PASS] 8. Direct login with Doctor Name 'DR.Harish Rao1361' + 'doctor123' works 100%!")

# 10. Test direct manual login via /login with another doctor: DR.Isha Rao13412 (Eye Specialist)
with client.session_transaction() as sess:
    sess.clear()
eye_login_res = client.post(
    "/login",
    data={
        "email": "drisharao13412@hospital.com",
        "role": "doctor",
        "password": "doctor123"
    },
    follow_redirects=False
)
assert eye_login_res.status_code == 302
assert eye_login_res.headers["Location"].endswith("/doctor/dashboard")
print("[PASS] 9. Direct login with Doctor Email 'drisharao13412@hospital.com' + 'doctor123' works 100%!")

print("================================================================================")
print("ALL 9 MULTI-DOCTOR WORKFLOW TESTS PASSED PERFECTLY!")
print("================================================================================")
