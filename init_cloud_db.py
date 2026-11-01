"""
init_cloud_db.py - Automated Database Setup & Migration for Render Cloud Deployment

Guarantees:
1. All schemas and tables (patients, doctors, appointments, patient_reviews, notifications, faqs, hospitals) exist.
2. If doctors catalogue is empty, imports the 26,712 doctors dataset via high-speed multi-row batch insert (~3s).
3. Seeds all localhost storage history (registered patients, appointments, reviews, notifications, hospitals, faqs).
4. Synchronizes PostgreSQL auto-increment sequences.
"""

import os
import sys
import time
from pathlib import Path
from db import get_connection, is_db_connected
import init_system_db

WORKSPACE_DIR = Path(__file__).resolve().parent

def wait_for_db(max_retries=15, delay=2):
    """Wait for database to become reachable on cloud startup."""
    print("[DB] Verifying PostgreSQL connection...")
    for attempt in range(1, max_retries + 1):
        if is_db_connected():
            print(f"[DB] PostgreSQL connection verified (attempt {attempt}).")
            return True
        print(f"[DB] Waiting for PostgreSQL to be ready (attempt {attempt}/{max_retries})...")
        time.sleep(delay)
    return False

def seed_doctors_dataset(cur, con):
    """Import the 26,712 doctors dataset using high-speed multi-row SQL batches."""
    excel_path = WORKSPACE_DIR / "Final_20Hospitals_Per_District.xlsx"
    if not excel_path.exists():
        print(f"[WARN] Doctors dataset {excel_path} not found!")
        return False

    import pandas as pd
    t0 = time.time()
    print(f"[INFO] Loading doctors catalogue from {excel_path.name}...")
    df = pd.read_excel(excel_path)
    print(f"  [OK] Read {len(df):,} doctor records in {time.time() - t0:.2f}s")

    # Get doctors table columns
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'doctors';")
    existing_cols = {r[0] for r in cur.fetchall()}

    valid_cols = [c for c in df.columns if c in existing_cols]
    cols_quoted = ', '.join([f'"{c}"' for c in valid_cols])
    single_row_ph = f"({', '.join(['%s'] * len(valid_cols))})"

    raw_records = df[valid_cols].values.tolist()
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

    batch_size = 400
    total = len(clean_records)
    t_insert = time.time()
    for i in range(0, total, batch_size):
        batch = clean_records[i:i + batch_size]
        flat_vals = [val for row in batch for val in row]
        row_phs = ", ".join([single_row_ph] * len(batch))
        sql = f'INSERT INTO "doctors" ({cols_quoted}) VALUES {row_phs};'
        cur.execute(sql, flat_vals)
        con.commit()
    print(f"  [OK] Inserted {total:,} doctors in {time.time() - t_insert:.2f}s")

    # Generate doctor emails & credentials
    try:
        cur.execute('''
            UPDATE "doctors" 
            SET email = LOWER(REGEXP_REPLACE(doctor, '[^a-zA-Z0-9]', '', 'g')) || '@hospital.com' 
            WHERE (email IS NULL OR email = '') AND doctor IS NOT NULL;
        ''')
        cur.execute('''
            UPDATE "doctors" 
            SET password = 'doctor123' 
            WHERE password IS NULL OR password = '';
        ''')
        con.commit()
        print("  [OK] Doctor login credentials generated.")
    except Exception as exc:
        print(f"  [WARN] Doctor credentials notice: {exc}")

    return True

def seed_localhost_history(cur, con):
    """Seed existing localhost history (registered accounts, appointments, reviews, etc.)."""
    history_file = WORKSPACE_DIR / "initial_data" / "localhost_history.json"
    if not history_file.exists():
        print("[INFO] No localhost_history.json found. Skipping history seed.")
        return

    try:
        import json
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as exc:
        print(f"[WARN] Error reading {history_file}: {exc}")
        return

    print("[INFO] Step 3: Seeding localhost history (patients, appointments, reviews, notifications)...")
    tables_order = ["patients", "appointments", "patient_reviews", "notifications", "hospitals", "faqs", "audit_logs"]

    # Ensure unique indexes exist to prevent any duplicates
    try:
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS patients_email_idx ON patients (LOWER(email));')
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS faqs_question_idx ON faqs (LOWER(TRIM(question)));')
        con.commit()
    except Exception:
        pass

    for tbl in tables_order:
        raw_rows = history.get(tbl, [])
        if not raw_rows:
            continue

        try:
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{tbl}';")
            existing_cols = {r[0] for r in cur.fetchall()}
            if not existing_cols:
                continue

            # Idempotent deduplication against current database state
            filtered_rows = []
            if tbl == "patients" and "email" in existing_cols:
                cur.execute('SELECT LOWER(email) FROM "patients" WHERE email IS NOT NULL;')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if (r.get("email") or "").strip().lower() not in seen]
            elif tbl == "appointments" and "appointment_ref" in existing_cols:
                cur.execute('SELECT appointment_ref FROM "appointments" WHERE appointment_ref IS NOT NULL;')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if r.get("appointment_ref") not in seen]
            elif tbl == "patient_reviews" and "id" in existing_cols:
                cur.execute('SELECT id FROM "patient_reviews";')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if r.get("id") not in seen]
            elif tbl == "notifications" and "id" in existing_cols:
                cur.execute('SELECT id FROM "notifications";')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if r.get("id") not in seen]
            elif tbl == "hospitals" and "name" in existing_cols:
                cur.execute('SELECT name FROM "hospitals" WHERE name IS NOT NULL;')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if r.get("name") not in seen]
            elif tbl == "faqs" and "question" in existing_cols:
                cur.execute('SELECT LOWER(TRIM(question)) FROM "faqs" WHERE question IS NOT NULL;')
                seen = {r[0] for r in cur.fetchall()}
                filtered_rows = [r for r in raw_rows if (r.get("question") or "").strip().lower() not in seen]
            elif tbl == "audit_logs":
                cur.execute('SELECT COUNT(*) FROM "audit_logs";')
                cnt = cur.fetchone()[0]
                if cnt == 0:
                    filtered_rows = raw_rows
            else:
                filtered_rows = raw_rows

            if not filtered_rows:
                cur.execute(f'SELECT COUNT(*) FROM "{tbl}";')
                cnt = cur.fetchone()[0]
                print(f"  [OK] Table \"{tbl}\": {cnt:,} records active (up to date).")
                continue

            batch_size = 100
            for i in range(0, len(filtered_rows), batch_size):
                batch = filtered_rows[i:i + batch_size]
                cols = [k for k in batch[0].keys() if k in existing_cols]
                cols_quoted = ", ".join([f'"{c}"' for c in cols])
                single_row_ph = f"({', '.join(['%s'] * len(cols))})"
                row_phs = ", ".join([single_row_ph] * len(batch))

                flat_vals = []
                for r in batch:
                    for c in cols:
                        flat_vals.append(r.get(c))

                sql = f'INSERT INTO "{tbl}" ({cols_quoted}) VALUES {row_phs} ON CONFLICT DO NOTHING;'
                try:
                    cur.execute(sql, flat_vals)
                    con.commit()
                except Exception as b_exc:
                    con.rollback()
                    print(f"  [WARN] Batch insert notice for {tbl}: {b_exc}")

            # Re-sync auto-increment sequence
            if "id" in existing_cols:
                try:
                    cur.execute(f"SELECT setval(pg_get_serial_sequence('\"{tbl}\"', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM \"{tbl}\";")
                    con.commit()
                except Exception:
                    pass

            cur.execute(f'SELECT COUNT(*) FROM "{tbl}";')
            cnt = cur.fetchone()[0]
            print(f"  [OK] Table \"{tbl}\": {cnt:,} records active.")
        except Exception as t_exc:
            print(f"  [WARN] History seed notice for \"{tbl}\": {t_exc}")

def run_migration_if_needed():
    if not wait_for_db(max_retries=15, delay=2):
        print("[WARN] Database is not reachable right now. Skipping migration.")
        return False

    # Step 1: ALWAYS ensure all foundational tables & schemas exist first
    print("[INFO] Step 1: Ensuring all database schemas, tables, and credentials...")
    try:
        init_system_db.setup_all_schemas()
        print("[SUCCESS] All schemas (appointments, patients, doctors, notifications, patient_reviews) verified!")
    except Exception as e:
        print(f"[ERROR] Error configuring schemas: {e}")

    # Step 2: Check doctors dataset
    con = None
    try:
        con = get_connection()
        cur = con.cursor()

        # Check doctors count
        cur.execute('SELECT COUNT(*) FROM "doctors";')
        cnt = cur.fetchone()[0]
        if cnt == 0:
            print("[INFO] Step 2: Fresh database detected. Importing initial doctors dataset...")
            seed_doctors_dataset(cur, con)
        else:
            print(f"[INFO] Step 2: Doctors catalogue active with {cnt:,} records. Preserving data.")

        # Step 3: Seed localhost history
        seed_localhost_history(cur, con)

        # Step 4: Summary audit
        print("\n" + "=" * 50)
        print("CLOUD DATABASE INITIALIZATION SUMMARY")
        print("=" * 50)
        for tbl in ["doctors", "patients", "appointments", "patient_reviews", "notifications", "hospitals", "faqs"]:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{tbl}";')
                count = cur.fetchone()[0]
                print(f"  [OK] {tbl.ljust(18)}: {count:,} records")
            except Exception as e:
                print(f"  [--] {tbl.ljust(18)}: {e}")
        print("=" * 50 + "\n")

        cur.close()
    except Exception as exc:
        print(f"[WARN] Error during database setup: {exc}")
    finally:
        if con:
            try:
                con.close()
            except Exception as e:
                print(f"  ✗ {tbl.ljust(18)}: {e}")

    return True

if __name__ == "__main__":
    success = run_migration_if_needed()
    if not success:
        print("[WARN] init_cloud_db completed with warnings.")
    sys.exit(0)
