import pandas as pd
from datetime import datetime
from pathlib import Path
from db import get_connection

WORKSPACE_DIR = Path(__file__).resolve().parent

def setup_all_schemas():
    con = get_connection()
    cur = con.cursor()

    print("[0] Ensuring foundational tables exist...")
    # Base patients table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "patients" (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(255) DEFAULT 'Patient',
            last_name VARCHAR(255) DEFAULT '',
            email VARCHAR(255) UNIQUE,
            password VARCHAR(255) DEFAULT 'password123',
            role VARCHAR(50) DEFAULT 'patient',
            status VARCHAR(50) DEFAULT 'active',
            phone VARCHAR(50),
            age INTEGER DEFAULT 30,
            gender VARCHAR(20) DEFAULT 'Not specified',
            country VARCHAR(100) DEFAULT 'India',
            address TEXT,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    # Base doctors table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "doctors" (
            id SERIAL PRIMARY KEY,
            doctor VARCHAR(255),
            specialization VARCHAR(255),
            hospital VARCHAR(255),
            "Location (Tamil Nadu)" VARCHAR(255),
            location VARCHAR(255),
            department VARCHAR(255),
            email VARCHAR(255),
            password VARCHAR(255) DEFAULT 'doctor123',
            experience_years INTEGER DEFAULT 10,
            consultation_fee INTEGER DEFAULT 500,
            average_rating DOUBLE PRECISION DEFAULT 4.5,
            recommendation_score DOUBLE PRECISION DEFAULT 90.0,
            sentiment_label VARCHAR(50) DEFAULT 'Positive',
            complaint_category VARCHAR(255),
            is_verified BOOLEAN DEFAULT TRUE,
            verification_status VARCHAR(40) DEFAULT 'Approved',
            qualifications VARCHAR(255) DEFAULT 'MBBS, MD',
            bio TEXT,
            registration_number VARCHAR(120),
            registration_council VARCHAR(180),
            available_days VARCHAR(180) DEFAULT 'Mon - Sat',
            available_timings VARCHAR(180) DEFAULT '09:30 AM - 05:30 PM',
            document_reference TEXT,
            rejection_reason TEXT,
            verified_by VARCHAR(255),
            verified_at TIMESTAMP,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    # Base patient_reviews table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "patient_reviews" (
            id SERIAL PRIMARY KEY,
            doctor_name VARCHAR(255),
            hospital VARCHAR(255),
            patient_email VARCHAR(255) DEFAULT 'patient@example.com',
            patient_name VARCHAR(255) DEFAULT 'Patient',
            patient_rating INTEGER DEFAULT 5,
            new_feedback TEXT,
            sentiment_label VARCHAR(50) DEFAULT 'Positive',
            doctor_response TEXT,
            is_reported BOOLEAN DEFAULT FALSE,
            report_reason TEXT,
            is_moderated BOOLEAN DEFAULT FALSE,
            moderation_status VARCHAR(40) DEFAULT 'Published',
            moderation_note TEXT,
            waiting_time_rating INTEGER DEFAULT 5,
            communication_rating INTEGER DEFAULT 5,
            cost_satisfaction_rating INTEGER DEFAULT 5,
            appointment_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    # Base faqs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS "faqs" (
            id SERIAL PRIMARY KEY,
            question TEXT,
            answer TEXT,
            category VARCHAR(255)
        );
    """)
    con.commit()

    print("[1] Enhancing 'patients' table...")
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='role') THEN
                ALTER TABLE "patients" ADD COLUMN role VARCHAR(50) DEFAULT 'patient';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='status') THEN
                ALTER TABLE "patients" ADD COLUMN status VARCHAR(50) DEFAULT 'active';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='id') THEN
                ALTER TABLE "patients" ADD COLUMN id SERIAL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='phone') THEN
                ALTER TABLE "patients" ADD COLUMN phone VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='age') THEN
                ALTER TABLE "patients" ADD COLUMN age INTEGER DEFAULT 30;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='gender') THEN
                ALTER TABLE "patients" ADD COLUMN gender VARCHAR(20) DEFAULT 'Not specified';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patients' AND column_name='country') THEN
                ALTER TABLE "patients" ADD COLUMN country VARCHAR(100) DEFAULT 'India';
            END IF;
        END $$;
    """)
    con.commit()

    # Ensure Default Admin exists
    cur.execute('SELECT 1 FROM "patients" WHERE email = %s;', ['admin@healthcare.com'])
    if not cur.fetchone():
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cur.execute('''
            INSERT INTO "patients" (first_name, last_name, email, password, role, status, enrolled_at, country, age)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        ''', ['System', 'Administrator', 'admin@healthcare.com', 'admin123', 'admin', 'active', now_str, 'India', 35])
        con.commit()
        print("    -> Default admin created: admin@healthcare.com / admin123")
    else:
        cur.execute('UPDATE "patients" SET role = %s, password = %s WHERE email = %s;', ['admin', 'admin123', 'admin@healthcare.com'])
        con.commit()
        print("    -> Default admin verified.")

    # Ensure Default Demo Patient exists
    cur.execute('SELECT 1 FROM "patients" WHERE email = %s;', ['patient@example.com'])
    if not cur.fetchone():
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cur.execute('''
            INSERT INTO "patients" (first_name, last_name, email, password, role, status, enrolled_at, country, age)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        ''', ['Test', 'Patient', 'patient@example.com', 'password123', 'patient', 'active', now_str, 'India', 28])
        con.commit()
        print("    -> Default patient created: patient@example.com / password123")

    print("[2] Enhancing 'doctors' table with credentials & verification...")
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='email') THEN
                ALTER TABLE "doctors" ADD COLUMN email VARCHAR(255);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='password') THEN
                ALTER TABLE "doctors" ADD COLUMN password VARCHAR(255) DEFAULT 'doctor123';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='is_verified') THEN
                ALTER TABLE "doctors" ADD COLUMN is_verified BOOLEAN DEFAULT TRUE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='qualifications') THEN
                ALTER TABLE "doctors" ADD COLUMN qualifications VARCHAR(255) DEFAULT 'MBBS, MD';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='bio') THEN
                ALTER TABLE "doctors" ADD COLUMN bio TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='experience_years') THEN
                ALTER TABLE "doctors" ADD COLUMN experience_years INTEGER DEFAULT 10;
            END IF;
        END $$;
    """)
    con.commit()

    # Provide demo doctor accounts if needed
    try:
        cur.execute('UPDATE "doctors" SET email = LOWER(REGEXP_REPLACE(doctor, \'[^a-zA-Z0-9]\', \'\', \'g\')) || \'@hospital.com\' WHERE (email IS NULL OR email = \'\') AND doctor IS NOT NULL;')
        con.commit()
        print("    -> Doctor emails verified/generated.")
    except Exception as e:
        print(f"    -> Doctor email generation notice: {e}")

    print("[3] Creating & ensuring 'appointments' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            appointment_ref VARCHAR(30) UNIQUE,
            patient_email VARCHAR(255),
            patient_name VARCHAR(255),
            patient_phone VARCHAR(50),
            patient_age INTEGER,
            patient_gender VARCHAR(20),
            doctor_id INTEGER,
            doctor_name VARCHAR(255),
            doctor_email VARCHAR(255),
            hospital VARCHAR(255),
            specialization VARCHAR(255),
            appointment_date DATE,
            appointment_time VARCHAR(50),
            symptoms TEXT,
            disease TEXT,
            notes TEXT,
            status VARCHAR(50) DEFAULT 'Pending',
            doctor_notes TEXT,
            prescription TEXT,
            has_feedback BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    # Ensure doctor_email exists in appointments table
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='appointments' AND column_name='doctor_email') THEN
                ALTER TABLE appointments ADD COLUMN doctor_email VARCHAR(255);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='appointments' AND column_name='doctor_notes') THEN
                ALTER TABLE appointments ADD COLUMN doctor_notes TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='appointments' AND column_name='prescription') THEN
                ALTER TABLE appointments ADD COLUMN prescription TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='appointments' AND column_name='has_feedback') THEN
                ALTER TABLE appointments ADD COLUMN has_feedback BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    """)
    con.commit()
    print("    -> 'appointments' table ready with all columns (including doctor_email).")

    print("[4] Creating 'notifications' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255),
            user_role VARCHAR(50),
            title VARCHAR(255),
            message TEXT,
            type VARCHAR(50),
            reference_id INTEGER,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()
    print("    -> 'notifications' table ready.")

    print("[5] Enhancing 'patient_reviews' table...")
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='patient_email') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN patient_email VARCHAR(255) DEFAULT 'patient@example.com';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='doctor_response') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN doctor_response TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='is_reported') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN is_reported BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='report_reason') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN report_reason TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='is_moderated') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN is_moderated BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='appointment_id') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN appointment_id INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='waiting_time_rating') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN waiting_time_rating INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='communication_rating') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN communication_rating INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='cost_satisfaction_rating') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN cost_satisfaction_rating INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='moderation_status') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN moderation_status VARCHAR(40) DEFAULT 'Published';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='patient_reviews' AND column_name='moderation_note') THEN
                ALTER TABLE "patient_reviews" ADD COLUMN moderation_note TEXT;
            END IF;
        END $$;
    """)
    con.commit()
    print("    -> 'patient_reviews' table ready with privacy & moderation columns.")

    print("[6] Creating 'audit_logs' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            actor_email VARCHAR(255),
            actor_role VARCHAR(50),
            action VARCHAR(255),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()
    print("    -> 'audit_logs' table ready.")

    print("[7] Creating & populating 'hospitals' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE,
            location VARCHAR(255),
            facilities TEXT DEFAULT '24/7 Emergency, ICU, Pharmacy, Diagnostic Lab, Ambulance',
            contact_phone VARCHAR(50) DEFAULT '+91 44 2829 0200',
            emergency_available BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    # Pre-populate distinct hospitals from doctors table if empty
    try:
        cur.execute("SELECT COUNT(*) FROM hospitals;")
        hosp_count = cur.fetchone()[0]
        if hosp_count == 0:
            cur.execute("""
                INSERT INTO hospitals (name, location)
                SELECT DISTINCT hospital, "Location (Tamil Nadu)"
                FROM doctors
                WHERE hospital IS NOT NULL AND TRIM(hospital) != ''
                ON CONFLICT (name) DO NOTHING;
            """)
            con.commit()
            print("    -> Populated hospitals from doctors dataset.")
    except Exception as exc:
        print(f"    -> Hospital population notice: {exc}")

    print("[8] Doctor verification workflow columns...")
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='verification_status') THEN
                ALTER TABLE "doctors" ADD COLUMN verification_status VARCHAR(40) DEFAULT 'Approved';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='registration_number') THEN
                ALTER TABLE "doctors" ADD COLUMN registration_number VARCHAR(120);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='registration_council') THEN
                ALTER TABLE "doctors" ADD COLUMN registration_council VARCHAR(180);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='available_days') THEN
                ALTER TABLE "doctors" ADD COLUMN available_days VARCHAR(180) DEFAULT 'Mon - Sat';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='available_timings') THEN
                ALTER TABLE "doctors" ADD COLUMN available_timings VARCHAR(180) DEFAULT '09:30 AM - 05:30 PM';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='document_reference') THEN
                ALTER TABLE "doctors" ADD COLUMN document_reference TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='rejection_reason') THEN
                ALTER TABLE "doctors" ADD COLUMN rejection_reason TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='verified_by') THEN
                ALTER TABLE "doctors" ADD COLUMN verified_by VARCHAR(255);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='verified_at') THEN
                ALTER TABLE "doctors" ADD COLUMN verified_at TIMESTAMP;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='doctors' AND column_name='submitted_at') THEN
                ALTER TABLE "doctors" ADD COLUMN submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END $$;
    """)
    con.commit()

    try:
        cur.execute("""
            UPDATE "doctors"
            SET is_verified = TRUE
            WHERE is_verified IS NULL AND (registration_number IS NULL OR registration_number = '');
        """)
        cur.execute("""
            UPDATE "doctors"
            SET verification_status = 'Approved'
            WHERE verification_status IS NULL AND is_verified = TRUE;
        """)
        con.commit()
    except Exception:
        pass

    print("[9] Creating 'review_reports' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS review_reports (
            id SERIAL PRIMARY KEY,
            review_id INTEGER,
            reporter_role VARCHAR(50),
            reporter_email VARCHAR(255),
            reason TEXT,
            status VARCHAR(40) DEFAULT 'Open',
            resolved_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    print("[10] Creating 'doctor_profile_requests' table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctor_profile_requests (
            id SERIAL PRIMARY KEY,
            doctor_id INTEGER,
            doctor_email VARCHAR(255),
            requested_changes TEXT,
            request_note TEXT,
            status VARCHAR(40) DEFAULT 'Pending Review',
            reviewed_by VARCHAR(255),
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()

    con.close()
    print("\n[ALL SCHEMAS SETUP SUCCESSFULLY!]")

if __name__ == "__main__":
    setup_all_schemas()
