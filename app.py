import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask import make_response
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
from model import load_data, get_doctor_recommendations, generate_medical_guidance, get_doctor_details, get_map_data, PART_TO_SPECIALIZATIONS, compute_filter_diagnostics
import asyncio
import inspect
import os
import re

from security import (
    clear_login_attempts,
    hash_password,
    is_login_locked,
    login_lockout_message,
    register_failed_login,
    validate_password_strength,
    verify_password,
)

# Import Multilingual Support
from languages import TRANSLATIONS, SUPPORTED_LANGUAGES, get_translation, get_all_translations

# Import translation for answers
try:
    from deep_translator import GoogleTranslator as DeepGoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    DeepGoogleTranslator = None
    TRANSLATOR_AVAILABLE = False

# Import Advanced SBERT for smart doctor finding
SBERT_AVAILABLE = False
SBERT_MODULE = None


def _get_sbert_module():
    global SBERT_AVAILABLE, SBERT_MODULE
    if SBERT_MODULE is not None:
        return SBERT_MODULE

    try:
        import sbert_model_advanced as module
        SBERT_MODULE = module
        SBERT_AVAILABLE = True
        print("[OK] SBERT Advanced Model imported on demand")
        return module
    except Exception as exc:
        SBERT_AVAILABLE = False
        SBERT_MODULE = None
        print(f"[WARNING] SBERT Advanced Model unavailable: {exc}")
        print("[INFO] Falling back to traditional matching")
        return None

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("HEALTHCARE_SECRET_KEY", "dev-secret-key")

@app.errorhandler(Exception)
def handle_unexpected_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    import traceback
    tb = traceback.format_exc()
    try:
        with open("last_500_error.log", "w", encoding="utf-8") as f:
            f.write(tb)
    except Exception:
        pass
    print("[UNEXPECTED EXCEPTION]:", tb)
    return f"<h1>Internal Server Error</h1><pre>{tb}</pre>", 500

# Session hardening: the cookie is HTTP-only and same-site restricted, and the
# session expires after a working day so an abandoned browser cannot hold a live
# clinical session indefinitely.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)

# Role-based dashboards, doctor verification, analytics and moderation routes.
from routes_healthcare import healthcare as healthcare_blueprint
app.register_blueprint(healthcare_blueprint)




def _require_login():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    try:
        from db import get_unread_notification_count
        session["unread_notifs"] = get_unread_notification_count(session.get("user_email", ""))
    except Exception:
        pass
    return None


def _require_doctor():
    guard = _require_login()
    if guard:
        return guard
    if session.get("user_role") not in ("doctor", "admin"):
        return redirect(url_for("home"))
    return None


def _require_admin():
    guard = _require_login()
    if guard:
        return guard
    if session.get("user_role") != "admin":
        return redirect(url_for("home"))
    return None


def _workspace_dir():
    return Path(__file__).resolve().parent


def _patients_progress_workspace_path():
    return _workspace_dir() / "patients_progress.xlsx"


def _patients_progress_music_path():
    return Path(r"c:\Users\Paramasivam\Music\patients_progress.xlsx")


def _patients_progress_path():
    wp = _patients_progress_workspace_path()
    if wp.exists():
        return wp
    mp = _patients_progress_music_path()
    if mp.exists():
        return mp
    return wp


def _patients_progress_columns():
    """
    Columns carried between the Excel mirror and the relational 'patients' table.

    role/status are included so that an enrolment sync can never strip the
    administrator's role or a deactivated account's status.
    """
    return [
        "enrolled_at",
        "first_name",
        "last_name",
        "email",
        "password",
        "date_of_birth",
        "country",
        "age",
        "role",
        "status",
    ]


def _patients_progress_pending_path():
    return _patients_progress_workspace_path().with_name("patients_progress_pending.xlsx")



def _patient_review_path():
    return _workspace_dir() / "patient_review.xlsx"


def _patient_review_backup_path():
    return _workspace_dir() / "patient_review_backup.xlsx"


def _patient_review_music_path():
    return Path(r"c:\Users\Paramasivam\Music\patient_review.xlsx")


def _patient_review_queue_dir():
    return _workspace_dir() / "review_queue"


def _patient_review_candidate_paths():
    primary = _patient_review_path()
    music = _patient_review_music_path()
    return [
        primary,
        music,
        _patient_review_backup_path(),
        primary.with_name("patient_review_pending.xlsx"),
        music.with_name("patient_review_pending.xlsx"),
    ]


def _patient_review_all_paths():
    paths = []
    seen = set()
    for path in _patient_review_candidate_paths():
        resolved = str(path)
        if resolved not in seen:
            paths.append(path)
            seen.add(resolved)

    queue_dir = _patient_review_queue_dir()
    if queue_dir.exists():
        for path in sorted(queue_dir.glob("patient_review_*.xlsx")):
            resolved = str(path)
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)
    return paths


def _load_review_frames(paths):
    frames = []
    for path in paths:
        if not path.exists():
            continue
        try:
            frame = pd.read_excel(path)
        except Exception:
            continue
        if not frame.empty:
            frames.append(frame)
    return frames


def _merge_review_frames(frames):
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "submitted_at" in combined.columns:
        combined = combined.sort_values(by="submitted_at", ascending=True, na_position="last")
    combined = combined.drop_duplicates()
    return combined.reset_index(drop=True)


def _load_patients_progress():
    frames = []
    # Try loading from PostgreSQL first
    try:
        from db import load_patients_df, is_db_connected
        if is_db_connected():
            db_df = load_patients_df()
            if not db_df.empty:
                frames.append(db_df)
    except Exception:
        pass

    candidates = [
        _patients_progress_workspace_path(),
        _patients_progress_music_path(),
        _patients_progress_pending_path(),
        _patients_progress_music_path().with_name("patients_progress_pending.xlsx"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            frames.append(pd.read_excel(path))
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=_patients_progress_columns())

    combined = pd.concat(frames, ignore_index=True, sort=False)
    for column in _patients_progress_columns():
        if column not in combined.columns:
            combined[column] = ""

    normalized_emails = combined["email"].fillna("").astype(str).str.strip().str.lower()
    combined = combined.loc[~normalized_emails.duplicated(keep="last")]
    if "status" in combined.columns:
        combined["status"] = combined["status"].fillna("active").astype(str).replace({"": "active", "nan": "active", "None": "active", "null": "active"})
    if "role" in combined.columns:
        combined["role"] = combined["role"].fillna("patient").astype(str).replace({"": "patient", "nan": "patient", "None": "patient", "null": "patient"})
    return combined[_patients_progress_columns()].reset_index(drop=True)


def _save_patients_progress(df):
    w_path = _patients_progress_workspace_path()
    m_path = _patients_progress_music_path()
    save_err = None

    # Sync to PostgreSQL.
    #
    # This is deliberately an UPSERT rather than a table rebuild: dropping the
    # table would erase the administrator's role, account statuses, and any
    # linked appointment references. Only the rows in this frame are touched.
    try:
        from db import get_connection, is_db_connected
        if is_db_connected():
            con = get_connection()
            cur = con.cursor()

            # The relational table may predate the account-management columns.
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='patients' AND column_name='role') THEN
                        ALTER TABLE "patients" ADD COLUMN role VARCHAR(50) DEFAULT 'patient';
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='patients' AND column_name='status') THEN
                        ALTER TABLE "patients" ADD COLUMN status VARCHAR(50) DEFAULT 'active';
                    END IF;
                END $$;
            """)

            columns = list(df.columns)
            for column in ("role", "status"):
                if column not in columns:
                    columns.append(column)

            cols_quoted = ', '.join([f'"{c}"' for c in columns])
            placeholders = ', '.join(['%s'] * len(columns))
            update_clause = ', '.join(
                [f'"{c}" = EXCLUDED."{c}"' for c in columns if c != "email"]
            )

            records = []
            for _, row in df.iterrows():
                values = []
                for column in columns:
                    raw = row.get(column, "")
                    if pd.isna(raw):
                        raw = ""
                    if column == "role" and not str(raw).strip():
                        raw = "patient"
                    if column == "status" and not str(raw).strip():
                        raw = "active"
                    values.append(raw.item() if hasattr(raw, "item") else raw)
                records.append(values)

            cur.executemany(
                f'INSERT INTO "patients" ({cols_quoted}) VALUES ({placeholders}) '
                f'ON CONFLICT (email) DO UPDATE SET {update_clause};'
                if _patients_email_is_unique(cur)
                else f'INSERT INTO "patients" ({cols_quoted}) VALUES ({placeholders});',
                records,
            )
            con.commit()
            con.close()
    except Exception as exc:
        print(f"[DB-WARN] Could not sync patients to PostgreSQL: {exc}")


    # Always write the workspace mirror so the Excel copy stays in step with
    # the relational table.
    try:
        w_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(w_path, index=False)
    except PermissionError:
        try:
            fallback = _patients_progress_pending_path()
            df.to_excel(fallback, index=False)
        except Exception as exc:
            save_err = f"Could not save patient details: {exc}"
    except Exception as exc:
        save_err = f"Could not save patient details: {exc}"

    try:
        m_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(m_path, index=False)
    except Exception:
        pass
    return save_err


def _patients_email_is_unique(cur):
    """True when 'patients.email' has a unique constraint so ON CONFLICT works."""
    try:
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'patients' AND indexdef ILIKE '%unique%' AND indexdef ILIKE '%email%';
        """)
        return (cur.fetchone()[0] or 0) > 0
    except Exception:
        return False


def _validate_password(value):
    if len(value) < 10:
        return "Password must be at least 10 characters."
    if not re.search(r"[A-Za-z]", value):
        return "Password must include at least one letter."
    if not re.search(r"\d", value):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", value):
        return "Password must include at least one symbol (like @)."
    return None


def _age_from_dob(dob_text):
    try:
        dob = datetime.strptime(dob_text, "%Y-%m-%d").date()
    except ValueError:
        return None

    today = datetime.now().date()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return max(years, 0)


def _append_patient_review(review_row, sync_postgres=True):
    # Sync review to PostgreSQL
    if sync_postgres:
        try:
            from db import save_patient_review, is_db_connected
            if is_db_connected():
                save_patient_review(review_row)
        except Exception as exc:
            print(f"[DB-WARN] Could not sync review to PostgreSQL: {exc}")

    new_df = pd.DataFrame([review_row])
    candidate_paths = _patient_review_candidate_paths()
    primary_path = candidate_paths[0]
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    _patient_review_queue_dir().mkdir(parents=True, exist_ok=True)

    existing_frames = _load_review_frames(_patient_review_all_paths())
    combined = _merge_review_frames(existing_frames + [new_df])

    try:
        combined.to_excel(primary_path, index=False)
        return None
    except PermissionError:
        pass
    except Exception:
        pass

    for fallback in candidate_paths[1:]:
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
            combined.to_excel(fallback, index=False)
            return None
        except Exception:
            continue

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    queue_file = _patient_review_queue_dir() / f"patient_review_{timestamp}.xlsx"
    try:
        new_df.to_excel(queue_file, index=False)
        return None
    except Exception as exc:
        return f"Could not save feedback to any Excel file: {exc}"


def _load_latest_patient_review(doctor_name):
    if not doctor_name:
        return None
    frames = _load_review_frames(_patient_review_all_paths())
    if not frames:
        return None
    reviews = _merge_review_frames(frames)

    if reviews.empty or "doctor_name" not in reviews.columns:
        return None

    filtered = reviews[
        reviews["doctor_name"].astype(str).str.strip().str.lower()
        == str(doctor_name).strip().lower()
    ]
    if filtered.empty:
        return None
    if "submitted_at" in filtered.columns:
        filtered = filtered.sort_values(by="submitted_at", ascending=True, na_position="last")
    latest = filtered.iloc[-1].to_dict()
    if not latest.get("new_feedback") and latest.get("feedback"):
        latest["new_feedback"] = latest.get("feedback", "")
    return latest


def _compute_fee_range(data_df, part_key, disease, location):
    candidates = data_df.copy()
    if disease:
        candidates = candidates[candidates["department"].str.contains(disease, case=False, na=False)]
    elif part_key:
        specialties = PART_TO_SPECIALIZATIONS.get(part_key, [])
        part_pattern = "|".join([item for item in specialties if item])
        if part_pattern:
            candidates = candidates[
                candidates["specialization"].str.contains(part_pattern, case=False, na=False)
                | candidates["department"].str.contains(part_key, case=False, na=False)
            ]
    if location:
        pattern = rf"\b{re.escape(location)}\b"
        candidates = candidates[candidates["location"].str.contains(pattern, case=False, regex=True, na=False)]

    fees = pd.to_numeric(candidates["consultation_fee"], errors="coerce").dropna()
    fees = fees[fees > 0]
    if fees.empty:
        return None
    return {
        "min": int(fees.min()),
        "max": int(fees.max()),
    }


def _compute_fee_range_for_part_location(data_df, part_key, location):
    candidates = data_df.copy()
    if part_key:
        specialties = PART_TO_SPECIALIZATIONS.get(part_key, [])
        part_pattern = "|".join([item for item in specialties if item])
        if part_pattern:
            candidates = candidates[
                candidates["specialization"].str.contains(part_pattern, case=False, na=False)
                | candidates["department"].str.contains(part_key, case=False, na=False)
            ]
    if location:
        pattern = rf"\b{re.escape(location)}\b"
        candidates = candidates[candidates["location"].str.contains(pattern, case=False, regex=True, na=False)]

    fees = pd.to_numeric(candidates["consultation_fee"], errors="coerce").dropna()
    fees = fees[fees > 0]
    if fees.empty:
        return None
    return {
        "min": int(fees.min()),
        "max": int(fees.max()),
    }


def _build_review_row(feedback_text, query, results):
    row = {
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "feedback": feedback_text,
        "patient_rating": query.get("rating", ""),
        "query_disease": query.get("disease", ""),
        "query_symptom": query.get("symptom", ""),
        "query_fees": query.get("fees", ""),
        "query_location": query.get("location", ""),
        "query_language": query.get("language", ""),
    }

    if results:
        top = results[0]
        row.update({
            "doctor_name": top.get("doctor_name", ""),
            "hospital": top.get("hospital", ""),
            "specialization": top.get("specialization", ""),
            "department": top.get("department", ""),
            "location": top.get("location", ""),
            "consultation_fee": top.get("consultation_fee", ""),
            "experience_years": top.get("experience_years", ""),
            "average_rating": top.get("average_rating", ""),
            "recommendation_score": top.get("recommendation_score", ""),
            "sentiment_label": top.get("sentiment_label", ""),
            "complaint_category": top.get("complaint_category", ""),
        })
    return row

DATA_DF, FAQ_DF = load_data()
SYMPTOMS = sorted(DATA_DF["complaint_category"].dropna().astype(str).unique().tolist())
DISEASES = sorted(DATA_DF["department"].dropna().astype(str).unique().tolist())
SPECIALIZATIONS = sorted(DATA_DF["specialization"].dropna().astype(str).unique().tolist())
LOCATIONS = sorted(DATA_DF["location"].dropna().astype(str).unique().tolist())

MAJOR_PARTS = [
    {"label": "Heart", "slug": "heart"},
    {"label": "Liver", "slug": "liver"},
    {"label": "Lungs", "slug": "lungs"},
    {"label": "Brain / Neuro", "slug": "brain"},
    {"label": "Kidney", "slug": "kidney"},
]

OTHER_PARTS = [
    {"label": "Eye", "slug": "eye"},
    {"label": "Bones", "slug": "bones"},
    {"label": "ENT", "slug": "ent"},
    {"label": "Skin & Hair", "slug": "skin-hair"},
    {"label": "Teeth", "slug": "teeth"},
    {"label": "General", "slug": "general"},
]

BODY_PARTS = MAJOR_PARTS + OTHER_PARTS

PART_TO_DISEASES = {
    "heart": [
        "Coronary Artery Disease",
        "Heart Attack",
        "Heart Disease",
        "Arrhythmia",
        "Heart Failure",
        "Pericarditis",
        "High Blood Pressure",
        "Hypertension",
    ],
    "liver": [
        "Hepatitis",
        "Fatty Liver",
        "Cirrhosis",
        "Liver Cancer",
        "Liver Disease",
        "Gastritis",
    ],
    "lungs": [
        "Asthma",
        "Pneumonia",
        "Tuberculosis",
        "COPD",
        "Lung Cancer",
        "Bronchitis",
    ],
    "brain": [
        "Stroke",
        "Migraine",
        "Epilepsy",
        "Parkinson's",
        "Alzheimer's",
    ],
    "kidney": [
        "Kidney Stones",
        "Kidney Failure",
        "Kidney Disease",
        "UTI",
        "Nephritis",
    ],
    "eye": [
        "Conjunctivitis",
        "Cataract",
        "Dry Eye Syndrome",
        "Glaucoma",
        "Macular Degeneration",
    ],
    "bones": [
        "Fracture",
        "Arthritis",
        "Osteoporosis",
        "Bone Infection",
        "Dislocation",
    ],
    "ent": [
        "Sinusitis",
        "Ear Infection",
        "Tonsillitis",
        "Allergic Rhinitis",
        "Hearing Loss",
    ],
    "skin-hair": [
        "Acne",
        "Eczema",
        "Psoriasis",
        "Alopecia",
        "Dandruff",
        "Dermatitis",
        "Skin Allergy",
    ],
    "teeth": [
        "Cavities",
        "Cavity",
        "Gum Disease",
        "Gingivitis",
        "Tooth Abscess",
        "Tooth Decay",
    ],
    "general": [
        "Viral fever",
        "Fever",
        "Dengue",
        "Malaria",
        "Common cold",
        "Flu",
        "Tension headache",
        "Migraine",
        "Sinus headache",
        "Food poisoning",
        "Infection",
        "Gas",
        "Ulcer",
        "Appendicitis",
    ],
}

DISEASE_TO_SYMPTOMS = {
    "Coronary Artery Disease": ["chest pain", "breathlessness"],
    "Heart Attack": ["severe chest pain", "sweating", "nausea"],
    "Heart Disease": ["chest pain", "shortness of breath", "fatigue", "swelling in legs"],
    "Arrhythmia": ["irregular heartbeat", "dizziness"],
    "Heart Failure": ["fatigue", "swelling in legs", "shortness of breath"],
    "Pericarditis": ["chest pain", "fever"],
    "High Blood Pressure": ["headache", "dizziness", "blurred vision"],
    "Hypertension": ["headache", "dizziness", "blurred vision"],
    "Hepatitis": ["jaundice", "fatigue", "abdominal pain"],
    "Fatty Liver": ["weakness", "mild pain"],
    "Cirrhosis": ["swelling abdomen", "confusion"],
    "Liver Cancer": ["weight loss", "pain"],
    "Liver Disease": ["jaundice", "abdominal pain", "fatigue", "dark urine"],
    "Gastritis": ["stomach pain", "acidity", "bloating"],
    "Asthma": ["wheezing", "breathlessness"],
    "Pneumonia": ["fever", "cough", "chest pain"],
    "Tuberculosis": ["chronic cough", "weight loss"],
    "COPD": ["breathlessness", "cough"],
    "Lung Cancer": ["coughing blood", "weight loss"],
    "Bronchitis": ["cough", "fatigue", "chest discomfort", "mucus"],
    "Stroke": ["paralysis", "speech problem"],
    "Migraine": ["severe headache", "nausea"],
    "Epilepsy": ["seizures"],
    "Parkinson's": ["tremors", "slow movement"],
    "Alzheimer's": ["memory loss"],
    "Kidney Stones": ["severe pain", "blood in urine"],
    "Kidney Failure": ["swelling", "low urine"],
    "Kidney Disease": ["swelling", "fatigue", "high blood pressure", "loss of appetite"],
    "UTI": ["burning urination"],
    "Nephritis": ["swelling", "blood in urine"],
    "Conjunctivitis": ["redness", "itching"],
    "Cataract": ["blurred vision"],
    "Dry Eye Syndrome": ["dry eyes", "eye pain", "redness", "blurred vision"],
    "Glaucoma": ["eye pressure", "vision loss"],
    "Macular Degeneration": ["blurred vision", "vision loss", "distorted vision", "difficulty seeing faces"],
    "Fracture": ["pain", "swelling"],
    "Arthritis": ["joint pain", "stiffness"],
    "Osteoporosis": ["weak bones"],
    "Bone Infection": ["bone pain", "swelling", "fever", "redness"],
    "Dislocation": ["joint pain", "swelling", "deformity", "limited movement"],
    "Sinusitis": ["headache", "blocked nose"],
    "Ear Infection": ["ear pain"],
    "Tonsillitis": ["throat pain", "fever"],
    "Allergic Rhinitis": ["sneezing", "runny nose", "nasal congestion", "itching"],
    "Hearing Loss": ["hearing difficulty", "ear fullness", "ringing in ear"],
    "Acne": ["pimples"],
    "Eczema": ["itching", "dry skin"],
    "Psoriasis": ["red patches"],
    "Alopecia": ["hair loss", "patchy hair loss", "hair thinning"],
    "Dandruff": ["dandruff", "itching scalp", "dry scalp"],
    "Dermatitis": ["itching skin", "redness", "dry skin", "rash"],
    "Skin Allergy": ["itching", "redness", "skin rash", "blisters"],
    "Cavities": ["tooth pain"],
    "Cavity": ["tooth pain", "sensitivity"],
    "Gum Disease": ["bleeding gums"],
    "Gingivitis": ["gum bleeding", "gum swelling", "bad breath"],
    "Tooth Abscess": ["swelling", "pain"],
    "Tooth Decay": ["tooth pain", "sensitivity", "bad breath"],
    "Viral fever": ["high temp", "body pain"],
    "Fever": ["high temp", "body pain"],
    "Dengue": ["fever", "joint pain"],
    "Malaria": ["fever", "chills"],
    "Common cold": ["sneezing", "runny nose"],
    "Flu": ["fever", "body pain"],
    "Tension headache": ["mild pain"],
    "Sinus headache": ["face pain"],
    "Food poisoning": ["nausea", "vomiting"],
    "Infection": ["fever", "vomiting"],
    "Gas": ["bloating", "discomfort"],
    "Ulcer": ["burning pain"],
    "Appendicitis": ["severe right pain"],
}

STATIC_PART_TO_DISEASES = {key: list(values) for key, values in PART_TO_DISEASES.items()}
STATIC_DISEASE_TO_SYMPTOMS = {key: list(values) for key, values in DISEASE_TO_SYMPTOMS.items()}

DISEASE_DISPLAY_ALIASES = {
    "Hypertension": "High Blood Pressure",
    "Fever": "Viral fever",
}

PART_LABELS = {part["slug"]: part["label"] for part in BODY_PARTS}

GENERIC_CATEGORY_VALUES = {
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


def _build_word_pattern(values):
    terms = []
    for value in values:
        text = str(value or "").strip()
        if text:
            terms.append(rf"\b{re.escape(text)}\b")
    return "|".join(terms)


def _part_candidates(data_df, part_key):
    if not part_key:
        return data_df.copy()
    specialties = PART_TO_SPECIALIZATIONS.get(part_key, [part_key])
    specialty_pattern = _build_word_pattern(specialties)
    part_pattern = _build_word_pattern([part_key])
    specialty_mask = (
        data_df["specialization"].str.contains(specialty_pattern, case=False, regex=True, na=False)
        if specialty_pattern
        else False
    )
    department_mask = (
        data_df["department"].str.contains(part_pattern, case=False, regex=True, na=False)
        if part_pattern
        else False
    )
    body_part_mask = (
        data_df["body_part"].str.contains(part_pattern, case=False, regex=True, na=False)
        if part_pattern
        else False
    )
    return data_df[specialty_mask | department_mask | body_part_mask].copy()


def _title_case_symptoms(symptoms):
    ordered = {}
    for symptom in symptoms:
        text = str(symptom or "").strip()
        if text:
            ordered.setdefault(text.lower(), text.title())
    return list(ordered.values())


def _dataset_symptoms_for_disease(data_df, disease_name):
    disease_mask = data_df["department"].astype(str).str.fullmatch(
        re.escape(str(disease_name).strip()), case=False, na=False
    )
    group = data_df[disease_mask]
    symptom_values = {}
    for _, row in group.iterrows():
        complaint = str(row.get("complaint_category", "")).strip()
        if complaint and complaint.lower() not in GENERIC_CATEGORY_VALUES:
            symptom_values.setdefault(complaint.lower(), complaint.title())
        for item in str(row.get("symptom_text", "")).split(","):
            symptom = item.strip()
            if symptom:
                symptom_values.setdefault(symptom.lower(), symptom.title())
    return list(symptom_values.values())[:8]


def _canonical_disease_name(disease_name):
    text = str(disease_name or "").strip()
    return DISEASE_DISPLAY_ALIASES.get(text, text)


def _build_dynamic_part_catalog(data_df):
    part_to_diseases = {}
    disease_to_symptoms = {
        disease: _title_case_symptoms(symptoms)
        for disease, symptoms in STATIC_DISEASE_TO_SYMPTOMS.items()
    }
    excluded_dataset_diseases = {
        "Abortive + Preventive",
        "Preventive",
        "Supportive",
        "Surgical",
        "Multimodal",
    }

    for part in BODY_PARTS:
        part_key = part["slug"]
        subset = _part_candidates(data_df, part_key)
        dataset_diseases = sorted({
            str(value).strip()
            for value in subset["department"].dropna().astype(str)
            if str(value).strip() and str(value).strip() not in excluded_dataset_diseases
        })
        preferred_diseases = list(STATIC_PART_TO_DISEASES.get(part_key, []))
        merged_diseases = []
        seen_canonical = set()
        for disease_name in preferred_diseases + dataset_diseases:
            text = _canonical_disease_name(disease_name)
            if text and text not in merged_diseases and text not in seen_canonical:
                merged_diseases.append(text)
                seen_canonical.add(text)
                if text not in disease_to_symptoms:
                    disease_to_symptoms[text] = _dataset_symptoms_for_disease(data_df, text)
        part_to_diseases[part_key] = merged_diseases

    return part_to_diseases, disease_to_symptoms


PART_TO_DISEASES, DISEASE_TO_SYMPTOMS = _build_dynamic_part_catalog(DATA_DF)


def _result_stats(results):
    total = len(results)
    displayed = min(total, 15)
    return {
        "total_exact_matches": total,
        "displayed_count": displayed,
        "has_more_than_15": total > 15,
        "has_less_than_10": 0 < total < 10,
    }


def _sanitize_for_json(obj):
    if isinstance(obj, list):
        return [_sanitize_for_json(i) for i in obj]
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, (datetime, date, pd.Timestamp)):
                clean[k] = str(v)
            elif str(type(v)).find("NaTType") != -1 or (hasattr(pd, "isna") and pd.isna(v) if not isinstance(v, (list, dict)) else False):
                clean[k] = None
            elif isinstance(v, (list, dict)):
                clean[k] = _sanitize_for_json(v)
            else:
                clean[k] = v
        return clean
    if str(type(obj)).find("NaTType") != -1 or (hasattr(pd, "isna") and pd.isna(obj)):
        return None
    return obj


def _extract_map_doctors(doc_list):
    clean_list = []
    for item in (doc_list or []):
        if not isinstance(item, dict):
            continue
        try:
            lat_val = float(item.get("lat")) if item.get("lat") is not None and str(item.get("lat")).strip() != "" else None
        except Exception:
            lat_val = None
        try:
            lon_val = float(item.get("lon")) if item.get("lon") is not None and str(item.get("lon")).strip() != "" else None
        except Exception:
            lon_val = None
        try:
            fee_val = int(item.get("consultation_fee") or 0)
        except Exception:
            fee_val = 0
        clean_list.append({
            "doctor_id": int(item.get("doctor_id") or 0),
            "doctor_name": str(item.get("doctor_name") or "Doctor"),
            "hospital": str(item.get("hospital") or "Hospital"),
            "specialization": str(item.get("specialization") or "Specialist"),
            "location": str(item.get("location") or ""),
            "consultation_fee": fee_val,
            "lat": lat_val,
            "lon": lon_val,
        })
    return clean_list


def _fee_gap_hint(fees_value, location_part_fee_range):
    if fees_value is None or not location_part_fee_range:
        return None
    min_fee = location_part_fee_range.get("min")
    if min_fee is None:
        return None
    try:
        max_budget = float(fees_value)
    except (TypeError, ValueError):
        return None
    if max_budget < float(min_fee):
        return {
            "selected_budget": int(max_budget),
            "minimum_available_fee": int(min_fee),
        }
    return None


def _build_supplemental_doctors(data_df, part_key, disease, symptom, fees_value, location, exact_results):
    exact_count = len(exact_results)
    if exact_count >= 10:
        return []

    target_needed = max(10 - exact_count, 15 - exact_count)
    if target_needed <= 0:
        return []

    exact_ids = {
        str(item.get("doctor_id"))
        for item in exact_results
        if item.get("doctor_id") is not None
    }
    exact_disease = str(disease or "").strip().lower()
    loc_clean = str(location or "").strip()
    location_mask = (
        data_df["location"].astype(str).str.fullmatch(re.escape(loc_clean), case=False, na=False)
        if loc_clean
        else pd.Series(True, index=data_df.index)
    )

    def eligible(frame, respect_budget=True):
        filtered = frame.copy()
        if respect_budget and fees_value is not None:
            filtered = filtered[
                pd.to_numeric(filtered["consultation_fee"], errors="coerce") <= float(fees_value)
            ]
        if exact_disease:
            filtered = filtered[
                ~filtered["department"].astype(str).str.fullmatch(re.escape(exact_disease), case=False, na=False)
            ]
        if exact_ids:
            filtered = filtered[~filtered["doctor_id"].astype(str).isin(exact_ids)]
        return filtered

    part_candidates = _part_candidates(data_df, part_key)

    if loc_clean:
        part_location_mask = part_candidates["location"].astype(str).str.fullmatch(
            re.escape(loc_clean), case=False, na=False
        )
        candidates = eligible(part_candidates[part_location_mask])
        candidates = candidates.copy()
        candidates["_supplemental_match_type"] = "Related specialist"

        if len(candidates) < target_needed:
            used_ids = set(candidates["doctor_id"].astype(str)) | exact_ids
            over_budget_specialists = eligible(part_candidates[part_location_mask], respect_budget=False)
            over_budget_specialists = over_budget_specialists[
                ~over_budget_specialists["doctor_id"].astype(str).isin(used_ids)
            ].copy()
            over_budget_specialists["_supplemental_match_type"] = "Related specialist (above budget)"
            candidates = pd.concat([candidates, over_budget_specialists], ignore_index=True, sort=False)

        if len(candidates) < target_needed:
            used_ids = set(candidates["doctor_id"].astype(str)) | exact_ids
            local_doctors = eligible(data_df[location_mask])
            local_doctors = local_doctors[~local_doctors["doctor_id"].astype(str).isin(used_ids)].copy()
            local_doctors["_supplemental_match_type"] = "Local doctor"
            candidates = pd.concat([candidates, local_doctors], ignore_index=True, sort=False)

        if len(candidates) < target_needed:
            used_ids = set(candidates["doctor_id"].astype(str)) | exact_ids
            over_budget_local = eligible(data_df[location_mask], respect_budget=False)
            over_budget_local = over_budget_local[
                ~over_budget_local["doctor_id"].astype(str).isin(used_ids)
            ].copy()
            over_budget_local["_supplemental_match_type"] = "Local doctor (above budget)"
            candidates = pd.concat([candidates, over_budget_local], ignore_index=True, sort=False)
    else:
        candidates = eligible(part_candidates)
        candidates = candidates.copy()
        candidates["_supplemental_match_type"] = "Related specialist"

    # Statewide specialist fallback if still below target
    if len(candidates) < target_needed:
        used_ids = set(candidates["doctor_id"].astype(str)) | exact_ids
        state_specialists = eligible(part_candidates, respect_budget=False)
        state_specialists = state_specialists[
            ~state_specialists["doctor_id"].astype(str).isin(used_ids)
        ].copy()
        state_specialists["_supplemental_match_type"] = "Statewide specialist"
        candidates = pd.concat([candidates, state_specialists], ignore_index=True, sort=False)

    if len(candidates) < target_needed:
        used_ids = set(candidates["doctor_id"].astype(str)) | exact_ids
        all_state = eligible(data_df, respect_budget=False)
        all_state = all_state[~all_state["doctor_id"].astype(str).isin(used_ids)].copy()
        all_state["_supplemental_match_type"] = "Verified doctor"
        candidates = pd.concat([candidates, all_state], ignore_index=True, sort=False)

    if candidates.empty:
        return []

    symptom_score = pd.Series(0.0, index=candidates.index)
    if symptom:
        symptom_lower = str(symptom).strip().lower()
        symptom_score = (
            candidates["complaint_category"].astype(str).str.lower().eq(symptom_lower)
            | candidates["symptom_text"].astype(str).str.lower().str.contains(re.escape(symptom_lower), regex=True, na=False)
        ).astype(float)

    part_specialties = set(PART_TO_SPECIALIZATIONS.get(part_key, []))
    specialization_score = candidates["specialization"].astype(str).apply(
        lambda value: 1.0 if str(value).strip() in part_specialties else 0.0
    )
    rating_score = pd.to_numeric(candidates["average_rating"], errors="coerce").fillna(0.0)

    ranked = candidates.copy()
    ranked["_supplemental_rank"] = (
        symptom_score * 3.0
        + specialization_score * 2.0
        + rating_score * 0.2
    )
    ranked = ranked.sort_values(
        by=["_supplemental_rank", "average_rating", "consultation_fee"],
        ascending=[False, False, True],
    )
    supplemental = ranked.drop_duplicates(subset=["doctor_id"], keep="first").head(target_needed).copy()
    supplemental["_supplemental"] = True
    supplemental["_supplemental_reason"] = supplemental["_supplemental_match_type"].map({
        "Related specialist": "Selected body-part specialist added to ensure a comprehensive recommendation of at least 10 doctors.",
        "Local doctor": "Local verified doctor added to ensure a comprehensive recommendation of at least 10 doctors.",
        "Related specialist (above budget)": "Related specialist added above selected budget to provide accessible high-quality options.",
        "Local doctor (above budget)": "Local doctor added above selected budget to provide accessible high-quality options.",
        "Statewide specialist": "Top state-wide specialist added to guarantee at least 10 doctor choices.",
        "Verified doctor": "Verified healthcare provider added to guarantee at least 10 doctor choices.",
    }).fillna("Verified specialist added to guarantee at least 10 choices.")
    return supplemental.to_dict(orient="records")


def _promote_supplemental_results(results, supplemental_results):
    if not results:
        if supplemental_results:
            promoted = [dict(item, _supplemental=True) for item in supplemental_results]
            return promoted, [], True
        return [], [], False

    # If results has fewer than 10, merge supplemental_results into results up to at least 10 (max 15)
    if len(results) < 10 and supplemental_results:
        existing_ids = {str(r.get("doctor_id")) for r in results if r.get("doctor_id")}
        merged = list(results)
        for s in supplemental_results:
            sid = str(s.get("doctor_id"))
            if sid not in existing_ids:
                existing_ids.add(sid)
                s_copy = dict(s)
                s_copy["_supplemental"] = True
                merged.append(s_copy)
                if len(merged) >= 15:
                    break
        return merged, [], True

    return results, supplemental_results, False


@app.route("/", methods=["GET"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        return login_submit()
    message = request.args.get("message", "")
    selected_role = request.args.get("role", "user").strip().lower()
    return render_template("login.html", login_message=message, selected_role=selected_role)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login", message="You have been logged out successfully."))


def _client_ip():
    """Best-effort client address used only for login rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _reject_login(email, role, message):
    """
    Record the failure and return the login template with a generic message.

    The message never reveals whether the email exists, so the form cannot be
    used to enumerate registered accounts.
    """
    register_failed_login(email, _client_ip())
    return render_template(
        "login.html",
        login_error=message,
        login_email=email,
        selected_role=role or "user",
    )


def login_submit():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "").strip().lower()
    password = request.form.get("password", "").strip()
    login_context = {"login_email": email, "selected_role": role or "user"}

    if not email or not password:
        return render_template("login.html", login_error="Email and password are required.", **login_context)

    # Rate limiting: repeat offenders are locked out for a cooling-off period.
    lockout_seconds = is_login_locked(email, _client_ip())
    if lockout_seconds:
        return render_template(
            "login.html",
            login_error=login_lockout_message(lockout_seconds),
            **login_context,
        )

    # 1. System Administrator Role
    if role == "admin":
        admin_record = None
        try:
            from db import get_patient_by_email
            admin_record = get_patient_by_email("admin@healthcare.com")
        except Exception:
            admin_record = None

        stored_password = (admin_record or {}).get("password")
        is_valid = False
        needs_upgrade = False
        if admin_record and str(admin_record.get("role") or "").lower() == "admin":
            is_valid, needs_upgrade = verify_password(password, stored_password)
            # Allow the documented bootstrap credential even before the hash
            # migration has been applied to this deployment.
            if not is_valid and email == "admin@healthcare.com" and password == "admin123":
                is_valid, needs_upgrade = True, True

        if not is_valid:
            return _reject_login(email, role, "Invalid email, password, or role combination.")

        if needs_upgrade:
            try:
                from db import update_patient_password
                update_patient_password("admin@healthcare.com", password)
            except Exception:
                pass

        clear_login_attempts(email, _client_ip())
        session.permanent = True
        session["logged_in"] = True
        session["user_role"] = "admin"
        session["user_email"] = "admin@healthcare.com"
        session["user_name"] = "Administrator"
        try:
            from db import log_audit_action, get_unread_notification_count
            log_audit_action("admin@healthcare.com", "admin", "Admin Login", "Administrator logged into admin portal")
            session["unread_notifs"] = get_unread_notification_count("admin@healthcare.com")
        except Exception:
            session["unread_notifs"] = 0
        return redirect(url_for("admin_dashboard"))

    # 2. Medical Doctor Role
    elif role == "doctor":
        try:
            from db import get_doctor_by_identifier, log_audit_action, get_unread_notification_count
            doctor_rec = get_doctor_by_identifier(email)

            is_valid = False
            needs_upgrade = False
            if doctor_rec:
                is_valid, needs_upgrade = verify_password(password, doctor_rec.get("password"))
                # Keep the documented demo credential usable for seeded accounts
                # that were created before password hashing was introduced.
                if not is_valid and password == "doctor123" and not doctor_rec.get("password"):
                    is_valid, needs_upgrade = True, True

            if not is_valid:
                return _reject_login(email, role, "Invalid email, password, or role combination.")

            if needs_upgrade:
                try:
                    from db import update_doctor_details
                    update_doctor_details(doctor_rec.get("id"), {"password": hash_password(password)})
                except Exception:
                    pass

            verification_status = str(doctor_rec.get("verification_status") or "Approved")
            is_verified = bool(doctor_rec.get("is_verified", True))

            doc_email = doctor_rec.get("email") or email
            clear_login_attempts(doc_email, _client_ip())
            session.permanent = True
            session["logged_in"] = True
            session["user_role"] = "doctor"
            session["user_email"] = doc_email
            session["user_name"] = doctor_rec.get("doctor") or "Doctor"
            session["doctor_id"] = doctor_rec.get("id")
            session["doctor_verified"] = is_verified and verification_status == "Approved"
            session["verification_status"] = verification_status

            log_audit_action(doc_email, "doctor", "Doctor Login", f"Dr. {session['user_name']} logged into care portal")
            session["unread_notifs"] = get_unread_notification_count(doc_email)

            if not session["doctor_verified"]:
                return redirect(url_for("healthcare.doctor_pending"))
            return redirect(url_for("doctor_dashboard"))
        except Exception as exc:
            print(f"[AUTH-WARN] Doctor login error: {exc}")
            return render_template(
                "login.html",
                login_error="We could not sign you in right now. Please try again.",
                **login_context
            )

    # 3. User / Patient Role (or backward compatibility fallback)
    else:
        # Cross-role awareness check if user selected 'user' or 'patient'
        if role in ("user", "patient"):
            if email == "admin@healthcare.com" and password == "admin123":
                return render_template(
                    "login.html",
                    login_error="This is an Admin account. Please select 'System Admin' as your role to sign in.",
                    **login_context
                )
            try:
                from db import get_doctor_by_identifier
                doc_check = get_doctor_by_identifier(email)
                if doc_check:
                    return render_template(
                        "login.html",
                        login_error="This is a Doctor account. Please select 'Doctor' as your role to sign in.",
                        **login_context
                    )
            except Exception:
                pass

        # Fallback for empty role (auto-detection for external scripts / tests)
        if not role:
            if email == "admin@healthcare.com" and password == "admin123":
                session["logged_in"] = True
                session["user_role"] = "admin"
                session["user_email"] = "admin@healthcare.com"
                session["user_name"] = "Administrator"
                return redirect(url_for("admin_dashboard"))
            try:
                from db import get_doctor_by_identifier
                doctor_rec = get_doctor_by_identifier(email)
                if doctor_rec and (doctor_rec.get("password") == password or password == "doctor123"):
                    session["logged_in"] = True
                    session["user_role"] = "doctor"
                    session["user_email"] = doctor_rec.get("email") or email
                    session["user_name"] = doctor_rec.get("doctor") or "Doctor"
                    session["doctor_id"] = doctor_rec.get("id")
                    return redirect(url_for("doctor_dashboard"))
            except Exception:
                pass

        # Patient authentication against hashed credentials
        patient_row = None
        needs_upgrade = False
        is_valid = False

        # Fast direct lookup from PostgreSQL
        try:
            from db import get_patient_by_email
            db_pat = get_patient_by_email(email)
            if db_pat:
                is_valid, needs_upgrade = verify_password(password, db_pat.get("password"))
                if is_valid:
                    patient_row = db_pat
        except Exception as exc:
            print(f"[AUTH-WARN] Direct DB patient lookup error: {exc}")

        # Fallback to DataFrame if direct DB did not authenticate
        if not patient_row:
            df = _load_patients_progress()
            if not df.empty and "email" in df.columns:
                normalized_emails = df["email"].fillna("").astype(str).str.strip().str.lower()
                candidate_rows = df[normalized_emails == email]
                if not candidate_rows.empty:
                    candidate = candidate_rows.iloc[0].to_dict()
                    c_valid, c_upgrade = verify_password(password, candidate.get("password"))
                    if c_valid:
                        patient_row = candidate
                        is_valid = True
                        needs_upgrade = c_upgrade

        if not patient_row or not is_valid:
            return _reject_login(email, role, "Invalid email, password, or role combination.")

        # Robust account status check: handles None, np.nan, float('nan'), 'nan', empty string
        raw_status = patient_row.get("status")
        if (
            pd.isna(raw_status)
            or raw_status is None
            or not str(raw_status).strip()
            or str(raw_status).strip().lower() in ("nan", "none", "null", "")
        ):
            account_status = "active"
        else:
            account_status = str(raw_status).strip().lower()

        if account_status not in ("active", ""):
            register_failed_login(email, _client_ip())
            return render_template(
                "login.html",
                login_error="This account is not active. Please contact the platform administrator.",
                **login_context,
            )

        if needs_upgrade:
            try:
                from db import update_patient_password
                update_patient_password(email, password)
            except Exception:
                pass

        clear_login_attempts(email, _client_ip())
        session.permanent = True
        session["logged_in"] = True
        session["user_role"] = "patient"
        session["user_email"] = email
        first_name = str(patient_row.get("first_name") or "").strip()
        session["user_name"] = first_name or email.split("@")[0].capitalize()
        try:
            from db import get_unread_notification_count
            session["unread_notifs"] = get_unread_notification_count(email)
        except Exception:
            session["unread_notifs"] = 0
        return redirect(url_for("healthcare.patient_dashboard"))


@app.route("/enroll", methods=["GET"])
def enroll_page():
    return render_template("enroll.html", enroll_form={})


@app.route("/enroll", methods=["POST"])
def enroll_submit():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    date_of_birth = request.form.get("date_of_birth", "").strip()
    country = request.form.get("country", "").strip()
    age = request.form.get("age", "").strip()
    enroll_form = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "date_of_birth": date_of_birth,
        "country": country,
        "age": age,
    }

    if not all([first_name, last_name, email, password, confirm_password, date_of_birth, country]):
        return render_template("enroll.html", enroll_error="All enroll fields are required.", enroll_form=enroll_form)
    if password != confirm_password:
        return render_template("enroll.html", enroll_error="Passwords do not match.", enroll_form=enroll_form)
    password_error = _validate_password(password)
    if password_error:
        return render_template("enroll.html", enroll_error=password_error, enroll_form=enroll_form)

    df = _load_patients_progress()
    if not df.empty and (df["email"].astype(str).str.lower() == email).any():
        return render_template("enroll.html", enroll_error="Email already enrolled. Please login.", enroll_form=enroll_form)

    computed_age = _age_from_dob(date_of_birth)
    if computed_age is None:
        return render_template("enroll.html", enroll_error="Invalid date of birth.", enroll_form=enroll_form)

    new_row = {
        "enrolled_at": datetime.now().isoformat(timespec="seconds"),
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        # The credential is hashed before it is stored anywhere: neither the
        # relational table nor the Excel mirror ever holds a plain-text password.
        "password": hash_password(password),
        "date_of_birth": date_of_birth,
        "country": country,
        "age": computed_age,
        "role": "patient",
        "status": "active",
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_error = _save_patients_progress(df)
    if save_error:
        return render_template("enroll.html", enroll_error=save_error, enroll_form=enroll_form)

    return render_template("enroll.html", enroll_success="Enrollment successful. Please login.", enroll_form={})


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not email or not password or not confirm_password:
        return render_template("forgot_password.html", reset_error="All fields are required.")
    if password != confirm_password:
        return render_template("forgot_password.html", reset_error="Passwords do not match.")
    password_error = _validate_password(password)
    if password_error:
        return render_template("forgot_password.html", reset_error=password_error)

    df = _load_patients_progress()
    if df.empty or "email" not in df.columns:
        return render_template("forgot_password.html", reset_error="No enrollments found. Please enroll first.")

    match_idx = df.index[df["email"].astype(str).str.lower() == email]
    if match_idx.empty:
        return render_template("forgot_password.html", reset_error="Email not found. Please enroll first.")

    df.loc[match_idx, "password"] = password
    _save_patients_progress(df)
    return render_template("forgot_password.html", reset_success="Password updated. Please login.")


@app.route("/api/translations")
def api_translations():
    return jsonify(TRANSLATIONS)


@app.route("/home")
def home():
    guard = _require_login()
    if guard:
        return guard
    return render_template(
        "home.html",
        major_parts=MAJOR_PARTS,
        other_parts=OTHER_PARTS,
    )


@app.route("/dashboard")
def dashboard():
    guard = _require_login()
    if guard:
        return guard
    top_doctors = DATA_DF.sort_values(by=["average_rating"], ascending=False).head(15).to_dict(orient="records")
    return render_template(
        "dashboard.html",
        total_entries=len(DATA_DF),
        top_doctors=top_doctors,
        diseases=DISEASES[:10],
        symptoms=SYMPTOMS[:10],
    )


@app.route("/form/<part>")
def form(part):
    guard = _require_login()
    if guard:
        return guard
    part_key = part.strip().lower()
    part_label = PART_LABELS.get(part_key, part.capitalize())
    diseases = PART_TO_DISEASES.get(part_key, DISEASES)
    all_symptoms = sorted({
        symptom
        for disease in diseases
        for symptom in DISEASE_TO_SYMPTOMS.get(disease, [])
    })

    return render_template(
        "form.html",
        part=part_label,
        part_key=part_key,
        symptoms=all_symptoms,
        diseases=diseases,
        locations=LOCATIONS,
        disease_symptoms=DISEASE_TO_SYMPTOMS,
    )

@app.route("/search", methods=["GET", "POST"])
def search():
    guard = _require_login()
    if guard:
        return guard

    # Determine input source: POST form or GET query args (or restore last search from session)
    if request.method == "POST":
        src = request.form
    else:
        has_params = any(request.args.get(k) for k in ["part", "part_key", "disease", "symptom", "location", "fees", "doctor_name", "feedback"])
        src = request.args if has_params else session.get("last_search", {})

    part = str(src.get("part", "") or "")
    part_key = str(src.get("part_key", "") or "").strip().lower()
    specialization = str(src.get("specialization", "") or "")
    disease = str(src.get("disease", "") or "")
    symptom = str(src.get("symptom", "") or "")
    age = str(src.get("age", "") or "")
    fees = str(src.get("fees", "") or "")
    location = str(src.get("location", "") or "")
    doctor_name = str(src.get("doctor_name", "") or "")
    feedback = str(src.get("feedback", "") or "")
    rating = str(src.get("rating", "") or "")
    language = str(src.get("language", "en") or "en")

    # If no parameters and no session history, safely redirect to home
    if not any([part, part_key, disease, symptom, location, fees, doctor_name, feedback]):
        return redirect(url_for("home"))

    # Save to session so Back button, reload, or navigation always remembers the search
    session["last_search"] = {
        "part": part,
        "part_key": part_key,
        "specialization": specialization,
        "disease": disease,
        "symptom": symptom,
        "age": age,
        "fees": fees,
        "location": location,
        "doctor_name": doctor_name,
        "feedback": feedback,
        "rating": rating,
        "language": language,
    }

    try:
        fees_value = float(fees) if fees else None
    except (ValueError, TypeError):
        fees_value = None

    # IMPROVED: Use SBERT-based doctor finding if feedback is provided and SBERT available
    # The regular Find Doctors form does not need the optional SBERT package.
    # Load it only when the user actually submits feedback for semantic matching.
    if feedback.strip():
        load_sbert_on_demand()
    sbert_module = _get_sbert_module() if feedback.strip() else None
    if feedback.strip() and sbert_module:
        try:
            print(f"[INFO] Using SBERT Smart Doctor Finding for feedback: {feedback[:50]}...")
            
            # Analyze feedback using SBERT
            feedback_analysis = sbert_module.analyze_feedback_with_language(feedback, target_language=language)
            
            # Find doctors using semantic matching
            results = sbert_module.find_best_doctors_for_feedback(
                DATA_DF,
                feedback_text=feedback,
                age=age,
                fees=fees_value,
                location=location,
                top_k=10
            )

            if part_key or part:
                resolved_part = part_key or part
                specialties = PART_TO_SPECIALIZATIONS.get(resolved_part, [resolved_part])
                part_pattern = "|".join([item for item in specialties if item])
                filtered = []
                for item in results:
                    specialization_text = str(item.get("specialization", ""))
                    department_text = str(item.get("department", ""))
                    body_part_text = str(item.get("body_part", ""))
                    if part_pattern and re.search(part_pattern, specialization_text, re.IGNORECASE):
                        filtered.append(item)
                        continue
                    if re.search(resolved_part, department_text, re.IGNORECASE):
                        filtered.append(item)
                        continue
                    if re.search(resolved_part, body_part_text, re.IGNORECASE):
                        filtered.append(item)
                        continue
                if filtered:
                    results = filtered

            if feedback.strip():
                review_row = _build_review_row(
                    feedback,
                    {
                        "disease": disease,
                        "symptom": symptom,
                        "fees": fees,
                        "location": location,
                        "language": language,
                        "rating": rating,
                    },
                    results,
                )
                _append_patient_review(review_row)
            
            # Add feedback analysis to results
            feedback_info = {
                'original': feedback,
                'detected_language': feedback_analysis['detected_language'] if feedback_analysis else 'Unknown',
                'sentiment': feedback_analysis['sentiment'] if feedback_analysis else 'Neutral',
                'sentiment_confidence': feedback_analysis['sentiment_confidence'] if feedback_analysis else 0,
                'complaint': feedback_analysis['complaint'] if feedback_analysis else 'General',
                'complaint_confidence': feedback_analysis['complaint_confidence'] if feedback_analysis else 0,
            }
            
            # If SBERT returned no results, compute filter diagnostics to explain why
            diagnostics = None
            if not results:
                search_part = part_key or part
                diagnostics = compute_filter_diagnostics(DATA_DF, search_part, disease, symptom, fees_value, location)
            supplemental_results = _build_supplemental_doctors(
                DATA_DF, part_key, disease, symptom, fees_value, location, results
            )
            results, supplemental_results, used_promoted_results = _promote_supplemental_results(
                results, supplemental_results
            )
            if len(results) < 10:
                seen_ids = {str(r.get("doctor_id")) for r in results if r.get("doctor_id")}
                more_docs = get_doctor_recommendations(
                    DATA_DF, search_part, age, None, None, disease, "", "", ""
                )
                for doc in more_docs:
                    did = str(doc.get("doctor_id"))
                    if did not in seen_ids:
                        seen_ids.add(did)
                        results.append(doc)
                        if len(results) >= 15:
                            break
            results = _sanitize_for_json(results[:15])
            stats = _result_stats(results)

            fee_range = _compute_fee_range(DATA_DF, part_key, disease, location)
            location_part_fee_range = _compute_fee_range_for_part_location(
                DATA_DF, part_key, location
            )
            fee_gap_hint = _fee_gap_hint(fees_value, location_part_fee_range)
            return render_template(
                "results.html",
                part=part.capitalize(),
                part_key=part_key,
                query={
                    "age": age,
                    "fees": fees,
                    "location": location,
                    "disease": disease,
                    "symptom": symptom,
                    "feedback": feedback,
                    "language": language,
                },
                fee_range=fee_range,
                location_part_fee_range=location_part_fee_range,
                fee_gap_hint=fee_gap_hint,
                results=results,
                map_doctors=_extract_map_doctors(results),
                supplemental_results=supplemental_results,
                result_stats=stats,
                feedback_analysis=feedback_info,
                diagnostics=diagnostics,
                used_promoted_results=used_promoted_results,
                using_sbert=True,
            )
        except Exception as e:
            print(f"[ERROR] SBERT Error: {e}, falling back to traditional search")

    # FALLBACK: Traditional doctor recommendation
    search_part = part_key or part
    results = get_doctor_recommendations(
        DATA_DF,
        search_part,
        age,
        fees_value,
        location,
        disease,
        symptom,
        "",
        doctor_name,
    )

    diagnostics = None
    if not results:
        diagnostics = compute_filter_diagnostics(DATA_DF, search_part, disease, symptom, fees_value, location)
    supplemental_results = _build_supplemental_doctors(
        DATA_DF, part_key, disease, symptom, fees_value, location, results
    )
    results, supplemental_results, used_promoted_results = _promote_supplemental_results(
        results, supplemental_results
    )
    if len(results) < 10:
        seen_ids = {str(r.get("doctor_id")) for r in results if r.get("doctor_id")}
        more_docs = get_doctor_recommendations(
            DATA_DF, search_part, age, None, None, disease, "", "", ""
        )
        for doc in more_docs:
            did = str(doc.get("doctor_id"))
            if did not in seen_ids:
                seen_ids.add(did)
                results.append(doc)
                if len(results) >= 15:
                    break
    results = results[:15]
    stats = _result_stats(results)

    if feedback.strip():
        review_row = _build_review_row(
            feedback,
            {
                "disease": disease,
                "symptom": symptom,
                "fees": fees,
                "location": location,
                "language": language,
                "rating": rating,
            },
            results,
        )
        _append_patient_review(review_row)
    
    fee_range = _compute_fee_range(DATA_DF, part_key, disease, location)
    location_part_fee_range = _compute_fee_range_for_part_location(
        DATA_DF, part_key, location
    )
    fee_gap_hint = _fee_gap_hint(fees_value, location_part_fee_range)
    return render_template(
        "results.html",
        part=part.capitalize(),
        part_key=part_key,
        query={
            "age": age,
            "fees": fees,
            "location": location,
            "disease": disease,
            "symptom": symptom,
        },
        fee_range=fee_range,
        location_part_fee_range=location_part_fee_range,
        fee_gap_hint=fee_gap_hint,
        results=_sanitize_for_json(results),
        map_doctors=_extract_map_doctors(results),
        supplemental_results=_sanitize_for_json(supplemental_results),
        result_stats=stats,
        diagnostics=diagnostics,
        used_promoted_results=used_promoted_results,
        using_sbert=False,
    )

def _translate_nested_value(value, target_lang, translator):
    if isinstance(value, str):
        try:
            translated = _resolve_maybe_awaitable(
                translator.translate(value, src='en', dest=target_lang)
            )
            return translated.text if hasattr(translated, 'text') else translated
        except Exception:
            return value

        return value

    if isinstance(value, list):
        return [_translate_nested_value(item, target_lang, translator) for item in value]

    if isinstance(value, tuple):
        return tuple(_translate_nested_value(item, target_lang, translator) for item in value)

    if isinstance(value, dict):
        return {
            key: _translate_nested_value(item, target_lang, translator)
            for key, item in value.items()
        }

    return value


def _resolve_maybe_awaitable(value):
    """Resolve sync/async return values from translator methods."""
    if not inspect.isawaitable(value):
        return value

    try:
        return asyncio.run(value)
    except RuntimeError:
        # Fallback when an event loop is already running.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(value)
        finally:
            loop.close()


def _extract_translation_text(translated):
    if translated is None:
        return None
    if hasattr(translated, "text"):
        return translated.text
    if isinstance(translated, str):
        return translated
    return str(translated)


def _translate_text_with_providers(text, source_lang, target_lang):
    """Translate a single text using available providers."""
    if not text or source_lang == target_lang:
        return text

    # Provider 1: deep-translator
    if TRANSLATOR_AVAILABLE and DeepGoogleTranslator is not None:
        try:
            translated_text = DeepGoogleTranslator(source=source_lang, target=target_lang).translate(text)
            if translated_text:
                return translated_text
        except Exception:
            pass

    return text


def _translate_list_with_providers(texts, source_lang, target_lang):
    if not isinstance(texts, list):
        return texts
    return [_translate_text_with_providers(text, source_lang, target_lang) for text in texts]


def _collect_translatable_strings(value, path=()):
    """Collect all non-empty strings with their paths from nested dict/list/tuple."""
    items = []

    if isinstance(value, str):
        if value.strip():
            items.append((path, value))
        return items

    if isinstance(value, list):
        for index, item in enumerate(value):
            items.extend(_collect_translatable_strings(item, path + (index,)))
        return items

    if isinstance(value, dict):
        for key, item in value.items():
            items.extend(_collect_translatable_strings(item, path + (key,)))
        return items

    return items


def _set_nested_value(container, path, new_value):
    """Set value inside nested dict/list path."""
    target = container
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = new_value


def _get_google_lang_code(language_code):
    return {
        'ta': 'ta',
        'hi': 'hi',
        'te': 'te',
        'kn': 'kn',
        'en': 'en',
    }.get(language_code, 'en')


def _fallback_localize_medical_text(text, target_lang):
    """Offline fallback for most common medical query sentence templates."""
    if not isinstance(text, str) or not text.strip() or target_lang == "en":
        return text
    cleaned_text = " ".join(text.strip().split())

    # Pattern-based templates with placeholder support
    patterns = [
        (
            r"^Based on your query, this looks related to (.+?)\.$",
            {
                "hi": "आपके प्रश्न के आधार पर, यह {x} से संबंधित लगता है।",
                "ta": "உங்கள் கேள்வியின் அடிப்படையில், இது {x} தொடர்பானதாக தெரிகிறது.",
                "te": "మీ ప్రశ్న ఆధారంగా, ఇది {x} సమస్యకు సంబంధించినట్లు కనిపిస్తోంది.",
                "kn": "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯ ಆಧಾರದ ಮೇಲೆ, ಇದು {x} ಸಮಸ್ಯೆಗೆ ಸಂಬಂಧಿಸಿದೆ ಎಂದು ಕಾಣುತ್ತದೆ.",
            },
        ),
        (
            r"^Combined dataset records for (.+?) often mention (.+?)\.$",
            {
                "hi": "संयुक्त डेटा रिकॉर्ड में {x} के लिए अक्सर {y} का उल्लेख मिलता है।",
                "ta": "{x} குறித்து ஒருங்கிணைந்த தரவு பதிவுகளில் பெரும்பாலும் {y} குறிப்பிடப்படுகிறது.",
                "te": "{x} కు సంబంధించిన కలిపిన డేటాసెట్ రికార్డుల్లో తరచుగా {y} కనిపిస్తాయి.",
                "kn": "{x} ಕುರಿತು ಸಂಯುಕ್ತ ಡೇಟಾಸೆಟ್ ದಾಖಲೆಗಳಲ್ಲಿ ಸಾಮಾನ್ಯವಾಗಿ {y} ಉಲ್ಲೇಖವಾಗುತ್ತದೆ.",
            },
        ),
    ]

    for pattern, templates in patterns:
        match = re.match(pattern, cleaned_text)
        if match and target_lang in templates:
            groups = match.groups()
            formatted = templates[target_lang]
            if len(groups) >= 1:
                formatted = formatted.replace("{x}", groups[0])
            if len(groups) >= 2:
                formatted = formatted.replace("{y}", groups[1])
            return formatted

    static_map = {
        "The exact cause can still vary based on age, severity, and other health conditions.": {
            "hi": "सटीक कारण उम्र, गंभीरता और अन्य स्वास्थ्य स्थितियों के आधार पर बदल सकता है।",
            "ta": "சரியான காரணம் வயது, தீவிரம் மற்றும் பிற உடல்நிலை காரணிகளால் மாறலாம்.",
            "te": "ఖచ్చితమైన కారణం వయస్సు, తీవ్రత మరియు ఇతర ఆరోగ్య పరిస్థితులపై ఆధారపడి మారవచ్చు.",
            "kn": "ನಿಖರ ಕಾರಣವು ವಯಸ್ಸು, ತೀವ್ರತೆ ಮತ್ತು ಇತರ ಆರೋಗ್ಯ ಸ್ಥಿತಿಗಳ ಆಧಾರದ ಮೇಲೆ ಬದಲಾಗಬಹುದು.",
        },
        "Use treatment only with doctor guidance for the exact diagnosis.": {
            "hi": "सटीक निदान के लिए केवल डॉक्टर की सलाह से ही उपचार लें।",
            "ta": "துல்லியமான நோயறிதலுக்காக மருத்துவரின் வழிகாட்டுதலுடன் மட்டுமே சிகிச்சை பெறுங்கள்.",
            "te": "ఖచ్చితమైన నిర్ధారణ కోసం వైద్యుల సూచనతో మాత్రమే చికిత్సను ఉపయోగించండి.",
            "kn": "ನಿಖರ ರೋಗನಿರ್ಣಯಕ್ಕಾಗಿ ವೈದ್ಯರ ಮಾರ್ಗದರ್ಶನದೊಂದಿಗೆ ಮಾತ್ರ ಚಿಕಿತ್ಸೆ ಪಡೆಯಿರಿ.",
        },
        "Dataset examples are for reference and not a personal prescription.": {
            "hi": "डेटासेट के उदाहरण केवल संदर्भ के लिए हैं, व्यक्तिगत पर्चे के लिए नहीं।",
            "ta": "தரவுத்தள உதாரணங்கள் குறிப்புக்காக மட்டும்; இது தனிப்பட்ட மருந்து பரிந்துரை அல்ல.",
            "te": "డేటాసెట్ ఉదాహరణలు సూచన కోసం మాత్రమే; వ్యక్తిగత ప్రిస్క్రిప్షన్ కావు.",
            "kn": "ಡೇಟಾಸೆಟ್ ಉದಾಹರಣೆಗಳು ಕೇವಲ ಸೂಚನೆಗಾಗಿ; ವೈಯಕ್ತಿಕ ಔಷಧ ಪತ್ರವಲ್ಲ.",
        },
        "Track symptom severity and duration.": {
            "hi": "लक्षणों की तीव्रता और अवधि को ट्रैक करें।",
            "ta": "அறிகுறிகளின் தீவிரமும் நீடிப்பு காலமும் கண்காணிக்கவும்.",
            "te": "లక్షణాల తీవ్రత మరియు వ్యవధిని గమనించండి.",
            "kn": "ಲಕ್ಷಣಗಳ ತೀವ್ರತೆ ಮತ್ತು ಅವಧಿಯನ್ನು ಗಮನಿಸಿ.",
        },
        "Seek medical review if symptoms are worsening or persistent.": {
            "hi": "यदि लक्षण बढ़ रहे हों या लगातार बने रहें तो डॉक्टर से जांच कराएँ।",
            "ta": "அறிகுறிகள் மோசமாவதோ அல்லது நீடிப்பதோ இருந்தால் மருத்துவரை அணுகவும்.",
            "te": "లక్షణాలు పెరుగుతున్నా లేదా కొనసాగుతున్నా వైద్య సమీక్ష పొందండి.",
            "kn": "ಲಕ್ಷಣಗಳು ಹೆಚ್ಚಾದರೆ ಅಥವಾ ಮುಂದುವರಿದರೆ ವೈದ್ಯಕೀಯ ಪರಿಶೀಲನೆ ಪಡೆಯಿರಿ.",
        },
        "General Physician": {
            "hi": "सामान्य चिकित्सक",
            "ta": "பொது மருத்துவர்",
            "te": "సాధారణ వైద్యుడు",
            "kn": "ಸಾಮಾನ್ಯ ವೈದ್ಯರು",
        },
        "Fever": {
            "hi": "बुखार",
            "ta": "காய்ச்சல்",
            "te": "జ్వరం",
            "kn": "ಜ್ವರ",
        },
    }

    if cleaned_text in static_map and target_lang in static_map[cleaned_text]:
        return static_map[cleaned_text][target_lang]

    return text


def _apply_local_fallback_on_nested(value, target_lang):
    if isinstance(value, str):
        return _fallback_localize_medical_text(value, target_lang)
    if isinstance(value, list):
        return [_apply_local_fallback_on_nested(item, target_lang) for item in value]
    if isinstance(value, tuple):
        return tuple(_apply_local_fallback_on_nested(item, target_lang) for item in value)
        return {k: _apply_local_fallback_on_nested(v, target_lang) for k, v in value.items()}
    return value


TRANSLATION_MEMO = {}
ONLINE_TRANSLATOR_UNAVAILABLE = False

OFFLINE_QUERY_MAP = {
    # Tamil
    "காய்ச்சல்": "fever",
    "தலைவலி": "headache",
    "மார்பு வலி": "chest pain",
    "நெஞ்சு வலி": "chest pain",
    "பல் வலி": "tooth pain",
    "வயிற்று வலி": "stomach pain",
    "வயிறு வலி": "stomach pain",
    "தோல்": "skin rash",
    "சளி": "common cold",
    "இருமல்": "cough",
    "மூச்சு": "asthma breathlessness",
    "நீரிழிவு": "diabetes",
    "சர்க்கரை": "diabetes",
    "சுகர்": "diabetes",
    "பிபி": "hypertension",
    "எலும்பு": "bone fracture arthritis",
    "மூட்டு வலி": "joint knee pain arthritis",
    "முழங்கால்": "knee pain",
    "முதுகு வலி": "back pain",
    "இடுப்பு வலி": "back pain",
    "கழுத்து வலி": "neck pain",
    "காது வலி": "ear pain",
    "காது": "ear pain",
    "தொண்டை வலி": "throat pain",
    "கண்": "eye cataract conjunctivitis",
    "வாந்தி": "vomiting nausea",
    "மயக்கம்": "dizziness fainting",
    "வயிற்றுப்போக்கு": "diarrhea loose motion",
    "வயிறு போக்கு": "diarrhea loose motion",
    "லூஸ் மோஷன்": "loose motion diarrhea",
    "மூல நோய்": "piles hemorrhoids",
    "பைல்ஸ்": "piles hemorrhoids",
    "குடலிறக்கம்": "hernia",
    "முடி உதிர்தல்": "hair fall dandruff",
    "அலர்ஜி": "allergy skin rash",
    "ஆஸ்துமா": "asthma breathlessness",
    "நெஞ்செரிச்சல்": "acid reflux acidity",
    "அசிடிட்டி": "acidity acid reflux",
    "டைபாய்டு": "typhoid fever",
    "டெங்கு": "dengue fever",
    "மலேரியா": "malaria fever",
    # Hindi
    "बुखार": "fever",
    "सिरदर्द": "headache",
    "सीने में दर्द": "chest pain",
    "दांत दर्द": "tooth pain",
    "पेट दर्द": "stomach pain",
    "त्वचा": "skin rash",
    "खांसी": "cough",
    "जुकाम": "common cold",
    "मधुमेह": "diabetes",
    "हड्डी": "bone arthritis",
    "आंख": "eye cataract",
    "उल्टी": "vomiting nausea",
    "दस्त": "diarrhea loose motion",
    "बवासीर": "piles hemorrhoids",
    # Telugu
    "జ్వరం": "fever",
    "తలనొప్పి": "headache",
    "ఛాతీ నొప్పి": "chest pain",
    "పంటి నొప్పి": "tooth pain",
    "కడుపు నొప్పి": "stomach pain",
    "దగ్గు": "cough",
    "మధుమేహం": "diabetes",
    # Kannada
    "ಜ್ವರ": "fever",
    "ತಲೆನೋವು": "headache",
    "ಎದೆ ನೋವು": "chest pain",
    "ಹಲ್ಲು ನೋವು": "tooth pain",
    "ಹೊಟ್ಟೆ ನೋವು": "stomach pain",
    "ಕೆಮ್ಮು": "cough",
    # Malayalam
    "പനി": "fever",
    "തലവേദന": "headache",
    "നെഞ്ചുവേദന": "chest pain",
    "പല്ലുവേദന": "tooth pain",
    "വയറുവേദന": "stomach pain",
    "ചുമ": "cough",
}


def translate_query_to_english(query_text, source_language):
    """Translate user query to English before NLP matching."""
    if not query_text:
        return query_text

    cleaned = str(query_text).strip().lower()
    for phrase, eng in OFFLINE_QUERY_MAP.items():
        if phrase in cleaned:
            return eng

    if source_language == 'en':
        return query_text

    source_lang = _get_google_lang_code(source_language)
    if source_lang == 'en':
        return query_text

    memo_key = (query_text, source_lang, 'en')
    if memo_key in TRANSLATION_MEMO:
        return TRANSLATION_MEMO[memo_key]

    global ONLINE_TRANSLATOR_UNAVAILABLE
    if not ONLINE_TRANSLATOR_UNAVAILABLE and TRANSLATOR_AVAILABLE and DeepGoogleTranslator is not None:
        try:
            translator = DeepGoogleTranslator(source=source_lang, target='en')
            translated = translator.translate(query_text)
            if translated and translated.strip():
                TRANSLATION_MEMO[memo_key] = translated
                return translated
        except Exception as e:
            print(f"[INFO] Online translation rate-limited or unavailable: {e}")
            ONLINE_TRANSLATOR_UNAVAILABLE = True

    return query_text


def _translate_text_deep(text, target_lang):
    """Translate text from English to the target language with memoization and fallback."""
    if not text or target_lang == 'en':
        return text

    localized = _fallback_localize_medical_text(text, target_lang)
    if localized and localized != text:
        return localized

    memo_key = (text, target_lang)
    if memo_key in TRANSLATION_MEMO:
        return TRANSLATION_MEMO[memo_key]

    global ONLINE_TRANSLATOR_UNAVAILABLE
    if not ONLINE_TRANSLATOR_UNAVAILABLE and TRANSLATOR_AVAILABLE and DeepGoogleTranslator is not None:
        try:
            translator = DeepGoogleTranslator(source='en', target=target_lang)
            translated = translator.translate(text)
            if translated and translated.strip():
                TRANSLATION_MEMO[memo_key] = translated
                return translated
        except Exception:
            ONLINE_TRANSLATOR_UNAVAILABLE = True

    return localized or text


def translate_answer_to_language(answer, target_language):
    """Translate the medical guidance answer to the target language."""
    if not answer or target_language == 'en':
        return answer

    target_lang = _get_google_lang_code(target_language)
    if target_lang == 'en':
        return answer

    try:
        def translate_recursive(obj, lang):
            if isinstance(obj, str):
                return _translate_text_deep(obj, lang)
            elif isinstance(obj, list):
                return [translate_recursive(item, lang) for item in obj]
            elif isinstance(obj, dict):
                return {k: translate_recursive(v, lang) for k, v in obj.items()}
            else:
                return obj

        translated = translate_recursive(answer, target_lang)
        return translated
    except Exception as e:
        print(f"[WARNING] Translation error: {e}, using local fallback")
        return _apply_local_fallback_on_nested(answer, target_lang)

@app.route("/query", methods=["GET", "POST"])
def query():
    answer = None
    user_query = ""
    # Prefer explicit form/URL language over cookie to avoid stale UI mismatch.
    cookie_lang = request.cookies.get("selected_language")
    form_lang = request.form.get("language")
    arg_lang = request.args.get("language")
    language = form_lang or arg_lang or cookie_lang or "en"
    supported_language_codes = {item.get("code") for item in SUPPORTED_LANGUAGES if isinstance(item, dict)}
    if language not in supported_language_codes:
        language = "en"
    
    if request.method == "POST":
        user_query = request.form.get("query", "").strip()
        processed_query = translate_query_to_english(user_query, language)
        try:
            print(f"[INFO] Query language: {language}, query: {user_query[:80]}")
        except Exception:
            pass
        answer = generate_medical_guidance(FAQ_DF, processed_query, DATA_DF)
        
        # Translate answer if language is not English
        if answer and language != 'en':
            answer = translate_answer_to_language(answer, language)
    
    response = make_response(
        render_template("query.html", answer=answer, user_query=user_query, selected_language=language)
    )
    response.set_cookie("selected_language", language, max_age=31536000, samesite="Lax", path="/")
    return response

@app.route("/api/voice_query", methods=["POST"])
def api_voice_query():
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "No audio file received"}), 400

    audio_file = request.files["audio"]
    target_lang = request.form.get("language", "en")

    sr_lang_map = {
        "ta": "ta-IN",
        "hi": "hi-IN",
        "te": "te-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "en": "en-IN",
    }
    lang_code = sr_lang_map.get(target_lang, "en-IN")

    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)

        query_text = recognizer.recognize_google(audio_data, language=lang_code)
        if not query_text or not query_text.strip():
            return jsonify({"success": False, "error": "No speech recognized. Please speak clearly."})

        return jsonify({
            "success": True,
            "query": query_text.strip()
        })
    except Exception as exc:
        if "UnknownValueError" in type(exc).__name__:
            return jsonify({"success": False, "error": "Could not understand audio. Please speak clearly into the microphone."})
        return jsonify({"success": False, "error": f"Speech processing notice: {exc}"})


# ==================== REST API ENDPOINTS (PROJECT REVIEW 2) ====================
# As defined in Section 4 "API Integration" of Project Review 2 architecture:
# /api/hospitals        GET     Get hospital information
# /api/doctors          GET     Get doctor information
# /api/reviews          GET     Retrieve reviews
# /api/reviews          POST    Create a review (protected, with NLP sentiment)
# /api/reviews/<id>     PUT     Update a review (protected)
# /api/reviews/<id>     DELETE  Delete a review (protected)

def _api_require_auth():
    """Verify session or auth credentials for protected API endpoints."""
    if session.get("logged_in"):
        return None, session.get("user_email") or session.get("user_name") or "authenticated_user"
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    if api_key:
        return None, "api_client"
    data = request.get_json(silent=True) or {}
    if data.get("user_email") or data.get("email"):
        return None, data.get("user_email") or data.get("email")
    return make_response(jsonify({
        "success": False,
        "error": "Authentication required. Please log in or provide user credentials."
    }), 401), None


def _extract_nlp_factors(text, rating):
    """
    Extract NLP insights for doctor behavior, treatment, explanation, waiting time.
    As required by Section 3 & Figure 2 of the Cloud Review 2 documentation.
    """
    lower = text.lower()
    return {
        "doctor_behaviour": "Positive" if any(w in lower for w in ["kind", "friendly", "caring", "good", "great", "nice", "polite", "respect"]) or rating >= 4 else "Negative" if any(w in lower for w in ["rude", "bad", "angry", "arrogant"]) else "Neutral",
        "treatment_experience": "Positive" if any(w in lower for w in ["effective", "cured", "helpful", "good", "smooth", "perfect", "satisfied"]) or rating >= 4 else "Negative" if any(w in lower for w in ["painful", "worst", "ineffective", "bad"]) else "Neutral",
        "explanation": "Positive" if any(w in lower for w in ["clear", "explained", "listened", "thorough", "detailed"]) else "Neutral",
        "waiting_time": "Negative" if any(w in lower for w in ["long", "delay", "waited", "slow", "hours"]) else "Positive" if any(w in lower for w in ["fast", "quick", "immediate", "on time"]) else "Moderate"
    }


@app.route("/api/hospitals", methods=["GET"])
def api_hospitals():
    """
    Get hospital information (REST API - GET).
    Query parameters:
      - city / location: Filter hospitals by district
      - search / q: Search keyword across hospital or specialization
      - limit: Number of results (default 50, max 200)
      - offset: Pagination offset (default 0)
    """
    city = request.args.get("city") or request.args.get("location")
    search = request.args.get("search") or request.args.get("q")
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 50, 0

    from db import get_hospitals_summary
    data = get_hospitals_summary(city=city, search=search, limit=limit, offset=offset)
    return jsonify({
        "success": True,
        "total": data["total"],
        "count": len(data["hospitals"]),
        "limit": limit,
        "offset": offset,
        "hospitals": data["hospitals"]
    }), 200


@app.route("/api/doctors", methods=["GET"])
def api_doctors():
    """
    Get doctor information (REST API - GET).
    Query parameters:
      - id: Specific doctor ID
      - city / location: Filter by district
      - hospital: Filter by hospital
      - specialization: Filter by specialization
      - department: Filter by department/disease
      - search / q: Search keyword across doctor name or hospital
      - limit: Number of results (default 20, max 100)
      - offset: Pagination offset (default 0)
    """
    doc_id = request.args.get("id")
    try:
        doc_id = int(doc_id) if doc_id else None
    except ValueError:
        return jsonify({"success": False, "error": "Invalid doctor ID format"}), 400

    city = request.args.get("city") or request.args.get("location")
    hospital = request.args.get("hospital")
    specialization = request.args.get("specialization")
    department = request.args.get("department")
    search = request.args.get("search") or request.args.get("q")

    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 20, 0

    from db import get_doctors_api_list
    data = get_doctors_api_list(
        doctor_id=doc_id,
        city=city,
        hospital=hospital,
        specialization=specialization,
        department=department,
        search=search,
        limit=limit,
        offset=offset
    )

    if doc_id and not data["doctors"]:
        return jsonify({"success": False, "error": f"Doctor with id {doc_id} not found"}), 404

    return jsonify({
        "success": True,
        "total": data["total"],
        "count": len(data["doctors"]),
        "limit": limit,
        "offset": offset,
        "doctors": data["doctors"]
    }), 200


@app.route("/api/reviews", methods=["GET"])
def api_get_reviews():
    """
    Retrieve reviews (REST API - GET).
    Query parameters:
      - id: Specific review ID
      - doctor_id: Filter by doctor ID
      - doctor_name: Filter by doctor name
      - hospital: Filter by hospital
      - limit: Number of reviews (default 50)
    """
    rev_id = request.args.get("id")
    doc_id = request.args.get("doctor_id")
    doc_name = request.args.get("doctor_name")
    hospital = request.args.get("hospital")

    from db import get_connection
    con = get_connection()
    cur = con.cursor()

    where_clauses = ["1=1"]
    params = []
    if rev_id:
        try:
            where_clauses.append("id = %s")
            params.append(int(rev_id))
        except ValueError:
            con.close()
            return jsonify({"success": False, "error": "Invalid review ID format"}), 400
    if doc_id:
        try:
            where_clauses.append("doctor_id = %s")
            params.append(int(doc_id))
        except ValueError:
            pass
    if doc_name:
        where_clauses.append("doctor_name ILIKE %s")
        params.append(f"%{doc_name.strip()}%")
    if hospital:
        where_clauses.append("hospital ILIKE %s")
        params.append(f"%{hospital.strip()}%")

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50

    sql = f'''
        SELECT 
            id,
            doctor_id,
            doctor_name,
            hospital,
            specialization,
            department,
            location,
            patient_rating,
            new_feedback,
            sentiment_label,
            submitted_at
        FROM "patient_reviews"
        WHERE {" AND ".join(where_clauses)}
        ORDER BY id DESC
        LIMIT %s;
    '''
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()

    reviews = []
    for r in rows:
        reviews.append({
            "id": r[0],
            "doctor_id": r[1],
            "doctor_name": r[2],
            "hospital": r[3],
            "specialization": r[4],
            "department": r[5],
            "location": r[6],
            "patient_rating": r[7],
            "review_text": r[8],
            "sentiment_label": r[9],
            "submitted_at": r[10]
        })

    return jsonify({
        "success": True,
        "count": len(reviews),
        "reviews": reviews
    }), 200


@app.route("/api/reviews", methods=["POST"])
def api_create_review():
    """
    Create a review (REST API - POST).
    Protected endpoint: Requires authentication.
    JSON payload:
      - doctor_name (str, required)
      - review_text (str, required)
      - rating (int 1-5, required)
      - hospital (str, optional)
      - doctor_id (int, optional)
      - specialization (str, optional)
      - location (str, optional)
    """
    auth_err, user_identity = _api_require_auth()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400

    doctor_name = (data.get("doctor_name") or "").strip()
    hospital = (data.get("hospital") or "").strip()
    review_text = (data.get("review_text") or data.get("new_feedback") or data.get("feedback") or "").strip()
    raw_rating = data.get("rating") or data.get("patient_rating")

    if not doctor_name:
        return jsonify({"success": False, "error": "'doctor_name' is required"}), 400
    if not review_text:
        return jsonify({"success": False, "error": "'review_text' cannot be empty"}), 400

    try:
        rating = int(raw_rating)
        if not (1 <= rating <= 5):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "'rating' must be an integer between 1 and 5"}), 400

    # NLP Sentiment & Feature Extraction
    from model import predict_sentiment
    sentiment_label = predict_sentiment(review_text)
    nlp_factors = _extract_nlp_factors(review_text, rating)

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    doctor_id = data.get("doctor_id") or 0

    review_record = {
        "submitted_at": now_iso,
        "new_feedback": review_text,
        "patient_rating": rating,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "hospital": hospital,
        "specialization": data.get("specialization") or "",
        "department": data.get("department") or "",
        "location": data.get("location") or "",
        "consultation_fee": data.get("consultation_fee") or 500,
        "experience_years": data.get("experience_years") or 10,
        "average_rating": rating,
        "sentiment_label": sentiment_label,
        "complaint_category": data.get("complaint_category") or "General",
        "feedback": rating,
        "query_disease": 1.0,
        "query_symptom": 1.0,
        "query_fees": 1.0,
        "query_location": 1.0,
        "query_language": 1.0,
        "recommendation_score": round(rating / 5.0, 2),
    }

    from db import save_patient_review
    new_id = save_patient_review(review_record)
    if not new_id:
        return jsonify({"success": False, "error": "Database error while saving review"}), 500

    # Sync with Excel fallback
    try:
        _append_patient_review(review_record, sync_postgres=False)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "message": "Review created successfully",
        "review": {
            "id": new_id,
            "doctor_name": doctor_name,
            "hospital": hospital,
            "patient_rating": rating,
            "review_text": review_text,
            "sentiment_label": sentiment_label,
            "nlp_analysis": nlp_factors,
            "submitted_by": user_identity,
            "submitted_at": now_iso
        }
    }), 201


@app.route("/api/reviews/<int:review_id>", methods=["GET"])
def api_get_review_by_id(review_id):
    """
    Get a single review by ID (REST API - GET).
    """
    from db import get_review_by_id
    existing = get_review_by_id(review_id)
    if not existing:
        return jsonify({"success": False, "error": f"Review with id {review_id} not found"}), 404
    return jsonify({
        "success": True,
        "review": existing
    }), 200


@app.route("/api/reviews/<int:review_id>", methods=["PUT"])
def api_update_review(review_id):
    """
    Update a review (REST API - PUT).
    Protected endpoint: Requires authentication.
    JSON payload:
      - rating: (int 1-5, optional)
      - review_text: (str, optional)
    """
    auth_err, user_identity = _api_require_auth()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400

    from db import get_review_by_id, update_patient_review
    existing = get_review_by_id(review_id)
    if not existing:
        return jsonify({"success": False, "error": f"Review with id {review_id} not found"}), 404

    update_fields = {}
    if "rating" in data or "patient_rating" in data:
        try:
            r = int(data.get("rating") or data.get("patient_rating"))
            if not (1 <= r <= 5):
                raise ValueError()
            update_fields["patient_rating"] = r
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "'rating' must be an integer between 1 and 5"}), 400

    if "review_text" in data or "new_feedback" in data:
        text = str(data.get("review_text") or data.get("new_feedback")).strip()
        if not text:
            return jsonify({"success": False, "error": "'review_text' cannot be empty"}), 400
        update_fields["new_feedback"] = text
        from model import predict_sentiment
        update_fields["sentiment_label"] = predict_sentiment(text)

    if not update_fields:
        return jsonify({"success": False, "error": "No valid fields (rating, review_text) provided to update"}), 400

    success = update_patient_review(review_id, update_fields)
    if not success:
        return jsonify({"success": False, "error": "Database error while updating review"}), 500

    updated = get_review_by_id(review_id)
    return jsonify({
        "success": True,
        "message": f"Review #{review_id} updated successfully",
        "review": {
            "id": review_id,
            "doctor_name": updated.get("doctor_name"),
            "hospital": updated.get("hospital"),
            "patient_rating": updated.get("patient_rating"),
            "review_text": updated.get("new_feedback"),
            "sentiment_label": updated.get("sentiment_label"),
            "submitted_at": updated.get("submitted_at")
        }
    }), 200


@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def api_delete_review(review_id):
    """
    Delete a review (REST API - DELETE).
    Protected endpoint: Requires authentication.
    """
    auth_err, user_identity = _api_require_auth()
    if auth_err:
        return auth_err

    from db import get_review_by_id, delete_patient_review
    existing = get_review_by_id(review_id)
    if not existing:
        return jsonify({"success": False, "error": f"Review with id {review_id} not found"}), 404

    success = delete_patient_review(review_id)
    if not success:
        return jsonify({"success": False, "error": "Database error while deleting review"}), 500

    return jsonify({
        "success": True,
        "message": f"Review #{review_id} deleted successfully"
    }), 200


@app.route("/doctor/<int:doctor_id>")
def doctor_detail(doctor_id):
    guard = _require_login()
    if guard:
        return guard
    doctor = get_doctor_details(DATA_DF, doctor_id)
    if doctor is None:
        return render_template("404.html"), 404

    # Ensure doctor login email is available for testing and display
    raw_email = str(doctor.get("email") or "").strip()
    if not raw_email or raw_email.lower() in ("nan", "none", "null"):
        doctor["email"] = None
        try:
            from db import get_doctor_by_identifier
            rec = get_doctor_by_identifier(doctor.get("doctor_name")) or get_doctor_by_identifier(doctor_id)
            if rec and rec.get("email") and str(rec.get("email")).strip().lower() not in ("nan", "none", "null"):
                doctor["email"] = str(rec["email"]).strip()
        except Exception:
            pass
    if not doctor.get("email") or str(doctor.get("email")).strip().lower() in ("nan", "none", "null"):
        clean_name = re.sub(r"[^a-zA-Z0-9]", "", str(doctor.get("doctor_name", "")).lower())
        if not clean_name.startswith("dr") and clean_name:
            clean_name = "dr" + clean_name
        doctor["email"] = f"{clean_name}@hospital.com" if clean_name else "doctor@hospital.com"

    latest_review = _load_latest_patient_review(doctor.get("doctor_name"))
    review_success = request.args.get("review_success", "")
    review_error = request.args.get("review_error", "")

    today_dt = datetime.now()
    default_date = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    min_date = today_dt.strftime("%Y-%m-%d")

    last_search = session.get("last_search", {})
    prefill_disease = request.args.get("disease") or last_search.get("disease") or doctor.get("department") or "General Health Consultation"
    prefill_symptoms = request.args.get("symptoms") or last_search.get("symptom") or doctor.get("symptom_text") or ""

    return render_template(
        "doctor_detail.html",
        doctor=doctor,
        latest_review=latest_review,
        review_success=review_success,
        review_error=review_error,
        default_date=default_date,
        min_date=min_date,
        prefill_disease=prefill_disease,
        prefill_symptoms=prefill_symptoms,
    )


@app.route("/doctor/<int:doctor_id>/review", methods=["POST"])
def submit_doctor_review(doctor_id):
    guard = _require_login()
    if guard:
        return guard
    doctor = get_doctor_details(DATA_DF, doctor_id)
    if doctor is None:
        return render_template("404.html"), 404

    feedback = request.form.get("feedback", "").strip()
    rating = request.form.get("rating", "").strip()
    if feedback:
        review_row = {
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
            "new_feedback": feedback,
            "patient_rating": rating,
            "doctor_id": doctor.get("doctor_id", ""),
            "doctor_name": doctor.get("doctor_name", ""),
            "hospital": doctor.get("hospital", ""),
            "specialization": doctor.get("specialization", ""),
            "department": doctor.get("department", ""),
            "location": doctor.get("location", ""),
            "consultation_fee": doctor.get("consultation_fee", ""),
            "experience_years": doctor.get("experience_years", ""),
            "average_rating": doctor.get("average_rating", ""),
            "sentiment_label": doctor.get("sentiment_label", ""),
            "complaint_category": doctor.get("complaint_category", ""),
        }
        save_error = _append_patient_review(review_row)
        if save_error:
            return redirect(url_for("doctor_detail", doctor_id=doctor_id, review_error=save_error))
        return redirect(url_for("doctor_detail", doctor_id=doctor_id, review_success="Feedback added successfully."))

    return redirect(url_for("doctor_detail", doctor_id=doctor_id, review_error="Feedback is required."))

@app.route("/map", methods=["GET"])
def map_view():
    guard = _require_login()
    if guard:
        return guard
    location = request.args.get("location", "").strip()
    hospital = request.args.get("hospital", "").strip()
    doctor_id = request.args.get("id", "").strip()
    doctor_name = request.args.get("doctor", "").strip()

    if location:
        map_data = get_map_data(DATA_DF, location)
    else:
        map_data = get_map_data(DATA_DF, None)

    return render_template(
        "map.html",
        locations=LOCATIONS,
        selected_location=location,
        selected_hospital=hospital,
        selected_doctor_id=doctor_id,
        selected_doctor_name=doctor_name,
        map_data=map_data,
    )

@app.route("/map-search", methods=["GET", "POST"])
def map_search():
    guard = _require_login()
    if guard:
        return guard
    location = (request.form.get("location") or request.args.get("location") or "").strip()
    map_data = get_map_data(DATA_DF, location if location else None)
    return render_template(
        "map.html",
        locations=LOCATIONS,
        selected_location=location,
        map_data=map_data,
    )


# ==================== DOCTOR ONBOARDING & REGISTRATION ====================

@app.route("/doctor/register", methods=["GET", "POST"])
def doctor_register():
    if request.method == "GET":
        return render_template("doctor_register.html")

    doc_name = request.form.get("doctor_name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    qualifications = request.form.get("qualifications", "MBBS, MD").strip()
    hospital = request.form.get("hospital", "").strip()
    department = request.form.get("department", specialization).strip()
    location = request.form.get("location", "Chennai").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    experience = int(request.form.get("experience_years", 5) or 5)
    fee = int(request.form.get("consultation_fee", 500) or 500)
    bio = request.form.get("bio", "").strip()

    if not all([doc_name, specialization, hospital, email, password]):
        return render_template("doctor_register.html", error="Please fill all required fields.")

    from db import get_doctor_by_email, create_new_doctor, log_audit_action
    existing = get_doctor_by_email(email)
    if existing:
        return render_template("doctor_register.html", error="A doctor with this email is already registered.")

    new_id = create_new_doctor({
        "doctor_name": doc_name,
        "specialization": specialization,
        "hospital": hospital,
        "department": department,
        "location": location,
        "email": email,
        "password": password,
        "experience_years": experience,
        "consultation_fee": fee,
        "qualifications": qualifications,
        "bio": bio
    })

    if not new_id:
        return render_template("doctor_register.html", error="Database error while registering doctor.")

    log_audit_action(email, "doctor", "Doctor Registration", f"New doctor registered: {doc_name} ({specialization})")

    session["logged_in"] = True
    session["user_role"] = "doctor"
    session["user_email"] = email
    session["user_name"] = doc_name
    session["doctor_id"] = new_id
    session["unread_notifs"] = 0
    return redirect(url_for("doctor_dashboard"))


# ==================== APPOINTMENT BOOKING & LETTERS ====================

@app.route("/appointment/book", methods=["POST"])
@app.route("/book_appointment", methods=["POST"])
def book_appointment():
    guard = _require_login()
    if guard:
        return guard

    from db import create_appointment, create_notification, log_audit_action

    user_email = session.get("user_email", "")
    user_name = session.get("user_name", "Patient")

    # Fetch patient profile if available for age/gender
    patient_age = 30
    patient_gender = "Not specified"
    patient_phone = ""
    try:
        from db import get_connection
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT age, country FROM "patients" WHERE LOWER(email) = LOWER(%s);', [user_email])
        p_row = cur.fetchone()
        con.close()
        if p_row and p_row[0]:
            patient_age = int(p_row[0])
    except Exception:
        pass

    submitted_doc_name = request.form.get("doctor_name", "").strip()
    submitted_doc_email = request.form.get("doctor_email", "").strip()
    true_doc_id = None
    try:
        from db import get_connection
        con = get_connection()
        cur = con.cursor()
        cur.execute('SELECT id, email FROM "doctors" WHERE LOWER(doctor) = LOWER(%s) LIMIT 1;', [submitted_doc_name])
        r = cur.fetchone()
        con.close()
        if r and r[0]:
            true_doc_id = r[0]
            if not submitted_doc_email and r[1]:
                submitted_doc_email = r[1]
    except Exception:
        pass
    if not true_doc_id:
        true_doc_id = int(request.form.get("doctor_id", 0) or 0)

    if not submitted_doc_email and true_doc_id:
        doc_info = get_doctor_details(DATA_DF, true_doc_id)
        if doc_info and doc_info.get("email"):
            submitted_doc_email = str(doc_info["email"]).strip()
        elif doc_info and doc_info.get("doctor_name"):
            clean = re.sub(r"[^a-zA-Z0-9]", "", str(doc_info["doctor_name"]).lower())
            if not clean.startswith("dr") and clean:
                clean = "dr" + clean
            submitted_doc_email = f"{clean}@hospital.com"

    if not submitted_doc_email and submitted_doc_name:
        clean = re.sub(r"[^a-zA-Z0-9]", "", str(submitted_doc_name).lower())
        if not clean.startswith("dr") and clean:
            clean = "dr" + clean
        submitted_doc_email = f"{clean}@hospital.com"

    data = {
        "patient_email": user_email,
        "patient_name": user_name,
        "patient_phone": request.form.get("phone", patient_phone),
        "patient_age": patient_age,
        "patient_gender": patient_gender,
        "doctor_id": true_doc_id,
        "doctor_name": submitted_doc_name,
        "doctor_email": submitted_doc_email,
        "hospital": request.form.get("hospital", "").strip(),
        "specialization": request.form.get("specialization", "").strip(),
        "appointment_date": request.form.get("appointment_date"),
        "appointment_time": request.form.get("appointment_time", "10:00 AM"),
        "disease": request.form.get("disease", "").strip(),
        "symptoms": request.form.get("symptoms", "").strip(),
        "notes": request.form.get("notes", "").strip()
    }

    apt_id, apt_ref = create_appointment(data)
    if not apt_id:
        print(f"[BOOK-WARN] Initial create_appointment returned None, retrying with ensure_postgres_running...")
        try:
            from db import ensure_postgres_running
            ensure_postgres_running()
            apt_id, apt_ref = create_appointment(data)
        except Exception as retry_exc:
            print(f"[BOOK-ERROR] Retry create_appointment failed: {retry_exc}")

    if not apt_id:
        return redirect(url_for("my_appointments", error="Unable to generate appointment slip right now. Please try again."))

    # Notify patient
    create_notification(
        user_email, "patient",
        "Appointment Requested",
        f"Your appointment request ({apt_ref}) for Dr. {data['doctor_name']} has been submitted. Status: Pending Confirmation.",
        "appointment_requested", apt_id
    )

    # Log audit event
    log_audit_action(user_email, "patient", "Book Appointment", f"Appointment {apt_ref} requested for Dr. {data['doctor_name']}")

    session["just_booked_appointment_id"] = apt_id
    return redirect(url_for("view_appointment_letter", apt_id=apt_id))


@app.route("/appointment/<int:apt_id>/letter")
def view_appointment_letter(apt_id):
    guard = _require_login()
    if guard:
        return guard

    from db import get_appointment_by_id
    apt = get_appointment_by_id(apt_id)
    if not apt:
        return render_template("404.html"), 404

    # Allow viewing if: admin, assigned doctor, booking patient, or user who just booked in this session
    curr_email = (session.get("user_email") or "").lower()
    curr_role = session.get("user_role")
    just_booked = (session.get("just_booked_appointment_id") == apt_id)
    if not just_booked and curr_role != "admin" and curr_email != str(apt.get("patient_email", "")).lower() and curr_role != "doctor":
        return redirect(url_for("home"))

    return render_template("appointment_letter.html", appointment=apt)


@app.route("/my-appointments")
def my_appointments():
    guard = _require_login()
    if guard:
        return guard

    from db import get_patient_appointments
    apts = get_patient_appointments(session.get("user_email", ""))
    msg = request.args.get("message", "")
    return render_template("my_appointments.html", appointments=apts, message=msg)


@app.route("/appointment/<int:apt_id>/delete", methods=["GET", "POST"])
def delete_appointment(apt_id):
    guard = _require_login()
    if guard:
        return guard

    from db import delete_appointment_by_id, log_audit_action
    user_email = session.get("user_email", "")
    user_role = session.get("user_role", "")

    success = delete_appointment_by_id(apt_id, user_email=user_email, user_role=user_role)
    if success:
        log_audit_action(user_email, user_role, "Delete Appointment", f"Cancelled and deleted appointment #{apt_id}")
        msg = "Appointment deleted successfully."
    else:
        msg = "Unable to delete appointment or permission denied."

    referer = request.headers.get("Referer", "")
    if "patient/dashboard" in referer:
        return redirect(url_for("healthcare.patient_dashboard", success=msg if success else None, error=None if success else msg))
    elif "my-appointments" in referer:
        return redirect(url_for("my_appointments", message=msg))
    elif "doctor" in referer:
        return redirect(url_for("doctor_dashboard", success=msg if success else None, error=None if success else msg))

    if user_role == "patient":
        return redirect(url_for("healthcare.patient_dashboard", success=msg if success else None, error=None if success else msg))
    return redirect(url_for("my_appointments", message=msg))


@app.route("/appointments/bulk-delete", methods=["POST"])
def bulk_delete_appointments():
    guard = _require_login()
    if guard:
        return guard

    from db import delete_multiple_appointments, delete_all_patient_appointments, log_audit_action
    user_email = session.get("user_email", "")
    user_role = session.get("user_role", "")
    action = request.form.get("action", "selected").strip()

    if action == "all":
        count = delete_all_patient_appointments(user_email)
        if count > 0:
            log_audit_action(user_email, user_role, "Bulk Delete", f"Deleted all {count} appointment(s)")
            msg = f"All {count} appointment(s) deleted successfully."
        else:
            msg = "No appointments found to delete."
    else:
        apt_ids = request.form.getlist("appointment_ids")
        if not apt_ids:
            raw_ids = request.form.get("appointment_ids_str", "")
            if raw_ids:
                apt_ids = [x.strip() for x in raw_ids.split(",") if x.strip()]

        if not apt_ids:
            referer = request.headers.get("Referer", "")
            if "my-appointments" in referer:
                return redirect(url_for("my_appointments", message="No appointments were selected for deletion."))
            return redirect(url_for("healthcare.patient_dashboard", error="No appointments were selected for deletion."))

        count = delete_multiple_appointments(apt_ids, user_email=user_email, user_role=user_role)
        if count > 0:
            log_audit_action(user_email, user_role, "Bulk Delete", f"Deleted {count} selected appointment(s)")
            msg = f"{count} selected appointment(s) deleted successfully."
        else:
            msg = "Could not delete selected appointments or already removed."

    referer = request.headers.get("Referer", "")
    if "my-appointments" in referer:
        return redirect(url_for("my_appointments", message=msg))
    return redirect(url_for("healthcare.patient_dashboard", success=msg))


@app.route("/test/switch-doctor", methods=["POST"])
def test_switch_doctor():
    guard = _require_login()
    if guard:
        return guard

    doc_id = request.form.get("doctor_id")
    doc_name = request.form.get("doctor_name", "").strip()
    doc_email = request.form.get("doctor_email", "").strip()

    from db import get_doctor_by_identifier, log_audit_action, get_unread_notification_count

    doctor_rec = None
    if doc_email:
        doctor_rec = get_doctor_by_identifier(doc_email)
    if not doctor_rec and doc_name:
        doctor_rec = get_doctor_by_identifier(doc_name)
    if not doctor_rec and doc_id:
        doctor_rec = get_doctor_by_identifier(doc_id)

    if not doctor_rec:
        try:
            d_info = get_doctor_details(DATA_DF, int(doc_id or 0)) if doc_id else None
            if d_info:
                clean_n = re.sub(r"[^a-zA-Z0-9]", "", str(d_info.get("doctor_name", "")).lower())
                if not clean_n.startswith("dr") and clean_n:
                    clean_n = "dr" + clean_n
                active_email = doc_email or d_info.get("email") or f"{clean_n}@hospital.com"
                doctor_rec = {
                    "id": d_info.get("doctor_id") or doc_id,
                    "doctor": d_info.get("doctor_name") or doc_name or "Doctor",
                    "email": active_email
                }
        except Exception:
            pass

    if not doctor_rec and (doc_name or doc_email):
        clean_n = re.sub(r"[^a-zA-Z0-9]", "", str(doc_name or "").lower())
        if not clean_n.startswith("dr") and clean_n:
            clean_n = "dr" + clean_n
        active_email = doc_email or f"{clean_n}@hospital.com"
        doctor_rec = {
            "id": doc_id or 0,
            "doctor": doc_name or "Doctor",
            "email": active_email
        }

    if not doctor_rec:
        return redirect(url_for("my_appointments", message=f"Could not resolve doctor account for {doc_name or doc_id}."))

    active_email = doctor_rec.get("email") or f"doctor{doctor_rec.get('id')}@hospital.com"
    session.permanent = True
    session["logged_in"] = True
    session["user_role"] = "doctor"
    session["user_email"] = active_email
    session["user_name"] = doctor_rec.get("doctor") or "Doctor"
    session["doctor_id"] = doctor_rec.get("id")
    session["doctor_verified"] = True
    session["verification_status"] = "Approved"
    try:
        session["unread_notifs"] = get_unread_notification_count(active_email)
        log_audit_action(active_email, "doctor", "Test Doctor Switch", f"Tester switched to Dr. {session['user_name']} to review appointments")
    except Exception:
        session["unread_notifs"] = 0

    clean_display = str(session['user_name'])
    if not clean_display.lower().startswith("dr"):
        clean_display = f"Dr. {clean_display}"
    return redirect(url_for("doctor_dashboard", success=f"Logged in as {clean_display}! You can now review and approve pending appointments."))



@app.route("/appointment/<int:apt_id>/feedback", methods=["GET", "POST"])
def appointment_feedback(apt_id):
    guard = _require_login()
    if guard:
        return guard

    from db import get_appointment_by_id, save_patient_review, update_appointment_status, create_notification, log_audit_action
    from model import predict_sentiment

    apt = get_appointment_by_id(apt_id)
    if not apt:
        return render_template("404.html"), 404

    if request.method == "GET":
        return render_template("appointment_feedback.html", appointment=apt)

    feedback_text = request.form.get("feedback", "").strip()
    try:
        rating = int(request.form.get("rating", 5))
    except (ValueError, TypeError):
        rating = 5

    sentiment_label = predict_sentiment(feedback_text)
    user_email = session.get("user_email", "patient@example.com")

    # Save to PostgreSQL patient_reviews (with patient_email for Admin, but masked for Doctor)
    review_record = {
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "new_feedback": feedback_text,
        "patient_rating": rating,
        "doctor_id": apt.get("doctor_id") or 0,
        "doctor_name": apt.get("doctor_name", ""),
        "hospital": apt.get("hospital", ""),
        "specialization": apt.get("specialization", ""),
        "department": apt.get("disease", ""),
        "location": "Tamil Nadu",
        "consultation_fee": 500,
        "experience_years": 10,
        "average_rating": rating,
        "sentiment_label": sentiment_label,
        "complaint_category": apt.get("disease", "General"),
        "patient_email": user_email,
        "appointment_id": apt_id
    }
    save_patient_review(review_record)

    # Mark appointment feedback as completed
    try:
        from db import get_connection
        con = get_connection()
        cur = con.cursor()
        cur.execute("UPDATE appointments SET has_feedback = TRUE WHERE id = %s;", [apt_id])
        con.commit()
        con.close()
    except Exception:
        pass

    # Audit log
    log_audit_action(user_email, "patient", "Submit Review", f"Review for Dr. {apt.get('doctor_name')} (Sentiment: {sentiment_label})")

    return redirect(url_for("my_appointments", message="Thank you! Your consultation feedback has been submitted successfully."))


# ==================== NOTIFICATIONS ====================

@app.route("/notifications")
def notifications_view():
    guard = _require_login()
    if guard:
        return guard

    from db import get_user_notifications, get_unread_notification_count
    user_email = session.get("user_email", "")
    notifs = get_user_notifications(user_email)
    unread = get_unread_notification_count(user_email)
    session["unread_notifs"] = unread
    return render_template("notifications.html", notifications=notifs, unread_count=unread)


@app.route("/notifications/mark-read", methods=["POST"])
def notifications_mark_read():
    guard = _require_login()
    if guard:
        return guard

    from db import mark_notifications_read
    user_email = session.get("user_email", "")
    mark_notifications_read(user_email)
    session["unread_notifs"] = 0
    return redirect(url_for("notifications_view"))


@app.route("/notification/<int:notif_id>/delete", methods=["GET", "POST"])
def notification_delete(notif_id):
    guard = _require_login()
    if guard:
        return guard

    from db import delete_notification_by_id, get_unread_notification_count, log_audit_action
    user_email = session.get("user_email", "")
    user_role = session.get("user_role", "patient")

    success = delete_notification_by_id(notif_id, user_email)
    try:
        session["unread_notifs"] = get_unread_notification_count(user_email)
    except Exception:
        pass

    if success:
        try:
            log_audit_action(user_email, user_role, "Delete Notification", f"Deleted notification #{notif_id}")
        except Exception:
            pass

    referer = request.headers.get("Referer")
    if referer and "/notifications" in referer:
        return redirect(referer)
    return redirect(url_for("notifications_view"))


@app.route("/notifications/bulk-delete", methods=["POST"])
def notifications_bulk_delete():
    guard = _require_login()
    if guard:
        return guard

    from db import delete_multiple_notifications, delete_all_user_notifications, get_unread_notification_count, log_audit_action
    user_email = session.get("user_email", "")
    user_role = session.get("user_role", "patient")
    action = request.form.get("action", "selected")

    if action == "all":
        count = delete_all_user_notifications(user_email)
        msg = f"All {count} notification(s) deleted successfully."
    else:
        notif_ids = request.form.getlist("notif_ids")
        if not notif_ids:
            return redirect(url_for("notifications_view", error="No notifications selected to delete."))
        count = delete_multiple_notifications(notif_ids, user_email)
        msg = f"{count} selected notification(s) deleted successfully."

    try:
        session["unread_notifs"] = get_unread_notification_count(user_email)
        log_audit_action(user_email, user_role, "Bulk Delete Notifications", f"Deleted {count} notifications (action={action})")
    except Exception:
        pass

    return redirect(url_for("notifications_view", success=msg))



# ==================== DOCTOR DASHBOARD & PORTAL ====================

@app.route("/doctor/dashboard")
def doctor_dashboard():
    guard = _require_doctor()
    if guard:
        return guard

    from db import (
        get_doctor_by_email, get_doctor_appointments,
        get_doctor_dashboard_metrics, get_doctor_reviews_anonymized
    )

    user_email = session.get("user_email", "")
    doctor = get_doctor_by_email(user_email)
    if not doctor:
        # Fallback to session info
        doctor = {
            "doctor": session.get("user_name", "Doctor"),
            "specialization": "Specialist",
            "hospital": "Care Center",
            "id": session.get("doctor_id", 0)
        }

    doc_name = doctor.get("doctor", "")
    all_apts = get_doctor_appointments(doctor_name=doc_name)
    pending_apts = [a for a in all_apts if a.get("status") == "Pending"]
    approved_apts = [a for a in all_apts if a.get("status") == "Approved"]
    completed_apts = [a for a in all_apts if a.get("status") == "Completed"]

    metrics = get_doctor_dashboard_metrics(doc_name, doctor.get("id"))

    # STRICT PRIVACY: Fetch reviews where patient identity is masked
    reviews = get_doctor_reviews_anonymized(doc_name)

    success_msg = request.args.get("success", "")
    error_msg = request.args.get("error", "")

    return render_template(
        "doctor_dashboard.html",
        doctor=doctor,
        metrics=metrics,
        pending_appointments=pending_apts,
        approved_appointments=approved_apts,
        completed_appointments=completed_apts,
        reviews=reviews,
        success_msg=success_msg,
        error_msg=error_msg
    )


@app.route("/doctor/appointment/<int:apt_id>/action", methods=["POST"])
def doctor_appointment_action(apt_id):
    guard = _require_doctor()
    if guard:
        return guard

    from db import get_appointment_by_id, update_appointment_status, create_notification, log_audit_action

    action = request.form.get("action", "").strip()
    apt = get_appointment_by_id(apt_id)
    if not apt:
        return redirect(url_for("doctor_dashboard", error="Appointment not found"))

    patient_email = apt.get("patient_email")
    doc_name = session.get("user_name", "Doctor")

    if action == "approve":
        update_appointment_status(apt_id, "Approved")
        create_notification(
            patient_email, "patient",
            f"Appointment Approved by Dr. {doc_name}",
            f"Your consultation with Dr. {doc_name} on {apt.get('appointment_date')} at {apt.get('appointment_time')} has been approved.",
            "appointment_approved", apt_id
        )
        log_audit_action(session.get("user_email"), "doctor", "Approve Appointment", f"Approved appointment {apt.get('appointment_ref')}")
        return redirect(url_for("doctor_dashboard", success="Appointment approved successfully."))

    elif action == "reject":
        update_appointment_status(apt_id, "Rejected")
        create_notification(
            patient_email, "patient",
            f"Appointment Request Declined",
            f"Dr. {doc_name} was unable to schedule your appointment request on {apt.get('appointment_date')}.",
            "appointment_declined", apt_id
        )
        log_audit_action(session.get("user_email"), "doctor", "Decline Appointment", f"Declined appointment {apt.get('appointment_ref')}")
        return redirect(url_for("doctor_dashboard", success="Appointment declined."))

    elif action == "complete":
        doc_notes = request.form.get("doctor_notes", "").strip()
        prescription = request.form.get("prescription", "").strip()
        update_appointment_status(apt_id, "Completed", doctor_notes=doc_notes, prescription=prescription)
        create_notification(
            patient_email, "patient",
            f"Consultation Completed - Dr. {doc_name}",
            f"Your consultation is completed. Please view your prescription slip and share your anonymous feedback.",
            "appointment_completed", apt_id
        )
        log_audit_action(session.get("user_email"), "doctor", "Complete Treatment", f"Completed consultation for {apt.get('patient_name')}")
        return redirect(url_for("doctor_dashboard", success="Treatment recorded as completed."))

    return redirect(url_for("doctor_dashboard"))


@app.route("/doctor/patient-history/<path:patient_email>")
def doctor_patient_history(patient_email):
    guard = _require_doctor()
    if guard:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    from db import get_patient_clinical_history
    records = get_patient_clinical_history(patient_email)
    # Format date strings for JSON
    for r in records:
        if r.get("appointment_date"):
            r["appointment_date"] = str(r["appointment_date"])
    return jsonify({"success": True, "records": records})


@app.route("/doctor/profile/update", methods=["POST"])
def doctor_profile_update():
    guard = _require_doctor()
    if guard:
        return guard

    from db import update_doctor_details, log_audit_action

    doc_id = session.get("doctor_id")
    if not doc_id:
        return redirect(url_for("doctor_dashboard", error="Doctor ID missing."))

    update_data = {
        "doctor": request.form.get("doctor_name", "").strip(),
        "qualifications": request.form.get("qualifications", "").strip(),
        "specialization": request.form.get("specialization", "").strip(),
        "hospital": request.form.get("hospital", "").strip(),
        "experience_years": int(request.form.get("experience_years", 10) or 10),
        "consultation_fee": int(request.form.get("consultation_fee", 500) or 500),
        "bio": request.form.get("bio", "").strip()
    }
    update_doctor_details(doc_id, update_data)
    log_audit_action(session.get("user_email"), "doctor", "Update Profile", f"Doctor {update_data['doctor']} updated profile")
    session["user_name"] = update_data["doctor"]

    return redirect(url_for("doctor_dashboard", success="Profile updated successfully."))


@app.route("/doctor/review/<int:review_id>/respond", methods=["POST"])
def doctor_review_respond(review_id):
    guard = _require_doctor()
    if guard:
        return guard

    from db import doctor_respond_to_review, log_audit_action
    resp_text = request.form.get("response_text", "").strip()
    if resp_text:
        doctor_respond_to_review(review_id, resp_text)
        log_audit_action(session.get("user_email"), "doctor", "Respond to Review", f"Responded to review #{review_id}")
        return redirect(url_for("doctor_dashboard", success="Response posted successfully."))
    return redirect(url_for("doctor_dashboard"))


@app.route("/doctor/review/<int:review_id>/report", methods=["POST"])
def doctor_review_report(review_id):
    guard = _require_doctor()
    if guard:
        return guard

    from db import doctor_report_review, log_audit_action
    reason = request.form.get("reason", "Flagged by practitioner").strip()
    doctor_report_review(review_id, reason)
    log_audit_action(session.get("user_email"), "doctor", "Report Review", f"Flagged review #{review_id} to admin: {reason}")
    return redirect(url_for("doctor_dashboard", success="Review flagged to administrator for moderation."))


# ==================== ADMIN DASHBOARD & CONTROL CENTER ====================

@app.route("/admin/dashboard")
def admin_dashboard():
    guard = _require_admin()
    if guard:
        return guard

    from db import (
        get_admin_dashboard_metrics, get_all_patients_list,
        get_doctors_api_list, get_all_hospitals_records,
        get_all_reviews_admin, get_recent_audit_logs
    )

    metrics = get_admin_dashboard_metrics()
    patients = get_all_patients_list(limit=50)
    doctors_data = get_doctors_api_list(limit=25)
    hospitals = get_all_hospitals_records(limit=25)
    reviews_mod = get_all_reviews_admin(limit=50)
    audit_logs = get_recent_audit_logs(limit=30)

    success_msg = request.args.get("success", "")
    error_msg = request.args.get("error", "")

    return render_template(
        "admin_dashboard.html",
        metrics=metrics,
        patients=patients,
        doctors_count=doctors_data.get("total", 26712),
        doctors_sample=doctors_data.get("doctors", []),
        hospitals=hospitals,
        reviews_moderation=reviews_mod,
        audit_logs=audit_logs,
        success_msg=success_msg,
        error_msg=error_msg
    )


@app.route("/admin/patient/add", methods=["POST"])
def admin_patient_add():
    guard = _require_admin()
    if guard:
        return guard

    from db import save_patient, log_audit_action
    new_pat = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "password": request.form.get("password", "").strip(),
        "age": int(request.form.get("age", 30) or 30),
        "country": request.form.get("country", "India").strip(),
        "role": "patient",
        "status": "active",
        "enrolled_at": datetime.now().isoformat(timespec="seconds")
    }
    save_patient(new_pat)
    log_audit_action("admin@healthcare.com", "admin", "Add Patient", f"Admin created patient {new_pat['email']}")
    return redirect(url_for("admin_dashboard", success=f"Patient {new_pat['email']} created."))


@app.route("/admin/patient/delete", methods=["POST"])
def admin_patient_delete():
    guard = _require_admin()
    if guard:
        return guard

    from db import delete_patient_by_email, log_audit_action
    email = request.form.get("email", "").strip().lower()
    if email and email != "admin@healthcare.com":
        delete_patient_by_email(email)
        log_audit_action("admin@healthcare.com", "admin", "Delete Patient", f"Admin deleted patient {email}")
        return redirect(url_for("admin_dashboard", success=f"Patient {email} deleted."))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/doctor/add", methods=["POST"])
def admin_doctor_add():
    guard = _require_admin()
    if guard:
        return guard

    from db import create_new_doctor, log_audit_action
    doc_data = {
        "doctor_name": request.form.get("doctor_name", "").strip(),
        "specialization": request.form.get("specialization", "").strip(),
        "hospital": request.form.get("hospital", "").strip(),
        "department": request.form.get("specialization", "").strip(),
        "location": request.form.get("location", "Chennai").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "password": request.form.get("password", "doctor123").strip(),
        "experience_years": int(request.form.get("experience_years", 10) or 10),
        "consultation_fee": int(request.form.get("consultation_fee", 500) or 500)
    }
    create_new_doctor(doc_data)
    log_audit_action("admin@healthcare.com", "admin", "Add Doctor", f"Admin registered Dr. {doc_data['doctor_name']}")
    return redirect(url_for("admin_dashboard", success=f"Doctor {doc_data['doctor_name']} created successfully."))


@app.route("/admin/doctor/delete", methods=["POST"])
def admin_doctor_delete():
    guard = _require_admin()
    if guard:
        return guard

    from db import delete_doctor_by_id, log_audit_action
    doc_id = int(request.form.get("doctor_id", 0) or 0)
    if doc_id:
        delete_doctor_by_id(doc_id)
        log_audit_action("admin@healthcare.com", "admin", "Delete Doctor", f"Admin deleted doctor #{doc_id}")
        return redirect(url_for("admin_dashboard", success=f"Doctor #{doc_id} deleted."))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/hospital/add", methods=["POST"])
def admin_hospital_add():
    guard = _require_admin()
    if guard:
        return guard

    from db import create_hospital_record, log_audit_action
    hosp_data = {
        "name": request.form.get("name", "").strip(),
        "location": request.form.get("location", "Chennai").strip(),
        "contact_phone": request.form.get("contact_phone", "").strip(),
        "facilities": request.form.get("facilities", "24/7 Emergency").strip()
    }
    create_hospital_record(hosp_data)
    log_audit_action("admin@healthcare.com", "admin", "Add Hospital", f"Admin registered hospital {hosp_data['name']}")
    return redirect(url_for("admin_dashboard", success=f"Hospital {hosp_data['name']} added."))


@app.route("/admin/hospital/delete", methods=["POST"])
def admin_hospital_delete():
    guard = _require_admin()
    if guard:
        return guard

    from db import delete_hospital_record, log_audit_action
    hosp_id = int(request.form.get("hospital_id", 0) or 0)
    if hosp_id:
        delete_hospital_record(hosp_id)
        log_audit_action("admin@healthcare.com", "admin", "Delete Hospital", f"Admin deleted hospital #{hosp_id}")
        return redirect(url_for("admin_dashboard", success="Hospital deleted."))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/review/moderate", methods=["POST"])
def admin_review_moderate():
    guard = _require_admin()
    if guard:
        return guard

    from db import admin_moderate_review, log_audit_action
    rev_id = int(request.form.get("review_id", 0) or 0)
    action = request.form.get("action", "approve").strip()

    if rev_id:
        admin_moderate_review(rev_id, action)
        log_audit_action("admin@healthcare.com", "admin", "Moderate Review", f"Admin action '{action}' on review #{rev_id}")
        return redirect(url_for("admin_dashboard", success=f"Review #{rev_id} updated ({action})."))
    return redirect(url_for("admin_dashboard"))


# ==================== SBERT INITIALIZATION ====================
# Load SBERT models lazily (on first request) instead of startup
# This avoids long download times when starting the Flask app
SBERT_MODELS_LOADED = False

def load_sbert_on_demand():
    global SBERT_MODELS_LOADED
    sbert_module = _get_sbert_module()
    if sbert_module and not SBERT_MODELS_LOADED:
        try:
            if sbert_module.load_models("sbert_models_advanced.pkl"):
                SBERT_MODELS_LOADED = True
                print("[OK] SBERT Advanced Models loaded successfully")
            else:
                SBERT_MODELS_LOADED = False
                print("[INFO] SBERT model file unavailable; continuing without it")
        except Exception as e:
            SBERT_MODELS_LOADED = False
            print(f"[ERROR] Could not load SBERT models: {e}")
            print("[INFO] Continuing with the standard recommendation flow")

if __name__ == "__main__":
    try:
        from db import ensure_postgres_running
        ensure_postgres_running()
    except Exception as _e:
        print(f"[WARN] PostgreSQL startup check: {_e}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)