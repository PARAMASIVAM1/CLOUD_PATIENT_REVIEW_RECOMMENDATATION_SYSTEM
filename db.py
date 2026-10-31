"""
db.py - PostgreSQL Database Connection & Query Module for Healthcare AI System

Provides seamless, high-performance PostgreSQL access using pg8000.
Falls back automatically to local Excel/CSV files if PostgreSQL server is offline.
"""

import os
import pg8000.dbapi
import pandas as pd
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# PostgreSQL Connection Configuration (Supports Local & Cloud platforms like Render)
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DB_USER = parsed.username or "postgres"
    DB_PASSWORD = parsed.password
    DB_HOST = parsed.hostname or "127.0.0.1"
    DB_PORT = parsed.port or 5432
    DB_NAME = parsed.path.lstrip("/") or "healthcare_db"
else:
    DB_HOST = os.environ.get("PGHOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("PGPORT", 5432))
    DB_NAME = os.environ.get("PGDATABASE", "healthcare_db")
    DB_USER = os.environ.get("PGUSER", "postgres")
    DB_PASSWORD = os.environ.get("PGPASSWORD", None)

WORKSPACE_DIR = Path(__file__).resolve().parent

def ensure_postgres_running():
    """Ensure local PostgreSQL server is active, starting it automatically if stopped."""
    # Cloud environments (Render, Heroku, etc.) use remote database URL and do not run local postgres.exe
    if os.environ.get("DATABASE_URL") or os.name != 'nt':
        return False

    import socket, subprocess, time
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    result = sock.connect_ex((DB_HOST, DB_PORT))
    sock.close()
    if result == 0:
        return True  # Already running and listening

    print("[DB-INIT] PostgreSQL not detected on port 5432. Auto-starting PostgreSQL...")
    bat_file = WORKSPACE_DIR / "start_postgres.bat"
    data_dir = r"d:\syllabus2026\SEAP PROJECT\pgsql\data"
    exe_file = r"d:\syllabus2026\SEAP PROJECT\pgsql\bin\postgres.exe"

    pid_file = Path(data_dir) / "postmaster.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except Exception:
            pass

    flags = 0
    if os.name == 'nt' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
        flags = subprocess.CREATE_NO_WINDOW

    try:
        if Path(exe_file).exists():
            subprocess.Popen([exe_file, "-D", data_dir], creationflags=flags)
        elif bat_file.exists():
            subprocess.Popen(["cmd.exe", "/c", str(bat_file)], creationflags=flags)
    except Exception as exc:
        print(f"[DB-INIT] Could not auto-launch postgres: {exc}")

    # Wait up to 6 seconds for port 5432 to become available
    for _ in range(30):
        time.sleep(0.2)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        if sock.connect_ex((DB_HOST, DB_PORT)) == 0:
            sock.close()
            print("[DB-INIT] PostgreSQL successfully auto-started and ready!")
            return True
        sock.close()
    return False

def get_connection():
    """Establish and return a connection to PostgreSQL with auto-recovery and cloud SSL support."""
    ssl_context = None
    if DB_HOST not in ("127.0.0.1", "localhost", "::1"):
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    port_num = int(DB_PORT) if DB_PORT else 5432

    try:
        return pg8000.dbapi.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=port_num,
            database=DB_NAME,
            ssl_context=ssl_context,
        )
    except Exception as exc:
        # Fallback 1: On internal private networks (e.g., Render dpg-xxx-a), SSL might be rejected; retry without SSL
        if ssl_context is not None:
            try:
                return pg8000.dbapi.connect(
                    user=DB_USER,
                    password=DB_PASSWORD,
                    host=DB_HOST,
                    port=port_num,
                    database=DB_NAME,
                    ssl_context=None,
                )
            except Exception:
                pass

        # Fallback 2: Local postgres auto-start
        if ensure_postgres_running():
            return pg8000.dbapi.connect(
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=port_num,
                database=DB_NAME,
                ssl_context=None,
            )
        raise exc


def is_db_connected():
    """Quick health check to see if PostgreSQL is reachable."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT 1;")
        res = cur.fetchone()
        con.close()
        return res is not None and res[0] == 1
    except Exception:
        return False

def load_doctors_df():
    """
    Load doctors dataset from PostgreSQL 'doctors' table.

    Only administrator-approved doctors are returned. A practitioner who has
    self-registered but is still Pending Verification, Rejected or Suspended is
    excluded, so unverified credentials can never surface in public search.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "doctors" ORDER BY id ASC;')
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        df = pd.DataFrame(rows, columns=columns)

        if "verification_status" in df.columns:
            approved_mask = (
                df["verification_status"].fillna("Approved").astype(str).str.strip() == "Approved"
            )
            if "is_verified" in df.columns:
                verified_series = df["is_verified"].fillna(True)
                approved_mask = approved_mask & verified_series.astype(bool)
            excluded = int((~approved_mask).sum())
            df = df[approved_mask].reset_index(drop=True)
            if excluded:
                print(
                    f"[DB] Excluded {excluded:,} doctor record(s) awaiting administrator "
                    "approval from the public directory."
                )

        print(f"[DB] Successfully loaded {len(df):,} verified doctors from PostgreSQL table 'doctors'")
        return df
    except Exception as exc:
        print(f"[DB-WARN] Could not load doctors from PostgreSQL ({exc}). Falling back to Excel...")
        excel_path = WORKSPACE_DIR / "Final_20Hospitals_Per_District.xlsx"
        if excel_path.exists():
            return pd.read_excel(excel_path)
        return pd.read_csv(WORKSPACE_DIR / "dataset.csv")

def load_faqs_df():
    """
    Load FAQ dataset from PostgreSQL 'faqs' table.
    Falls back to CSV if database is unavailable.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "faqs";')
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        df = pd.DataFrame(rows, columns=columns)
        print(f"[DB] Successfully loaded {len(df):,} FAQs from PostgreSQL table 'faqs'")
        return df
    except Exception as exc:
        print(f"[DB-WARN] Could not load FAQs from PostgreSQL ({exc}). Falling back to CSV...")
        return pd.read_csv(WORKSPACE_DIR / "faq.csv")

def load_patients_df():
    """
    Load registered patients from PostgreSQL 'patients' table.
    Falls back to patients_progress.xlsx if database is unavailable.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "patients";')
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return pd.DataFrame(rows, columns=columns)
    except Exception as exc:
        print(f"[DB-WARN] Could not load patients from PostgreSQL ({exc}). Falling back to Excel...")
        return pd.read_excel(WORKSPACE_DIR / "patients_progress.xlsx")

def save_patient(patient_dict):
    """
    Insert a newly registered patient into PostgreSQL 'patients' table.

    The password is hashed with PBKDF2 before it is written, so a plain-text
    credential is never persisted.
    """
    try:
        from security import hash_password, is_hashed

        payload = dict(patient_dict)
        raw_password = payload.get("password")
        if raw_password and not is_hashed(raw_password):
            payload["password"] = hash_password(raw_password)

        con = get_connection()
        cur = con.cursor()
        cols = list(payload.keys())
        cols_quoted = ', '.join([f'"{c}"' for c in cols])
        placeholders = ', '.join(['%s'] * len(cols))
        vals = [payload[c] for c in cols]
        cur.execute(f'INSERT INTO "patients" ({cols_quoted}) VALUES ({placeholders});', vals)
        con.commit()
        con.close()
        print(f"[DB] Registered patient '{payload.get('email')}' saved to PostgreSQL.")
        return True
    except Exception as exc:
        print(f"[DB-WARN] Could not save patient to PostgreSQL: {exc}")
        return False


def update_patient_password(email, new_password):
    """Replace a patient's stored credential with a freshly hashed value."""
    try:
        from security import hash_password, is_hashed

        stored = new_password if is_hashed(new_password) else hash_password(new_password)
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            'UPDATE "patients" SET password = %s WHERE LOWER(email) = LOWER(%s) RETURNING email;',
            [stored, email.strip()],
        )
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Could not update patient password: {exc}")
        return False


def get_patient_by_email(email):
    """Fetch a single patient account record by email address."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "patients" WHERE LOWER(email) = LOWER(%s) LIMIT 1;', [email.strip()])
        row = cur.fetchone()
        if not row:
            con.close()
            return None
        columns = [desc[0] for desc in cur.description]
        con.close()
        return dict(zip(columns, row))
    except Exception as exc:
        print(f"[DB-WARN] Could not fetch patient record: {exc}")
        return None


def set_patient_status(email, status):
    """Activate or deactivate a patient account instead of hard-deleting it."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            'UPDATE "patients" SET status = %s WHERE LOWER(email) = LOWER(%s) RETURNING email;',
            [status, email.strip()],
        )
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Could not update patient status: {exc}")
        return False

def load_reviews_df():
    """
    Load patient reviews from PostgreSQL 'patient_reviews' table.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "patient_reviews";')
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return pd.DataFrame(rows, columns=columns)
    except Exception as exc:
        print(f"[DB-WARN] Could not load reviews from PostgreSQL ({exc}). Falling back to Excel...")
        return pd.read_excel(WORKSPACE_DIR / "patient_review.xlsx")

def save_patient_review(review_dict):
    """
    Insert a submitted review into PostgreSQL 'patient_reviews' table.
    Returns the generated review id.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cols = list(review_dict.keys())
        cols_quoted = ', '.join([f'"{c}"' for c in cols])
        placeholders = ', '.join(['%s'] * len(cols))
        vals = [review_dict[c] for c in cols]
        cur.execute(f'INSERT INTO "patient_reviews" ({cols_quoted}) VALUES ({placeholders}) RETURNING id;', vals)
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        print(f"[DB] Review #{new_id} for Doctor '{review_dict.get('doctor_name')}' saved to PostgreSQL.")
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Could not save review to PostgreSQL: {exc}")
        return None

def get_review_by_id(review_id):
    """Retrieve a single review by id from PostgreSQL."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "patient_reviews" WHERE id = %s;', [review_id])
        row = cur.fetchone()
        if not row:
            con.close()
            return None
        columns = [desc[0] for desc in cur.description]
        con.close()
        return dict(zip(columns, row))
    except Exception as exc:
        print(f"[DB-WARN] Could not fetch review #{review_id}: {exc}")
        return None

def update_patient_review(review_id, update_dict):
    """Update fields of an existing review by id in PostgreSQL."""
    try:
        con = get_connection()
        cur = con.cursor()
        set_clauses = []
        vals = []
        for k, v in update_dict.items():
            set_clauses.append(f'"{k}" = %s')
            vals.append(v)
        vals.append(review_id)
        cur.execute(f'UPDATE "patient_reviews" SET {", ".join(set_clauses)} WHERE id = %s RETURNING id;', vals)
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Could not update review #{review_id}: {exc}")
        return False

def delete_patient_review(review_id):
    """Delete a review by id from PostgreSQL."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('DELETE FROM "patient_reviews" WHERE id = %s RETURNING id;', [review_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Could not delete review #{review_id}: {exc}")
        return False

def get_hospitals_summary(city=None, search=None, limit=50, offset=0):
    """Retrieve unique hospitals list with aggregated doctor count and rating."""
    try:
        con = get_connection()
        cur = con.cursor()
        where_clauses = ["hospital IS NOT NULL AND TRIM(hospital) != ''"]
        params = []
        if city:
            where_clauses.append('"Location (Tamil Nadu)" ILIKE %s')
            params.append(f'%{city.strip()}%')
        if search:
            where_clauses.append('(hospital ILIKE %s OR specialization ILIKE %s)')
            params.extend([f'%{search.strip()}%', f'%{search.strip()}%'])

        where_sql = " AND ".join(where_clauses)
        sql = f'''
            SELECT 
                MIN(id) AS hospital_id,
                hospital,
                "Location (Tamil Nadu)" AS location,
                COUNT(*) AS total_doctors,
                ROUND(AVG(rating), 2) AS average_rating,
                STRING_AGG(DISTINCT specialization, ', ') AS specializations
            FROM "doctors"
            WHERE {where_sql}
            GROUP BY hospital, "Location (Tamil Nadu)"
            ORDER BY total_doctors DESC, hospital
            LIMIT %s OFFSET %s;
        '''
        query_params = params + [limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()

        count_sql = f'SELECT COUNT(DISTINCT (hospital, "Location (Tamil Nadu)")) FROM "doctors" WHERE {where_sql};'
        cur.execute(count_sql, params)
        total_count = cur.fetchone()[0]
        con.close()

        result = []
        for r in rows:
            specs = [s.strip() for s in (r[5] or '').split(',') if s.strip()]
            result.append({
                "hospital_id": r[0],
                "hospital": r[1],
                "location": r[2] or "Tamil Nadu",
                "total_doctors": r[3],
                "average_rating": float(r[4]) if r[4] is not None else 4.5,
                "specializations": specs[:8]
            })
        return {"total": total_count, "hospitals": result}
    except Exception as exc:
        print(f"[DB-WARN] Error in get_hospitals_summary: {exc}")
        return {"total": 0, "hospitals": []}

def get_doctors_api_list(doctor_id=None, city=None, hospital=None, specialization=None, department=None, search=None, limit=20, offset=0):
    """Retrieve doctors list from PostgreSQL for the REST API."""
    try:
        con = get_connection()
        cur = con.cursor()
        where_clauses = ["1=1"]
        params = []
        if doctor_id is not None:
            where_clauses.append("id = %s")
            params.append(doctor_id)
        if city:
            where_clauses.append('"Location (Tamil Nadu)" ILIKE %s')
            params.append(f'%{city.strip()}%')
        if hospital:
            where_clauses.append('hospital ILIKE %s')
            params.append(f'%{hospital.strip()}%')
        if specialization:
            where_clauses.append('specialization ILIKE %s')
            params.append(f'%{specialization.strip()}%')
        if department:
            where_clauses.append('disease ILIKE %s')
            params.append(f'%{department.strip()}%')
        if search:
            where_clauses.append('(doctor ILIKE %s OR hospital ILIKE %s OR specialization ILIKE %s)')
            s = f'%{search.strip()}%'
            params.extend([s, s, s])

        # Only administrator-approved doctors are exposed through the public API.
        where_clauses.append("verification_status = 'Approved'")

        where_sql = " AND ".join(where_clauses)
        sql = f'''
            SELECT 
                id,
                doctor,
                hospital,
                specialization,
                disease,
                "Location (Tamil Nadu)" AS location,
                consultation_fee,
                waiting_time,
                rating,
                age,
                gender
            FROM "doctors"
            WHERE {where_sql}
            ORDER BY rating DESC, id ASC
            LIMIT %s OFFSET %s;
        '''
        query_params = params + [limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()

        count_sql = f'SELECT COUNT(*) FROM "doctors" WHERE {where_sql};'
        cur.execute(count_sql, params)
        total_count = cur.fetchone()[0]
        con.close()

        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "doctor_name": r[1],
                "hospital": r[2],
                "specialization": r[3],
                "department": r[4],
                "location": r[5] or "Tamil Nadu",
                "consultation_fee": r[6],
                "waiting_time_minutes": r[7],
                "rating": r[8],
                "age": r[9],
                "gender": r[10]
            })
        return {"total": total_count, "doctors": result}
    except Exception as exc:
        print(f"[DB-WARN] Error in get_doctors_api_list: {exc}")
        return {"total": 0, "doctors": []}


# ==================== APPOINTMENT MANAGEMENT ====================

def _get_fallback_sqlite():
    import sqlite3
    db_path = WORKSPACE_DIR / "appointments_fallback.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_ref TEXT UNIQUE,
            patient_email TEXT,
            patient_name TEXT,
            patient_phone TEXT,
            patient_age INTEGER,
            patient_gender TEXT,
            doctor_id INTEGER,
            doctor_name TEXT,
            doctor_email TEXT,
            hospital TEXT,
            specialization TEXT,
            appointment_date TEXT,
            appointment_time TEXT,
            symptoms TEXT,
            disease TEXT,
            notes TEXT,
            status TEXT DEFAULT 'Pending',
            doctor_notes TEXT,
            prescription TEXT,
            has_feedback INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()
    return conn

def _save_fallback_appointment(data, ref, apt_date, time_slot, patient_age, doc_id, doc_name, doc_email):
    try:
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = _get_fallback_sqlite()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO appointments (
                appointment_ref, patient_email, patient_name, patient_phone,
                patient_age, patient_gender, doctor_id, doctor_name, doctor_email, hospital,
                specialization, appointment_date, appointment_time, symptoms,
                disease, notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?);
        """, (
            ref,
            str(data.get("patient_email") or "patient@example.com").strip(),
            str(data.get("patient_name") or "Patient").strip(),
            str(data.get("patient_phone") or "").strip(),
            patient_age,
            str(data.get("patient_gender") or "Not specified").strip(),
            doc_id,
            doc_name,
            doc_email,
            str(data.get("hospital") or "Hospital").strip(),
            str(data.get("specialization") or "Specialist").strip(),
            str(apt_date),
            time_slot,
            str(data.get("symptoms") or "").strip(),
            str(data.get("disease") or "General Health Consultation").strip(),
            str(data.get("notes") or "").strip(),
            now_str,
            now_str
        ))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        print(f"[FALLBACK-DB] Successfully saved appointment #{new_id} ({ref}) to local fallback store.")
        return new_id, ref
    except Exception as exc:
        print(f"[FALLBACK-DB-ERROR] Error saving to fallback store: {exc}")
        return None, None

def create_appointment(data):
    """
    Create a new patient appointment request with reference token.
    Returns (appointment_id, appointment_ref).
    """
    import uuid
    from datetime import datetime, date, timedelta
    ref = f"APT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # 1. Safely parse appointment_date (PostgreSQL DATE cannot take empty string "")
    raw_date = data.get("appointment_date")
    apt_date = None
    if raw_date and str(raw_date).strip():
        try:
            if isinstance(raw_date, (datetime, date)):
                apt_date = raw_date
            else:
                apt_date = datetime.strptime(str(raw_date).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            apt_date = (datetime.now() + timedelta(days=1)).date()
    if not apt_date:
        apt_date = (datetime.now() + timedelta(days=1)).date()

    # 2. Safely parse integer fields
    try:
        patient_age = int(data.get("patient_age") or 30)
    except Exception:
        patient_age = 30

    try:
        doc_id = int(data.get("doctor_id") or 0)
    except Exception:
        doc_id = 0

    # 3. Safely clean text fields
    doc_name = str(data.get("doctor_name") or "Specialist").strip()
    disease = str(data.get("disease") or "General Health Consultation").strip()
    if not disease:
        disease = "General Health Consultation"
    symptoms = str(data.get("symptoms") or "Clinical Checkup").strip()
    time_slot = str(data.get("appointment_time") or "09:30 AM - Morning").strip()

    # Resolve doctor email
    doc_email = str(data.get("doctor_email") or "").strip()
    if not doc_email:
        clean = re.sub(r"[^a-zA-Z0-9]", "", str(doc_name or "").lower())
        if not clean.startswith("dr") and clean:
            clean = "dr" + clean
        doc_email = f"{clean}@hospital.com" if clean else "doctor@hospital.com"

    try:
        con = get_connection()
        cur = con.cursor()

        # If doc_id is 0 or missing, resolve from doctors table by name
        if doc_id == 0 and doc_name:
            try:
                cur.execute('SELECT id FROM "doctors" WHERE LOWER(doctor) = LOWER(%s) LIMIT 1;', [doc_name])
                row = cur.fetchone()
                if row and row[0]:
                    doc_id = row[0]
            except Exception:
                pass

        sql = '''
            INSERT INTO appointments (
                appointment_ref, patient_email, patient_name, patient_phone,
                patient_age, patient_gender, doctor_id, doctor_name, doctor_email, hospital,
                specialization, appointment_date, appointment_time, symptoms,
                disease, notes, status, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending', NOW(), NOW()
            ) RETURNING id;
        '''
        cur.execute(sql, [
            ref,
            str(data.get("patient_email") or "patient@example.com").strip(),
            str(data.get("patient_name") or "Patient").strip(),
            str(data.get("patient_phone") or "").strip(),
            patient_age,
            str(data.get("patient_gender") or "Not specified").strip(),
            doc_id,
            doc_name,
            doc_email,
            str(data.get("hospital") or "Hospital").strip(),
            str(data.get("specialization") or "Specialist").strip(),
            apt_date,
            time_slot,
            symptoms,
            disease,
            str(data.get("notes") or "").strip()
        ])
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id, ref
    except Exception as exc:
        print(f"[DB-WARN] Error creating appointment in PostgreSQL: {exc}")
        # Auto-heal: ensure schema exists and retry once
        try:
            print("[DB-AUTOHEAL] Attempting auto-recovery for missing table or column in PostgreSQL...")
            import init_system_db
            init_system_db.setup_all_schemas()
            con_retry = get_connection()
            cur_retry = con_retry.cursor()
            cur_retry.execute(sql, [
                ref,
                str(data.get("patient_email") or "patient@example.com").strip(),
                str(data.get("patient_name") or "Patient").strip(),
                str(data.get("patient_phone") or "").strip(),
                patient_age,
                str(data.get("patient_gender") or "Not specified").strip(),
                doc_id,
                doc_name,
                doc_email,
                str(data.get("hospital") or "Hospital").strip(),
                str(data.get("specialization") or "Specialist").strip(),
                apt_date,
                time_slot,
                symptoms,
                disease,
                str(data.get("notes") or "").strip()
            ])
            new_id = cur_retry.fetchone()[0]
            con_retry.commit()
            con_retry.close()
            print(f"[DB-AUTOHEAL] Successfully recovered and created appointment #{new_id} ({ref})")
            return new_id, ref
        except Exception as retry_err:
            print(f"[DB-AUTOHEAL-FAIL] Recovery failed ({retry_err}). Falling back to local store.")
            return _save_fallback_appointment(data, ref, apt_date, time_slot, patient_age, doc_id, doc_name, doc_email)


def get_appointment_by_id(apt_id):
    """Fetch complete details of an appointment by ID with doctor email attached."""
    apt = None
    try:
        import re
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM appointments WHERE id = %s;', [apt_id])
        row = cur.fetchone()
        if row:
            columns = [desc[0] for desc in cur.description]
            apt = dict(zip(columns, row))
            
            # Attach doctor email for testing and communication
            if not apt.get("doctor_email"):
                doc_id = apt.get("doctor_id")
                doc_name = (apt.get("doctor_name") or "").strip()
                
                # Priority 1: Match by doctor name (exact or normalized)
                doc_row = None
                if doc_name:
                    cur.execute('SELECT email, id FROM "doctors" WHERE LOWER(doctor) = LOWER(%s) LIMIT 1;', [doc_name])
                    doc_row = cur.fetchone()
                    if not doc_row:
                        norm_name = re.sub(r"^dr\.?\s*", "dr.", doc_name, flags=re.IGNORECASE)
                        cur.execute(r'''SELECT email, id FROM "doctors" WHERE LOWER(REGEXP_REPLACE(doctor, '^dr\.?\s*', 'dr.', 'i')) = LOWER(%s) LIMIT 1;''', [norm_name])
                        doc_row = cur.fetchone()

                # Priority 2: Fallback to doctor_id if name query didn't match
                if not doc_row and doc_id:
                    cur.execute('SELECT email, id FROM "doctors" WHERE id = %s LIMIT 1;', [doc_id])
                    doc_row = cur.fetchone()

                if doc_row and doc_row[0]:
                    apt["doctor_email"] = doc_row[0]
                    if doc_row[1]:
                        apt["doctor_id"] = doc_row[1]
                else:
                    clean = re.sub(r"[^a-zA-Z0-9]", "", str(doc_name or "").lower())
                    if not clean.startswith("dr") and clean:
                        clean = "dr" + clean
                    apt["doctor_email"] = f"{clean}@hospital.com" if clean else "doctor@hospital.com"
            con.close()
            return apt
        con.close()
    except Exception as exc:
        print(f"[DB-WARN] Error fetching appointment #{apt_id} from PostgreSQL: {exc}")

    # Fallback to local SQLite store
    try:
        conn = _get_fallback_sqlite()
        cur = conn.cursor()
        cur.execute("SELECT * FROM appointments WHERE id = ?;", (apt_id,))
        fb_row = cur.fetchone()
        conn.close()
        if fb_row:
            return dict(fb_row)
    except Exception as fb_exc:
        print(f"[FALLBACK-DB-ERROR] Error looking up appointment in fallback: {fb_exc}")

    return None


def get_patient_appointments(patient_email):
    """Fetch all appointments booked by a patient with doctor email attached."""
    results = []
    seen_refs = set()
    try:
        import re
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT a.*, d.email AS doctor_email 
            FROM appointments a
            LEFT JOIN "doctors" d ON (LOWER(a.doctor_name) = LOWER(d.doctor))
            WHERE LOWER(a.patient_email) = LOWER(%s)
            ORDER BY a.created_at DESC;
        ''', [patient_email])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        for r in rows:
            item = dict(zip(columns, r))
            if not item.get("doctor_email"):
                clean = re.sub(r"[^a-zA-Z0-9]", "", str(item.get("doctor_name") or "").lower())
                if not clean.startswith("dr") and clean:
                    clean = "dr" + clean
                item["doctor_email"] = f"{clean}@hospital.com" if clean else "doctor@hospital.com"
            results.append(item)
            if item.get("appointment_ref"):
                seen_refs.add(item["appointment_ref"])
    except Exception as exc:
        print(f"[DB-WARN] Error fetching patient appointments from PostgreSQL: {exc}")

    # Merge any fallback stored appointments
    try:
        conn = _get_fallback_sqlite()
        cur = conn.cursor()
        cur.execute("SELECT * FROM appointments WHERE LOWER(patient_email) = LOWER(?) ORDER BY id DESC;", (patient_email,))
        fb_rows = cur.fetchall()
        conn.close()
        for r in fb_rows:
            d = dict(r)
            if d.get("appointment_ref") not in seen_refs:
                results.append(d)
                seen_refs.add(d.get("appointment_ref"))
    except Exception:
        pass

    return results


def delete_appointment_by_id(apt_id, user_email=None, user_role=None):
    """
    Delete an appointment by ID.
    If user_role is patient, ensure the appointment belongs to them.
    If doctor, ensure it is assigned to them.
    If admin, allow deletion directly.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        if user_role == "admin" or not user_email:
            cur.execute('DELETE FROM appointments WHERE id = %s RETURNING id, appointment_ref;', [apt_id])
        else:
            clean_email = user_email.strip().lower()
            cur.execute('''
                DELETE FROM appointments 
                WHERE id = %s AND (LOWER(patient_email) = %s OR LOWER(COALESCE(doctor_email, '')) = %s)
                RETURNING id, appointment_ref;
            ''', [apt_id, clean_email, clean_email])
        row = cur.fetchone()
        con.commit()
        con.close()
        return bool(row)
    except Exception as exc:
        print(f"[DB-WARN] Could not delete appointment #{apt_id}: {exc}")
        return False


def delete_multiple_appointments(apt_ids, user_email=None, user_role=None):
    """
    Delete multiple appointments by ID list.
    If user_role is patient, ensure only their own appointments are deleted.
    """
    if not apt_ids:
        return 0
    try:
        clean_ids = [int(i) for i in apt_ids if str(i).strip().isdigit()]
        if not clean_ids:
            return 0
        con = get_connection()
        cur = con.cursor()
        placeholders = ', '.join(['%s'] * len(clean_ids))
        if user_role == "admin" or not user_email:
            cur.execute(f'DELETE FROM appointments WHERE id IN ({placeholders}) RETURNING id;', clean_ids)
        else:
            clean_email = user_email.strip().lower()
            params = clean_ids + [clean_email, clean_email]
            cur.execute(f'''
                DELETE FROM appointments 
                WHERE id IN ({placeholders}) AND (LOWER(patient_email) = %s OR LOWER(COALESCE(doctor_email, '')) = %s)
                RETURNING id;
            ''', params)
        rows = cur.fetchall()
        con.commit()
        con.close()
        return len(rows)
    except Exception as exc:
        print(f"[DB-WARN] Could not delete appointments {apt_ids}: {exc}")
        return 0


def delete_all_patient_appointments(user_email, status=None):
    """
    Delete all appointments for a patient (optionally filtered by status).
    """
    if not user_email:
        return 0
    try:
        con = get_connection()
        cur = con.cursor()
        clean_email = user_email.strip().lower()
        if status:
            cur.execute('''
                DELETE FROM appointments 
                WHERE LOWER(patient_email) = %s AND status = %s
                RETURNING id;
            ''', [clean_email, status])
        else:
            cur.execute('''
                DELETE FROM appointments 
                WHERE LOWER(patient_email) = %s
                RETURNING id;
            ''', [clean_email])
        rows = cur.fetchall()
        con.commit()
        con.close()
        return len(rows)
    except Exception as exc:
        print(f"[DB-WARN] Could not delete all appointments for {user_email}: {exc}")
        return 0


def get_doctor_appointments(doctor_name=None, doctor_id=None, status=None):
    """Fetch all appointments assigned to a doctor (Pending, Approved, Completed)."""
    try:
        con = get_connection()
        cur = con.cursor()
        where_clauses = ["1=1"]
        params = []
        if doctor_id and doctor_name:
            where_clauses.append("(doctor_id = %s OR LOWER(doctor_name) = LOWER(%s))")
            params.extend([doctor_id, doctor_name.strip()])
        elif doctor_id:
            where_clauses.append("doctor_id = %s")
            params.append(doctor_id)
        elif doctor_name:
            where_clauses.append("LOWER(doctor_name) = LOWER(%s)")
            params.append(doctor_name.strip())

        if status:
            where_clauses.append("status = %s")
            params.append(status)

        sql = f'''
            SELECT * FROM appointments 
            WHERE {" AND ".join(where_clauses)}
            ORDER BY 
                CASE status 
                    WHEN 'Pending' THEN 1 
                    WHEN 'Approved' THEN 2 
                    WHEN 'Completed' THEN 3 
                    ELSE 4 
                END,
                appointment_date ASC, created_at DESC;
        '''
        cur.execute(sql, params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return [dict(zip(columns, r)) for r in rows]
    except Exception as exc:
        print(f"[DB-WARN] Error fetching doctor appointments: {exc}")
        return []


def update_appointment_status(apt_id, new_status, doctor_notes=None, prescription=None):
    """Update appointment status (Approved, Rejected, Completed) and notes."""
    try:
        con = get_connection()
        cur = con.cursor()
        updates = ["status = %s", "updated_at = NOW()"]
        params = [new_status]
        if doctor_notes is not None:
            updates.append("doctor_notes = %s")
            params.append(doctor_notes)
        if prescription is not None:
            updates.append("prescription = %s")
            params.append(prescription)
        params.append(apt_id)

        sql = f"UPDATE appointments SET {', '.join(updates)} WHERE id = %s RETURNING id;"
        cur.execute(sql, params)
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error updating appointment #{apt_id}: {exc}")
        return False


def get_patient_clinical_history(patient_email):
    """
    Retrieve clinical history for a patient across all appointments.
    Allows doctors to view previous diagnoses, symptoms, treatments, and prescriptions.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT id, appointment_ref, doctor_name, hospital, specialization,
                   appointment_date, disease, symptoms, doctor_notes, prescription, status
            FROM appointments
            WHERE LOWER(patient_email) = LOWER(%s) AND status IN ('Approved', 'Completed')
            ORDER BY appointment_date DESC, id DESC;
        ''', [patient_email])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return [dict(zip(columns, r)) for r in rows]
    except Exception as exc:
        print(f"[DB-WARN] Error getting patient history: {exc}")
        return []


# ==================== NOTIFICATIONS ====================

def create_notification(user_email, user_role, title, message, notif_type="system", reference_id=None):
    """Create an in-app notification for a patient or doctor."""
    try:
        con = get_connection()
        cur = con.cursor()
        sql = '''
            INSERT INTO notifications (user_email, user_role, title, message, type, reference_id, is_read, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, NOW()) RETURNING id;
        '''
        cur.execute(sql, [user_email, user_role, title, message, notif_type, reference_id])
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error creating notification: {exc}")
        return None


def get_user_notifications(user_email, limit=100):
    """Fetch notifications for a user."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT * FROM notifications 
            WHERE LOWER(user_email) = LOWER(%s)
            ORDER BY is_read ASC, created_at DESC
            LIMIT %s;
        ''', [user_email, limit])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return [dict(zip(columns, r)) for r in rows]
    except Exception as exc:
        print(f"[DB-WARN] Error fetching notifications: {exc}")
        return []


def get_unread_notification_count(user_email):
    """Count unread notifications for navbar badge."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT COUNT(*) FROM notifications WHERE LOWER(user_email) = LOWER(%s) AND is_read = FALSE;', [user_email])
        cnt = cur.fetchone()[0]
        con.close()
        return cnt
    except Exception:
        return 0


def mark_notifications_read(user_email, notif_id=None):
    """Mark one or all notifications as read."""
    try:
        con = get_connection()
        cur = con.cursor()
        if notif_id:
            cur.execute('UPDATE notifications SET is_read = TRUE WHERE id = %s AND LOWER(user_email) = LOWER(%s);', [notif_id, user_email])
        else:
            cur.execute('UPDATE notifications SET is_read = TRUE WHERE LOWER(user_email) = LOWER(%s);', [user_email])
        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[DB-WARN] Error marking notifications read: {exc}")
        return False


def delete_notification_by_id(notif_id, user_email):
    """Delete a single notification by id ensuring ownership."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            DELETE FROM notifications 
            WHERE id = %s AND LOWER(user_email) = LOWER(%s)
            RETURNING id;
        ''', [notif_id, user_email])
        row = cur.fetchone()
        con.commit()
        con.close()
        return row is not None
    except Exception as exc:
        print(f"[DB-WARN] Could not delete notification #{notif_id}: {exc}")
        return False


def delete_multiple_notifications(notif_ids, user_email):
    """Bulk delete a list of notifications belonging to user_email."""
    if not notif_ids:
        return 0
    try:
        clean_ids = [int(i) for i in notif_ids if str(i).isdigit()]
        if not clean_ids:
            return 0
        con = get_connection()
        cur = con.cursor()
        placeholders = ', '.join(['%s'] * len(clean_ids))
        sql = f'''
            DELETE FROM notifications 
            WHERE id IN ({placeholders}) AND LOWER(user_email) = LOWER(%s)
            RETURNING id;
        '''
        params = list(clean_ids) + [user_email]
        cur.execute(sql, params)
        deleted_rows = cur.fetchall()
        con.commit()
        con.close()
        return len(deleted_rows)
    except Exception as exc:
        print(f"[DB-WARN] Could not bulk delete notifications: {exc}")
        return 0


def delete_all_user_notifications(user_email):
    """Delete all notifications for a specific user."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            DELETE FROM notifications 
            WHERE LOWER(user_email) = LOWER(%s)
            RETURNING id;
        ''', [user_email])
        deleted_rows = cur.fetchall()
        con.commit()
        con.close()
        return len(deleted_rows)
    except Exception as exc:
        print(f"[DB-WARN] Could not delete all notifications for {user_email}: {exc}")
        return 0



# ==================== DOCTOR PROFILE & AUTH ====================

def get_doctor_by_identifier(identifier):
    """
    Look up doctor by email, doctor name, or numeric ID for doctor login.
    Enables testing ANY doctor from search or booked appointments.
    """
    if not identifier:
        return None
    raw_text = str(identifier).strip()
    try:
        import re
        con = get_connection()
        cur = con.cursor()
        
        # 1. Exact email match (case-insensitive)
        cur.execute('SELECT * FROM "doctors" WHERE LOWER(email) = LOWER(%s) LIMIT 1;', [raw_text])
        row = cur.fetchone()
        
        # 2. Exact doctor name match (case-insensitive)
        if not row:
            cur.execute('SELECT * FROM "doctors" WHERE LOWER(doctor) = LOWER(%s) LIMIT 1;', [raw_text])
            row = cur.fetchone()
            
        # 3. Partial doctor name match
        if not row:
            clean_name = raw_text.replace("Dr.", "").replace("DR.", "").replace("dr.", "").strip()
            if "@" in clean_name:
                clean_name = clean_name.split("@")[0].strip()
            cur.execute('SELECT * FROM "doctors" WHERE LOWER(doctor) LIKE LOWER(%s) LIMIT 1;', [f"%{clean_name}%"])
            row = cur.fetchone()
            
        # 4. If numeric, lookup by ID
        if not row and raw_text.isdigit():
            cur.execute('SELECT * FROM "doctors" WHERE id = %s LIMIT 1;', [int(raw_text)])
            row = cur.fetchone()

        # 5. Tokenized name/email match (e.g. drharishrao@hospital.com -> matches Harish Rao)
        if not row:
            clean_token = re.sub(r"[^a-zA-Z]", "", raw_text.split("@")[0].lower())
            if clean_token.startswith("dr"):
                clean_token = clean_token[2:]
            if len(clean_token) >= 3:
                cur.execute('SELECT * FROM "doctors" WHERE LOWER(doctor) LIKE LOWER(%s) OR LOWER(email) LIKE LOWER(%s) LIMIT 1;', [f"%{clean_token}%", f"%{clean_token}%"])
                row = cur.fetchone()
            
        if not row:
            con.close()
            return None
            
        columns = [desc[0] for desc in cur.description]
        con.close()
        return dict(zip(columns, row))
    except Exception as exc:
        print(f"[DB-WARN] Error in get_doctor_by_identifier: {exc}")
        return None


def get_doctor_by_email(email):
    """Look up doctor by email or identifier for doctor login."""
    return get_doctor_by_identifier(email)


def get_doctor_record_by_id(doctor_id):
    """Look up doctor by ID."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT * FROM "doctors" WHERE id = %s;', [doctor_id])
        row = cur.fetchone()
        if not row:
            con.close()
            return None
        columns = [desc[0] for desc in cur.description]
        con.close()
        return dict(zip(columns, row))
    except Exception as exc:
        print(f"[DB-WARN] Error looking up doctor by id #{doctor_id}: {exc}")
        return None


def create_new_doctor(doc_dict):
    """
    Register a doctor created directly by an administrator.

    Administrator-created records are approved immediately because the admin is
    the verifying authority. Self-registered doctors must instead go through
    db_verification.submit_doctor_application and stay Pending Verification.
    Passwords are always hashed before storage.
    """
    try:
        from security import hash_password, is_hashed

        raw_password = doc_dict.get("password") or "doctor123"
        stored_password = raw_password if is_hashed(raw_password) else hash_password(raw_password)

        is_verified = bool(doc_dict.get("is_verified", True))
        verification_status = doc_dict.get(
            "verification_status", "Approved" if is_verified else "Pending Verification"
        )

        con = get_connection()
        cur = con.cursor()
        sql = '''
            INSERT INTO "doctors" (
                doctor, specialization, hospital, disease, "Location (Tamil Nadu)",
                consultation_fee, waiting_time, rating, experience_years,
                email, password, is_verified, qualifications, bio,
                verification_status, registration_number, registration_council,
                available_days, available_timings, submitted_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, NOW()
            ) RETURNING id;
        '''
        cur.execute(sql, [
            doc_dict.get("doctor_name"),
            doc_dict.get("specialization"),
            doc_dict.get("hospital"),
            doc_dict.get("department") or doc_dict.get("disease", "General"),
            doc_dict.get("location", "Chennai"),
            int(doc_dict.get("consultation_fee") or 500),
            int(doc_dict.get("waiting_time") or 15),
            float(doc_dict.get("rating") or 0),
            int(doc_dict.get("experience_years") or 5),
            doc_dict.get("email"),
            stored_password,
            is_verified,
            doc_dict.get("qualifications", "MBBS, MD"),
            doc_dict.get("bio", ""),
            verification_status,
            doc_dict.get("registration_number", ""),
            doc_dict.get("registration_council", ""),
            doc_dict.get("available_days", "Mon - Sat"),
            doc_dict.get("available_timings", "09:30 AM - 05:30 PM"),
        ])
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error creating doctor: {exc}")
        return None


def update_doctor_details(doctor_id, update_dict):
    """Update doctor qualifications, fees, bio, etc."""
    try:
        con = get_connection()
        cur = con.cursor()
        set_clauses = []
        vals = []
        for k, v in update_dict.items():
            set_clauses.append(f'"{k}" = %s')
            vals.append(v)
        vals.append(doctor_id)
        cur.execute(f'UPDATE "doctors" SET {", ".join(set_clauses)} WHERE id = %s RETURNING id;', vals)
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error updating doctor #{doctor_id}: {exc}")
        return False


def delete_doctor_by_id(doctor_id):
    """Delete a doctor record from the database."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('DELETE FROM "doctors" WHERE id = %s RETURNING id;', [doctor_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error deleting doctor #{doctor_id}: {exc}")
        return False


# ==================== PATIENTS MANAGEMENT ====================

def get_all_patients_list(search=None, limit=50, offset=0):
    """Fetch all patient accounts for Admin."""
    try:
        con = get_connection()
        cur = con.cursor()
        where_sql = "1=1"
        params = []
        if search:
            where_sql = "(first_name ILIKE %s OR last_name ILIKE %s OR email ILIKE %s)"
            s = f"%{search.strip()}%"
            params.extend([s, s, s])

        cur.execute(f'SELECT COUNT(*) FROM "patients" WHERE {where_sql};', params)
        total = cur.fetchone()[0]

        cur.execute(f'''
            SELECT id, first_name, last_name, email, age, country, role, status, enrolled_at
            FROM "patients"
            WHERE {where_sql}
            ORDER BY enrolled_at DESC NULLS LAST, id DESC
            LIMIT %s OFFSET %s;
        ''', params + [limit, offset])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return {"total": total, "patients": [dict(zip(columns, r)) for r in rows]}
    except Exception as exc:
        print(f"[DB-WARN] Error fetching patients list: {exc}")
        return {"total": 0, "patients": []}


def update_patient_record(email, update_dict):
    """Update patient info by email."""
    try:
        con = get_connection()
        cur = con.cursor()
        set_clauses = []
        vals = []
        for k, v in update_dict.items():
            set_clauses.append(f'"{k}" = %s')
            vals.append(v)
        vals.append(email.strip().lower())
        cur.execute(f'UPDATE "patients" SET {", ".join(set_clauses)} WHERE LOWER(email) = %s RETURNING email;', vals)
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error updating patient: {exc}")
        return False


def delete_patient_by_email(email):
    """Delete patient account by email."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('DELETE FROM "patients" WHERE LOWER(email) = LOWER(%s) RETURNING email;', [email.strip()])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error deleting patient: {exc}")
        return False


# ==================== HOSPITALS MANAGEMENT ====================

def get_all_hospitals_records(search=None, limit=50, offset=0):
    """Fetch hospitals list for Admin."""
    try:
        con = get_connection()
        cur = con.cursor()
        where_sql = "1=1"
        params = []
        if search:
            where_sql = "(name ILIKE %s OR location ILIKE %s)"
            s = f"%{search.strip()}%"
            params.extend([s, s])

        cur.execute(f'SELECT COUNT(*) FROM hospitals WHERE {where_sql};', params)
        total = cur.fetchone()[0]

        cur.execute(f'''
            SELECT id, name, location, facilities, contact_phone, emergency_available
            FROM hospitals
            WHERE {where_sql}
            ORDER BY name ASC
            LIMIT %s OFFSET %s;
        ''', params + [limit, offset])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return {"total": total, "hospitals": [dict(zip(columns, r)) for r in rows]}
    except Exception as exc:
        print(f"[DB-WARN] Error fetching hospitals: {exc}")
        return {"total": 0, "hospitals": []}


def create_hospital_record(data):
    """Add new hospital record."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            INSERT INTO hospitals (name, location, facilities, contact_phone, emergency_available)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        ''', [
            data.get("name"),
            data.get("location", "Tamil Nadu"),
            data.get("facilities", "24/7 Emergency, Pharmacy, Diagnostic Lab"),
            data.get("contact_phone", "+91 44 2829 0200"),
            data.get("emergency_available", True)
        ])
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error creating hospital: {exc}")
        return None


def update_hospital_record(hosp_id, data):
    """Update hospital details."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            UPDATE hospitals SET 
                name = %s, location = %s, facilities = %s, 
                contact_phone = %s, emergency_available = %s
            WHERE id = %s RETURNING id;
        ''', [
            data.get("name"),
            data.get("location"),
            data.get("facilities"),
            data.get("contact_phone"),
            data.get("emergency_available", True),
            hosp_id
        ])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error updating hospital #{hosp_id}: {exc}")
        return False


def delete_hospital_record(hosp_id):
    """Delete hospital record."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('DELETE FROM hospitals WHERE id = %s RETURNING id;', [hosp_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error deleting hospital #{hosp_id}: {exc}")
        return False


# ==================== REVIEWS: PRIVACY & MODERATION ====================

def get_doctor_reviews_anonymized(doctor_name):
    """
    STRICT PRIVACY GUARANTEE:
    Fetch reviews for a doctor where PATIENT IDENTITY IS COMPLETELY MASKED.
    Doctor can see feedback text, ratings, sentiment, and doctor response,
    but CANNOT see who submitted it (patient name and email are strictly hidden).
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT
                id,
                new_feedback AS review_text,
                patient_rating,
                sentiment_label,
                doctor_response,
                is_reported,
                submitted_at,
                waiting_time_rating,
                communication_rating,
                cost_satisfaction_rating,
                moderation_status,
                'Verified Patient' AS patient_display_name
            FROM "patient_reviews"
            WHERE LOWER(doctor_name) = LOWER(%s)
              AND (moderation_status IS NULL OR moderation_status <> 'Removed')
            ORDER BY id DESC;
        ''', [doctor_name.strip()])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()

        # The reviewer's identity is never returned: only a stable, non-reversible
        # label is exposed so the doctor cannot re-identify the patient.
        from security import anonymised_reviewer_label

        reviews = []
        for row in rows:
            record = dict(zip(columns, row))
            record["patient_display_name"] = "Verified Patient"
            record["reviewer_reference"] = anonymised_reviewer_label(f"{doctor_name}-{record.get('id')}")
            reviews.append(record)
        return reviews
    except Exception as exc:
        print(f"[DB-WARN] Error fetching doctor reviews: {exc}")
        return []


def doctor_respond_to_review(review_id, response_text):
    """Doctor provides a professional reply to a patient review."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            UPDATE "patient_reviews" 
            SET doctor_response = %s 
            WHERE id = %s RETURNING id;
        ''', [response_text.strip(), review_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error responding to review #{review_id}: {exc}")
        return False


def doctor_report_review(review_id, reason):
    """Doctor flags/reports a false or abusive review to Admin for moderation."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            UPDATE "patient_reviews" 
            SET is_reported = TRUE, report_reason = %s 
            WHERE id = %s RETURNING id;
        ''', [reason.strip(), review_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error reporting review #{review_id}: {exc}")
        return False


def get_all_reviews_admin(reported_only=False, limit=50):
    """
    ADMIN MODERATION VIEW:
    Admin CAN see the submitter's identity (patient_email) to moderate spam or abuse.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        where_sql = "1=1"
        if reported_only:
            where_sql = "is_reported = TRUE"

        cur.execute(f'''
            SELECT 
                id, doctor_name, hospital, specialization,
                patient_rating, new_feedback, sentiment_label,
                patient_email, is_reported, report_reason,
                doctor_response, is_moderated, submitted_at
            FROM "patient_reviews"
            WHERE {where_sql}
            ORDER BY is_reported DESC, id DESC
            LIMIT %s;
        ''', [limit])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return [dict(zip(columns, r)) for r in rows]
    except Exception as exc:
        print(f"[DB-WARN] Error fetching admin reviews: {exc}")
        return []


def admin_moderate_review(review_id, action):
    """Admin takes action on a review: 'approve', 'dismiss_report', or 'delete'."""
    try:
        con = get_connection()
        cur = con.cursor()
        if action == "delete":
            cur.execute('DELETE FROM "patient_reviews" WHERE id = %s RETURNING id;', [review_id])
        elif action == "dismiss_report":
            cur.execute('UPDATE "patient_reviews" SET is_reported = FALSE, report_reason = NULL, is_moderated = TRUE WHERE id = %s RETURNING id;', [review_id])
        else: # approve
            cur.execute('UPDATE "patient_reviews" SET is_moderated = TRUE WHERE id = %s RETURNING id;', [review_id])
        res = cur.fetchone()
        con.commit()
        con.close()
        return res is not None
    except Exception as exc:
        print(f"[DB-WARN] Error moderating review #{review_id}: {exc}")
        return False


# ==================== AUDIT LOGS & ANALYTICS ====================

def log_audit_action(actor_email, actor_role, action, details=""):
    """Record an audit trail event for security and tracking."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            INSERT INTO audit_logs (actor_email, actor_role, action, details, created_at)
            VALUES (%s, %s, %s, %s, NOW());
        ''', [actor_email, actor_role, action, details])
        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[DB-WARN] Could not write audit log: {exc}")
        return False


def get_recent_audit_logs(limit=25):
    """Retrieve recent audit logs for Admin."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT id, actor_email, actor_role, action, details, created_at
            FROM audit_logs
            ORDER BY created_at DESC, id DESC
            LIMIT %s;
        ''', [limit])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        con.close()
        return [dict(zip(columns, r)) for r in rows]
    except Exception as exc:
        print(f"[DB-WARN] Error reading audit logs: {exc}")
        return []


def get_admin_dashboard_metrics():
    """Aggregate high-level system metrics for Admin Dashboard."""
    try:
        con = get_connection()
        cur = con.cursor()

        cur.execute('SELECT COUNT(*) FROM "patients" WHERE role = \'patient\';')
        total_patients = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM "doctors";')
        total_doctors = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM hospitals;')
        total_hospitals = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM appointments;')
        total_appointments = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM "patient_reviews";')
        total_reviews = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM "patient_reviews" WHERE is_reported = TRUE;')
        reported_reviews = cur.fetchone()[0]

        # Sentiment breakdown
        cur.execute('''
            SELECT 
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'positive') AS pos,
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'negative') AS neg,
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'neutral') AS neu
            FROM "patient_reviews";
        ''')
        sent_row = cur.fetchone()
        pos_cnt = sent_row[0] or 0
        neg_cnt = sent_row[1] or 0
        neu_cnt = sent_row[2] or 0
        total_sent = max(pos_cnt + neg_cnt + neu_cnt, 1)

        pos_pct = round((pos_cnt / total_sent) * 100, 1)
        neg_pct = round((neg_cnt / total_sent) * 100, 1)
        neu_pct = round((neu_cnt / total_sent) * 100, 1)

        # Top hospitals by doctor count
        cur.execute('''
            SELECT hospital, "Location (Tamil Nadu)" AS location, COUNT(*) AS doc_count, ROUND(AVG(rating), 2) AS avg_rat
            FROM "doctors"
            WHERE hospital IS NOT NULL AND TRIM(hospital) != ''
            GROUP BY hospital, "Location (Tamil Nadu)"
            ORDER BY doc_count DESC
            LIMIT 5;
        ''')
        top_hospitals = [{"hospital": r[0], "location": r[1], "doc_count": r[2], "avg_rating": float(r[3] or 4.5)} for r in cur.fetchall()]

        # High-profile doctors
        cur.execute('''
            SELECT id, doctor, hospital, specialization, rating, experience_years, consultation_fee
            FROM "doctors"
            ORDER BY rating DESC, experience_years DESC
            LIMIT 5;
        ''')
        top_doctors = [{"id": r[0], "name": r[1], "hospital": r[2], "specialization": r[3], "rating": float(r[4] or 4.5), "experience": r[5], "fee": r[6]} for r in cur.fetchall()]

        con.close()
        return {
            "total_patients": total_patients,
            "total_doctors": total_doctors,
            "total_hospitals": total_hospitals,
            "total_appointments": total_appointments,
            "total_reviews": total_reviews,
            "reported_reviews": reported_reviews,
            "sentiment_positive_pct": pos_pct,
            "sentiment_negative_pct": neg_pct,
            "sentiment_neutral_pct": neu_pct,
            "sentiment_positive_count": pos_cnt,
            "sentiment_negative_count": neg_cnt,
            "sentiment_neutral_count": neu_cnt,
            "top_hospitals": top_hospitals,
            "top_doctors": top_doctors
        }
    except Exception as exc:
        print(f"[DB-WARN] Error computing admin metrics: {exc}")
        return {
            "total_patients": 0, "total_doctors": 0, "total_hospitals": 0,
            "total_appointments": 0, "total_reviews": 0, "reported_reviews": 0,
            "sentiment_positive_pct": 75.0, "sentiment_negative_pct": 10.0, "sentiment_neutral_pct": 15.0,
            "top_hospitals": [], "top_doctors": []
        }


def get_doctor_dashboard_metrics(doctor_name, doctor_id=None):
    """Aggregate metrics and feedback insights specifically for Doctor Dashboard."""
    try:
        con = get_connection()
        cur = con.cursor()

        # Appointments breakdown
        cur.execute('''
            SELECT 
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'Pending') AS pending,
                COUNT(*) FILTER (WHERE status = 'Approved') AS approved,
                COUNT(*) FILTER (WHERE status = 'Completed') AS completed
            FROM appointments
            WHERE LOWER(doctor_name) = LOWER(%s);
        ''', [doctor_name.strip()])
        apt_row = cur.fetchone()

        # Reviews & Sentiments
        cur.execute('''
            SELECT 
                COUNT(*) AS total_rev,
                ROUND(AVG(patient_rating), 2) AS avg_rating,
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'positive') AS pos,
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'negative') AS neg,
                COUNT(*) FILTER (WHERE LOWER(sentiment_label) = 'neutral') AS neu
            FROM "patient_reviews"
            WHERE LOWER(doctor_name) = LOWER(%s);
        ''', [doctor_name.strip()])
        rev_row = cur.fetchone()

        tot_rev = rev_row[0] or 0
        avg_rat = float(rev_row[1]) if rev_row[1] is not None else 4.5
        pos_cnt = rev_row[2] or 0
        neg_cnt = rev_row[3] or 0
        neu_cnt = rev_row[4] or 0
        tot_sent = max(tot_rev, 1)

        # NLP Service Insights (waiting time, communication, explanation)
        cur.execute('''
            SELECT new_feedback FROM "patient_reviews" WHERE LOWER(doctor_name) = LOWER(%s);
        ''', [doctor_name.strip()])
        feedbacks = [r[0] or "" for r in cur.fetchall()]
        con.close()

        waiting_time_issues = sum(1 for f in feedbacks if any(w in f.lower() for w in ["wait", "delay", "queue", "late", "slow"]))
        good_explanation = sum(1 for f in feedbacks if any(w in f.lower() for w in ["clear", "explain", "listen", "kind", "good", "patient"]))
        cost_concerns = sum(1 for f in feedbacks if any(w in f.lower() for w in ["cost", "expensive", "fee", "charge", "money"]))

        return {
            "total_appointments": apt_row[0] or 0,
            "pending_appointments": apt_row[1] or 0,
            "approved_appointments": apt_row[2] or 0,
            "completed_appointments": apt_row[3] or 0,
            "total_reviews": tot_rev,
            "average_rating": avg_rat,
            "positive_count": pos_cnt,
            "negative_count": neg_cnt,
            "neutral_count": neu_cnt,
            "positive_pct": round((pos_cnt / tot_sent) * 100, 1),
            "negative_pct": round((neg_cnt / tot_sent) * 100, 1),
            "neutral_pct": round((neu_cnt / tot_sent) * 100, 1),
            "waiting_time_issues": waiting_time_issues,
            "good_explanation_score": good_explanation,
            "cost_concerns": cost_concerns
        }
    except Exception as exc:
        print(f"[DB-WARN] Error computing doctor metrics: {exc}")
        return {
            "total_appointments": 0, "pending_appointments": 0,
            "approved_appointments": 0, "completed_appointments": 0,
            "total_reviews": 0, "average_rating": 4.5,
            "positive_pct": 80.0, "negative_pct": 10.0, "neutral_pct": 10.0,
            "waiting_time_issues": 0, "good_explanation_score": 0, "cost_concerns": 0
        }
