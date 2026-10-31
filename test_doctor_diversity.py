import app
from model import get_doctor_recommendations

tests = [
    ('heart', 'Heart Attack', 'Chennai'),
    ('eyes', 'Glaucoma', 'Chennai'),
    ('skin', 'Skin Allergy', 'Chennai'),
    ('lungs', 'Asthma', 'Chennai'),
    ('brain', 'Migraine', 'Chennai'),
    ('teeth', 'Tooth Decay', 'Chennai'),
    ('bones', 'Fracture', 'Chennai'),
    ('ent', 'Sinusitis', 'Chennai'),
]

print("=== 1. TESTING DIFFERENT BODY PARTS AND DISEASES ===")
results_map = {}
for part, disease, location in tests:
    recs = get_doctor_recommendations(
        app.DATA_DF,
        part=part,
        age=35,
        fees=1000,
        location=location,
        disease=disease,
        symptom="",
        specialization=""
    )
    results_map[(part, disease)] = set(d["doctor_id"] for d in recs[:10])
    print(f"\n[{part.upper()} - {disease}] (Total returned: {len(recs)})")
    for i in range(min(3, len(recs))):
        d = recs[i]
        print(f"  {i+1}. {d.get('doctor_name')} | Specialization: {d.get('specialization')} | Disease/Dept: {d.get('department')} | Hospital: {d.get('hospital')} | Rating: {d.get('average_rating')}")

print("\n=== OVERLAP CHECK ACROSS DIFFERENT BODY PARTS ===")
keys = list(results_map.keys())
cross_overlap_found = False
for i in range(len(keys)):
    for j in range(i+1, len(keys)):
        overlap = results_map[keys[i]].intersection(results_map[keys[j]])
        if overlap:
            print(f"WARNING: Overlap between {keys[i]} and {keys[j]}: {len(overlap)} doctors! (IDs: {overlap})")
            cross_overlap_found = True

if not cross_overlap_found:
    print("SUCCESS: 0% overlap between doctors of different body parts!")


print("\n=== 2. TESTING DIFFERENT DISEASES WITHIN THE SAME BODY PART ===")
same_part_tests = {
    'heart': ['Heart Attack', 'Hypertension', 'Arrhythmia'],
    'eyes': ['Glaucoma', 'Cataract', 'Conjunctivitis'],
    'skin': ['Skin Allergy', 'Acne', 'Psoriasis'],
    'lungs': ['Asthma', 'Pneumonia', 'Bronchitis'],
}

for part, diseases in same_part_tests.items():
    print(f"\n--- Checking Body Part: {part.upper()} ---")
    part_doc_map = {}
    for dis in diseases:
        recs = get_doctor_recommendations(
            app.DATA_DF,
            part=part,
            age=35,
            fees=1000,
            location='Chennai',
            disease=dis,
            symptom="",
            specialization=""
        )
        doc_names = [d.get("doctor_name") for d in recs[:5]]
        depts = [d.get("department") for d in recs[:5]]
        part_doc_map[dis] = set(d["doctor_id"] for d in recs[:10])
        print(f"  Disease '{dis}': Top 3 doctors:")
        for k in range(min(3, len(recs))):
            d = recs[k]
            print(f"     -> {d.get('doctor_name')} ({d.get('specialization')}) | Dept: {d.get('department')} | Hospital: {d.get('hospital')}")
    
    # Check overlap
    dis_list = list(part_doc_map.keys())
    for i in range(len(dis_list)):
        for j in range(i+1, len(dis_list)):
            overlap = part_doc_map[dis_list[i]].intersection(part_doc_map[dis_list[j]])
            print(f"     Overlap between '{dis_list[i]}' and '{dis_list[j]}': {len(overlap)}/10 common doctors")

