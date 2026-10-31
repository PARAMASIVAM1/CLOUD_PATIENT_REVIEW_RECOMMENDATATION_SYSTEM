"""
db_records.py - Patient medical history, patient feedback history, doctor
appointment search and doctor improvement insights.

Privacy rules enforced here:

* A patient only ever reads their own records (callers pass the session email).
* A doctor reads history only for a patient they hold a treatment relationship
  with, and only for consultations that reached Approved/Completed state.
* Reviewer identity is never returned on any doctor-facing query.
"""

from calendar import month_abbr
from datetime import datetime

from db import get_connection

FEEDBACK_ELIGIBLE_STATUSES = ("Completed",)


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


def _fetch_one_dict(cursor):
    row = cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
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
    return record


# ==================== PATIENT RECORDS ====================

def get_patient_medical_history(patient_email, limit=200):
    """
    Full consultation history for one patient.

    Read only by the patient themselves or by the treating doctor through
    `get_doctor_patient_history_for_relationship`.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT a.id, a.appointment_ref, a.doctor_id, a.doctor_name, a.hospital,
                   a.specialization, a.appointment_date, a.appointment_time,
                   a.disease, a.symptoms, a.notes, a.doctor_notes, a.prescription,
                   a.status, a.has_feedback, a.created_at
            FROM appointments a
            WHERE LOWER(a.patient_email) = LOWER(%s)
              AND a.status IN ('Approved', 'Completed')
            ORDER BY a.appointment_date DESC NULLS LAST, a.id DESC
            LIMIT %s;
            """,
            [patient_email.strip(), limit],
        )
        records = _rows_to_dicts(cur)
        con.close()
        return records
    except Exception as exc:
        print(f"[DB-WARN] Error reading patient medical history: {exc}")
        return []


def get_patient_appointment_groups(patient_email):
    """Split a patient's appointments into upcoming / past / cancelled groups."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, appointment_ref, doctor_id, doctor_name, hospital,
                   specialization, appointment_date, appointment_time, disease,
                   symptoms, notes, doctor_notes, prescription, status,
                   has_feedback, created_at
            FROM appointments
            WHERE LOWER(patient_email) = LOWER(%s)
            ORDER BY appointment_date DESC NULLS LAST, id DESC;
            """,
            [patient_email.strip()],
        )
        appointments = _rows_to_dicts(cur)
        con.close()
    except Exception as exc:
        print(f"[DB-WARN] Error grouping patient appointments: {exc}")
        return {"upcoming": [], "past": [], "cancelled": [], "all": []}

    today = datetime.now().date().isoformat()
    upcoming, past, cancelled = [], [], []
    for apt in appointments:
        status = str(apt.get("status") or "")
        date_text = str(apt.get("appointment_date") or "")
        if status in ("Cancelled", "Rejected"):
            cancelled.append(apt)
        elif status == "Completed" or (date_text and date_text < today):
            past.append(apt)
        else:
            upcoming.append(apt)
    return {"upcoming": upcoming, "past": past, "cancelled": cancelled, "all": appointments}


def get_patient_feedback_history(patient_email, limit=100):
    """Feedback the signed-in patient has already submitted."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, doctor_name, hospital, specialization, patient_rating,
                   new_feedback, sentiment_label, waiting_time_rating,
                   communication_rating, cost_satisfaction_rating,
                   doctor_response, moderation_status, submitted_at, appointment_id
            FROM "patient_reviews"
            WHERE LOWER(patient_email) = LOWER(%s)
            ORDER BY id DESC
            LIMIT %s;
            """,
            [patient_email.strip(), limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()
        return rows
    except Exception as exc:
        print(f"[DB-WARN] Error reading patient feedback history: {exc}")
        return []


def get_patient_dashboard_summary(patient_email):
    """Everything the patient dashboard needs, in one round trip."""
    groups = get_patient_appointment_groups(patient_email)
    feedback = get_patient_feedback_history(patient_email, limit=200)

    reviewed_ids = {
        item.get("appointment_id")
        for item in feedback
        if item.get("appointment_id") is not None
    }
    awaiting_feedback = [
        apt for apt in groups["past"]
        if apt.get("status") == "Completed"
        and not apt.get("has_feedback")
        and apt.get("id") not in reviewed_ids
    ]

    return {
        "upcoming": groups["upcoming"],
        "past": groups["past"],
        "cancelled": groups["cancelled"],
        "total_appointments": len(groups["all"]),
        "awaiting_feedback": awaiting_feedback,
        "feedback_count": len(feedback),
        "latest_feedback": feedback[0] if feedback else None,
        "next_appointment": groups["upcoming"][0] if groups["upcoming"] else None,
        "history_count": sum(
            1 for apt in groups["past"] if apt.get("doctor_notes") or apt.get("prescription")
        ),
    }


def check_feedback_eligibility(appointment_id, patient_email):
    """
    A patient may submit exactly one review, and only for their own appointment
    that the doctor has marked Completed.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, status, has_feedback, patient_email, doctor_name, hospital,
                   specialization, disease, appointment_date, appointment_time
            FROM appointments
            WHERE id = %s;
            """,
            [appointment_id],
        )
        appointment = _fetch_one_dict(cur)
        if not appointment:
            con.close()
            return False, "Appointment not found."

        if str(appointment.get("patient_email") or "").strip().lower() != str(patient_email or "").strip().lower():
            con.close()
            return False, "This appointment does not belong to your account."

        if appointment.get("status") != "Completed":
            con.close()
            return False, "Feedback becomes available only after the doctor marks the consultation completed."

        cur.execute(
            """
            SELECT id FROM "patient_reviews"
            WHERE appointment_id = %s OR (LOWER(patient_email) = LOWER(%s) AND LOWER(doctor_name) = LOWER(%s))
            LIMIT 1;
            """,
            [appointment_id, patient_email, appointment.get("doctor_name")],
        )
        existing = cur.fetchone()
        con.close()

        if existing and appointment.get("has_feedback"):
            return False, "You have already submitted feedback for this consultation."

        return True, None
    except Exception as exc:
        print(f"[DB-WARN] Error checking feedback eligibility: {exc}")
        return False, "Could not verify this appointment. Please try again."


# ==================== DOCTOR APPOINTMENT SEARCH ====================

def search_doctor_appointments(doctor_name, status=None, search=None,
                               date_from=None, date_to=None, limit=200):
    """
    Search and filter a doctor's own appointment record.

    Only rows belonging to the signed-in doctor are ever returned; the doctor
    name is a mandatory argument, never optional.
    """
    if not doctor_name:
        return []

    try:
        con = get_connection()
        cur = con.cursor()
        where = ["LOWER(doctor_name) = LOWER(%s)"]
        params = [doctor_name.strip()]

        if status:
            where.append("status = %s")
            params.append(status)
        if search:
            where.append(
                "(appointment_ref ILIKE %s OR patient_name ILIKE %s OR disease ILIKE %s OR symptoms ILIKE %s)"
            )
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        if date_from:
            where.append("appointment_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("appointment_date <= %s")
            params.append(date_to)

        cur.execute(
            f"""
            SELECT id, appointment_ref, patient_email, patient_name, patient_age,
                   patient_gender, appointment_date, appointment_time, disease,
                   symptoms, notes, doctor_notes, prescription, status,
                   has_feedback, created_at
            FROM appointments
            WHERE {" AND ".join(where)}
            ORDER BY appointment_date DESC NULLS LAST, id DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()
        return rows
    except Exception as exc:
        print(f"[DB-WARN] Error searching doctor appointments: {exc}")
        return []


def get_doctor_patient_history_for_relationship(doctor_name, patient_email):
    """
    Clinical history a doctor may legitimately read.

    Access is granted only when this doctor has at least one Approved or
    Completed consultation with the patient. A doctor cannot browse the history
    of a patient they have never treated.
    """
    if not doctor_name or not patient_email:
        return {"allowed": False, "reason": "Missing doctor or patient reference.", "records": []}

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM appointments
            WHERE LOWER(doctor_name) = LOWER(%s)
              AND LOWER(patient_email) = LOWER(%s)
              AND status IN ('Approved', 'Completed');
            """,
            [doctor_name.strip(), patient_email.strip()],
        )
        relationship_count = cur.fetchone()[0]

        if relationship_count == 0:
            con.close()
            return {
                "allowed": False,
                "reason": (
                    "No treatment relationship exists between your account and this patient. "
                    "Clinical history is restricted to patients you are actively treating."
                ),
                "records": [],
            }

        cur.execute(
            """
            SELECT id, appointment_ref, doctor_name, hospital, specialization,
                   appointment_date, disease, symptoms, doctor_notes, prescription, status
            FROM appointments
            WHERE LOWER(patient_email) = LOWER(%s)
              AND status IN ('Approved', 'Completed')
            ORDER BY appointment_date DESC NULLS LAST, id DESC;
            """,
            [patient_email.strip()],
        )
        records = _rows_to_dicts(cur)
        con.close()
        return {
            "allowed": True,
            "reason": None,
            "relationship_count": relationship_count,
            "records": records,
        }
    except Exception as exc:
        print(f"[DB-WARN] Error checking treatment relationship: {exc}")
        return {"allowed": False, "reason": "Could not verify the treatment relationship.", "records": []}


# ==================== DOCTOR IMPROVEMENT INSIGHTS ====================

INDICATOR_KEYWORDS = {
    "Waiting time": ("wait", "delay", "queue", "late", "slow"),
    "Communication & behaviour": ("explain", "listen", "kind", "behav", "friendly", "rude", "clear"),
    "Cost / fees": ("cost", "expensive", "fee", "charge", "money", "afford"),
    "Treatment quality": ("treat", "cure", "medicine", "recover", "relief", "heal", "effective"),
}


def get_doctor_improvement_insights(doctor_name):
    """
    Month-wise sentiment trend plus per-indicator counts for one doctor.

    These are service-quality signals derived from patient reviews. They are
    indicators only and never presented as a clinical quality rating.
    """
    if not doctor_name:
        return {"months": [], "indicators": [], "total_reviews": 0, "average_rating": None}

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, new_feedback, patient_rating, sentiment_label,
                   waiting_time_rating, communication_rating,
                   cost_satisfaction_rating, submitted_at
            FROM "patient_reviews"
            WHERE LOWER(doctor_name) = LOWER(%s)
              AND (moderation_status IS NULL OR moderation_status <> 'Removed')
            ORDER BY submitted_at ASC NULLS LAST, id ASC;
            """,
            [doctor_name.strip()],
        )
        rows = _rows_to_dicts(cur)
        con.close()
    except Exception as exc:
        print(f"[DB-WARN] Error building improvement insights: {exc}")
        return {"months": [], "indicators": [], "total_reviews": 0, "average_rating": None}

    month_buckets = {}
    indicator_hits = {name: {"positive": 0, "negative": 0, "neutral": 0} for name in INDICATOR_KEYWORDS}
    ratings = []
    detail_totals = {"waiting_time": [], "communication": [], "cost": []}

    for row in rows:
        text = str(row.get("new_feedback") or "").lower()
        label = str(row.get("sentiment_label") or "Neutral").capitalize()

        raw_date = str(row.get("submitted_at") or "")
        month_key = "Unknown"
        if len(raw_date) >= 7 and raw_date[4] == "-":
            try:
                month_index = int(raw_date[5:7])
                month_key = f"{month_abbr[month_index]} {raw_date[:4]}"
            except (ValueError, IndexError):
                month_key = "Unknown"

        bucket = month_buckets.setdefault(
            month_key, {"month": month_key, "total": 0, "positive": 0, "negative": 0, "neutral": 0, "rating_sum": 0.0}
        )
        bucket["total"] += 1
        key = label.lower()
        if key in ("positive", "negative", "neutral"):
            bucket[key] += 1

        try:
            rating_value = float(row.get("patient_rating"))
            ratings.append(rating_value)
            bucket["rating_sum"] += rating_value
        except (TypeError, ValueError):
            pass

        for indicator, keywords in INDICATOR_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                indicator_hits[indicator][label.lower() if label.lower() in ("positive", "negative", "neutral") else "neutral"] += 1

        for column, bucket_name in (
            ("waiting_time_rating", "waiting_time"),
            ("communication_rating", "communication"),
            ("cost_satisfaction_rating", "cost"),
        ):
            try:
                detail_totals[bucket_name].append(float(row.get(column)))
            except (TypeError, ValueError):
                pass

    months = []
    for bucket in month_buckets.values():
        total = max(bucket["total"], 1)
        months.append({
            "month": bucket["month"],
            "total": bucket["total"],
            "average_rating": round(bucket["rating_sum"] / total, 2) if bucket["rating_sum"] else None,
            "positive_pct": round(bucket["positive"] / total * 100, 1),
            "negative_pct": round(bucket["negative"] / total * 100, 1),
            "neutral_pct": round(bucket["neutral"] / total * 100, 1),
        })

    indicators = []
    for indicator, counts in indicator_hits.items():
        total_mentions = counts["positive"] + counts["negative"] + counts["neutral"]
        indicators.append({
            "indicator": indicator,
            "mentions": total_mentions,
            "positive": counts["positive"],
            "negative": counts["negative"],
            "neutral": counts["neutral"],
            "tone": (
                "Improvement area" if counts["negative"] > counts["positive"]
                else "Strength" if counts["positive"] > 0
                else "No signal"
            ),
        })
    indicators.sort(key=lambda item: item["mentions"], reverse=True)

    def _average(values):
        return round(sum(values) / len(values), 2) if values else None

    return {
        "months": months,
        "indicators": indicators,
        "total_reviews": len(rows),
        "average_rating": _average(ratings),
        "waiting_time_average": _average(detail_totals["waiting_time"]),
        "communication_average": _average(detail_totals["communication"]),
        "cost_average": _average(detail_totals["cost"]),
        "is_low_sample": len(rows) < 10,
    }


# ==================== REVIEW REPORTS ====================

def create_review_report(review_id, reporter_role, reporter_email, reason):
    """Record a doctor's report against a review for administrator investigation."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO review_reports (review_id, reporter_role, reporter_email, reason, status, created_at)
            VALUES (%s, %s, %s, %s, 'Open', NOW())
            RETURNING id;
            """,
            [review_id, reporter_role, reporter_email, reason],
        )
        new_id = cur.fetchone()[0]
        cur.execute(
            """
            UPDATE "patient_reviews"
            SET is_reported = TRUE, report_reason = %s
            WHERE id = %s;
            """,
            [reason, review_id],
        )
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error creating review report: {exc}")
        return None


def get_review_reports(status=None, limit=50):
    """Open report queue for administrator moderation."""
    try:
        con = get_connection()
        cur = con.cursor()
        where = "1=1"
        params = []
        if status:
            where = "rr.status = %s"
            params.append(status)

        cur.execute(
            f"""
            SELECT rr.id, rr.review_id, rr.reporter_role, rr.reporter_email,
                   rr.reason, rr.status, rr.resolved_by, rr.created_at,
                   r.doctor_name, r.hospital, r.patient_rating, r.new_feedback,
                   r.sentiment_label, r.patient_email AS reviewer_email,
                   r.moderation_status
            FROM review_reports rr
            LEFT JOIN "patient_reviews" r ON r.id = rr.review_id
            WHERE {where}
            ORDER BY rr.created_at DESC, rr.id DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()
        return rows
    except Exception as exc:
        print(f"[DB-WARN] Error reading review reports: {exc}")
        return []


def resolve_review_report(report_id, action, admin_email, note=None):
    """Close a review report as 'Upheld' (review removed) or 'Dismissed'."""
    if action not in ("uphold", "dismiss"):
        return False

    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT review_id FROM review_reports WHERE id = %s;", [report_id])
        row = cur.fetchone()
        if not row:
            con.close()
            return False
        review_id = row[0]

        cur.execute(
            """
            UPDATE review_reports
            SET status = %s, resolved_by = %s
            WHERE id = %s;
            """,
            ["Upheld" if action == "uphold" else "Dismissed", admin_email, report_id],
        )

        if action == "uphold":
            cur.execute(
                """
                UPDATE "patient_reviews"
                SET moderation_status = 'Removed',
                    moderation_note = %s,
                    is_moderated = TRUE,
                    is_reported = FALSE
                WHERE id = %s;
                """,
                [note or "Removed after moderation review.", review_id],
            )
        else:
            cur.execute(
                """
                UPDATE "patient_reviews"
                SET moderation_status = 'Published',
                    moderation_note = %s,
                    is_moderated = TRUE,
                    is_reported = FALSE,
                    report_reason = NULL
                WHERE id = %s;
                """,
                [note or "Report reviewed and dismissed.", review_id],
            )

        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[DB-WARN] Error resolving review report #{report_id}: {exc}")
        return False


def get_open_reports_count():
    """Number of review reports still awaiting administrator action."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM review_reports WHERE status = 'Open';")
        count = cur.fetchone()[0]
        con.close()
        return count
    except Exception:
        return 0
