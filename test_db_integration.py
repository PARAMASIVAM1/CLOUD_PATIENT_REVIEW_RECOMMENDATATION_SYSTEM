import sys
import pg8000.dbapi
import pandas as pd
from db import is_db_connected, load_doctors_df, load_faqs_df, load_patients_df, load_reviews_df
from model import load_data, get_doctor_recommendations

print("=== 1. Testing DB Connectivity ===")
assert is_db_connected(), "PostgreSQL is not connected!"
print("[OK] Database connection successful!")

print("\n=== 2. Testing Row Counts & Data Integrity ===")
df_docs = load_doctors_df()
print(f"[OK] Doctors Table: {len(df_docs):,} rows (Expected: 26,712)")
assert len(df_docs) == 26712, f"Expected 26712, got {len(df_docs)}"

df_faqs = load_faqs_df()
print(f"[OK] FAQs Table: {len(df_faqs):,} rows (Expected: 104)")
assert len(df_faqs) == 104, f"Expected 104, got {len(df_faqs)}"

df_pats = load_patients_df()
print(f"[OK] Patients Table: {len(df_pats):,} rows (Expected: >= 5)")
assert len(df_pats) >= 5, f"Expected >= 5, got {len(df_pats)}"

df_revs = load_reviews_df()
print(f"[OK] Patient Reviews Table: {len(df_revs):,} rows (Expected: >= 23)")
assert len(df_revs) >= 23, f"Expected >= 23, got {len(df_revs)}"

print("\n=== 3. Testing Model Loading & Doctor Recommendations ===")
data_df, faq_df = load_data()
print(f"[OK] load_data() returned {len(data_df):,} doctors, {len(faq_df):,} FAQs")

# Test recommendation with correct signature
recs = get_doctor_recommendations(
    data_df=data_df,
    part="heart",
    age=35,
    fees=1000,
    location="Chennai",
    disease="Cardiology",
    symptom="Chest Pain",
    specialization="Cardiologist"
)
print(f"[OK] Doctor Recommendations for Cardiology in Chennai: {len(recs)} doctors found")
assert len(recs) >= 10, f"Expected at least 10 doctors, got {len(recs)}"
print(f"  First recommendation: {recs[0]['doctor_name']} at {recs[0]['hospital']} ({recs[0]['location']})")

print("\n=======================================================")
print("[SUCCESS] ALL POSTGRESQL INTEGRATION TESTS PASSED 100%!")
print("=======================================================")

