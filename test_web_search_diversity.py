import requests
from bs4 import BeautifulSoup

session = requests.Session()

# 1. Login as user
login_res = session.post(
    "http://localhost:5000/login",
    data={
        "email": "patient@example.com",
        "password": "password123",
        "role": "user"
    },
    allow_redirects=True
)

if "logout" not in login_res.text.lower() and "sign out" not in login_res.text.lower() and login_res.status_code == 200:
    # Check if login was successful
    print("Logged in successfully to Flask server.")

test_cases = [
    {"part": "Heart", "part_key": "heart", "disease": "Heart Attack", "location": "Chennai", "fees": "1000"},
    {"part": "Heart", "part_key": "heart", "disease": "Hypertension", "location": "Chennai", "fees": "1000"},
    {"part": "Eyes", "part_key": "eyes", "disease": "Glaucoma", "location": "Chennai", "fees": "1000"},
    {"part": "Eyes", "part_key": "eyes", "disease": "Cataract", "location": "Chennai", "fees": "1000"},
    {"part": "Skin", "part_key": "skin", "disease": "Skin Allergy", "location": "Chennai", "fees": "1000"},
    {"part": "Skin", "part_key": "skin", "disease": "Acne", "location": "Chennai", "fees": "1000"},
    {"part": "Lungs", "part_key": "lungs", "disease": "Asthma", "location": "Chennai", "fees": "1000"},
    {"part": "Lungs", "part_key": "lungs", "disease": "Pneumonia", "location": "Chennai", "fees": "1000"},
]

results = {}

for tc in test_cases:
    post_data = {
        "part": tc["part"],
        "part_key": tc["part_key"],
        "disease": tc["disease"],
        "age": "35",
        "fees": tc["fees"],
        "location": tc["location"],
        "symptom": "",
        "doctor_name": "",
        "feedback": "",
    }
    resp = session.post("http://localhost:5000/search", data=post_data, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Extract doctor cards / names from results.html
    # In results.html, doctor names are inside .doctor-card h2
    doc_cards = []
    for h in soup.select(".doctor-card h2"):
        txt = h.get_text(strip=True)
        if txt:
            doc_cards.append(txt)
            
    key = f"{tc['part_key']}:{tc['disease']}"
    results[key] = doc_cards
    print(f"\n[HTTP Search] {tc['part']} -> {tc['disease']}: Found {len(doc_cards)} doctors.")
    for d in doc_cards[:3]:
        print(f"   -> {d}")

print("\n=== WEB SEARCH DIVERSITY CHECK ===")
keys = list(results.keys())
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        k1, k2 = keys[i], keys[j]
        set1 = set(results[k1])
        set2 = set(results[k2])
        common = set1.intersection(set2)
        print(f"Comparison between '{k1}' vs '{k2}': {len(common)} common doctors.")
