import pandas as pd
import random
import re
import hashlib
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import LabelEncoder
import difflib
import pickle
from pathlib import Path

DATA_PATH = "Final_20Hospitals_Per_District.xlsx"
FALLBACK_DATA_PATH = "dataset.csv"
DATA_SHEET = "Sheet1"
FAQ_PATH = "faq.csv"
CACHE_PATH = Path(__file__).resolve().parent / "data_cache.pkl"

vectorizer = None
sentiment_model = None
label_encoder = None
faq_vectorizer = None
faq_tfidf = None
doctor_examples = []
dataset_condition_guidance = {}
GENERIC_QUERY_WORDS = {
    "what", "should", "know", "about", "disease", "diseases", "doctor",
    "specialist", "condition", "problem", "issue", "symptom", "symptoms",
    "medical", "health", "need", "see", "visit", "for", "i", "my", "a", "an", "the"
}

CONDITION_GUIDANCE = {
    "fever": {
        "keywords": ["fever", "temperature", "viral fever", "body pain with fever"],
        "title": "Fever",
        "possible_reasons": [
            "Viral or bacterial infection",
            "Inflammation in the body",
            "Dehydration or heat exposure",
        ],
        "medicines": [
            "Paracetamol or acetaminophen (Rs. 10-20 per 10 tablets) is commonly used to reduce fever",
            "Ibuprofen (Rs. 15-30 per 10 tablets) may help in some adults if it is safe for them, but avoid it without medical advice if you have kidney problems, ulcers, or are pregnant",
        ],
        "self_care": [
            "Drink plenty of water and rest",
            "Check temperature regularly",
            "Wear light clothing and avoid overheating",
        ],
        "specialist": "General Physician",
        "emergency": [
            "Fever above 103 F or 39.4 C",
            "Breathing trouble, confusion, seizure, or severe weakness",
            "Fever lasting more than 3 days",
        ],
    },
    "cold": {
        "keywords": ["cold", "cough and cold", "runny nose", "common cold"],
        "title": "Common Cold",
        "possible_reasons": [
            "Viral upper respiratory infection",
            "Allergy or weather-triggered irritation",
            "Sinus congestion",
        ],
        "medicines": [
            "Paracetamol can help with fever or body pain",
            "Saline nasal spray or steam inhalation may help nasal blockage",
            "Cough syrup may help depending on the type of cough, but it should be chosen carefully",
        ],
        "self_care": [
            "Take rest and drink warm fluids",
            "Use steam inhalation for congestion relief",
            "Avoid smoking and cold irritants",
        ],
        "specialist": "General Physician or ENT Specialist",
        "emergency": [
            "Shortness of breath",
            "High fever or chest pain",
            "Symptoms worsening after a few days",
        ],
    },
    "headache": {
        "keywords": ["headache", "migraine", "head pain"],
        "title": "Headache",
        "possible_reasons": [
            "Stress or poor sleep",
            "Migraine or eye strain",
            "Dehydration, sinusitis, or infection",
        ],
        "medicines": [
            "Paracetamol (Rs. 10-20 per 10 tablets) is commonly used for mild headache",
            "Ibuprofen (Rs. 15-30 per 10 tablets) may help some people if it is medically safe for them",
        ],
        "self_care": [
            "Rest in a quiet and dark room",
            "Drink water and avoid skipping meals",
            "Reduce screen time if eye strain is suspected",
        ],
        "specialist": "General Physician, Neurologist, or Ophthalmologist depending on symptoms",
        "emergency": [
            "Sudden severe headache",
            "Headache with weakness, fainting, or vision loss",
            "Headache after injury or with persistent vomiting",
        ],
    },
    "stomach pain": {
        "keywords": ["stomach pain", "abdominal pain", "gastric pain", "stomach ache"],
        "title": "Stomach Pain",
        "possible_reasons": [
            "Gas, indigestion, or acidity",
            "Food infection or gastritis",
            "Appendix, gallbladder, or intestinal problems",
        ],
        "medicines": [
            "Antacids like Digene (Rs. 20-40 per bottle) are commonly used for acidity or indigestion",
            "ORS (Rs. 10-20 per packet) may help if there is vomiting or loose motion causing dehydration",
        ],
        "self_care": [
            "Eat light food and avoid oily or spicy meals",
            "Drink water in small amounts",
            "Monitor whether pain is related to food, vomiting, or bowel changes",
        ],
        "specialist": "General Physician or Gastroenterologist",
        "emergency": [
            "Severe or one-sided pain",
            "Blood in stool or vomit",
            "Persistent vomiting, high fever, or rigid abdomen",
        ],
    },
    "tooth pain": {
        "keywords": ["tooth pain", "toothache", "teeth pain", "dental pain"],
        "title": "Tooth Pain",
        "possible_reasons": [
            "Tooth decay or cavity",
            "Gum infection or swelling",
            "Cracked tooth or sensitivity",
        ],
        "medicines": [
            "Paracetamol (Rs. 10-20 per 10 tablets) is commonly used for pain relief",
            "Dentists may prescribe antibiotics like Amoxicillin (Rs. 50-100 per strip) only if there is an infection, so do not start them on your own",
        ],
        "self_care": [
            "Rinse with warm salt water",
            "Avoid very hot, cold, or sugary food",
            "Brush gently and keep the area clean",
        ],
        "specialist": "Dentist",
        "emergency": [
            "Facial swelling",
            "Fever with dental pain",
            "Difficulty swallowing or opening the mouth",
        ],
    },
    "chest pain": {
        "keywords": ["chest pain", "heart pain", "tightness in chest"],
        "title": "Chest Pain",
        "possible_reasons": [
            "Heart-related problem",
            "Acidity or gastric reflux",
            "Muscle strain, anxiety, or lung problem",
        ],
        "medicines": [
            "Do not self-medicate for unexplained chest pain",
            "If you already have doctor-prescribed emergency heart medication, use it exactly as instructed by your doctor",
        ],
        "self_care": [
            "Stop activity and sit down",
            "Seek urgent medical evaluation",
            "Note whether pain spreads to arm, jaw, or back",
        ],
        "specialist": "Cardiologist or Emergency Care",
        "emergency": [
            "Chest pain with sweating, breathlessness, or fainting",
            "Pain spreading to the arm, jaw, or back",
            "Known heart disease with new chest discomfort",
        ],
    },
    "skin rash": {
        "keywords": ["skin rash", "rash", "itching", "allergy", "skin allergy"],
        "title": "Skin Rash or Allergy",
        "possible_reasons": [
            "Allergic reaction",
            "Fungal, bacterial, or viral skin infection",
            "Reaction to soap, food, medicine, or heat",
        ],
        "medicines": [
            "Calamine lotion (Rs. 30-50 per bottle) or mild anti-itch creams may help some simple rashes",
            "Antihistamines like Cetirizine (Rs. 20-40 per 10 tablets) are commonly used for allergy symptoms, but they should be chosen carefully based on age and medical history",
        ],
        "self_care": [
            "Avoid scratching",
            "Use mild soap and keep the area dry",
            "Stop any recently started cosmetic or skin product if it seems to trigger the rash",
        ],
        "specialist": "Dermatologist",
        "emergency": [
            "Swelling of lips or face",
            "Breathing difficulty",
            "Fast-spreading rash, fever, or skin peeling",
        ],
    },
}

CONDITION_GUIDANCE.update({
    "diabetes": {
        "keywords": ["diabetes", "blood sugar", "high sugar", "frequent urination", "excess thirst"],
        "title": "Diabetes",
        "possible_reasons": [
            "High blood glucose due to reduced insulin action",
            "Family history, obesity, or lifestyle factors",
            "Hormonal or metabolic health conditions",
        ],
        "medicines": [
            "Doctors may use metformin or other diabetes medicines depending on the patient",
            "Insulin may be needed in some situations",
        ],
        "self_care": [
            "Monitor blood sugar regularly",
            "Follow a controlled diet and regular exercise plan",
            "Take medicines exactly as prescribed",
        ],
        "specialist": "Diabetologist, Endocrinologist, or General Physician",
        "emergency": [
            "Very high sugar with vomiting or drowsiness",
            "Confusion, dehydration, or difficulty breathing",
            "Repeated low sugar episodes",
        ],
    },
    "hypertension": {
        "keywords": ["bp", "high blood pressure", "hypertension", "pressure problem"],
        "title": "High Blood Pressure",
        "possible_reasons": [
            "Stress, salt-heavy diet, and low physical activity",
            "Kidney, hormone, or heart-related causes",
            "Family history or obesity",
        ],
        "medicines": [
            "Blood pressure tablets must be chosen by a doctor",
            "Do not stop prescribed BP medicines suddenly",
        ],
        "self_care": [
            "Reduce salt intake",
            "Check blood pressure regularly",
            "Exercise, sleep well, and avoid smoking",
        ],
        "specialist": "General Physician or Cardiologist",
        "emergency": [
            "BP very high with severe headache or chest pain",
            "Breathing difficulty or weakness on one side",
            "Blurred vision or confusion",
        ],
    },
    "asthma": {
        "keywords": ["asthma", "wheezing", "breathlessness", "shortness of breath", "chest tightness"],
        "title": "Asthma",
        "possible_reasons": [
            "Airway inflammation and allergy triggers",
            "Dust, smoke, infection, or weather changes",
            "Exercise or strong smells in sensitive people",
        ],
        "medicines": [
            "Inhalers are commonly used for relief and control",
            "Use asthma medicines only as directed by a doctor",
        ],
        "self_care": [
            "Avoid known triggers like dust and smoke",
            "Keep prescribed inhalers available",
            "Seek review if you need the reliever inhaler often",
        ],
        "specialist": "Pulmonologist or General Physician",
        "emergency": [
            "Severe breathlessness or bluish lips",
            "Unable to speak full sentences",
            "Reliever inhaler not helping",
        ],
    },
    "arthritis": {
        "keywords": ["arthritis", "joint pain", "joint swelling", "stiff joints", "swollen joints"],
        "title": "Arthritis or Joint Inflammation",
        "possible_reasons": [
            "Wear-and-tear joint disease",
            "Inflammatory arthritis",
            "Old injury or infection-related joint issues",
        ],
        "medicines": [
            "Pain relief and anti-inflammatory medicines may be used based on the condition",
            "Some patients also need physiotherapy guidance",
        ],
        "self_care": [
            "Avoid overloading painful joints",
            "Use doctor-advised exercises",
            "Track swelling, morning stiffness, and fever",
        ],
        "specialist": "Orthopedic Doctor or Rheumatology Review",
        "emergency": [
            "Very hot swollen joint with fever",
            "Sudden inability to bear weight",
            "Severe deformity or injury",
        ],
    },
    "sinusitis": {
        "keywords": ["sinus", "sinusitis", "nose congestion", "facial pressure", "nasal blockage"],
        "title": "Sinusitis",
        "possible_reasons": [
            "Infection or allergy-related sinus swelling",
            "Cold leading to blocked drainage",
            "Dust or weather-triggered irritation",
        ],
        "medicines": [
            "Saline rinse and steam may help congestion",
            "Other medicines depend on the cause and should be doctor-guided",
        ],
        "self_care": [
            "Use steam inhalation carefully",
            "Drink fluids and rest",
            "Avoid dust and smoke",
        ],
        "specialist": "ENT Specialist",
        "emergency": [
            "Eye swelling or severe facial pain",
            "High fever with worsening symptoms",
            "Symptoms not improving after many days",
        ],
    },
    "dengue": {
        "keywords": ["dengue", "platelet", "mosquito fever", "high fever with body pain"],
        "title": "Dengue",
        "possible_reasons": [
            "Mosquito-borne viral infection",
            "Seasonal outbreaks in some places",
            "Low fluid intake can worsen weakness during illness",
        ],
        "medicines": [
            "Paracetamol may be used for fever only if a doctor says it is suitable",
            "Avoid self-medicating with strong painkillers unless medically advised",
        ],
        "self_care": [
            "Drink plenty of fluids",
            "Monitor weakness, bleeding, and urine output",
            "Follow blood test advice if given by a doctor",
        ],
        "specialist": "General Physician",
        "emergency": [
            "Bleeding, black stool, severe stomach pain, or repeated vomiting",
            "Extreme weakness, fainting, or confusion",
            "Very low urine output",
        ],
    },
    "typhoid": {
        "keywords": ["typhoid", "enteric fever", "prolonged fever", "stomach pain with fever"],
        "title": "Typhoid",
        "possible_reasons": [
            "Bacterial infection from contaminated food or water",
            "Poor sanitation exposure",
            "Delayed treatment can worsen dehydration and weakness",
        ],
        "medicines": [
            "Typhoid needs doctor-prescribed antibiotics",
            "ORS and fluids may help prevent dehydration",
        ],
        "self_care": [
            "Drink safe water and eat light food",
            "Take the full course of prescribed treatment",
            "Rest and monitor fever pattern",
        ],
        "specialist": "General Physician",
        "emergency": [
            "Persistent high fever with confusion",
            "Severe abdominal pain or repeated vomiting",
            "Signs of dehydration",
        ],
    },
    "malaria": {
        "keywords": ["malaria", "fever with chills", "shivering fever", "mosquito bite fever"],
        "title": "Malaria",
        "possible_reasons": [
            "Mosquito-borne parasitic infection",
            "Travel or stay in affected areas",
            "Delayed treatment can increase severity",
        ],
        "medicines": [
            "Malaria treatment depends on test results and medical evaluation",
            "Do not start medicines without diagnosis confirmation",
        ],
        "self_care": [
            "Get tested if fever with chills keeps returning",
            "Drink fluids and rest",
            "Monitor fever timing and weakness",
        ],
        "specialist": "General Physician",
        "emergency": [
            "Confusion, breathing trouble, or severe weakness",
            "Persistent vomiting or seizures",
            "Very high fever not settling",
        ],
    },
    "pneumonia": {
        "keywords": ["pneumonia", "lung infection", "cough with fever", "chest infection"],
        "title": "Pneumonia",
        "possible_reasons": [
            "Bacterial, viral, or fungal lung infection",
            "Weak immunity or older age can increase risk",
            "Untreated infection may affect breathing",
        ],
        "medicines": [
            "Treatment depends on the cause and severity",
            "Doctor-guided antibiotics may be needed in some cases",
        ],
        "self_care": [
            "Rest well and drink fluids",
            "Monitor cough, fever, and breathing",
            "Do not ignore chest pain or breathlessness",
        ],
        "specialist": "Pulmonologist or General Physician",
        "emergency": [
            "Shortness of breath or bluish lips",
            "Chest pain with low oxygen symptoms",
            "Confusion or very high fever",
        ],
    },
    "bronchitis": {
        "keywords": ["bronchitis", "persistent cough", "chest congestion", "mucus cough"],
        "title": "Bronchitis",
        "possible_reasons": [
            "Airway infection or inflammation",
            "Smoking, pollution, or viral illness",
            "Sometimes follows a cold or flu",
        ],
        "medicines": [
            "Treatment depends on whether the cause is viral, bacterial, or allergic",
            "Cough medicines should be chosen carefully",
        ],
        "self_care": [
            "Rest and drink warm fluids",
            "Avoid smoking and dust exposure",
            "Monitor for wheezing or breathlessness",
        ],
        "specialist": "General Physician or Pulmonologist",
        "emergency": [
            "Breathing trouble",
            "High fever with chest pain",
            "Cough worsening significantly",
        ],
    },
    "tuberculosis": {
        "keywords": ["tb", "tuberculosis", "cough for weeks", "weight loss with cough"],
        "title": "Tuberculosis",
        "possible_reasons": [
            "Bacterial infection affecting the lungs or other organs",
            "Close contact with an infected person",
            "Low immunity can increase risk",
        ],
        "medicines": [
            "TB needs confirmed diagnosis and a full doctor-prescribed treatment course",
            "Do not stop treatment early if it is started",
        ],
        "self_care": [
            "Get tested for chronic cough, fever, or weight loss",
            "Maintain nutrition and follow-up regularly",
            "Take medicines exactly as prescribed",
        ],
        "specialist": "Chest Physician or General Physician",
        "emergency": [
            "Breathing trouble or coughing blood",
            "Severe weakness or persistent fever",
            "Unable to eat or drink properly",
        ],
    },
    "kidney stone": {
        "keywords": ["kidney stone", "renal stone", "side pain", "stone pain", "urine stone"],
        "title": "Kidney Stone",
        "possible_reasons": [
            "Mineral crystal formation in the urinary tract",
            "Low water intake",
            "Dietary and metabolic factors",
        ],
        "medicines": [
            "Pain relief and other treatment depend on the stone size and location",
            "Some cases need procedures by a specialist",
        ],
        "self_care": [
            "Drink enough water unless a doctor restricts fluids",
            "Track pain, fever, and urine symptoms",
            "Seek review if pain is severe or recurrent",
        ],
        "specialist": "Urologist or General Physician",
        "emergency": [
            "Severe side pain with vomiting",
            "Fever with urine blockage symptoms",
            "Blood in urine with severe weakness",
        ],
    },
    "uti": {
        "keywords": ["uti", "urine infection", "burning urination", "frequent urination", "urinary infection"],
        "title": "Urinary Tract Infection",
        "possible_reasons": [
            "Bacterial infection in the urinary tract",
            "Low fluid intake or delayed urination",
            "Sometimes associated with stones or diabetes",
        ],
        "medicines": [
            "UTI often needs doctor-advised antibiotics",
            "Fluids may help but do not replace treatment",
        ],
        "self_care": [
            "Drink water regularly",
            "Do not hold urine for long periods",
            "Seek testing if symptoms continue",
        ],
        "specialist": "General Physician or Urologist",
        "emergency": [
            "Fever with back pain",
            "Vomiting or severe weakness",
            "Blood in urine or severe pain",
        ],
    },
    "appendicitis": {
        "keywords": ["appendicitis", "right lower stomach pain", "appendix pain", "lower abdomen pain"],
        "title": "Appendicitis",
        "possible_reasons": [
            "Inflammation or infection of the appendix",
            "Pain often worsens over time and may shift location",
            "Delayed treatment can be risky",
        ],
        "medicines": [
            "Do not self-treat suspected appendicitis at home",
            "Treatment usually needs urgent doctor evaluation",
        ],
        "self_care": [
            "Avoid delaying hospital review",
            "Track fever, vomiting, and pain location",
            "Do not eat heavily if surgery is being considered",
        ],
        "specialist": "General Surgeon or Emergency Care",
        "emergency": [
            "Severe stomach pain with fever or vomiting",
            "Pain getting worse quickly",
            "Rigid abdomen or difficulty walking due to pain",
        ],
    },
    "gastritis": {
        "keywords": ["gastritis", "acidity", "burning stomach", "indigestion", "stomach burning"],
        "title": "Gastritis or Acidity",
        "possible_reasons": [
            "Acid irritation in the stomach lining",
            "Spicy food, irregular meals, alcohol, or certain medicines",
            "Infection or stress can also contribute",
        ],
        "medicines": [
            "Antacids or acid-reducing medicines may be used if a doctor feels they are suitable",
            "Avoid overusing pain tablets that irritate the stomach",
        ],
        "self_care": [
            "Eat light meals and avoid spicy or oily food",
            "Do not skip meals",
            "Reduce alcohol and smoking",
        ],
        "specialist": "General Physician or Gastroenterologist",
        "emergency": [
            "Black stool or vomiting blood",
            "Severe persistent stomach pain",
            "Repeated vomiting or dehydration",
        ],
    },
    "ulcer": {
        "keywords": ["ulcer", "stomach ulcer", "gastric ulcer", "peptic ulcer"],
        "title": "Peptic Ulcer",
        "possible_reasons": [
            "Acid injury in the stomach or upper intestine",
            "Certain medicines or bacterial infection",
            "Smoking and alcohol may worsen symptoms",
        ],
        "medicines": [
            "Acid-reducing medicines are often used under medical advice",
            "Treatment may also depend on infection testing",
        ],
        "self_care": [
            "Avoid spicy food, smoking, and alcohol",
            "Take medicines regularly if prescribed",
            "Seek review for persistent pain or vomiting",
        ],
        "specialist": "Gastroenterologist or General Physician",
        "emergency": [
            "Vomiting blood or black stool",
            "Sudden severe abdominal pain",
            "Severe weakness or fainting",
        ],
    },
    "eczema": {
        "keywords": ["eczema", "dry itchy skin", "skin patch itching", "dermatitis"],
        "title": "Eczema or Dermatitis",
        "possible_reasons": [
            "Skin barrier irritation and inflammation",
            "Allergy, dryness, soap, or weather triggers",
            "Family history can play a role",
        ],
        "medicines": [
            "Moisturizers and doctor-advised skin creams are commonly used",
            "Avoid random steroid creams without guidance",
        ],
        "self_care": [
            "Use mild soap and moisturize regularly",
            "Avoid scratching and trigger products",
            "Keep nails short if itching is severe",
        ],
        "specialist": "Dermatologist",
        "emergency": [
            "Spreading infection with pus or fever",
            "Severe swelling or skin cracking",
            "Breathing trouble after a trigger",
        ],
    },
    "psoriasis": {
        "keywords": ["psoriasis", "scaly skin patches", "thick skin patch"],
        "title": "Psoriasis",
        "possible_reasons": [
            "Chronic inflammatory skin condition",
            "Immune-related process",
            "Stress and skin injury may worsen flares",
        ],
        "medicines": [
            "Topical creams and other treatments depend on severity",
            "Doctor review is important before starting long-term treatment",
        ],
        "self_care": [
            "Moisturize the skin regularly",
            "Avoid harsh skin products",
            "Track flare triggers like stress or infection",
        ],
        "specialist": "Dermatologist",
        "emergency": [
            "Widespread painful skin inflammation",
            "Joint pain with severe skin flare",
            "Fever with skin worsening",
        ],
    },
    "conjunctivitis": {
        "keywords": ["conjunctivitis", "eye infection", "red eye", "itchy eye", "watering eye"],
        "title": "Eye Infection or Conjunctivitis",
        "possible_reasons": [
            "Viral or bacterial eye infection",
            "Allergy or irritant exposure",
            "Poor eye hygiene or contact lens issues",
        ],
        "medicines": [
            "Artificial tears may soothe irritation",
            "Other eye drops must be chosen carefully by a doctor",
        ],
        "self_care": [
            "Avoid rubbing the eyes",
            "Wash hands often and use a clean towel",
            "Avoid sharing cosmetics or eye drops",
        ],
        "specialist": "Ophthalmologist",
        "emergency": [
            "Vision loss or severe eye pain",
            "Marked swelling or light sensitivity",
            "Symptoms getting worse in contact lens users",
        ],
    },
    "cataract": {
        "keywords": ["cataract", "blurred vision in old age", "cloudy vision"],
        "title": "Cataract",
        "possible_reasons": [
            "Lens clouding in the eye, often age-related",
            "Diabetes, injury, or some medicines can contribute",
            "Vision gradually becomes cloudy or dim",
        ],
        "medicines": [
            "Medicines do not usually remove cataract",
            "Eye specialist evaluation is needed to plan treatment",
        ],
        "self_care": [
            "Use proper glasses if advised",
            "Avoid driving if vision becomes unsafe",
            "Get regular eye checkups",
        ],
        "specialist": "Ophthalmologist",
        "emergency": [
            "Sudden major vision drop",
            "Eye pain with blurred vision",
            "Injury-related eye symptoms",
        ],
    },
    "glaucoma": {
        "keywords": ["glaucoma", "eye pressure", "vision field loss", "eye nerve problem"],
        "title": "Glaucoma",
        "possible_reasons": [
            "Raised eye pressure damaging the optic nerve",
            "Family history can increase risk",
            "Often needs early diagnosis to protect vision",
        ],
        "medicines": [
            "Eye drops and other treatments must be prescribed by an eye specialist",
            "Do not skip regular follow-up if diagnosed",
        ],
        "self_care": [
            "Attend eye pressure checkups regularly",
            "Take drops exactly as prescribed",
            "Report any sudden eye pain or vision changes",
        ],
        "specialist": "Ophthalmologist",
        "emergency": [
            "Sudden severe eye pain",
            "Halos around lights with vomiting",
            "Rapid vision loss",
        ],
    },
    "anemia": {
        "keywords": ["anemia", "low hemoglobin", "pale skin", "tiredness", "weakness"],
        "title": "Anemia",
        "possible_reasons": [
            "Low hemoglobin due to iron deficiency or other causes",
            "Blood loss, poor diet, or chronic disease",
            "Sometimes linked with vitamin deficiency",
        ],
        "medicines": [
            "Treatment depends on the cause after testing",
            "Iron or vitamin supplements should be used only if appropriate",
        ],
        "self_care": [
            "Get blood tests if weakness is persistent",
            "Eat iron-rich foods if medically suitable",
            "Follow treatment and repeat testing if advised",
        ],
        "specialist": "General Physician",
        "emergency": [
            "Very severe weakness or shortness of breath",
            "Heavy bleeding",
            "Fainting or chest discomfort",
        ],
    },
    "thyroid disorder": {
        "keywords": ["thyroid", "thyroid disorder", "neck gland problem", "hormone imbalance"],
        "title": "Thyroid Disorder",
        "possible_reasons": [
            "Low or high thyroid hormone levels",
            "Autoimmune or gland-related conditions",
            "Symptoms vary from weight change to tiredness or palpitations",
        ],
        "medicines": [
            "Thyroid treatment depends on blood test results",
            "Dose adjustment should be done only by a doctor",
        ],
        "self_care": [
            "Get thyroid function tests if advised",
            "Take medicines consistently if prescribed",
            "Track weight, energy level, and heart symptoms",
        ],
        "specialist": "Endocrinologist or General Physician",
        "emergency": [
            "Severe palpitations or confusion",
            "Extreme weakness or breathlessness",
            "Rapid symptom worsening",
        ],
    },
    "depression": {
        "keywords": ["depression", "low mood", "sadness", "loss of interest", "mental health"],
        "title": "Depression",
        "possible_reasons": [
            "Mental health condition affecting mood and daily function",
            "Stress, trauma, biology, or long-term illness can contribute",
            "Sleep and appetite changes may also occur",
        ],
        "medicines": [
            "Treatment may involve counseling, therapy, and sometimes medicines",
            "Mental health medicines must be doctor-guided",
        ],
        "self_care": [
            "Seek support early instead of waiting",
            "Maintain sleep, food, and routine as much as possible",
            "Talk to a trusted person or professional",
        ],
        "specialist": "Psychiatrist or Clinical Psychologist",
        "emergency": [
            "Self-harm thoughts or suicidal thoughts",
            "Severe inability to function",
            "Confusion or extreme agitation",
        ],
    },
    "anxiety": {
        "keywords": ["anxiety", "panic", "panic attack", "excess worry", "nervousness"],
        "title": "Anxiety or Panic Symptoms",
        "possible_reasons": [
            "Stress response or anxiety disorder",
            "Sleep problems, caffeine, or emotional triggers",
            "Some physical illnesses can mimic anxiety symptoms",
        ],
        "medicines": [
            "Treatment may include counseling and sometimes medicines",
            "Do not self-medicate with sedatives",
        ],
        "self_care": [
            "Try slow breathing and reduce stimulant intake",
            "Track triggers and sleep pattern",
            "Seek mental health support if symptoms recur",
        ],
        "specialist": "Psychiatrist, Psychologist, or General Physician",
        "emergency": [
            "Chest pain or breathing trouble needing immediate evaluation",
            "Self-harm thoughts",
            "Severe confusion or uncontrolled panic",
        ],
    },
    "covid-19": {
        "keywords": ["covid", "coronavirus", "covid-19", "pandemic fever", "loss of taste"],
        "title": "COVID-19",
        "possible_reasons": [
            "Viral infection caused by SARS-CoV-2",
            "Spread through respiratory droplets",
            "Symptoms can range from mild to severe",
        ],
        "medicines": [
            "Treatment depends on severity; some cases need hospitalization",
            "Vaccines and preventive measures are key",
        ],
        "self_care": [
            "Isolate if symptoms appear",
            "Wear masks and maintain hygiene",
            "Monitor fever, cough, and breathing",
        ],
        "specialist": "General Physician or Infectious Disease Specialist",
        "emergency": [
            "Difficulty breathing or chest pain",
            "High fever with confusion",
            "Blue lips or severe weakness",
        ],
    },
    "cancer": {
        "keywords": ["cancer", "tumor", "malignancy", "oncology", "chemo"],
        "title": "Cancer",
        "possible_reasons": [
            "Uncontrolled cell growth leading to tumors",
            "Genetic, environmental, or lifestyle factors",
            "Early detection improves outcomes",
        ],
        "medicines": [
            "Treatment includes surgery, chemotherapy, radiation, or targeted therapy",
            "Always under oncologist guidance",
        ],
        "self_care": [
            "Follow screening recommendations",
            "Maintain healthy lifestyle",
            "Seek support for emotional well-being",
        ],
        "specialist": "Oncologist",
        "emergency": [
            "Severe pain or bleeding",
            "Difficulty breathing or swallowing",
            "Sudden worsening of symptoms",
        ],
    },
    "stroke": {
        "keywords": ["stroke", "brain attack", "paralysis", "sudden weakness", "speech loss"],
        "title": "Stroke",
        "possible_reasons": [
            "Blockage or rupture of blood vessels in the brain",
            "High blood pressure, diabetes, or smoking increases risk",
            "Requires immediate medical attention",
        ],
        "medicines": [
            "Emergency treatment like clot-busting drugs if applicable",
            "Long-term prevention with blood thinners or BP control",
        ],
        "self_care": [
            "Control risk factors like BP and diabetes",
            "Exercise and healthy diet",
            "Recognize FAST signs: Face drooping, Arm weakness, Speech slurred, Time to call emergency",
        ],
        "specialist": "Neurologist or Emergency Care",
        "emergency": [
            "Sudden numbness or weakness",
            "Confusion or trouble speaking",
            "Vision problems or difficulty walking",
        ],
    },
    "kidney disease": {
        "keywords": ["kidney disease", "renal failure", "chronic kidney", "dialysis"],
        "title": "Kidney Disease",
        "possible_reasons": [
            "Damage to kidney function over time",
            "Diabetes, hypertension, or infections",
            "May lead to fluid retention or waste buildup",
        ],
        "medicines": [
            "BP and diabetes control are key",
            "Some cases need dialysis or transplant",
        ],
        "self_care": [
            "Monitor urine output and swelling",
            "Low salt diet if advised",
            "Regular checkups for kidney function",
        ],
        "specialist": "Nephrologist",
        "emergency": [
            "Severe swelling or shortness of breath",
            "Blood in urine or severe pain",
            "Confusion or seizures",
        ],
    },
    "liver disease": {
        "keywords": ["liver disease", "hepatitis", "jaundice", "liver cirrhosis", "fatty liver"],
        "title": "Liver Disease",
        "possible_reasons": [
            "Infection, alcohol, or fatty accumulation",
            "Hepatitis viruses or autoimmune issues",
            "Can lead to jaundice or fluid buildup",
        ],
        "medicines": [
            "Treatment depends on the cause",
            "Vaccines for hepatitis if applicable",
        ],
        "self_care": [
            "Avoid alcohol and maintain healthy weight",
            "Get vaccinated for hepatitis",
            "Monitor for jaundice or abdominal swelling",
        ],
        "specialist": "Hepatologist or Gastroenterologist",
        "emergency": [
            "Severe abdominal pain or vomiting blood",
            "Confusion or jaundice with fever",
            "Swelling with breathing difficulty",
        ],
    },
    "migraine": {
        "keywords": ["migraine", "severe headache", "throbbing head pain", "headache with nausea"],
        "title": "Migraine",
        "possible_reasons": [
            "Neurological condition causing intense headaches",
            "Triggers like stress, food, or hormones",
            "Family history common",
        ],
        "medicines": [
            "Pain relievers or specific migraine medicines",
            "Preventive treatment if frequent",
        ],
        "self_care": [
            "Identify and avoid triggers",
            "Rest in dark room during attack",
            "Maintain regular sleep and meals",
        ],
        "specialist": "Neurologist",
        "emergency": [
            "Headache with neurological symptoms like weakness",
            "Sudden severe headache",
            "Headache after head injury",
        ],
    },
    "epilepsy": {
        "keywords": ["epilepsy", "seizure", "fits", "convulsions", "epileptic"],
        "title": "Epilepsy",
        "possible_reasons": [
            "Abnormal brain electrical activity",
            "Head injury, infection, or genetic factors",
            "Seizures can vary in type",
        ],
        "medicines": [
            "Anti-seizure medicines to control episodes",
            "Dose adjustment by neurologist",
        ],
        "self_care": [
            "Take medicines regularly",
            "Avoid triggers like lack of sleep",
            "Wear medical ID bracelet",
        ],
        "specialist": "Neurologist",
        "emergency": [
            "Prolonged seizure or multiple seizures",
            "Injury during seizure",
            "First seizure or status epilepticus",
        ],
    },
})

PART_TO_SPECIALIZATIONS = {
    "eyes": [
        "Ophthalmologist",
        "Optometrist",
        "Ophthalmology",
        "Opthalmology",
        "Eye",
        "Eye Specialist",
        "Eye Care",
    ],
    "eye": [
        "Ophthalmologist",
        "Optometrist",
        "Ophthalmology",
        "Opthalmology",
        "Eye",
        "Eye Specialist",
        "Eye Care",
    ],
    "nose": ["ENT", "ENT Specialist"],
    "ent": ["ENT", "ENT Specialist", "Otolaryngology"],
    "teeth": ["Dentist", "Dental", "Dentistry", "Dental Surgeon"],
    "tooth": ["Dentist", "Dental", "Dentistry", "Dental Surgeon"],
    "skin": ["Dermatologist", "Dermatology", "Skin Specialist"],
    "skin-hair": ["Dermatologist", "Dermatology", "Skin Specialist", "Trichologist"],
    "bones": ["Orthopedic", "Orthopaedic", "Orthopedics", "Orthopaedics"],
    "bone": ["Orthopedic", "Orthopaedic", "Orthopedics", "Orthopaedics"],
    "heart": ["Cardiologist", "Cardiology", "Cardiac"],
    "liver": ["Hepatologist", "Gastroenterologist"],
    "lungs": ["Pulmonologist", "Chest Physician"],
    "brain": ["Neurologist", "Neurosurgeon"],
    "neuro": ["Neurologist", "Neurology"],
    "kidney": ["Urologist", "Nephrologist"],
    "general": ["General Physician", "Physician"],
}

# List of all disease names for auto-correction
DISEASE_NAMES = [
    "fever", "cold", "headache", "stomach pain", "tooth pain", "chest pain", "skin rash",
    "diabetes", "hypertension", "asthma", "arthritis", "sinusitis", "dengue", "typhoid",
    "malaria", "pneumonia", "bronchitis", "tuberculosis", "kidney stone", "uti",
    "appendicitis", "gastritis", "ulcer", "eczema", "psoriasis", "conjunctivitis",
    "cataract", "glaucoma", "anemia", "thyroid disorder", "depression", "anxiety",
    "covid-19", "cancer", "stroke", "kidney disease", "liver disease", "migraine", "epilepsy",
    "coronavirus", "brain attack", "renal failure", "chronic kidney", "hepatitis", "jaundice",
    "liver cirrhosis", "fatty liver", "severe headache", "throbbing head pain", "headache with nausea",
    "seizure", "fits", "convulsions", "epileptic"
]

DISEASE_TO_PART = {
    "conjunctivitis": "eye",
    "cataract": "eye",
    "glaucoma": "eye",
    "dry eye": "eye",
    "macular": "eye",
    "ear pain": "ent",
    "ear": "ent",
    "sinusitis": "nose",
    "ear infection": "ent",
    "tonsillitis": "ent",
    "tooth": "teeth",
    "cavities": "teeth",
    "gum": "teeth",
    "fracture": "bones",
    "arthritis": "bones",
    "osteoporosis": "bones",
    "eczema": "skin",
    "psoriasis": "skin",
    "acne": "skin",
    "asthma": "lungs",
    "pneumonia": "lungs",
    "tuberculosis": "lungs",
    "copd": "lungs",
    "heart": "heart",
    "cardiac": "heart",
    "kidney": "kidney",
    "uti": "kidney",
    "liver": "liver",
    "hepatitis": "liver",
    "stroke": "brain",
    "migraine": "brain",
    "epilepsy": "brain",
}

BODY_PART_GUIDANCE = {
    "eye": {
        "keywords": ["eye", "eyes", "vision", "sight", "blind", "glasses"],
        "title": "Eye Problems",
        "possible_reasons": [
            "Eye strain, infection, allergy, or vision-related problems",
            "Dry eyes, conjunctivitis, cataract, or glaucoma depending on symptoms",
        ],
        "medicines": [
            "Use only doctor-advised eye drops like artificial tears (Rs. 50-100 per bottle)",
            "Avoid self-medicating with steroid eye drops",
        ],
        "self_care": [
            "Avoid rubbing the eyes",
            "Reduce screen strain and keep eyes clean",
        ],
        "specialist": "Ophthalmologist",
        "emergency": [
            "Sudden vision loss",
            "Severe eye pain, swelling, or injury",
        ],
        "faq_answer": "Eye symptoms can be related to infection, allergy, strain, cataract, or pressure problems. An ophthalmologist is the right specialist for proper evaluation.",
    },
    "nose": {
        "keywords": ["nose", "nasal", "sinus", "congestion", "runny nose", "blocked nose"],
        "title": "Nose Problems",
        "possible_reasons": [
            "Cold, sinusitis, allergy, or infection",
            "Nose block, bleeding, or facial pressure may need ENT review",
        ],
        "medicines": [
            "Saline rinse (Rs. 20-40 per bottle) or steam may help some simple congestion",
            "Other medicines depend on the exact cause",
        ],
        "self_care": [
            "Avoid dust and smoke exposure",
            "Stay hydrated and monitor fever or discharge",
        ],
        "specialist": "ENT Specialist",
        "emergency": [
            "Heavy bleeding",
            "Breathing trouble or severe facial pain",
        ],
        "faq_answer": "Nose complaints are commonly due to allergy, cold, sinusitis, or bleeding problems. An ENT specialist can evaluate blocked nose, discharge, or repeated nosebleeds.",
    },
    "skin": {
        "keywords": ["skin", "rash", "itching", "eczema", "dermatitis", "allergy"],
        "title": "Skin Problems",
        "possible_reasons": [
            "Allergy, rash, eczema, fungal infection, or irritation",
            "Itching, redness, scaling, or swelling can have multiple causes",
        ],
        "medicines": [
            "Use only suitable creams after medical advice if symptoms are significant",
            "Avoid random steroid creams",
        ],
        "self_care": [
            "Keep skin clean and dry",
            "Avoid scratching and avoid trigger products",
        ],
        "specialist": "Dermatologist",
        "emergency": [
            "Breathing trouble with rash",
            "Fast-spreading rash, swelling, or skin peeling",
        ],
        "faq_answer": "Skin symptoms can happen due to allergy, infection, eczema, or psoriasis. A dermatologist is the right specialist if the rash is persistent, spreading, or very itchy.",
    },
    "heart": {
        "keywords": ["heart", "chest pain", "palpitations", "cardiac", "blood pressure"],
        "title": "Heart Problems",
        "possible_reasons": [
            "Heart-related chest pain, rhythm issues, or blood pressure problems",
            "Symptoms like chest pain, breathlessness, or dizziness need attention",
        ],
        "medicines": [
            "Do not self-medicate for chest pain or suspected heart symptoms",
            "Use prescribed heart medicines only as instructed by your doctor",
        ],
        "self_care": [
            "Stop activity and rest if symptoms start",
            "Seek medical review quickly for chest discomfort or palpitations",
        ],
        "specialist": "Cardiologist",
        "emergency": [
            "Chest pain with sweating or breathlessness",
            "Fainting or pain spreading to the arm, jaw, or back",
        ],
        "faq_answer": "Heart-related complaints should be checked by a cardiologist, especially if there is chest pain, palpitations, swelling in legs, or shortness of breath.",
    },
    "teeth": {
        "keywords": ["teeth", "tooth", "dental", "mouth", "gum", "cavity", "toothache"],
        "title": "Teeth or Dental Problems",
        "possible_reasons": [
            "Tooth decay, gum infection, sensitivity, or dental injury",
            "Pain, swelling, or bleeding gums may need dental care",
        ],
        "medicines": [
            "Simple pain relief like Paracetamol (Rs. 10-20 per 10 tablets) may help temporarily if it is safe for you",
            "Antibiotics and dental procedures should be done by a dentist",
        ],
        "self_care": [
            "Brush gently and rinse with warm salt water",
            "Avoid very hot, cold, or sugary foods",
        ],
        "specialist": "Dentist",
        "emergency": [
            "Facial swelling",
            "Difficulty swallowing or opening the mouth",
        ],
        "faq_answer": "Dental complaints often come from cavities, gum infection, or sensitivity. A dentist is the correct specialist for pain, swelling, or damaged teeth.",
    },
    "bone": {
        "keywords": ["bone", "fracture", "swelling", "bone pain", "bone crack"],
        "title": "Bone Problems",
        "possible_reasons": [
            "Fracture, bone infection, osteoporosis, or trauma injury",
            "Deep bone pain or deformity needs orthopedic evaluation",
        ],
        "medicines": [
            "Pain relief like Paracetamol or Ibuprofen (Rs. 15-30 per 10 tablets) as advised",
            "Calcium and Vitamin D supplements if recommended",
        ],
        "self_care": [
            "Immobilize the painful area and avoid bearing weight",
            "Apply ice pack for recent swelling",
        ],
        "specialist": "Orthopedic Doctor",
        "emergency": [
            "Visible bone deformity or compound fracture",
            "Inability to move limb or bear weight",
        ],
        "faq_answer": "Bone injuries and fractures require urgent orthopedic review with X-rays or scans.",
    },
    "ear": {
        "keywords": ["ear", "ears", "earache", "ear pain", "hearing", "ear discharge", "tinnitus", "ear block"],
        "title": "Ear Problems & Hearing Care",
        "possible_reasons": [
            "Ear canal infection (otitis externa) or middle ear infection (otitis media)",
            "Earwax buildup, Eustachian tube block, or pressure changes",
        ],
        "medicines": [
            "Antibiotic or pain-relieving ear drops prescribed by an ENT doctor",
            "Oral pain relief like Paracetamol if safe for you",
        ],
        "self_care": [
            "Keep the ear dry and avoid inserting cotton buds or sharp objects",
            "Use a warm compress on the outside of the ear for comfort",
        ],
        "specialist": "ENT Specialist (Otolaryngologist)",
        "emergency": [
            "Sudden complete hearing loss",
            "Yellow or bloody discharge with high fever or dizziness",
        ],
        "faq_answer": "Ear pain or discharge is best checked by an ENT specialist to prevent eardrum damage.",
    },
    "throat": {
        "keywords": ["throat", "tonsil", "tonsils", "tonsillitis", "sore throat", "throat pain", "pharyngitis", "hoarseness"],
        "title": "Throat & Tonsil Care",
        "possible_reasons": [
            "Viral or bacterial throat infection (strep throat, tonsillitis)",
            "Acid reflux, voice strain, or environmental allergy",
        ],
        "medicines": [
            "Warm salt water gargle and throat lozenges for soothing relief",
            "Antibiotics only if a bacterial infection is diagnosed by an ENT",
        ],
        "self_care": [
            "Drink warm water, herbal teas, or honey-lemon water",
            "Rest your voice and avoid cold or oily foods",
        ],
        "specialist": "ENT Specialist",
        "emergency": [
            "Severe difficulty swallowing saliva or breathing",
            "Inability to open mouth (trismus)",
        ],
        "faq_answer": "Sore throat and tonsillitis are commonly evaluated and treated by an ENT specialist.",
    },
    "knee": {
        "keywords": ["knee", "knee pain", "knee swelling", "patella", "meniscus", "knee joint"],
        "title": "Knee & Joint Problems",
        "possible_reasons": [
            "Osteoarthritis, cartilage wear, or meniscus/ligament strain",
            "Sudden twist, sports injury, or fluid accumulation (bursitis)",
        ],
        "medicines": [
            "Paracetamol or topical pain relief gel (Rs. 60-120 per tube)",
            "Anti-inflammatory medicines prescribed after orthopedic examination",
        ],
        "self_care": [
            "Rest, ice application for 15 minutes, and gentle knee support bandage",
            "Avoid squatting, running, or high-impact activities while painful",
        ],
        "specialist": "Orthopedic Doctor",
        "emergency": [
            "Inability to stand or bear weight on the knee",
            "Severe swelling, redness, and fever",
        ],
        "faq_answer": "Persistent knee pain should be evaluated by an orthopedic specialist with an X-ray or MRI.",
    },
    "back": {
        "keywords": ["back", "back pain", "backache", "lower back", "spine", "sciatica", "slip disc", "lumbar"],
        "title": "Back Pain & Spine Care",
        "possible_reasons": [
            "Muscle strain from poor posture, heavy lifting, or prolonged sitting",
            "Lumbar disc herniation (slip disc) or sciatica nerve compression",
        ],
        "medicines": [
            "Paracetamol or muscle relaxant advised by your physician",
            "Topical pain relief spray or ointment",
        ],
        "self_care": [
            "Avoid complete bed rest; engage in gentle walking and maintain ergonomic posture",
            "Apply warm compress or heating pad to ease muscular tension",
        ],
        "specialist": "Orthopedic / Spine Specialist",
        "emergency": [
            "Pain radiating down both legs with numbness or tingling",
            "Loss of bowel or bladder control (cauda equina warning sign)",
        ],
        "faq_answer": "Lower back pain and sciatica are diagnosed and managed by orthopedic and spine specialists.",
    },
    "joint": {
        "keywords": ["joint", "joints", "joint pain", "arthritis", "osteoarthritis", "rheumatoid", "swollen joints"],
        "title": "Joint Pain & Arthritis",
        "possible_reasons": [
            "Osteoarthritis, rheumatoid arthritis, gout, or autoimmune inflammation",
            "Cartilage degeneration or joint fluid inflammation",
        ],
        "medicines": [
            "Pain management and anti-inflammatory medications prescribed by a specialist",
            "Disease-modifying medications for rheumatoid conditions",
        ],
        "self_care": [
            "Gentle low-impact exercises like swimming and walking",
            "Warm baths to relieve morning stiffness",
        ],
        "specialist": "Orthopedic Doctor or Rheumatologist",
        "emergency": [
            "Hot, red, acutely swollen joint with fever",
            "Sudden inability to move the affected joint",
        ],
        "faq_answer": "Chronic joint pain and arthritis need evaluation by a rheumatologist or orthopedic doctor.",
    },
    "neck": {
        "keywords": ["neck", "neck pain", "cervical", "stiff neck", "neck spasm"],
        "title": "Neck Pain & Cervical Care",
        "possible_reasons": [
            "Cervical spondylosis, muscle strain from mobile/laptop posture (text neck)",
            "Pinched nerve in the cervical spine",
        ],
        "medicines": [
            "Analgesics or muscle relaxants under medical advice",
            "Topical analgesic gels",
        ],
        "self_care": [
            "Adjust screen to eye level and perform gentle neck stretches",
            "Use an ergonomic supportive pillow",
        ],
        "specialist": "Orthopedic Doctor or Physiotherapist",
        "emergency": [
            "Neck stiffness with fever and headache (meningitis sign)",
            "Numbness or shooting pain spreading to the arm or fingers",
        ],
        "faq_answer": "Persistent neck pain or cervical stiffness is evaluated by orthopedic doctors and physiotherapists.",
    },
    "lungs": {
        "keywords": ["lung", "lungs", "respiratory", "breathing", "breath", "wheezing", "chest congestion", "shortness of breath"],
        "title": "Respiratory & Lung Care",
        "possible_reasons": [
            "Asthma, bronchitis, pneumonia, or respiratory viral infection",
            "Environmental pollution, smoking, or allergy trigger",
        ],
        "medicines": [
            "Inhalers or bronchodilators prescribed by a pulmonologist",
            "Steam inhalation and expectorant syrups if appropriate",
        ],
        "self_care": [
            "Avoid exposure to dust, smoke, and cold air",
            "Practice deep breathing exercises and stay well hydrated",
        ],
        "specialist": "Pulmonologist",
        "emergency": [
            "Severe breathlessness or inability to speak in sentences",
            "Blue lips or fingernails (low oxygen warning)",
        ],
        "faq_answer": "Respiratory complaints like wheezing, persistent cough, or breathlessness need pulmonology evaluation.",
    },
    "brain": {
        "keywords": ["brain", "headache", "migraine", "neurological", "dizziness", "stroke", "vertigo"],
        "title": "Brain or Neurological Problems",
        "possible_reasons": [
            "Headache, migraine, stroke, or neurological disorders",
            "Symptoms like dizziness, confusion, or weakness may need neurology review",
        ],
        "medicines": [
            "Medicines depend on the exact diagnosis",
            "Do not self-medicate for neurological symptoms",
        ],
        "self_care": [
            "Rest and avoid stress triggers",
            "Monitor symptoms and seek review if worsening",
        ],
        "specialist": "Neurologist",
        "emergency": [
            "Sudden weakness or numbness",
            "Severe headache or confusion",
        ],
        "faq_answer": "Brain-related symptoms can be due to migraine, stroke, or other conditions. A neurologist is the right specialist for headaches, dizziness, or neurological issues.",
    },
    "stomach": {
        "keywords": ["stomach", "abdominal", "vomit", "vomiting", "nausea", "gastritis", "acidity", "belly"],
        "title": "Stomach or Digestive Problems",
        "possible_reasons": [
            "Acidity, gastritis, infection, or digestive disorders",
            "Pain, bloating, or nausea may need gastroenterology review",
        ],
        "medicines": [
            "Antacids like Pantoprazole (Rs. 50-100 per strip) or other medicines depend on the cause",
            "Avoid self-medicating for stomach issues",
        ],
        "self_care": [
            "Eat light meals and avoid spicy food",
            "Stay hydrated and monitor symptoms",
        ],
        "specialist": "Gastroenterologist",
        "emergency": [
            "Severe pain or vomiting blood",
            "Inability to eat or drink",
        ],
        "faq_answer": "Stomach problems can be due to acidity, infection, or ulcers. A gastroenterologist can evaluate pain, bloating, or digestive symptoms.",
    },
    "kidney": {
        "keywords": ["kidney", "urine", "urination", "renal", "kidney stone"],
        "title": "Kidney Problems",
        "possible_reasons": [
            "Infection, stones, or chronic kidney disease",
            "Symptoms like pain, frequent urination, or swelling may need urology review",
        ],
        "medicines": [
            "Medicines depend on the exact condition",
            "Fluids and diet changes may be advised",
        ],
        "self_care": [
            "Stay hydrated and monitor urine output",
            "Seek review for persistent pain or changes",
        ],
        "specialist": "Urologist or Nephrologist",
        "emergency": [
            "Severe pain or blood in urine",
            "Reduced urine output or swelling",
        ],
        "faq_answer": "Kidney issues can include stones, infection, or failure. A urologist or nephrologist is the specialist for pain, urination problems, or kidney function concerns.",
    },
    "liver": {
        "keywords": ["liver", "jaundice", "hepatitis", "fatty liver", "yellow eyes"],
        "title": "Liver Problems",
        "possible_reasons": [
            "Infection, fatty liver, or liver disease",
            "Symptoms like jaundice, pain, or fatigue may need hepatology review",
        ],
        "medicines": [
            "Treatment depends on the cause",
            "Avoid alcohol and certain medicines",
        ],
        "self_care": [
            "Eat a healthy diet and exercise",
            "Monitor for jaundice or swelling",
        ],
        "specialist": "Hepatologist or Gastroenterologist",
        "emergency": [
            "Severe pain or jaundice",
            "Confusion or bleeding",
        ],
        "faq_answer": "Liver problems can be due to infection, alcohol, or disease. A hepatologist can evaluate jaundice, pain, or liver function abnormalities.",
    },
}


def correct_disease_name(query_text):
    """
    Correct misspelled disease names using difflib.
    """
    query_lower = query_text.lower()
    words = re.findall(r'\b\w+\b', query_lower)
    corrected_words = []
    for word in words:
        if word in DISEASE_NAMES:
            corrected_words.append(word)
        else:
            matches = difflib.get_close_matches(word, DISEASE_NAMES, n=1, cutoff=0.8)
            if matches:
                corrected_words.append(matches[0])
            else:
                corrected_words.append(word)
    return ' '.join(corrected_words)


def _safe_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


KNOWN_TN_LOCATIONS = [
    "Chennai",
    "Coimbatore",
    "Cuddalore",
    "Dindigul",
    "Erode",
    "Kanchipuram",
    "Karur",
    "Madurai",
    "Nagapattinam",
    "Salem",
    "Thanjavur",
    "Thoothukudi",
    "Tirunelveli",
    "Trichy",
    "Vellore",
]


def _split_hospital_name(hospital_name):
    text = _safe_text(hospital_name)
    if not text:
        return "", ""
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in set(KNOWN_TN_LOCATIONS + ["None"]):
        return parts[0].strip(), parts[1].strip()
    return text, ""


def _deterministic_pick(options, key_text):
    if not options:
        return ""
    digest = hashlib.sha256(_safe_text(key_text).encode("utf-8")).hexdigest()
    index = int(digest[:12], 16) % len(options)
    return options[index]


def _repair_location_and_hospital(data_df):
    if "location" not in data_df.columns or "hospital" not in data_df.columns:
        return data_df

    repaired = data_df.copy()
    repaired["location"] = repaired["location"].fillna("").astype(str).str.strip()
    repaired["hospital"] = repaired["hospital"].fillna("").astype(str).str.strip()

    base_location_pool = {}
    for _, row in repaired.iterrows():
        base_name, hospital_suffix = _split_hospital_name(row.get("hospital", ""))
        explicit_location = _safe_text(row.get("location", ""))
        city = explicit_location or (hospital_suffix if hospital_suffix in KNOWN_TN_LOCATIONS else "")
        if base_name and city:
            base_location_pool.setdefault(base_name, []).append(city)

    global_location_pool = repaired["location"][repaired["location"].ne("")].tolist()
    if not global_location_pool:
        global_location_pool = KNOWN_TN_LOCATIONS[:]

    new_locations = []
    new_hospitals = []
    for _, row in repaired.iterrows():
        hospital_text = _safe_text(row.get("hospital", ""))
        base_name, hospital_suffix = _split_hospital_name(hospital_text)
        current_location = _safe_text(row.get("location", ""))

        resolved_location = current_location
        if not resolved_location and hospital_suffix in KNOWN_TN_LOCATIONS:
            resolved_location = hospital_suffix
        if not resolved_location:
            choices = base_location_pool.get(base_name) or global_location_pool
            stable_key = "|".join([
                _safe_text(row.get("doctor_name", "")),
                _safe_text(row.get("department", "")),
                _safe_text(row.get("specialization", "")),
                base_name,
            ])
            resolved_location = _deterministic_pick(choices, stable_key)

        new_locations.append(resolved_location)
        new_hospitals.append(base_name or hospital_text)

    repaired["location"] = new_locations
    repaired["hospital"] = new_hospitals
    return repaired


def _first_symptom(symptom_text):
    parts = [item.strip() for item in _safe_text(symptom_text).split(",") if item.strip()]
    return parts[0].title() if parts else ""


GENERIC_COMPLAINT_CATEGORIES = {
    "eye",
    "eyes",
    "ent",
    "nose",
    "bone",
    "bones",
    "teeth",
    "tooth",
    "skin",
    "skin-hair",
    "heart",
    "lungs",
    "brain",
    "kidney",
    "general",
}


def _complaint_category_from_row(row):
    category = _safe_text(row.get("complaint_category", ""))
    symptom_text = _safe_text(row.get("symptom_text", ""))
    if not category or category.strip().lower() in GENERIC_COMPLAINT_CATEGORIES:
        return _first_symptom(symptom_text)
    return category


def _build_term_pattern(terms, whole_word=True):
    cleaned_terms = []
    for term in terms:
        text = _safe_text(term)
        if text:
            escaped = re.escape(text)
            cleaned_terms.append(rf"\b{escaped}\b" if whole_word else escaped)
    if not cleaned_terms:
        return ""
    return "|".join(cleaned_terms)


def _top_terms(series, limit=5):
    counter = Counter()
    for value in series.dropna().astype(str):
        for item in value.split(","):
            item = item.strip()
            if item:
                counter[item] += 1
    return [term for term, _ in counter.most_common(limit)]


def _normalize_dataset(raw_df):
    data_df = raw_df.copy().rename(columns={
        "doctor": "doctor_name",
        "disease": "department",
        "symptoms": "symptom_text",
        "review_english": "feedback_text",
        "sentiment": "sentiment_label",
        "rating": "average_rating",
        "Location (Tamil Nadu)": "location",
    })

    if "doctor_name" not in data_df.columns:
        data_df["doctor_name"] = ""
    if "department" not in data_df.columns:
        data_df["department"] = ""
    if "symptom_text" not in data_df.columns:
        data_df["symptom_text"] = data_df.get("complaint_category", "")
    if "feedback_text" not in data_df.columns:
        data_df["feedback_text"] = data_df.get("review_original", data_df.get("feedback_text", ""))
    if "sentiment_label" not in data_df.columns:
        data_df["sentiment_label"] = data_df.get("sentiment_label", "Neutral")
    if "average_rating" not in data_df.columns:
        data_df["average_rating"] = data_df.get("average_rating", 0)
    if "location" not in data_df.columns:
        data_df["location"] = data_df.get("location", "")
    if "body_part" not in data_df.columns:
        data_df["body_part"] = data_df.get("department", "")
    if "complaint_category" not in data_df.columns:
        if "category" in data_df.columns:
            data_df["complaint_category"] = data_df["category"]
        else:
            data_df["complaint_category"] = data_df["symptom_text"].apply(_first_symptom)
    if "qualification" not in data_df.columns:
        data_df["qualification"] = data_df["specialization"].fillna("").astype(str) + " Specialist"
    rng = random.Random(42)
    if "experience_years" not in data_df.columns:
        data_df["experience_years"] = [rng.randint(1, 70) for _ in range(len(data_df))]
    if "hospital" not in data_df.columns:
        data_df["hospital"] = ""
    if "recommendation_label" not in data_df.columns:
        data_df["recommendation_label"] = 0

    for column in [
        "doctor_name",
        "department",
        "symptom_text",
        "feedback_text",
        "sentiment_label",
        "location",
        "specialization",
        "complaint_category",
        "qualification",
        "hospital",
        "body_part",
    ]:
        data_df[column] = data_df[column].fillna("").astype(str)

    data_df["complaint_category"] = data_df.apply(_complaint_category_from_row, axis=1)

    if "experience_years" in data_df.columns:
        exp_series = pd.to_numeric(data_df["experience_years"], errors="coerce")
        missing_mask = exp_series.isna()
        if missing_mask.any():
            exp_series.loc[missing_mask] = [rng.randint(1, 70) for _ in range(missing_mask.sum())]
        data_df["experience_years"] = exp_series.astype(int)

    data_df = _repair_location_and_hospital(data_df)
    data_df["consultation_fee"] = pd.to_numeric(data_df["consultation_fee"], errors="coerce").fillna(0)
    data_df["average_rating"] = pd.to_numeric(data_df["average_rating"], errors="coerce").fillna(0)
    data_df["recommendation_label"] = pd.to_numeric(data_df["recommendation_label"], errors="coerce").fillna(0)
    
    # Convert all datetime or timestamp columns to string to prevent NaT serialization errors
    for col in data_df.columns:
        if pd.api.types.is_datetime64_any_dtype(data_df[col]):
            data_df[col] = data_df[col].astype(str).replace({"NaT": "", "nan": ""})

    data_df = data_df.reset_index(drop=True)
    if "doctor_id" not in data_df.columns:
        if "id" in data_df.columns:
            data_df["doctor_id"] = pd.to_numeric(data_df["id"], errors="coerce").fillna(pd.Series(data_df.index)).astype(int)
        else:
            data_df["doctor_id"] = data_df.index.astype(int)
    return data_df


def _ensure_unique_doctor_names(data_df):
    if "doctor_name" not in data_df.columns:
        return data_df

    names = data_df["doctor_name"].fillna("").astype(str)
    name_counts = names.groupby(names).cumcount()
    has_name = names.str.len() > 0
    needs_suffix = has_name & (name_counts > 0)
    data_df = data_df.copy()
    data_df.loc[needs_suffix, "doctor_name"] = (
        names[needs_suffix] + " (" + (name_counts[needs_suffix] + 1).astype(str) + ")"
    )
    return data_df


def _prepare_dynamic_resources(data_df):
    global doctor_examples, dataset_condition_guidance
    doctor_examples = (
        data_df.sort_values(by=["average_rating", "recommendation_label"], ascending=False)
        .drop_duplicates(subset=["doctor_name"])
        .head(5)["doctor_name"]
        .tolist()
    )
    dataset_condition_guidance = {}
    for disease, group in data_df.groupby("department"):
        disease_name = _safe_text(disease)
        if not disease_name:
            continue
        symptoms = _top_terms(group["symptom_text"], limit=5)
        specializations = [item for item in group["specialization"].dropna().astype(str).unique().tolist()[:2] if item]
        locations = [item for item in group["location"].dropna().astype(str).unique().tolist()[:3] if item]
        dataset_condition_guidance[disease_name.lower()] = {
            "keywords": [disease_name.lower()] + [item.lower() for item in symptoms],
            "title": disease_name,
            "possible_reasons": [
                f"Combined dataset records for {disease_name.lower()} often mention {', '.join(symptoms[:3]) or 'related symptoms'}.",
                "The exact cause can still vary based on age, severity, and other health conditions.",
            ],
            "medicines": [
                "Use treatment only with doctor guidance for the exact diagnosis.",
                "Dataset examples are for reference and not a personal prescription.",
            ],
            "self_care": [
                "Track symptom severity and duration.",
                "Seek medical review if symptoms are worsening or persistent.",
            ],
            "specialist": ", ".join(specializations) if specializations else "Relevant specialist",
            "emergency": [
                "Severe pain, breathing trouble, confusion, or sudden worsening",
                "Heavy bleeding, repeated vomiting, or inability to manage daily activity",
            ],
            "dataset_locations": locations,
        }


def _build_combined_faq(data_df, faq_df):
    rows = faq_df.fillna("").to_dict(orient="records")
    for disease, group in data_df.groupby("department"):
        disease_name = _safe_text(disease)
        if not disease_name:
            continue
        symptoms = _top_terms(group["symptom_text"], limit=5)
        doctors = [item for item in group["doctor_name"].dropna().astype(str).unique().tolist()[:3] if item]
        specializations = [item for item in group["specialization"].dropna().astype(str).unique().tolist()[:2] if item]
        locations = [item for item in group["location"].dropna().astype(str).unique().tolist()[:3] if item]
        avg_fee = pd.to_numeric(group["consultation_fee"], errors="coerce").fillna(0).mean()

        answer = [
            f"In the combined dataset, {disease_name.lower()} is commonly linked with {', '.join(symptoms) if symptoms else 'several related symptoms'}.",
        ]
        if specializations:
            answer.append(f"Patients usually consult {', '.join(specializations)}.")
        if doctors:
            answer.append(f"Example doctors include {', '.join(doctors)}.")
        if avg_fee > 0:
            answer.append(f"Average consultation fee in these records is about Rs. {int(round(avg_fee))}.")

        rows.append({
            "question": f"What should I know about {disease_name}?",
            "answer": " ".join(answer),
            "keywords": ", ".join([disease_name] + symptoms + specializations),
        })

    return pd.DataFrame(rows, columns=["question", "answer", "keywords"]).fillna("").drop_duplicates(subset=["question", "answer"])


def _augment_dataset(data_df):
    supplemental_rows = [
        {"age": 46, "gender": "Female", "doctor_name": "Dr. Lakshmi", "department": "Diabetes", "hospital": "City Care Clinic", "specialization": "Endocrinologist", "consultation_fee": 700, "feedback_text": "The doctor explained sugar control clearly and adjusted the treatment plan well.", "sentiment_label": "Positive", "average_rating": 4.6, "recommendation_label": 1, "location": "Chennai", "symptom_text": "frequent urination, excess thirst, tiredness", "complaint_category": "Frequent Urination", "qualification": "Endocrinologist", "experience_years": 12},
        {"age": 54, "gender": "Male", "doctor_name": "Dr. Prakash", "department": "High Blood Pressure", "hospital": "Heart Plus", "specialization": "Cardiologist", "consultation_fee": 900, "feedback_text": "Careful blood pressure monitoring and practical lifestyle advice were very helpful.", "sentiment_label": "Positive", "average_rating": 4.5, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "headache, dizziness, blurred vision", "complaint_category": "Headache", "qualification": "Cardiologist", "experience_years": 14},
        {"age": 29, "gender": "Male", "doctor_name": "Dr. Nivetha", "department": "Asthma", "hospital": "Breath Well Centre", "specialization": "Pulmonologist", "consultation_fee": 800, "feedback_text": "The inhaler technique was explained well and breathing improved with treatment.", "sentiment_label": "Positive", "average_rating": 4.7, "recommendation_label": 1, "location": "Madurai", "symptom_text": "wheezing, chest tightness, shortness of breath", "complaint_category": "Wheezing", "qualification": "Pulmonologist", "experience_years": 9},
        {"age": 38, "gender": "Female", "doctor_name": "Dr. Senthil", "department": "Sinusitis", "hospital": "ENT Care", "specialization": "ENT Specialist", "consultation_fee": 650, "feedback_text": "The doctor identified the sinus issue quickly and the treatment reduced facial pressure.", "sentiment_label": "Positive", "average_rating": 4.4, "recommendation_label": 1, "location": "Salem", "symptom_text": "blocked nose, facial pressure, headache", "complaint_category": "Blocked Nose", "qualification": "ENT Specialist", "experience_years": 11},
        {"age": 61, "gender": "Female", "doctor_name": "Dr. Arun", "department": "Arthritis", "hospital": "Ortho Mobility", "specialization": "Orthopedic", "consultation_fee": 750, "feedback_text": "The joint pain assessment was detailed and the exercise advice was useful.", "sentiment_label": "Positive", "average_rating": 4.5, "recommendation_label": 1, "location": "Trichy", "symptom_text": "joint pain, joint swelling, morning stiffness", "complaint_category": "Joint Pain", "qualification": "Orthopedic", "experience_years": 15},
        {"age": 35, "gender": "Female", "doctor_name": "Dr. Meera", "department": "Migraine", "hospital": "Neuro Health", "specialization": "Neurologist", "consultation_fee": 850, "feedback_text": "The migraine triggers were identified and medication helped reduce episodes.", "sentiment_label": "Positive", "average_rating": 4.8, "recommendation_label": 1, "location": "Chennai", "symptom_text": "severe headache, nausea, sensitivity to light", "complaint_category": "Severe Headache", "qualification": "Neurologist", "experience_years": 10},
        {"age": 42, "gender": "Male", "doctor_name": "Dr. Rajesh", "department": "Gastritis", "hospital": "Digestive Care", "specialization": "Gastroenterologist", "consultation_fee": 700, "feedback_text": "Dietary advice and antacids resolved the stomach burning quickly.", "sentiment_label": "Positive", "average_rating": 4.6, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "stomach pain, acidity, bloating", "complaint_category": "Stomach Pain", "qualification": "Gastroenterologist", "experience_years": 13},
        {"age": 50, "gender": "Female", "doctor_name": "Dr. Priya", "department": "Kidney Stones", "hospital": "Uro Clinic", "specialization": "Urologist", "consultation_fee": 900, "feedback_text": "The stone was diagnosed via scan and treatment plan was clear.", "sentiment_label": "Positive", "average_rating": 4.7, "recommendation_label": 1, "location": "Madurai", "symptom_text": "severe back pain, blood in urine, frequent urination", "complaint_category": "Severe Back Pain", "qualification": "Urologist", "experience_years": 16},
        {"age": 28, "gender": "Male", "doctor_name": "Dr. Karthik", "department": "Psoriasis", "hospital": "Skin Care Center", "specialization": "Dermatologist", "consultation_fee": 600, "feedback_text": "Creams and lifestyle tips improved the skin condition significantly.", "sentiment_label": "Positive", "average_rating": 4.5, "recommendation_label": 1, "location": "Salem", "symptom_text": "scaly skin patches, itching, redness", "complaint_category": "Scaly Skin", "qualification": "Dermatologist", "experience_years": 8},
        {"age": 55, "gender": "Male", "doctor_name": "Dr. Vijay", "department": "Cataract", "hospital": "Eye Vision", "specialization": "Ophthalmologist", "consultation_fee": 750, "feedback_text": "The cataract surgery was successful and vision improved.", "sentiment_label": "Positive", "average_rating": 4.9, "recommendation_label": 1, "location": "Trichy", "symptom_text": "blurred vision, difficulty seeing at night", "complaint_category": "Blurred Vision", "qualification": "Ophthalmologist", "experience_years": 18},
        {"age": 33, "gender": "Female", "doctor_name": "Dr. Anjali", "department": "Thyroid Disorder", "hospital": "Endo Clinic", "specialization": "Endocrinologist", "consultation_fee": 800, "feedback_text": "Thyroid tests were done and medication balanced the levels.", "sentiment_label": "Positive", "average_rating": 4.6, "recommendation_label": 1, "location": "Chennai", "symptom_text": "fatigue, weight gain, hair loss", "complaint_category": "Fatigue", "qualification": "Endocrinologist", "experience_years": 11},
        {"age": 47, "gender": "Male", "doctor_name": "Dr. Suresh", "department": "Depression", "hospital": "Mental Health Center", "specialization": "Psychiatrist", "consultation_fee": 1000, "feedback_text": "Counseling and medication helped manage the mood swings.", "sentiment_label": "Positive", "average_rating": 4.7, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "low mood, lack of interest, insomnia", "complaint_category": "Low Mood", "qualification": "Psychiatrist", "experience_years": 14},
        {"age": 40, "gender": "Female", "doctor_name": "Dr. Kavita", "department": "Anemia", "hospital": "Blood Health", "specialization": "Hematologist", "consultation_fee": 650, "feedback_text": "Iron supplements and diet changes improved energy levels.", "sentiment_label": "Positive", "average_rating": 4.4, "recommendation_label": 1, "location": "Madurai", "symptom_text": "tiredness, pale skin, shortness of breath", "complaint_category": "Tiredness", "qualification": "Hematologist", "experience_years": 12},
        {"age": 52, "gender": "Male", "doctor_name": "Dr. Ramesh", "department": "Pneumonia", "hospital": "Lung Care", "specialization": "Pulmonologist", "consultation_fee": 850, "feedback_text": "Antibiotics and rest cleared the lung infection effectively.", "sentiment_label": "Positive", "average_rating": 4.8, "recommendation_label": 1, "location": "Salem", "symptom_text": "cough with fever, chest pain, difficulty breathing", "complaint_category": "Cough with Fever", "qualification": "Pulmonologist", "experience_years": 17},
        {"age": 30, "gender": "Female", "doctor_name": "Dr. Nandini", "department": "UTI", "hospital": "Urinary Health", "specialization": "Urologist", "consultation_fee": 700, "feedback_text": "Urine tests confirmed infection and antibiotics worked quickly.", "sentiment_label": "Positive", "average_rating": 4.5, "recommendation_label": 1, "location": "Trichy", "symptom_text": "burning urination, frequent urination, lower abdominal pain", "complaint_category": "Burning Urination", "qualification": "Urologist", "experience_years": 9},
        {"age": 32, "gender": "Male", "doctor_name": "Dr. Arjun", "department": "Cavities", "hospital": "Smile Dental Clinic", "specialization": "Dentist", "consultation_fee": 600, "feedback_text": "The cavity filling was painless and the doctor explained aftercare clearly.", "sentiment_label": "Positive", "average_rating": 4.6, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "tooth pain, sensitivity", "complaint_category": "Tooth Pain", "qualification": "Dentist", "experience_years": 8},
        {"age": 41, "gender": "Female", "doctor_name": "Dr. Kavya", "department": "Gum Disease", "hospital": "Bright Dental Care", "specialization": "Dentist", "consultation_fee": 700, "feedback_text": "Bleeding gums improved after cleaning and the doctor gave good hygiene tips.", "sentiment_label": "Positive", "average_rating": 4.5, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "bleeding gums, gum swelling", "complaint_category": "Bleeding Gums", "qualification": "Dentist", "experience_years": 11},
        {"age": 27, "gender": "Male", "doctor_name": "Dr. Naveen", "department": "Tooth Abscess", "hospital": "City Dental Hospital", "specialization": "Dentist", "consultation_fee": 750, "feedback_text": "The abscess pain reduced quickly after treatment and follow-up was good.", "sentiment_label": "Positive", "average_rating": 4.7, "recommendation_label": 1, "location": "Coimbatore", "symptom_text": "swelling, pain", "complaint_category": "Tooth Abscess", "qualification": "Dentist", "experience_years": 6},
    ]
    supplemental_df = pd.DataFrame(supplemental_rows)
    combined_df = pd.concat([data_df, supplemental_df], ignore_index=True, sort=False)
    combined_df = combined_df.reset_index(drop=True)
    if "doctor_id" not in combined_df.columns:
        combined_df["doctor_id"] = combined_df.index.astype(int)
    else:
        missing_mask = combined_df["doctor_id"].isna() | (combined_df["doctor_id"] == 0)
        if missing_mask.any():
            max_id = int(pd.to_numeric(combined_df["doctor_id"], errors="coerce").fillna(0).max())
            combined_df.loc[missing_mask, "doctor_id"] = list(range(max_id + 1, max_id + 1 + int(missing_mask.sum())))
        combined_df["doctor_id"] = combined_df["doctor_id"].astype(int)
    return combined_df


def load_data(force_db_reload=False):
    global vectorizer, sentiment_model, label_encoder, faq_vectorizer, faq_tfidf, doctor_examples, dataset_condition_guidance
    from db import load_doctors_df, load_faqs_df, is_db_connected

    # Check cache if not forcing reload
    if not force_db_reload and CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "rb") as f:
                cache_payload = pickle.load(f)
            if cache_payload.get("source") == "postgresql":
                data_df = cache_payload["data_df"]
                faq_df = cache_payload["faq_df"]
                vectorizer = cache_payload["vectorizer"]
                sentiment_model = cache_payload["sentiment_model"]
                label_encoder = cache_payload["label_encoder"]
                faq_vectorizer = cache_payload["faq_vectorizer"]
                faq_tfidf = cache_payload["faq_tfidf"]
                doctor_examples = cache_payload.get("doctor_examples", [])
                dataset_condition_guidance = cache_payload.get("dataset_condition_guidance", {})
                print(f"[DATA] Successfully loaded {len(data_df):,} doctors from PostgreSQL cache ('healthcare_db')")
                return data_df, faq_df
        except Exception:
            pass

    # Primary: Direct load from PostgreSQL database
    if is_db_connected():
        print("[DATA] Connecting to PostgreSQL database: 'healthcare_db' at 127.0.0.1:5432...")
        data_df = load_doctors_df()
        faq_df = load_faqs_df()
        print(f"[DATA] SUCCESS: Loaded {len(data_df):,} doctor records and {len(faq_df):,} FAQs directly from PostgreSQL!")
    else:
        print("[DATA-WARN] PostgreSQL server offline, falling back to local files...")
        try:
            data_df = pd.read_excel(DATA_PATH, sheet_name=DATA_SHEET)
        except Exception:
            data_df = pd.read_csv(FALLBACK_DATA_PATH)
        faq_df = pd.read_csv(FAQ_PATH)

    data_df = _normalize_dataset(data_df)
    data_df = _augment_dataset(data_df)
    data_df = _ensure_unique_doctor_names(data_df)
    faq_df = _build_combined_faq(data_df, faq_df)
    _train_nlp_model(data_df)
    _build_faq_index(faq_df)
    _prepare_dynamic_resources(data_df)

    try:
        with open(CACHE_PATH, "wb") as f:
            pickle.dump({
                "source": "postgresql",
                "data_df": data_df,
                "faq_df": faq_df,
                "vectorizer": vectorizer,
                "sentiment_model": sentiment_model,
                "label_encoder": label_encoder,
                "faq_vectorizer": faq_vectorizer,
                "faq_tfidf": faq_tfidf,
                "doctor_examples": doctor_examples,
                "dataset_condition_guidance": dataset_condition_guidance,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[DATA] Saved fast PostgreSQL binary cache to {CACHE_PATH.name}")
    except Exception as exc:
        print(f"[DATA] Could not write cache file: {exc}")

    return data_df, faq_df


def _train_nlp_model(data_df):
    global vectorizer, sentiment_model, label_encoder

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=1200)
    label_encoder = LabelEncoder()

    texts = data_df["feedback_text"].fillna("").astype(str)
    labels = data_df["sentiment_label"].fillna("Neutral")

    X = vectorizer.fit_transform(texts)
    y = label_encoder.fit_transform(labels)

    sentiment_model = MultinomialNB()
    sentiment_model.fit(X, y)


def _build_faq_index(faq_df):
    global faq_vectorizer, faq_tfidf
    search_text = (
        faq_df["question"].fillna("").astype(str).str.strip() + " " +
        faq_df["keywords"].fillna("").astype(str).str.replace(",", " ", regex=False).str.strip()
    ).str.strip()
    faq_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    faq_tfidf = faq_vectorizer.fit_transform(search_text)


def _tokenize_text(text):
    return set(re.findall(r"[a-zA-Z]+", str(text).lower()))


def _clean_query_label(query_text):
    cleaned = " ".join(re.findall(r"[A-Za-z]+", str(query_text))).strip()
    return cleaned.title() if cleaned else "This condition"


def _meaningful_tokens(text):
    return {token for token in _tokenize_text(text) if token not in GENERIC_QUERY_WORDS}


def predict_sentiment(text):
    global vectorizer, sentiment_model, label_encoder
    if vectorizer is None or sentiment_model is None or label_encoder is None:
        return "Neutral"

    text_vec = vectorizer.transform([text])
    label_index = sentiment_model.predict(text_vec)[0]
    return label_encoder.inverse_transform([label_index])[0]


def _normalize_series(series):
    series = series.astype(float).fillna(0.0)
    if series.empty:
        return series
    min_val = series.min()
    max_val = series.max()
    if min_val == max_val:
        return series.apply(lambda x: 0.5)
    return (series - min_val) / (max_val - min_val)


SYMPTOM_SYNONYMS = {
    "breathlessness": ["shortness of breath", "dyspnea", "difficulty breathing"],
    "shortness of breath": ["breathlessness", "dyspnea", "difficulty breathing"],
    "difficulty breathing": ["breathlessness", "shortness of breath", "dyspnea"],
    "dyspnea": ["breathlessness", "shortness of breath", "difficulty breathing"],
    "wheezing": ["wheeze", "whistling breath"],
    "cough": ["coughing", "persistent cough"],
    "chest pain": ["chest tightness", "chest discomfort"],
    "abdominal pain": ["stomach pain", "belly pain", "abdominal discomfort"],
    "fever": ["high temperature", "elevated temp"],
    "fatigue": ["tiredness", "exhaustion", "weakness"],
}


def _normalize_symptom(symptom):
    """Normalize a symptom by checking synonyms and returning all variations."""
    if not symptom:
        return []
    symptom_lower = symptom.strip().lower()
    # Collect all synonyms for this symptom
    variations = [symptom_lower]
    if symptom_lower in SYMPTOM_SYNONYMS:
        variations.extend(SYMPTOM_SYNONYMS[symptom_lower])
    # Also check if symptom is a synonym of another symptom
    for key, syns in SYMPTOM_SYNONYMS.items():
        if symptom_lower in [s.lower() for s in syns]:
            variations.append(key)
            variations.extend(syns)
    return list(set(variations))  # Remove duplicates


def _part_base_candidates(data_df, part, specialization=""):
    part_key = (part or "").strip().lower()
    specialties = PART_TO_SPECIALIZATIONS.get(part_key, [part_key or part])
    specialty_pattern = _build_term_pattern(specialties, whole_word=True)
    part_pattern = _build_term_pattern([part_key], whole_word=True) if part_key else ""

    candidates = data_df.copy()
    if specialization:
        candidates = candidates[
            candidates["specialization"].str.contains(specialization, case=False, na=False)
        ]

    if not part_key:
        return candidates

    specialty_mask = (
        candidates["specialization"].str.contains(specialty_pattern, case=False, regex=True, na=False)
        if specialty_pattern
        else pd.Series(False, index=candidates.index)
    )
    department_mask = (
        candidates["department"].str.contains(part_pattern, case=False, regex=True, na=False)
        if part_pattern
        else pd.Series(False, index=candidates.index)
    )
    body_part_mask = (
        candidates["body_part"].str.contains(part_pattern, case=False, regex=True, na=False)
        if part_pattern
        else pd.Series(False, index=candidates.index)
    )
    return candidates[specialty_mask | department_mask | body_part_mask]


def _build_disease_mask(candidates, disease):
    if not disease:
        return pd.Series(True, index=candidates.index)

    exact_disease = _safe_text(disease)
    if not exact_disease:
        return pd.Series(True, index=candidates.index)

    exact_mask = candidates["department"].str.fullmatch(
        re.escape(exact_disease), case=False, na=False
    )
    if exact_mask.any():
        return exact_mask

    disease_aliases = {
        "Viral fever": "Fever",
        "Heart Attack": "Heart Disease",
        "Coronary Artery Disease": "Heart Disease",
        "Arrhythmia": "Heart Disease",
        "Heart Failure": "Heart Disease",
        "Pericarditis": "Heart Disease",
        "Migraine": "Migraine",
        "Fracture": "Fracture",
        "Skin Allergy": "Skin Allergy",
    }
    alias = _safe_text(disease_aliases.get(exact_disease, exact_disease))
    if not alias:
        return pd.Series(True, index=candidates.index)

    alias_mask = candidates["department"].str.fullmatch(
        re.escape(alias), case=False, na=False
    )
    if alias_mask.any():
        return alias_mask

    pattern = re.escape(alias)
    return candidates["department"].str.contains(
        pattern, case=False, regex=True, na=False
    ) | candidates["body_part"].str.contains(
        pattern, case=False, regex=True, na=False
    )


def _haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two coordinates."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371  # Earth radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R * c


def _resolve_city_name(location):
    text = str(location or "").strip()
    if not text:
        return None
    if text in CITY_COORDS:
        return text

    lowered = text.lower()
    for city in CITY_COORDS:
        if city.lower() == lowered:
            return city
    return None


def _get_nearby_cities(location, max_distance_km=150):
    """Get cities within max_distance_km of the given location."""
    resolved_location = _resolve_city_name(location)
    if not resolved_location:
        return []
    target_lat, target_lon = CITY_COORDS[resolved_location]
    nearby = []
    for city, (lat, lon) in CITY_COORDS.items():
        if city == resolved_location:
            continue  # Skip the location itself
        dist = _haversine_distance(target_lat, target_lon, lat, lon)
        if dist <= max_distance_km:
            nearby.append((city, dist))
    return sorted(nearby, key=lambda x: x[1])  # Sort by distance



CITY_COORDS = {
    "Chennai": (13.0827, 80.2707),
    "Coimbatore": (11.0168, 76.9558),
    "Madurai": (9.9252, 78.1198),
    "Salem": (11.6643, 78.1460),
    "Trichy": (10.7905, 78.7047),
    "Erode": (11.3410, 77.7172),
    "Tirunelveli": (8.7139, 77.7564),
    "Vellore": (12.9165, 79.1325),
    "Thoothukudi": (8.7642, 78.1348),
    "Dindigul": (10.3670, 77.9803),
    "Cuddalore": (11.7449, 79.7656),
    "Kanchipuram": (12.8342, 79.7036),
    "Karur": (10.9590, 78.0766),
    "Nagapattinam": (10.7737, 79.8430),
    "Thanjavur": (10.7867, 79.1378),
}


def get_doctor_recommendations(data_df, part, age, fees, location, disease, symptom, specialization, doctor_name=""):
    part_key = str(part or "").strip().lower()
    part_aliases = {
        "eyes": "eye",
        "tooth": "teeth",
        "bone": "bones",
        "skin": "skin-hair",
        "nose": "ent",
        "neuro": "brain",
    }
    part_key = part_aliases.get(part_key, part_key)

    normalized_disease = str(disease or "").strip().lower()
    inferred_part = ""
    if normalized_disease:
        for key, part_slug in DISEASE_TO_PART.items():
            if key in normalized_disease:
                inferred_part = part_slug
                break

    resolved_part = part_key or inferred_part
    base_candidates = _part_base_candidates(data_df, resolved_part, specialization)
    if base_candidates.empty:
        base_candidates = data_df.copy()

    seen_ids = set()
    collected = []

    def add_from_df(df_subset, tier_weight, tier_name):
        if df_subset is None or df_subset.empty:
            return
        for _, row in df_subset.iterrows():
            did = str(row["doctor_id"])
            if did not in seen_ids:
                seen_ids.add(did)
                item = row.to_dict()
                item["_tier_weight"] = float(tier_weight)
                item["_tier_name"] = str(tier_name)
                collected.append(item)

    disease_mask_all = _build_disease_mask(base_candidates, disease)
    has_fees = fees is not None and str(fees).strip() != ""
    fee_val = None
    if has_fees:
        try:
            fee_val = float(fees)
        except (ValueError, TypeError):
            fee_val = None

    loc_mask = pd.Series(True, index=base_candidates.index)
    if location and str(location).strip():
        pattern = rf"\b{re.escape(str(location).strip())}\b"
        loc_mask = base_candidates["location"].astype(str).str.contains(pattern, case=False, regex=True, na=False)

    fee_mask = pd.Series(True, index=base_candidates.index)
    if fee_val is not None:
        fee_mask = pd.to_numeric(base_candidates["consultation_fee"], errors="coerce") <= fee_val

    sym_mask = pd.Series(True, index=base_candidates.index)
    if symptom and str(symptom).strip():
        sym_vars = _normalize_symptom(str(symptom).strip())
        sym_pat = "|".join([re.escape(s) for s in sym_vars])
        sym_mask = (
            base_candidates["complaint_category"].astype(str).str.contains(sym_pat, case=False, regex=True, na=False)
            | base_candidates["symptom_text"].astype(str).str.contains(sym_pat, case=False, regex=True, na=False)
        )

    doc_mask = pd.Series(True, index=base_candidates.index)
    if doctor_name and str(doctor_name).strip():
        doc_mask = base_candidates["doctor_name"].astype(str).str.contains(str(doctor_name).strip(), case=False, na=False)

    TARGET_COUNT = 15

    # Tier 1: Exact matches (part + disease + loc + fee + sym + doc)
    t1 = base_candidates[disease_mask_all & loc_mask & fee_mask & sym_mask & doc_mask]
    add_from_df(t1, 60.0, "Exact Match")

    # Tier 2: Same location + disease + within fee (relax symptom & doc)
    if len(collected) < TARGET_COUNT:
        t2 = base_candidates[disease_mask_all & loc_mask & fee_mask]
        add_from_df(t2, 50.0, "Disease Match (Local)")

    # Tier 3: Same location + disease (relax fee ceiling)
    if len(collected) < TARGET_COUNT:
        t3 = base_candidates[disease_mask_all & loc_mask]
        add_from_df(t3, 40.0, "Disease Match (Above Budget)")

    # Tier 4: Same location + body part specialists
    if len(collected) < TARGET_COUNT:
        t4 = base_candidates[loc_mask]
        add_from_df(t4, 32.0, "Specialist Match (Local)")

    # Tier 5: Nearby cities for same disease & body part
    if len(collected) < TARGET_COUNT and location:
        nearby = _get_nearby_cities(str(location).strip(), max_distance_km=250)
        for near_city, dist in nearby:
            if len(collected) >= TARGET_COUNT:
                break
            near_pat = rf"\b{re.escape(near_city)}\b"
            near_mask = base_candidates["location"].astype(str).str.contains(near_pat, case=False, regex=True, na=False)
            t5_near = base_candidates[disease_mask_all & near_mask]
            add_from_df(t5_near, max(20.0, 30.0 - (dist / 15.0)), f"Nearby Specialist ({near_city})")

    # Tier 6: State-wide top specialists for same disease & body part
    if len(collected) < TARGET_COUNT:
        t6 = base_candidates[disease_mask_all]
        add_from_df(t6, 20.0, "Top Specialist (Statewide)")

    # Tier 7: Nearby cities for same body part
    if len(collected) < TARGET_COUNT and location:
        nearby = _get_nearby_cities(str(location).strip(), max_distance_km=250)
        for near_city, dist in nearby:
            if len(collected) >= TARGET_COUNT:
                break
            near_pat = rf"\b{re.escape(near_city)}\b"
            near_mask = base_candidates["location"].astype(str).str.contains(near_pat, case=False, regex=True, na=False)
            t7_near = base_candidates[near_mask]
            add_from_df(t7_near, max(15.0, 25.0 - (dist / 15.0)), f"Nearby Doctor ({near_city})")

    # Tier 8: Same district all doctors in dataset
    if len(collected) < TARGET_COUNT and location:
        all_loc_mask = data_df["location"].astype(str).str.contains(
            rf"\b{re.escape(str(location).strip())}\b", case=False, regex=True, na=False
        )
        t8 = data_df[all_loc_mask]
        add_from_df(t8, 12.0, "Verified Local Doctor")

    # Tier 9: State-wide body part candidates
    if len(collected) < TARGET_COUNT:
        add_from_df(base_candidates, 8.0, "Verified Specialist")

    # Tier 10: Absolute state-wide fallback
    if len(collected) < 10:
        add_from_df(data_df, 2.0, "Verified Doctor")

    if not collected:
        return []

    cand_df = pd.DataFrame(collected)

    cand_df["predicted_sentiment"] = cand_df["feedback_text"].fillna("").apply(predict_sentiment)
    sentiment_score = (
        cand_df["predicted_sentiment"]
        .astype(str)
        .str.lower()
        .map({"positive": 1.0, "neutral": 0.5, "negative": 0.0})
        .fillna(0.5)
    )
    rating_score = _normalize_series(cand_df["average_rating"])
    fee_score = 1 - _normalize_series(cand_df["consultation_fee"])
    rec_label = cand_df["recommendation_label"].fillna(0).astype(float)
    tier_weight = cand_df["_tier_weight"].astype(float)

    cand_df["recommendation_score"] = (
        tier_weight * 2.0
        + rating_score * 4.0
        + sentiment_score * 2.0
        + rec_label * 2.0
        + fee_score * 1.0
    ).round(2)

    cand_df = cand_df.sort_values(
        by=["recommendation_score", "average_rating", "consultation_fee"],
        ascending=[False, False, True],
    )
    def _compute_lat_lon(row):
        city = str(row.get("location", "")).strip()
        coords = CITY_COORDS.get(city)
        if coords:
            lat_jitter = coords[0] + (hash(str(row.get("doctor_name", ""))) % 100 - 50) * 0.0003
            lon_jitter = coords[1] + (hash(str(row.get("hospital", ""))) % 100 - 50) * 0.0003
            return round(lat_jitter, 6), round(lon_jitter, 6)
        return 11.0, 78.7

    cand_df["lat"], cand_df["lon"] = zip(*cand_df.apply(_compute_lat_lon, axis=1))

    return cand_df.head(15).to_dict(orient="records")


def get_doctor_body_part(doctor):
    """Derive canonical body part slug from doctor details."""
    if not doctor or not isinstance(doctor, dict):
        return "general"

    bp = str(doctor.get("body_part") or "").strip().lower()
    valid_parts = {"heart", "liver", "lungs", "brain", "kidney", "eye", "bones", "ent", "teeth", "general"}
    if bp in valid_parts:
        return bp
    if bp in ("skin", "skin-hair"):
        return "skin-hair"
    if bp == "bone":
        return "bones"
    if bp == "eyes":
        return "eye"

    spec = str(doctor.get("specialization") or "").strip().lower()
    for part, specs in PART_TO_SPECIALIZATIONS.items():
        canonical_part = (
            "skin-hair" if part in ("skin", "skin-hair")
            else "bones" if part in ("bone", "bones")
            else "eye" if part in ("eye", "eyes")
            else "ent" if part in ("ent", "nose")
            else part
        )
        for s in specs:
            if s.lower() in spec or spec in s.lower():
                return canonical_part

    dept = str(doctor.get("department") or "").strip().lower()
    for disease_key, part_slug in DISEASE_TO_PART.items():
        if disease_key in dept or disease_key in spec:
            canonical_part = (
                "skin-hair" if part_slug in ("skin", "skin-hair")
                else "bones" if part_slug in ("bone", "bones")
                else "eye" if part_slug in ("eye", "eyes")
                else "ent" if part_slug in ("ent", "nose")
                else part_slug
            )
            return canonical_part

    return "general"


def get_doctor_details(data_df, doctor_id):
    if "doctor_id" not in data_df.columns:
        return None
    row = data_df[data_df["doctor_id"] == doctor_id]
    if row.empty:
        return None
    doc = row.iloc[0].to_dict()
    doc["body_part_slug"] = get_doctor_body_part(doc)
    city = str(doc.get("location", "")).strip()
    coords = CITY_COORDS.get(city)
    if coords:
        lat_jitter = coords[0] + (hash(str(doc.get("doctor_name", ""))) % 100 - 50) * 0.0003
        lon_jitter = coords[1] + (hash(str(doc.get("hospital", ""))) % 100 - 50) * 0.0003
        doc["lat"] = round(lat_jitter, 6)
        doc["lon"] = round(lon_jitter, 6)
    else:
        doc["lat"] = 11.0
        doc["lon"] = 78.7
    return doc


def get_map_data(data_df, location=None):
    candidates = data_df.copy()
    if location and str(location).strip():
        pattern = rf"\b{re.escape(str(location).strip())}\b"
        candidates = candidates[candidates["location"].str.contains(pattern, case=False, regex=True, na=False)]
    else:
        # Default view: pick top-rated doctors across all 15 districts
        top_by_city = []
        for city in CITY_COORDS.keys():
            city_docs = candidates[candidates["location"].str.fullmatch(re.escape(city), case=False, na=False)]
            if not city_docs.empty:
                top_by_city.append(city_docs.sort_values(by=["average_rating"], ascending=False).head(4))
        if top_by_city:
            candidates = pd.concat(top_by_city, ignore_index=True)

    candidates = candidates.drop_duplicates(subset=["location", "doctor_name"])
    if location and str(location).strip():
        candidates = candidates.sort_values(by=["average_rating"], ascending=False).head(20)
    map_data = []
    for _, row in candidates.iterrows():
        city = str(row.get("location", "")).strip()
        coords = CITY_COORDS.get(city)
        if not coords:
            continue
        # Slight jitter for distinct markers in same city
        lat_jitter = coords[0] + (hash(str(row.get("doctor_name", ""))) % 100 - 50) * 0.0003
        lon_jitter = coords[1] + (hash(str(row.get("hospital", ""))) % 100 - 50) * 0.0003
        map_data.append({
            "doctor_id": int(row.get("doctor_id", -1)),
            "doctor": row.get("doctor_name", "Unknown"),
            "specialization": row.get("specialization", "Specialist"),
            "department": row.get("department", ""),
            "hospital": row.get("hospital", ""),
            "location": city,
            "consultation_fee": int(row.get("consultation_fee", 500)) if pd.notna(row.get("consultation_fee")) else 500,
            "experience_years": row.get("experience_years", 5),
            "lat": round(lat_jitter, 6),
            "lon": round(lon_jitter, 6),
            "rating": row.get("average_rating", 4.5),
        })
    return map_data


def answer_medical_query(faq_df, query_text):
    global faq_vectorizer, faq_tfidf
    if not query_text:
        return "Please enter a question about symptoms, disease, or treatment."

    query_lower = query_text.lower()

    # Check for fever-related queries
    if "fever" in query_lower:
        fever_advice = (
            "For fever, take over-the-counter medications like paracetamol (acetaminophen) or ibuprofen. "
            "Stay hydrated, rest, and monitor your temperature. If fever exceeds 103°F (39.4°C), persists for more than 3 days, "
            "or is accompanied by severe symptoms, consult a doctor immediately.\n\n"
            "Recommended doctors: General Physician or Family Medicine specialist."
        )
        return fever_advice

    # Check if query is about doctors
    doctor_keywords = ["doctor", "specialist", "physician", "consult", "see a", "visit"]
    is_doctor_query = any(keyword in query_lower for keyword in doctor_keywords)

    query_vec = faq_vectorizer.transform([query_text])
    similarity_scores = cosine_similarity(query_vec, faq_tfidf)[0]
    query_tokens = _meaningful_tokens(query_text)
    if not query_tokens:
        query_tokens = _tokenize_text(query_text)

    best_index = 0
    best_score = -1.0
    best_similarity = 0.0
    best_keyword_overlap = 0
    for index, (_, row) in enumerate(faq_df.iterrows()):
        keyword_tokens = _meaningful_tokens(row.get("keywords", ""))
        question_tokens = _meaningful_tokens(row.get("question", ""))
        keyword_overlap = len(query_tokens & keyword_tokens)
        question_overlap = len(query_tokens & question_tokens)
        similarity_value = similarity_scores[index]
        combined_score = (
            similarity_value +
            (keyword_overlap * 0.18) +
            (question_overlap * 0.06)
        )
        if combined_score > best_score:
            best_score = combined_score
            best_index = index
            best_similarity = similarity_value
            best_keyword_overlap = keyword_overlap

    if best_score < 0.05:  # Lower threshold to always respond
        disease_hint = ", ".join(sorted(dataset_condition_guidance.keys())[:5])
        query_label = _clean_query_label(query_text)
        general_advice = (
            f"I could not find a close direct match in the combined dataset for {query_label}. "
            "However, for general health concerns, it's important to monitor symptoms and consult a healthcare professional. "
            f"Common conditions include {disease_hint}. Please provide more details or see a doctor."
        )
        if is_doctor_query and doctor_examples:
            general_advice += f" Example doctors: {', '.join(doctor_examples[:3])}."
        return general_advice

    best_answer = str(faq_df.iloc[best_index].get("answer", "")).strip()
    if not best_answer or best_answer.lower() == "nan":
        return (
            "I found a related topic, but the answer entry is incomplete. "
            "Please try a more specific symptom or consult a doctor for guidance."
        )
    if is_doctor_query and doctor_examples:
        best_answer += f"\n\nExample doctors from the combined dataset: {', '.join(doctor_examples[:3])}."

    return best_answer


EXPANDED_SYNONYMS = {
    "sugar": "diabetes blood sugar glucose",
    "high sugar": "diabetes",
    "low sugar": "hypoglycemia diabetes",
    "bp": "hypertension high blood pressure",
    "high bp": "hypertension high blood pressure",
    "low bp": "hypotension blood pressure",
    "loose motion": "diarrhea loose motion",
    "loose motions": "diarrhea loose motion",
    "motions": "diarrhea loose motion",
    "hair fall": "hair loss alopecia",
    "hairfall": "hair loss alopecia",
    "hair loss": "hair loss alopecia",
    "dandruff": "dandruff seborrheic dermatitis",
    "ear pain": "ear pain otitis media",
    "earache": "ear pain otitis media",
    "hearing loss": "ear hearing problem",
    "throat pain": "sore throat tonsillitis pharyngitis",
    "sore throat": "sore throat tonsillitis pharyngitis",
    "tonsils": "tonsillitis sore throat",
    "knee pain": "knee pain joint arthritis osteoarthritis",
    "knee": "knee pain joint arthritis",
    "back pain": "back pain lumbar spine sciatica",
    "backache": "back pain spine",
    "neck pain": "neck pain cervical spondylosis",
    "joint pain": "arthritis joint pain swelling",
    "body pain": "body pain viral fever fatigue",
    "chest pain": "chest pain heart attack angina cardiac",
    "heart attack": "heart attack coronary artery disease",
    "stomach pain": "stomach pain gastritis abdominal cramps",
    "belly pain": "stomach pain gastritis",
    "vomit": "vomiting nausea gastroenteritis",
    "vomiting": "vomiting nausea gastroenteritis",
    "acidity": "acidity gas gerd acid reflux heartburn",
    "gas": "acidity gas gastric bloating",
    "gastric": "acidity gastritis gastric ulcer",
    "constipation": "constipation bowel problem hard stool",
    "piles": "piles hemorrhoids anal fissure",
    "hernia": "hernia inguinal hernia",
    "appendix": "appendicitis abdominal pain",
    "appendicitis": "appendicitis abdominal pain",
    "jaundice": "jaundice liver disease hepatitis",
    "fatty liver": "fatty liver disease hepatology",
    "kidney stone": "kidney stone renal calculus",
    "kidney pain": "kidney problem renal pain",
    "urine infection": "urinary tract infection uti burning urination",
    "burning urination": "urinary tract infection uti burning urination",
    "cold": "common cold runny nose sneezing viral",
    "cough": "cough bronchitis respiratory",
    "phlegm": "cough chest congestion phlegm",
    "fever": "fever viral temperature infection",
    "high fever": "fever viral infection",
    "headache": "headache migraine neurological",
    "migraine": "migraine headache neurological",
    "dizziness": "dizziness vertigo brain",
    "vertigo": "vertigo dizziness inner ear",
    "asthma": "asthma wheezing breathlessness respiratory",
    "wheezing": "asthma wheezing breathlessness",
    "breathlessness": "asthma shortness of breath respiratory",
    "shortness of breath": "breathlessness asthma respiratory",
    "skin allergy": "skin allergy rash itching dermatitis",
    "itching": "skin allergy itching rash pruritus",
    "rash": "skin rash eczema allergy",
    "acne": "acne pimples skin",
    "pimples": "acne pimples skin",
    "thyroid": "thyroid disorder hypothyroidism hyperthyroidism",
    "depression": "depression mental health anxiety",
    "anxiety": "anxiety panic stress mental health",
    "sleeplessness": "insomnia sleep disorder anxiety",
    "insomnia": "insomnia sleep disorder anxiety",
    "period pain": "menstrual cramps periods pcos",
    "irregular periods": "pcos irregular periods gynecology",
    "pcos": "pcos pcod irregular periods gynecology",
    "pregnancy": "pregnancy maternity gynecology",
    "fracture": "bone fracture orthopedic injury",
    "sprain": "sprain ligament injury orthopedic",
    "cancer": "cancer tumor oncology malignancy",
    "tumor": "cancer tumor oncology",
}


def _lookup_dataset_guidance(query_text, data_df):
    if data_df is None or (hasattr(data_df, "empty") and data_df.empty):
        return None

    q_clean = query_text.lower().strip()
    words = [w for w in re.split(r'[^a-z0-9]+', q_clean) if len(w) >= 3 and w not in GENERIC_QUERY_WORDS]
    if not words:
        words = [q_clean]

    pattern = '|'.join([re.escape(w) for w in words])
    try:
        matches = data_df[
            data_df["department"].astype(str).str.contains(pattern, case=False, na=False) |
            data_df["complaint_category"].astype(str).str.contains(pattern, case=False, na=False) |
            data_df["symptom_text"].astype(str).str.contains(pattern, case=False, na=False)
        ]
    except Exception:
        return None

    if matches.empty:
        return None

    top_dept = matches["department"].dropna().value_counts().index[0]
    top_spec = matches["specialization"].dropna().value_counts().index[0] if not matches["specialization"].dropna().empty else "Specialist"
    top_complaints = matches["complaint_category"].dropna().value_counts().head(3).index.tolist()
    sample_docs = matches["doctor_name"].dropna().unique()[:3].tolist()
    doc_str = f" Qualified specialists in our dataset include {', '.join(sample_docs)}." if sample_docs else ""

    return {
        "title": f"{top_dept} Care & Treatment",
        "summary": f"Based on hospital records, your query matches clinical cases in {top_dept}.",
        "possible_reasons": [
            f"Common symptoms documented in hospital records: {', '.join(top_complaints) or 'Clinical symptoms of ' + top_dept}",
            "Underlying infection, tissue inflammation, or structural strain",
            "Symptom severity varies by patient age, physical condition, and duration",
        ],
        "medicines": [
            f"Doctor-prescribed treatment plan specific to {top_dept}",
            "Standard pain relief or topical treatments under pharmacist guidance",
            "Avoid self-medicating with antibiotics or steroids without prescription",
        ],
        "self_care": [
            "Monitor symptoms daily and avoid known aggravating factors",
            "Maintain proper hydration, nutrition, and adequate rest",
            "Schedule an in-person consultation with a qualified doctor",
        ],
        "specialist": top_spec,
        "emergency": [
            "Rapidly worsening pain or breathing difficulty",
            "High fever, fainting, or sudden loss of normal function",
        ],
        "faq_answer": f"Patients with {top_dept} are evaluated and treated by {top_spec} specialists.{doc_str}",
        "disclaimer": "This information is derived from clinical dataset records and is intended for general health awareness only. Please consult a qualified specialist for personal diagnosis.",
    }


def _generate_dynamic_clinical_guidance(query_text):
    q_clean = query_text.lower().strip()
    title_words = [w.capitalize() for w in query_text.strip().split() if w.lower() not in GENERIC_QUERY_WORDS]
    title = " ".join(title_words) if title_words else query_text.strip().capitalize()
    if not title.lower().endswith(("problems", "care", "disease", "pain", "syndrome", "disorder")):
        display_title = f"{title} Care & Guidance"
    else:
        display_title = title

    spec = "General Physician"
    reasons = [
        "Infection, inflammation, or acute physiological strain",
        "Environmental triggers, lifestyle factors, or underlying condition",
        "Early stage of a localized or systemic health issue",
    ]
    emergency = [
        "Severe, unbearable pain or sudden collapse",
        "Breathing difficulty, confusion, or uncontrolled bleeding",
    ]

    if any(w in q_clean for w in ["heart", "chest", "angina", "cardiac", "artery", "pulse", "bp", "pressure"]):
        spec = "Cardiologist"
        emergency = ["Chest tightness radiating to arm or jaw", "Shortness of breath with sweating"]
    elif any(w in q_clean for w in ["eye", "vision", "cataract", "glaucoma", "blind", "cornea"]):
        spec = "Ophthalmologist"
        emergency = ["Sudden vision loss", "Severe eye trauma or acute redness with pain"]
    elif any(w in q_clean for w in ["ear", "hearing", "throat", "nose", "sinus", "tonsil", "vocal"]):
        spec = "ENT Specialist"
        emergency = ["Difficulty swallowing or breathing", "Bleeding from ear or nose with high fever"]
    elif any(w in q_clean for w in ["bone", "knee", "back", "joint", "spine", "fracture", "ligament", "muscle", "sciatica", "disc"]):
        spec = "Orthopedic Doctor"
        emergency = ["Visible bone deformity or inability to bear weight", "Sudden numbness or tingling in legs"]
    elif any(w in q_clean for w in ["brain", "headache", "migraine", "nerve", "dizzy", "vertigo", "seizure", "stroke", "paralysis"]):
        spec = "Neurologist"
        emergency = ["Facial drooping, arm weakness, slurred speech (stroke sign)", "Severe sudden thunderstorm headache"]
    elif any(w in q_clean for w in ["stomach", "vomit", "acidity", "diarrhea", "bowel", "digestion", "liver", "jaundice", "abdomen", "piles", "hernia"]):
        spec = "Gastroenterologist / General Surgeon"
        emergency = ["Vomiting blood or black stools", "Unbearable abdominal pain with rigid abdomen"]
    elif any(w in q_clean for w in ["skin", "rash", "itching", "allergy", "hair", "acne", "eczema"]):
        spec = "Dermatologist"
        emergency = ["Rapidly spreading rash with fever or facial swelling", "Difficulty breathing accompanying rash"]
    elif any(w in q_clean for w in ["kidney", "urine", "bladder", "urination", "prostate"]):
        spec = "Urologist or Nephrologist"
        emergency = ["Inability to pass urine", "Severe flank pain with blood in urine"]
    elif any(w in q_clean for w in ["lung", "breath", "cough", "asthma", "wheezing"]):
        spec = "Pulmonologist"
        emergency = ["Gasping for air or blue lips", "Coughing up significant blood"]
    elif any(w in q_clean for w in ["sugar", "diabetes", "thyroid", "hormone", "endocrine"]):
        spec = "Endocrinologist or General Physician"
        emergency = ["Extremely high or low sugar with confusion", "Fainting or severe dehydration"]
    elif any(w in q_clean for w in ["cancer", "tumor", "oncology", "lump", "malignan"]):
        spec = "Oncologist"
        emergency = ["Sudden unexplained weight loss, bleeding, or rapidly enlarging mass"]
    elif any(w in q_clean for w in ["period", "menstrual", "pregnancy", "pcos", "ovary", "uterus", "breast"]):
        spec = "Gynecologist"
        emergency = ["Heavy acute pelvic bleeding with dizziness", "Severe sharp one-sided pelvic pain"]

    return {
        "title": display_title,
        "summary": f"Clinical guidance for {query_text.strip()}. For comprehensive diagnosis, please consult a {spec}.",
        "possible_reasons": reasons,
        "medicines": [
            f"Doctor-directed medication suited to your age and clinical condition",
            "Avoid self-prescribing antibiotics, pain killers, or steroid treatments",
            "Discuss any ongoing medicines with your doctor to avoid drug interactions",
        ],
        "self_care": [
            "Track symptoms carefully (timing, severity, and any relief factors)",
            "Get sufficient sleep, rest, and drink plenty of fluids",
            "Schedule an in-person clinical checkup with a specialist",
        ],
        "specialist": spec,
        "emergency": emergency,
        "faq_answer": f"For {query_text.strip()}, consult a {spec} who can order relevant lab tests or imaging for accurate diagnosis.",
        "disclaimer": "This tool provides general medical information only and does not replace in-person clinical diagnosis or prescription.",
    }


def generate_medical_guidance(faq_df, query_text, data_df=None):
    if not query_text:
        return {
            "title": "Medical Query Assistant",
            "summary": "Please enter a disease name, symptom, or short medical question.",
            "possible_reasons": [],
            "medicines": [],
            "self_care": [],
            "specialist": "",
            "emergency": [],
            "faq_answer": "",
            "disclaimer": "This tool gives general information only and is not a medical diagnosis or prescription.",
        }

    # 1. Correct misspelled disease names
    corrected_query = correct_disease_name(query_text)
    if corrected_query != query_text:
        query_text = corrected_query

    raw_query = query_text.lower().strip()
    expanded_query = raw_query

    # 2. Expand common abbreviations & colloquial terminology
    for term, expansion in EXPANDED_SYNONYMS.items():
        if re.search(r'\b' + re.escape(term) + r'\b', raw_query):
            expanded_query = expanded_query + " " + expansion

    # 3. Match specific conditions in CONDITION_GUIDANCE (longest keyword match wins)
    best_condition = None
    best_condition_len = 0
    for condition in CONDITION_GUIDANCE.values():
        for keyword in condition.get("keywords", []):
            kw_clean = keyword.lower()
            if kw_clean in expanded_query or (len(kw_clean) >= 4 and kw_clean in raw_query):
                if len(kw_clean) > best_condition_len:
                    best_condition = condition
                    best_condition_len = len(kw_clean)

    # 4. If no specific condition matched, check BODY_PART_GUIDANCE
    best_body_part = None
    best_body_part_len = 0
    if not best_condition:
        normalized_query = raw_query.rstrip("s")
        if normalized_query in BODY_PART_GUIDANCE:
            best_body_part = BODY_PART_GUIDANCE[normalized_query]
        else:
            for bp_key, bp_data in BODY_PART_GUIDANCE.items():
                for kw in bp_data.get("keywords", []):
                    kw_clean = kw.lower()
                    if kw_clean in raw_query or kw_clean in expanded_query:
                        if len(kw_clean) > best_body_part_len:
                            best_body_part = bp_data
                            best_body_part_len = len(kw_clean)

    # 5. Return matched condition or body part guidance
    matched_item = best_condition or best_body_part
    if matched_item:
        faq_ans = answer_medical_query(faq_df, query_text) if faq_df is not None else ""
        return {
            "title": matched_item["title"],
            "summary": f"Based on your query, this looks related to {matched_item['title'].lower()}.",
            "possible_reasons": matched_item.get("possible_reasons", []),
            "medicines": matched_item.get("medicines", []),
            "self_care": matched_item.get("self_care", []),
            "specialist": matched_item.get("specialist", "General Physician"),
            "emergency": matched_item.get("emergency", []),
            "faq_answer": matched_item.get("faq_answer") or faq_ans,
            "disclaimer": "Medicines listed are standard clinical examples for general awareness only. Please consult a qualified specialist before taking any prescription.",
        }

    # 6. Check dataset records in DATA_DF (matching across 26,730 patient records)
    active_data = data_df if data_df is not None else globals().get("CACHED_DATA_DF")
    dataset_match = _lookup_dataset_guidance(query_text, active_data)
    if dataset_match:
        return dataset_match

    # 7. Check dataset_condition_guidance
    for cond_key, cond_val in dataset_condition_guidance.items():
        if any(kw in raw_query for kw in cond_val.get("keywords", [])):
            return {
                "title": cond_val.get("title", query_text.title()),
                "summary": f"Based on your query, this looks related to {cond_val.get('title', query_text).lower()}.",
                "possible_reasons": cond_val.get("possible_reasons", []),
                "medicines": cond_val.get("medicines", []),
                "self_care": cond_val.get("self_care", []),
                "specialist": cond_val.get("specialist", "General Physician"),
                "emergency": cond_val.get("emergency", []),
                "faq_answer": answer_medical_query(faq_df, query_text) if faq_df is not None else "",
                "disclaimer": "This tool gives general information only and is not a medical diagnosis or personalized prescription.",
            }

    # 8. Dynamic Intelligent Medical Inference (Ensures ANY disease or symptom returns full guidance!)
    return _generate_dynamic_clinical_guidance(query_text)


def compute_filter_diagnostics(data_df, part, disease, symptom, fees, location, specialization="", doctor_name=""):
    """Return diagnostic counts and samples after each filter step to explain why no matches were found."""
    part_key = (part or "").strip().lower()
    base = _part_base_candidates(data_df, part_key, specialization)
    disease_mask_all = _build_disease_mask(base, disease)

    counts = {}
    counts['base'] = len(base)

    # disease filter
    if disease:
        step_disease = base[disease_mask_all]
    else:
        step_disease = base
    counts['after_disease'] = len(step_disease)

    # symptom filter (with synonym normalization)
    if symptom:
        symptom_variations = _normalize_symptom(symptom)
        symptom_pattern = "|".join([re.escape(s) for s in symptom_variations])
        mask = step_disease['complaint_category'].str.contains(symptom_pattern, case=False, regex=True, na=False) | step_disease['symptom_text'].str.contains(symptom_pattern, case=False, regex=True, na=False)
        step_symptom = step_disease[mask]
    else:
        step_symptom = step_disease
    counts['after_symptom'] = len(step_symptom)

    # fees filter
    try:
        if fees is not None:
            step_fees = step_symptom[pd.to_numeric(step_symptom['consultation_fee'], errors='coerce') <= float(fees)]
        else:
            step_fees = step_symptom
    except Exception:
        step_fees = step_symptom
    counts['after_fees'] = len(step_fees)

    # location filter (word-boundary)
    if location:
        pattern = rf"\b{re.escape(location)}\b"
        loc_series = step_fees['location'].astype(str)
        step_location = step_fees[ loc_series.str.contains(pattern, case=False, regex=True, na=False) ]
    else:
        step_location = step_fees
    counts['after_location'] = len(step_location)

    # Determine likely breaking step
    missing_reason = None
    if counts['after_symptom'] == 0 and counts['after_disease'] > 0:
        missing_reason = 'symptom'
    elif counts['after_location'] == 0 and counts['after_fees'] > 0 and location:
        missing_reason = 'location'
    elif counts['after_fees'] == 0 and counts['after_symptom'] > 0:
        missing_reason = 'fees'
    elif counts['after_disease'] == 0 and counts['base'] > 0:
        missing_reason = 'disease'

    samples = {
        'after_part_sample': base[['doctor_name','department','specialization','location','consultation_fee']].head(6).to_dict(orient='records'),
        'after_disease_sample': step_disease[['doctor_name','department','specialization','location','consultation_fee']].head(6).to_dict(orient='records'),
    }

    any_location_in_dataset = any(data_df['location'].astype(str).str.contains(rf"\b{re.escape(location)}\b", case=False, regex=True, na=False)) if location else True

    return {
        'counts': counts,
        'missing_reason': missing_reason,
        'samples': samples,
        'any_location_in_dataset': bool(any_location_in_dataset),
    }
