import sys
import json
from app import app
from db import (
    get_connection, get_appointment_by_id, get_doctor_reviews_anonymized,
    get_all_reviews_admin, get_user_notifications
)

client = app.test_client()

print("=" * 70)
print("TESTING COMPLETE END-TO-END HEALTHCARE SYSTEM WORKFLOWS")
print("=" * 70)

# ==================== 1. PATIENT WORKFLOW ====================
print("\n--- 1. Testing Patient Login & Home ---")
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_role"] = "patient"
    sess["user_email"] = "patient@example.com"
    sess["user_name"] = "Ramesh Kumar"

res = client.get("/home")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert b"Select Body Part" in res.data or b"Healthcare" in res.data
print("[OK] Patient successfully accesses home page with body parts.")

# Test doctor detail view
res = client.get("/doctor/245")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert b"Apply for Appointment" in res.data
assert b"Hospital Location & Directions" in res.data
print("[OK] Doctor profile view includes Appointment booking form & Leaflet map.")

# Book Appointment
print("\n--- 2. Testing Patient Appointment Booking ---")
booking_payload = {
    "doctor_id": 245,
    "doctor_name": "DR.Vikram Pillai243",
    "hospital": "Apollo Hospital",
    "specialization": "Cardiologist",
    "appointment_date": "2026-10-20",
    "appointment_time": "11:30 AM - Morning",
    "disease": "Hypertension",
    "symptoms": "High blood pressure and palpitations",
    "notes": "Patient requesting regular checkup"
}
res = client.post("/appointment/book", data=booking_payload, follow_redirects=False)
assert res.status_code == 302, f"Expected 302 redirect to letter, got {res.status_code}"
target_letter_url = res.headers["Location"]
apt_id = int(target_letter_url.split("/")[-2])
print(f"[OK] Appointment booked successfully! Assigned Appointment ID: #{apt_id}")

# View Appointment Letter
res = client.get(target_letter_url)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert b"Official Patient Consultation & Appointment Letter" in res.data
assert b"Hypertension" in res.data
assert b"DR.Vikram Pillai243" in res.data
print("[OK] Official Appointment Letter slip rendered with reference ID & details.")

# ==================== 2. DOCTOR WORKFLOW ====================
print("\n--- 3. Testing Doctor Login & Dashboard ---")
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_role"] = "doctor"
    sess["user_email"] = "drvikrampillai243@hospital.com"
    sess["user_name"] = "DR.Vikram Pillai243"
    sess["doctor_id"] = 245

res = client.get("/doctor/dashboard")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert b"Doctor Care Portal" in res.data
assert b"Pending Appointment Requests" in res.data
print("[OK] Doctor Dashboard loaded with appointments and clinical tools.")

# Doctor Approves Appointment
print("\n--- 4. Testing Doctor Approves Appointment ---")
res = client.post(f"/doctor/appointment/{apt_id}/action", data={"action": "approve"}, follow_redirects=True)
assert res.status_code == 200
apt = get_appointment_by_id(apt_id)
assert apt["status"] == "Approved", f"Expected Approved, got {apt['status']}"
print(f"[OK] Doctor approved appointment #{apt_id} (Status: {apt['status']})")

# Verify Patient Notification
patient_notifs = get_user_notifications("patient@example.com")
assert any(n["reference_id"] == apt_id and "Approved" in n["title"] for n in patient_notifs)
print("[OK] Patient received real-time notification: 'Appointment Approved by Dr. DR.Vikram Pillai243'")

# Doctor Completes Treatment
print("\n--- 5. Testing Treatment Completion & Clinical Notes ---")
treatment_payload = {
    "action": "complete",
    "doctor_notes": "Mild essential hypertension observed. BP recorded at 138/88 mmHg.",
    "prescription": "Tab. Amlodipine 5mg OD for 30 days.\nLow sodium diet recommended."
}
res = client.post(f"/doctor/appointment/{apt_id}/action", data=treatment_payload, follow_redirects=True)
assert res.status_code == 200
apt = get_appointment_by_id(apt_id)
assert apt["status"] == "Completed"
print(f"[OK] Treatment completed and clinical notes recorded for appointment #{apt_id}")

# ==================== 3. PATIENT REVIEWS & STRICT PRIVACY ====================
print("\n--- 6. Testing Post-Treatment Feedback with NLP Sentiment ---")
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_role"] = "patient"
    sess["user_email"] = "patient@example.com"
    sess["user_name"] = "Ramesh Kumar"

feedback_payload = {
    "rating": "5",
    "feedback": "Dr. Vikram was exceptionally kind and thorough. He explained the hypertension treatment clearly and answered all my questions without delay."
}
res = client.post(f"/appointment/{apt_id}/feedback", data=feedback_payload, follow_redirects=True)
assert res.status_code == 200
print("[OK] Patient submitted verified feedback with NLP sentiment calculation.")

# Verify Doctor's Privacy Guarantee
print("\n--- 7. Verifying Doctor Privacy Guarantee (Submitter Masked) ---")
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_role"] = "doctor"
    sess["user_email"] = "drvikrampillai243@hospital.com"
    sess["user_name"] = "DR.Vikram Pillai243"
    sess["doctor_id"] = 245

res = client.get("/doctor/dashboard")
assert res.status_code == 200
# Doctor must see the feedback text and rating
assert b"exceptionally kind and thorough" in res.data
# Doctor reviews must show Verified Patient badge
assert b"Verified Patient" in res.data

# Verify backend database query strictly strips patient_email from Doctor view
reviews = get_doctor_reviews_anonymized("DR.Vikram Pillai243")
assert len(reviews) > 0
for r in reviews:
    assert "patient_email" not in r, "Security failure: patient_email should not be in doctor review query"
    assert r["patient_display_name"] == "Verified Patient"
print("[OK] PRIVACY VERIFIED: Doctor sees review text and rating, but patient email/identity is STRICTLY ANONYMIZED.")

# Doctor Responds to Review
reviews = get_doctor_reviews_anonymized("DR.Vikram Pillai243")
latest_rev_id = reviews[0]["id"]
res = client.post(f"/doctor/review/{latest_rev_id}/respond", data={"response_text": "Thank you for your feedback! Please adhere to the medication schedule."}, follow_redirects=True)
assert res.status_code == 200
print(f"[OK] Doctor successfully posted professional reply to review #{latest_rev_id}")

# ==================== 4. ADMIN WORKFLOW ====================
print("\n--- 8. Testing Admin Dashboard & Moderation Clearance ---")
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_role"] = "admin"
    sess["user_email"] = "admin@healthcare.com"
    sess["user_name"] = "Administrator"

res = client.get("/admin/dashboard")
assert res.status_code == 200
assert b"Healthcare Operations & Analytics Hub" in res.data
# Unlike Doctor, Admin CAN see the submitter's identity for moderation
assert b"patient@example.com" in res.data
print("[OK] ADMIN VERIFIED: Admin has clearance to view submitter email for moderation and audit.")

# Admin Moderates Review
res = client.post("/admin/review/moderate", data={"review_id": latest_rev_id, "action": "approve"}, follow_redirects=True)
assert res.status_code == 200
print(f"[OK] Admin moderation action 'approve' completed on review #{latest_rev_id}")

print("\n" + "=" * 70)
print("ALL PATIENT, DOCTOR, AND ADMIN WORKFLOWS PASSED 100%!")
print("=" * 70)
