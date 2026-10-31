import sys
sys.path.insert(0, r"c:\Users\Paramasivam\OneDrive\ドキュメント\vs code\ml website project")

import json
from app import app

client = app.test_client()

print("=" * 60)
print("TESTING REST APIS (CLOUD APPLICATION DEVELOPMENT REVIEW 2)")
print("=" * 60)

# 1. GET /api/hospitals
print("\n--- 1. Testing GET /api/hospitals ---")
res = client.get("/api/hospitals?limit=5")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
data = res.get_json()
assert data["success"] is True
assert "hospitals" in data
assert len(data["hospitals"]) > 0
print(f"[OK] GET /api/hospitals returned {data['count']} hospitals (Total in DB: {data['total']})")
print(f"     Sample hospital: {data['hospitals'][0]['hospital']} ({data['hospitals'][0]['location']})")

# 2. GET /api/doctors
print("\n--- 2. Testing GET /api/doctors ---")
res = client.get("/api/doctors?city=Chennai&limit=5")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
data = res.get_json()
assert data["success"] is True
assert "doctors" in data
assert len(data["doctors"]) > 0
print(f"[OK] GET /api/doctors returned {data['count']} doctors in Chennai (Total in DB: {data['total']})")
print(f"     Sample doctor: {data['doctors'][0]['doctor_name']} ({data['doctors'][0]['specialization']})")

# 3. GET /api/reviews
print("\n--- 3. Testing GET /api/reviews ---")
res = client.get("/api/reviews?limit=5")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
data = res.get_json()
assert data["success"] is True
assert "reviews" in data
print(f"[OK] GET /api/reviews returned {data['count']} reviews")
if data["reviews"]:
    sample_id = data["reviews"][0]["id"]
    print(f"     Sample review ID #{sample_id}: {data['reviews'][0]['review_text'][:50]}...")

# 4. POST /api/reviews (Auth check)
print("\n--- 4. Testing POST /api/reviews (Unauthorized) ---")
res = client.post("/api/reviews", json={"doctor_name": "Test", "rating": 5, "review_text": "Good"})
assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}"
print("[OK] Unauthenticated POST /api/reviews correctly rejected with 401")

# 5. POST /api/reviews (Authorized)
print("\n--- 5. Testing POST /api/reviews (Authorized) ---")
with client.session_transaction() as sess:
    sess['logged_in'] = True
    sess['user_name'] = 'Paramasivam'
    sess['user_email'] = 'paramasivam@example.com'

new_review_payload = {
    "doctor_name": "DR.Radhika Sharma23546",
    "hospital": "Velammal Hospital Chennai",
    "doctor_id": 23546,
    "rating": 5,
    "review_text": "The doctor was very friendly and kind, explained the treatment clearly without any delay.",
    "specialization": "Cardiologist",
    "location": "Chennai"
}

res = client.post("/api/reviews", json=new_review_payload)
assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.get_data(as_text=True)}"
created_data = res.get_json()
assert created_data["success"] is True
created_id = created_data["review"]["id"]
print(f"[OK] POST /api/reviews created review ID #{created_id}")
print(f"     Sentiment analyzed: {created_data['review']['sentiment_label']}")
print(f"     NLP factors: {created_data['review']['nlp_analysis']}")

# 6. PUT /api/reviews/<id> (Update review)
print(f"\n--- 6. Testing PUT /api/reviews/{created_id} ---")
update_payload = {
    "rating": 4,
    "review_text": "Doctor was great, but the hospital queue waiting time was a bit slow."
}
res = client.put(f"/api/reviews/{created_id}", json=update_payload)
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
updated_data = res.get_json()
assert updated_data["success"] is True
assert updated_data["review"]["patient_rating"] == 4
print(f"[OK] PUT /api/reviews/{created_id} updated successfully")
print(f"     New Rating: {updated_data['review']['patient_rating']}")
print(f"     New Sentiment: {updated_data['review']['sentiment_label']}")

# 7. DELETE /api/reviews/<id> (Delete review)
print(f"\n--- 7. Testing DELETE /api/reviews/{created_id} ---")
res = client.delete(f"/api/reviews/{created_id}")
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_data(as_text=True)}"
del_data = res.get_json()
assert del_data["success"] is True
print(f"[OK] DELETE /api/reviews/{created_id} deleted successfully")

# 8. Verify deletion
res = client.get(f"/api/reviews?id={created_id}")
verify_data = res.get_json()
assert len(verify_data["reviews"]) == 0
print(f"[OK] Verification check: Review #{created_id} no longer exists")

print("\n" + "=" * 60)
print("ALL 6 REST API TESTS PASSED 100% WITH JSON!")
print("=" * 60)

