import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    test_cases = [
        {"part": "chest", "disease": "Chest Pain & Breathing", "expected_part": "chest"},
        {"part": "brain", "disease": "Migraine Headache", "expected_part": "brain"},
        {"part": "eyes", "disease": "Blurred Vision", "expected_part": "eyes"},
        {"part": "teeth", "disease": "Severe Toothache", "expected_part": "teeth"},
        {"part": "skin-hair", "disease": "Skin Allergy Itching", "expected_part": "skin-hair"}
    ]
    
    for idx, tc in enumerate(test_cases, 1):
        print(f"\n======================================================================")
        print(f"TESTING CASE #{idx}: {tc['part'].upper()} ({tc['disease']})")
        print(f"======================================================================")
        
        # Fresh patient session for each test
        s = requests.Session()
        login_res = s.post(f"{BASE_URL}/login", data={
            "email": "patient@example.com",
            "password": "password123",
            "role": "patient"
        }, allow_redirects=True)
        assert login_res.status_code == 200, f"Login failed: {login_res.status_code}"
        print("  [PASS] 1. Patient logged in successfully")
        
        # 1. Find Doctors
        search_url = f"{BASE_URL}/search?part={tc['part']}&disease={requests.utils.quote(tc['disease'])}"
        search_res = s.get(search_url)
        assert search_res.status_code == 200, f"Search failed with status {search_res.status_code}"
        
        soup = BeautifulSoup(search_res.text, "html.parser")
        profile_links = [a["href"] for a in soup.find_all("a", href=True) if re.match(r"^/doctor/\d+", a["href"])]
        assert len(profile_links) > 0, f"No doctor profile links found for {tc['part']}!"
        
        target_profile_link = profile_links[0]
        print(f"  [PASS] 2. Found {len(profile_links)} doctors. Selected profile link: {target_profile_link}")
        
        # 2. View Doctor Profile
        profile_res = s.get(f"{BASE_URL}{target_profile_link}")
        assert profile_res.status_code == 200
        p_soup = BeautifulSoup(profile_res.text, "html.parser")
        
        # Verify booking form
        form = p_soup.find("form", action="/appointment/book")
        assert form is not None, "Booking form missing on doctor profile!"
        
        doc_id = form.find("input", {"name": "doctor_id"})["value"]
        doc_name = form.find("input", {"name": "doctor_name"})["value"]
        hospital = form.find("input", {"name": "hospital"})["value"]
        specialization = form.find("input", {"name": "specialization"})["value"]
        date_input = form.find("input", {"name": "appointment_date"})
        disease_input = form.find("input", {"name": "disease"})
        
        print(f"  [PASS] 3. Doctor Profile loaded: {doc_name} ({specialization}) at {hospital}")
        print(f"         Pre-filled Date: '{date_input.get('value', '')}', Pre-filled Disease: '{disease_input.get('value', '')}'")
        assert date_input.get("value"), "Date input should be pre-filled!"
        assert disease_input.get("value"), "Disease input should be pre-filled!"
        
        # 3. Apply for Appointment Letter (Submit Booking Form)
        book_res = s.post(f"{BASE_URL}/appointment/book", data={
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "hospital": hospital,
            "specialization": specialization,
            "appointment_date": date_input.get("value"),
            "appointment_time": "09:30 AM - Morning",
            "disease": disease_input.get("value"),
            "symptoms": "Moderate discomfort, consulting specialist",
            "notes": f"Automated test for {tc['part']}"
        }, allow_redirects=True)
        
        assert book_res.status_code == 200
        assert "appointment" in book_res.url and "letter" in book_res.url, f"Expected letter URL, got {book_res.url}"
        print(f"  [PASS] 4. Appointment successfully booked! Letter URL: {book_res.url}")
        
        # 4. Check Appointment Letter Content & Doctor Email
        letter_soup = BeautifulSoup(book_res.text, "html.parser")
        doc_login_code = letter_soup.find(id="docLoginEmail")
        assert doc_login_code is not None, "docLoginEmail element missing on appointment letter!"
        
        displayed_email = doc_login_code.text.strip()
        print(f"  [PASS] 5. Appointment Letter displays Doctor Login Email: {displayed_email}")
        
        # Verify doctor name is on the page
        assert doc_name.lower() in book_res.text.lower(), f"Doctor name '{doc_name}' not on letter page!"
        
        # Verify displayed email matches the chosen doctor
        clean_doc = re.sub(r"[^a-zA-Z0-9]", "", doc_name.lower())
        assert clean_doc[:6] in displayed_email.lower(), f"Email {displayed_email} does not match doctor name {doc_name}!"
        
        # 5. Test "Switch to Dr. <name> & Approve" button
        switch_res = s.post(f"{BASE_URL}/test/switch-doctor", data={
            "doctor_id": doc_id,
            "doctor_name": doc_name,
            "doctor_email": displayed_email
        }, allow_redirects=True)
        assert switch_res.status_code == 200
        assert "doctor/dashboard" in switch_res.url, f"Switch doctor failed! URL: {switch_res.url}"
        print(f"  [PASS] 6. Switch to Doctor dashboard worked seamlessly for {doc_name}")
        
        # 6. Test Direct Login at /login with this doctor's email and password
        doc_session = requests.Session()
        doc_login_res = doc_session.post(f"{BASE_URL}/login", data={
            "email": displayed_email,
            "password": "doctor123",
            "role": "doctor"
        }, allow_redirects=True)
        assert "doctor/dashboard" in doc_login_res.url, f"Direct doctor login failed! URL: {doc_login_res.url}"
        print(f"  [PASS] 7. Direct login with '{displayed_email}' + 'doctor123' succeeded 100%!")

    print("\n" + "=" * 70)
    print("ALL 5 BODY PARTS & APPOINTMENT LETTER WORKFLOW TESTS PASSED 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
