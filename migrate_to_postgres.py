import pandas as pd
import time
import sys
from pathlib import Path
from db import get_connection

WORKSPACE_DIR = Path(__file__).resolve().parent

def migrate_table(cur, con, table_name, df):
    print(f"\n[TABLE] Processing Table: \"{table_name}\" ({len(df):,} rows, {len(df.columns)} columns)...")
    t0 = time.time()
    
    # Drop table if exists
    cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
    con.commit()
    
    # Infer SQL types preserving exact schema
    col_defs = []
    for col in df.columns:
        dtype = df[col].dtype
        if "int" in str(dtype):
            sql_type = "BIGINT"
        elif "float" in str(dtype):
            sql_type = "DOUBLE PRECISION"
        else:
            sql_type = "TEXT"
        col_defs.append(f'"{col}" {sql_type}')
    
    create_sql = f'CREATE TABLE "{table_name}" ({", ".join(col_defs)});'
    cur.execute(create_sql)
    con.commit()
    print(f"  [OK] Schema created for \"{table_name}\"")
    
    # Prepare data rows
    cols_quoted = ', '.join([f'"{c}"' for c in df.columns])
    placeholders = ', '.join(['%s'] * len(df.columns))
    insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders});'
    
    # Convert DataFrame to clean Python records (None for NaN)
    raw_records = df.values.tolist()
    clean_records = []
    for row in raw_records:
        clean_row = []
        for val in row:
            if pd.isna(val) or val is None:
                clean_row.append(None)
            elif hasattr(val, 'item'):
                clean_row.append(val.item())
            else:
                clean_row.append(val)
        clean_records.append(clean_row)
        
    # Batch execute
    batch_size = 2000
    total = len(clean_records)
    for i in range(0, total, batch_size):
        batch = clean_records[i : i + batch_size]
        cur.executemany(insert_sql, batch)
        con.commit()
        sys.stdout.write(f"\r  [PROGRESS] Inserted {min(i + batch_size, total):,}/{total:,} rows...")
        sys.stdout.flush()
        
    print(f"\n  [OK] Completed in {time.time() - t0:.2f} seconds")
    
    # Verify row count
    cur.execute(f'SELECT COUNT(*) FROM "{table_name}";')
    count = cur.fetchone()[0]
    print(f"  [VERIFY] SELECT COUNT(*) FROM \"{table_name}\" -> {count:,} rows")
    assert count == len(df), f"Row count mismatch: expected {len(df)}, got {count}"

def run_all_migrations():
    print("=" * 60)
    print("HEALTHCARE AI SYSTEM - POSTGRESQL DATASET MIGRATION")
    print("=" * 60)

    con = get_connection()
    cur = con.cursor()
    print("[INFO] Successfully connected to PostgreSQL database!")

    try:
        # 1. Doctors Dataset
        print("\n[Step 1/4] Loading Doctors Dataset (Final_20Hospitals_Per_District.xlsx)...")
        t_read = time.time()
        excel_path = WORKSPACE_DIR / "Final_20Hospitals_Per_District.xlsx"
        df_doctors = pd.read_excel(excel_path)
        print(f"  Loaded Excel in {time.time() - t_read:.2f}s")
        migrate_table(cur, con, "doctors", df_doctors)

        # 2. Patients Progress Dataset
        print("\n[Step 2/4] Loading Patients Dataset (patients_progress.xlsx)...")
        df_patients = pd.read_excel(WORKSPACE_DIR / "patients_progress.xlsx")
        migrate_table(cur, con, "patients", df_patients)

        # 3. Patient Reviews Dataset
        print("\n[Step 3/4] Loading Patient Reviews Dataset (patient_review.xlsx)...")
        df_reviews = pd.read_excel(WORKSPACE_DIR / "patient_review.xlsx")
        migrate_table(cur, con, "patient_reviews", df_reviews)

        # 4. FAQ Dataset
        print("\n[Step 4/4] Loading FAQ Dataset (faq.csv)...")
        df_faq = pd.read_csv(WORKSPACE_DIR / "faq.csv")
        migrate_table(cur, con, "faqs", df_faq)

        print("\n" + "=" * 60)
        print("[SUCCESS] ALL 4 DATASETS SUCCESSFULLY MIGRATED TO POSTGRESQL!")
        print("=" * 60)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            con.close()
        except Exception:
            pass

if __name__ == "__main__":
    run_all_migrations()
