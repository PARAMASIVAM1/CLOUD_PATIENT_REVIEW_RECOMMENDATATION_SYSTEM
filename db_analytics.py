"""
db_analytics.py - Administrative analytics, hospital/doctor performance
indicators, NLP model monitoring and dataset health checks.

Everything here reports only what actually exists in the database or in the
trained model artefacts on disk. Nothing is fabricated: when a figure cannot be
computed it is returned as None/zero and the template renders an explicit
"insufficient data" state instead of a guess.
"""

import csv
import json
from collections import Counter
from pathlib import Path

from db import get_connection

WORKSPACE_DIR = Path(__file__).resolve().parent
PHASE2_DIR = WORKSPACE_DIR / "phase2_outputs"
SUMMARY_PATH = PHASE2_DIR / "summary.json"
COMPARISON_PATH = PHASE2_DIR / "model_comparison.csv"

# A rating computed from fewer reviews than this is flagged as low-confidence so
# a doctor with 2 reviews is never compared directly against one with 900.
MIN_RELIABLE_REVIEWS = 10


def _rows_to_dicts(cursor):
    columns = [desc[0] for desc in cursor.description]
    result = []
    for row in cursor.fetchall():
        record = {}
        for col, val in zip(columns, row):
            if isinstance(val, datetime):
                record[col] = val.strftime("%Y-%m-%d %H:%M:%S")
            elif hasattr(val, "strftime"):
                record[col] = val.strftime("%Y-%m-%d")
            elif hasattr(val, "isoformat"):
                record[col] = val.isoformat()
            else:
                record[col] = val
        result.append(record)
    return result


def _confidence_label(review_count):
    if not review_count:
        return "No reviews"
    if review_count < MIN_RELIABLE_REVIEWS:
        return "Low confidence"
    if review_count < 50:
        return "Moderate confidence"
    return "High confidence"


# ==================== HOSPITAL & DOCTOR PERFORMANCE ====================

def get_hospital_performance(limit=25):
    """
    Patient-feedback indicators aggregated per hospital.

    Ratings are grouped with their review counts so an average built from three
    reviews is never presented as equivalent to one built from three hundred.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT
                d.hospital,
                d."Location (Tamil Nadu)" AS location,
                COUNT(DISTINCT d.id) AS doctor_count,
                ROUND(AVG(d.rating), 2) AS directory_rating,
                COUNT(r.id) AS review_count,
                ROUND(AVG(r.patient_rating), 2) AS feedback_rating,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'positive') AS positive_count,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'negative') AS negative_count,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'neutral') AS neutral_count
            FROM "doctors" d
            LEFT JOIN "patient_reviews" r ON LOWER(r.doctor_name) = LOWER(d.doctor)
            WHERE d.hospital IS NOT NULL AND TRIM(d.hospital) != ''
            GROUP BY d.hospital, d."Location (Tamil Nadu)"
            ORDER BY review_count DESC, doctor_count DESC
            LIMIT %s;
            """,
            [limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()

        hospitals = []
        for row in rows:
            review_count = row.get("review_count") or 0
            positive = row.get("positive_count") or 0
            negative = row.get("negative_count") or 0
            neutral = row.get("neutral_count") or 0
            total_sentiment = max(positive + negative + neutral, 1)
            hospitals.append({
                **row,
                "positive_pct": round(positive / total_sentiment * 100, 1),
                "negative_pct": round(negative / total_sentiment * 100, 1),
                "neutral_pct": round(neutral / total_sentiment * 100, 1),
                "confidence": _confidence_label(review_count),
            })
        return hospitals
    except Exception as exc:
        print(f"[DB-WARN] Error building hospital performance: {exc}")
        return []


def get_doctor_performance(limit=25, sort_by="feedback_rating"):
    """Patient-feedback indicators per doctor, with review-count context."""
    allowed_sort = {
        "feedback_rating": "feedback_rating DESC NULLS LAST",
        "review_count": "review_count DESC",
        "doctor_count": "doctor_count DESC",
    }
    order_clause = allowed_sort.get(sort_by, allowed_sort["feedback_rating"])

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT
                d.id AS doctor_id,
                d.doctor AS doctor_name,
                d.specialization,
                d.hospital,
                d."Location (Tamil Nadu)" AS location,
                d.consultation_fee,
                d.experience_years,
                d.verification_status,
                d.is_verified,
                COUNT(r.id) AS review_count,
                ROUND(AVG(r.patient_rating), 2) AS feedback_rating,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'positive') AS positive_count,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'negative') AS negative_count,
                COUNT(r.id) FILTER (WHERE LOWER(r.sentiment_label) = 'neutral') AS neutral_count
            FROM "doctors" d
            LEFT JOIN "patient_reviews" r ON LOWER(r.doctor_name) = LOWER(d.doctor)
            WHERE d.verification_status = 'Approved'
            GROUP BY d.id, d.doctor, d.specialization, d.hospital,
                     d."Location (Tamil Nadu)", d.consultation_fee,
                     d.experience_years, d.verification_status, d.is_verified
            HAVING COUNT(r.id) > 0
            ORDER BY {order_clause}
            LIMIT %s;
            """,
            [limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()

        doctors = []
        for row in rows:
            review_count = row.get("review_count") or 0
            positive = row.get("positive_count") or 0
            negative = row.get("negative_count") or 0
            neutral = row.get("neutral_count") or 0
            total_sentiment = max(positive + negative + neutral, 1)
            doctors.append({
                **row,
                "positive_pct": round(positive / total_sentiment * 100, 1),
                "negative_pct": round(negative / total_sentiment * 100, 1),
                "neutral_pct": round(neutral / total_sentiment * 100, 1),
                "confidence": _confidence_label(review_count),
                "is_low_sample": review_count < MIN_RELIABLE_REVIEWS,
            })
        return doctors
    except Exception as exc:
        print(f"[DB-WARN] Error building doctor performance: {exc}")
        return []


COMPLAINT_INDICATORS = {
    "Waiting time": ("wait", "delay", "queue", "late", "slow", "long time"),
    "Communication": ("explain", "listen", "communication", "rude", "behav", "talk", "clear"),
    "Cost / fees": ("cost", "expensive", "fee", "charge", "money", "price", "afford"),
    "Treatment quality": ("treat", "cure", "medicine", "recover", "relief", "heal"),
    "Hospital facilities": ("clean", "hygiene", "facility", "room", "staff", "parking"),
}


def get_complaint_trends(limit=2000):
    """
    Count how often each service indicator is mentioned across recent feedback,
    split by the sentiment the model assigned to that same review.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT new_feedback, sentiment_label, patient_rating
            FROM "patient_reviews"
            ORDER BY id DESC
            LIMIT %s;
            """,
            [limit],
        )
        rows = cur.fetchall()
        con.close()
    except Exception as exc:
        print(f"[DB-WARN] Error reading feedback for trends: {exc}")
        return {"total_reviews": 0, "indicators": []}

    totals = Counter()
    negative_hits = Counter()
    positive_hits = Counter()

    for feedback, sentiment, _rating in rows:
        text = str(feedback or "").lower()
        if not text:
            continue
        label = str(sentiment or "").lower()
        for indicator, keywords in COMPLAINT_INDICATORS.items():
            if any(keyword in text for keyword in keywords):
                totals[indicator] += 1
                if label == "negative":
                    negative_hits[indicator] += 1
                elif label == "positive":
                    positive_hits[indicator] += 1

    total_reviews = len(rows)
    indicators = []
    for indicator, keywords in COMPLAINT_INDICATORS.items():
        mentions = totals.get(indicator, 0)
        indicators.append({
            "indicator": indicator,
            "mentions": mentions,
            "share_pct": round(mentions / total_reviews * 100, 1) if total_reviews else 0.0,
            "negative_mentions": negative_hits.get(indicator, 0),
            "positive_mentions": positive_hits.get(indicator, 0),
            "status": (
                "Frequently reported" if total_reviews and mentions / total_reviews >= 0.15
                else "Occasionally reported" if mentions else "Not reported"
            ),
            "keywords": ", ".join(keywords),
        })

    indicators.sort(key=lambda item: item["mentions"], reverse=True)
    return {"total_reviews": total_reviews, "indicators": indicators}


def get_appointment_operations(limit=100, status=None, search=None):
    """Operational appointment view for administrators (no clinical authority)."""
    try:
        con = get_connection()
        cur = con.cursor()
        where = ["1=1"]
        params = []
        if status:
            where.append("status = %s")
            params.append(status)
        if search:
            where.append("(appointment_ref ILIKE %s OR patient_email ILIKE %s OR doctor_name ILIKE %s)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])

        cur.execute(
            f"""
            SELECT id, appointment_ref, patient_email, patient_name, doctor_id,
                   doctor_name, hospital, specialization, appointment_date,
                   appointment_time, disease, symptoms, status, has_feedback,
                   created_at, updated_at
            FROM appointments
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        appointments = _rows_to_dicts(cur)

        cur.execute(
            """
            SELECT status, COUNT(*) FROM appointments GROUP BY status;
            """
        )
        status_counts = {row[0] or "Unknown": row[1] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) FROM appointments;")
        total = cur.fetchone()[0]
        con.close()

        completed = status_counts.get("Completed", 0)
        cancelled = status_counts.get("Cancelled", 0) + status_counts.get("Rejected", 0)
        return {
            "appointments": appointments,
            "status_counts": status_counts,
            "total": total,
            "completed": completed,
            "cancelled": cancelled,
            "completion_rate": round(completed / total * 100, 1) if total else 0.0,
            "cancellation_rate": round(cancelled / total * 100, 1) if total else 0.0,
        }
    except Exception as exc:
        print(f"[DB-WARN] Error loading appointment operations: {exc}")
        return {
            "appointments": [], "status_counts": {}, "total": 0,
            "completed": 0, "cancelled": 0,
            "completion_rate": 0.0, "cancellation_rate": 0.0,
        }


# ==================== NLP MODEL MONITORING ====================

def _load_training_summary():
    if not SUMMARY_PATH.exists():
        return {}
    try:
        with open(SUMMARY_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _load_model_comparison():
    if not COMPARISON_PATH.exists():
        return []
    try:
        with open(COMPARISON_PATH, "r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def get_ml_model_metrics():
    """
    Live sentiment-classification monitoring.

    The class distribution and the uncertain-classification queue are computed
    from the stored reviews; the evaluation table is read from the trained model
    artefacts so the accuracy shown is the measured value, not an estimate.
    """
    metrics = {
        "model_available": False,
        "model_version": "TF-IDF + Multinomial Naive Bayes (sentiment)",
        "accuracy": None,
        "precision": None,
        "recall": None,
        "f1_score": None,
        "class_distribution": [],
        "confusion_note": "",
        "review_queue": [],
        "reviewed_count": 0,
        "pending_review_count": 0,
        "model_comparison": [],
        "training_summary_available": False,
    }

    # Live dataset class distribution
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT COALESCE(sentiment_label, 'Unclassified') AS label, COUNT(*)
            FROM "doctors"
            WHERE review_text IS NOT NULL AND TRIM(review_text) != ''
            GROUP BY COALESCE(sentiment_label, 'Unclassified')
            ORDER BY COUNT(*) DESC;
            """
        )
        dataset_distribution = [
            {"label": row[0], "count": row[1]} for row in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT COALESCE(sentiment_label, 'Unclassified') AS label, COUNT(*)
            FROM "patient_reviews"
            GROUP BY COALESCE(sentiment_label, 'Unclassified')
            ORDER BY COUNT(*) DESC;
            """
        )
        live_distribution = [
            {"label": row[0], "count": row[1]} for row in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT id, doctor_name, new_feedback, sentiment_label,
                   patient_rating, moderation_status, submitted_at
            FROM "patient_reviews"
            WHERE new_feedback IS NOT NULL AND TRIM(new_feedback) != ''
            ORDER BY id DESC
            LIMIT 400;
            """
        )
        review_rows = _rows_to_dicts(cur)

        cur.execute("SELECT COUNT(*) FROM \"patient_reviews\" WHERE is_moderated = TRUE;")
        reviewed_count = cur.fetchone()[0]

        con.close()
        metrics["model_available"] = bool(dataset_distribution or live_distribution)
        metrics["class_distribution"] = live_distribution or dataset_distribution
        metrics["dataset_class_distribution"] = dataset_distribution
        metrics["reviewed_count"] = reviewed_count
    except Exception as exc:
        print(f"[DB-WARN] Error reading model metrics: {exc}")
        review_rows = []

    # Uncertain-classification queue: short reviews and rating/sentiment clashes
    uncertain = []
    for row in review_rows:
        text = str(row.get("new_feedback") or "").strip()
        rating = row.get("patient_rating")
        sentiment = str(row.get("sentiment_label") or "").capitalize()
        reasons = []
        if len(text.split()) < 4:
            reasons.append("Very short review text")
        try:
            numeric_rating = float(rating)
            if sentiment == "Negative" and numeric_rating >= 4:
                reasons.append("Rating and predicted sentiment disagree")
            if sentiment == "Positive" and numeric_rating <= 2:
                reasons.append("Rating and predicted sentiment disagree")
        except (TypeError, ValueError):
            reasons.append("Missing numeric rating")
        if reasons and len(uncertain) < 25:
            uncertain.append({
                "id": row.get("id"),
                "doctor_name": row.get("doctor_name"),
                "review_text": text,
                "sentiment_label": sentiment or "Unclassified",
                "patient_rating": rating,
                "flags": "; ".join(reasons),
                "moderation_status": row.get("moderation_status") or "Published",
            })

    metrics["review_queue"] = uncertain
    metrics["pending_review_count"] = len(uncertain)

    # Measured evaluation figures from the trained artefacts
    summary = _load_training_summary()
    if summary:
        metrics["training_summary_available"] = True
        best_model = summary.get("best_model") or {}
        if isinstance(best_model, dict):
            metrics["model_version"] = best_model.get("model") or metrics["model_version"]
            for source_key, target_key in (
                ("test_accuracy", "accuracy"),
                ("test_precision", "precision"),
                ("test_recall", "recall"),
                ("test_f1", "f1_score"),
                ("test_f1_score", "f1_score"),
            ):
                value = best_model.get(source_key)
                if value is not None and metrics[target_key] is None:
                    try:
                        metrics[target_key] = round(float(value), 4)
                    except (TypeError, ValueError):
                        pass
        for source_key, target_key in (("accuracy", "accuracy"), ("f1_score", "f1_score")):
            value = summary.get(source_key)
            if value is not None and metrics[target_key] is None:
                try:
                    metrics[target_key] = round(float(value), 4)
                except (TypeError, ValueError):
                    pass

    comparison_rows = _load_model_comparison()
    if comparison_rows:
        metrics["model_comparison"] = comparison_rows
        if metrics["accuracy"] is None:
            best_row = None
            best_value = -1.0
            for row in comparison_rows:
                try:
                    value = float(row.get("test_accuracy") or row.get("Test Accuracy") or 0)
                except (TypeError, ValueError):
                    continue
                if value > best_value:
                    best_value = value
                    best_row = row
            if best_row:
                metrics["model_version"] = (
                    best_row.get("model") or best_row.get("Model") or metrics["model_version"]
                )
                for source_key, target_key in (
                    ("test_accuracy", "accuracy"),
                    ("test_precision", "precision"),
                    ("test_recall", "recall"),
                    ("test_f1_score", "f1_score"),
                    ("test_f1", "f1_score"),
                ):
                    value = best_row.get(source_key)
                    if value is None:
                        continue
                    try:
                        metrics[target_key] = round(float(value), 4)
                    except (TypeError, ValueError):
                        pass

    metrics["confidence_note"] = (
        "Accuracy alone is not sufficient: inspect precision, recall and F1 per class "
        "because the sentiment classes are imbalanced."
    )
    return metrics


# ==================== DATASET HEALTH ====================

def get_dataset_health():
    """
    Real integrity checks across the relational tables: row counts, duplicate
    detection, missing-value counts and orphaned references.
    """
    health = {
        "tables": [],
        "duplicate_doctors": 0,
        "duplicate_reviews": 0,
        "orphaned_reviews": 0,
        "orphaned_appointments": 0,
        "missing_doctor_fields": 0,
        "issues": [],
        "is_healthy": True,
    }

    checks = [
        ("doctors", "Doctor directory"),
        ("patients", "Patient accounts"),
        ("hospitals", "Hospital facilities"),
        ("appointments", "Appointments"),
        ("patient_reviews", "Patient reviews"),
        ("notifications", "Notifications"),
        ("audit_logs", "Audit logs"),
    ]

    try:
        con = get_connection()
        cur = con.cursor()

        for table, label in checks:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{table}";')
                health["tables"].append({"table": table, "label": label, "rows": cur.fetchone()[0]})
            except Exception:
                health["tables"].append({"table": table, "label": label, "rows": None})

        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT LOWER(doctor), LOWER(hospital), LOWER(specialization)
                FROM "doctors"
                WHERE doctor IS NOT NULL
                GROUP BY LOWER(doctor), LOWER(hospital), LOWER(specialization)
                HAVING COUNT(*) > 1
            ) AS dup;
            """
        )
        health["duplicate_doctors"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT LOWER(new_feedback), LOWER(doctor_name)
                FROM "patient_reviews"
                WHERE new_feedback IS NOT NULL
                GROUP BY LOWER(new_feedback), LOWER(doctor_name)
                HAVING COUNT(*) > 1
            ) AS dup;
            """
        )
        health["duplicate_reviews"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM "patient_reviews" r
            WHERE r.appointment_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.id = r.appointment_id);
            """
        )
        health["orphaned_reviews"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM appointments a
            WHERE NOT EXISTS (
                SELECT 1 FROM "doctors" d WHERE d.id = a.doctor_id
            );
            """
        )
        health["orphaned_appointments"] = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM "doctors"
            WHERE verification_status = 'Approved'
              AND (email IS NULL OR TRIM(email) = ''
                   OR specialization IS NULL OR TRIM(specialization) = ''
                   OR hospital IS NULL OR TRIM(hospital) = '');
            """
        )
        health["missing_doctor_fields"] = cur.fetchone()[0]

        con.close()
    except Exception as exc:
        print(f"[DB-WARN] Error running dataset health checks: {exc}")
        health["issues"].append(f"Database unavailable: {exc}")
        health["is_healthy"] = False
        return health

    if health["duplicate_doctors"]:
        health["issues"].append(
            f"{health['duplicate_doctors']} duplicated doctor record group(s) detected."
        )
    if health["duplicate_reviews"]:
        health["issues"].append(
            f"{health['duplicate_reviews']} duplicated feedback group(s) detected."
        )
    if health["orphaned_reviews"]:
        health["issues"].append(
            f"{health['orphaned_reviews']} review(s) reference a missing appointment."
        )
    if health["orphaned_appointments"]:
        health["issues"].append(
            f"{health['orphaned_appointments']} appointment(s) reference a missing doctor."
        )
    if health["missing_doctor_fields"]:
        health["issues"].append(
            f"{health['missing_doctor_fields']} approved doctor record(s) have missing required fields."
        )

    health["is_healthy"] = not health["issues"]
    return health


# ==================== AUDIT LOGS ====================

def get_audit_logs(limit=100, role=None, search=None):
    """Filterable audit trail for the security screen."""
    try:
        con = get_connection()
        cur = con.cursor()
        where = ["1=1"]
        params = []
        if role:
            where.append("actor_role = %s")
            params.append(role)
        if search:
            where.append("(actor_email ILIKE %s OR action ILIKE %s OR details ILIKE %s)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])

        cur.execute(
            f"""
            SELECT id, actor_email, actor_role, action, details, created_at
            FROM audit_logs
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        rows = _rows_to_dicts(cur)

        cur.execute("SELECT actor_role, COUNT(*) FROM audit_logs GROUP BY actor_role;")
        role_counts = {row[0] or "unknown": row[1] for row in cur.fetchall()}
        con.close()
        return {"logs": rows, "role_counts": role_counts}
    except Exception as exc:
        print(f"[DB-WARN] Error reading audit logs: {exc}")
        return {"logs": [], "role_counts": {}}
