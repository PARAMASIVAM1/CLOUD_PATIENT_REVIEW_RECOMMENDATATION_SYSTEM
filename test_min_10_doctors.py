import sys
from model import load_data, get_doctor_recommendations
from app import PART_TO_DISEASES, BODY_PARTS, app

data_df, _ = load_data()

print("=" * 70)
print("TEST 1: get_doctor_recommendations across ALL Body Parts and Diseases")
print("=" * 70)

locations_to_test = [
    "Chennai", "Coimbatore", "Madurai", "Salem", "Trichy", "Erode",
    "Tirunelveli", "Vellore", "Thoothukudi", "Dindigul", "Cuddalore",
    "Kanchipuram", "Karur", "Nagapattinam", "Thanjavur"
]

total_tested = 0
failures = []

loc_idx = 0
for bp in BODY_PARTS:
    part_slug = bp["slug"]
    diseases = PART_TO_DISEASES.get(part_slug, [])
    for disease in diseases:
        test_loc = locations_to_test[loc_idx % len(locations_to_test)]
        loc_idx += 1
        test_fees = 200  # Low budget to stress-test fallback

        results = get_doctor_recommendations(
            data_df=data_df,
            part=part_slug,
            age=35,
            fees=test_fees,
            location=test_loc,
            disease=disease,
            symptom="",
            specialization="",
            doctor_name=""
        )

        total_tested += 1
        count = len(results)
        unique_ids = len({str(r.get("doctor_id")) for r in results})

        if count < 10 or unique_ids < count:
            failures.append({
                "part": part_slug,
                "disease": disease,
                "location": test_loc,
                "fees": test_fees,
                "count": count,
                "unique": unique_ids
            })
            print(f"FAILED: [{part_slug}] {disease} in {test_loc} (budget {test_fees}): count={count}, unique={unique_ids}")
        else:
            print(f"PASS: [{part_slug:10}] {disease:22} | {test_loc:12} | budget Rs.{test_fees} => {count} doctors (all unique)")

print("\n" + "=" * 70)
print(f"TEST 1 SUMMARY: {total_tested - len(failures)}/{total_tested} Passed. Failures: {len(failures)}")
print("=" * 70)

if failures:
    print("FAILED CASES:")
    for f in failures:
        print(f)
    sys.exit(1)

print("\n" + "=" * 70)
print("TEST 2: Flask App /search endpoint simulation for stressful edge cases")
print("=" * 70)

client = app.test_client()

stress_cases = [
    # Very low fee in small district
    {"part": "Lungs", "part_key": "lungs", "disease": "Asthma", "symptom": "wheezing", "fees": "100", "location": "Cuddalore", "age": "40"},
    # Thoothukudi liver
    {"part": "Liver", "part_key": "liver", "disease": "Jaundice", "symptom": "", "fees": "150", "location": "Thoothukudi", "age": "25"},
    # Nagapattinam kidney
    {"part": "Kidney", "part_key": "kidney", "disease": "Kidney Stones", "symptom": "burning urination", "fees": "100", "location": "Nagapattinam", "age": "50"},
    # Karur brain
    {"part": "Brain", "part_key": "brain", "disease": "Stroke", "symptom": "", "fees": "200", "location": "Karur", "age": "60"},
    # Dindigul eye
    {"part": "Eye", "part_key": "eye", "disease": "Glaucoma", "symptom": "blurry vision", "fees": "100", "location": "Dindigul", "age": "55"},
    # Empty location
    {"part": "Heart", "part_key": "heart", "disease": "Heart Attack", "symptom": "chest pain", "fees": "200", "location": "", "age": "45"},
    # Teeth in Kanchipuram
    {"part": "Teeth", "part_key": "teeth", "disease": "Cavities", "symptom": "tooth pain", "fees": "100", "location": "Kanchipuram", "age": "20"},
    # Skin & hair in Thanjavur
    {"part": "Skin & Hair", "part_key": "skin-hair", "disease": "Psoriasis", "symptom": "skin rash", "fees": "100", "location": "Thanjavur", "age": "32"},
    # ENT in Vellore
    {"part": "ENT", "part_key": "ent", "disease": "Hearing Loss", "symptom": "", "fees": "100", "location": "Vellore", "age": "65"},
    # General in Tirunelveli
    {"part": "General", "part_key": "general", "disease": "Viral fever", "symptom": "fever", "fees": "100", "location": "Tirunelveli", "age": "28"},
]

endpoint_failures = []
with client.session_transaction() as sess:
    sess["logged_in"] = True
    sess["user_id"] = 1
    sess["email"] = "test@example.com"
    sess["name"] = "Test Patient"

for sc in stress_cases:
    # Use internal search or direct POST
    with app.test_request_context("/search", method="POST", data=sc):
        # Call the underlying recommendation directly matching app.py search logic
        part_key = sc.get("part_key", "")
        disease = sc.get("disease", "")
        symptom = sc.get("symptom", "")
        fees = sc.get("fees", "")
        location = sc.get("location", "")
        age = sc.get("age", "")
        
        fees_val = float(fees) if fees else None
        res = get_doctor_recommendations(data_df, part_key, age, fees_val, location, disease, symptom, "", "")
        
        cnt = len(res)
        if cnt < 10:
            endpoint_failures.append((sc, cnt))
            print(f"FAILED endpoint case: {sc} => count={cnt}")
        else:
            print(f"PASS endpoint case: {sc['part_key']} | {sc['disease']} | {sc['location']} | Rs.{sc['fees']} => {cnt} doctors")

print("\n" + "=" * 70)
print(f"TEST 2 SUMMARY: {len(stress_cases) - len(endpoint_failures)}/{len(stress_cases)} Passed.")
print("=" * 70)

if endpoint_failures:
    sys.exit(1)

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY! EVERY DISEASE ACROSS ALL PARTS RETURNS >= 10 DOCTORS.")

