"""
db_verification.py - Doctor onboarding, credential verification and profile
change-request workflow.

A doctor who self-registers never becomes publicly visible immediately. The
record is created with:

    is_verified          = FALSE
    verification_status  = 'Pending Verification'

Only an administrator can move the record to 'Approved' (making it eligible for
public doctor search) or 'Rejected' with a recorded reason.
"""

from db import get_connection

STATUS_PENDING = "Pending Verification"
STATUS_UNDER_REVIEW = "Under Review"
STATUS_APPROVED = "Approved"
STATUS_REJECTED = "Rejected"
STATUS_SUSPENDED = "Suspended"

VISIBLE_STATUSES = (STATUS_APPROVED,)


def _serialise(value):
    if hasattr(value, "strftime"):
        if hasattr(value, "hour"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    elif hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _rows_to_dicts(cursor):
    columns = [desc[0] for desc in cursor.description]
    return [
        {col: _serialise(val) for col, val in zip(columns, row)}
        for row in cursor.fetchall()
    ]


def submit_doctor_application(application):
    """
    Create a doctor record in the Pending Verification state.

    Returns the new doctor id, or None when the email is already registered or
    the insert fails.
    """
    try:
        con = get_connection()
        cur = con.cursor()

        email = str(application.get("email") or "").strip().lower()
        cur.execute('SELECT id FROM "doctors" WHERE LOWER(email) = LOWER(%s);', [email])
        if cur.fetchone():
            con.close()
            return None

        cur.execute(
            """
            INSERT INTO "doctors" (
                doctor, specialization, hospital, disease, "Location (Tamil Nadu)",
                consultation_fee, waiting_time, rating, experience_years,
                email, password, is_verified, qualifications, bio,
                verification_status, registration_number, registration_council,
                available_days, available_timings, document_reference, submitted_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                FALSE, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            ) RETURNING id;
            """,
            [
                application.get("doctor_name"),
                application.get("specialization"),
                application.get("hospital"),
                application.get("department") or application.get("specialization"),
                application.get("location", "Chennai"),
                int(application.get("consultation_fee") or 500),
                int(application.get("waiting_time") or 15),
                0,
                int(application.get("experience_years") or 5),
                email,
                application.get("password"),
                application.get("qualifications", "MBBS, MD"),
                application.get("bio", ""),
                STATUS_PENDING,
                application.get("registration_number", ""),
                application.get("registration_council", ""),
                application.get("available_days", "Mon - Sat"),
                application.get("available_timings", "09:30 AM - 05:30 PM"),
                application.get("document_reference", ""),
            ],
        )
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error submitting doctor application: {exc}")
        return None


def get_doctor_applications(status=None, search=None, limit=100):
    """List doctor records for the administrator verification screen."""
    try:
        con = get_connection()
        cur = con.cursor()
        where = ["1=1"]
        params = []
        if status:
            where.append("verification_status = %s")
            params.append(status)
        if search:
            where.append("(doctor ILIKE %s OR email ILIKE %s OR specialization ILIKE %s)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])

        sql = f'''
            SELECT id, doctor, email, specialization, disease AS department,
                   hospital, "Location (Tamil Nadu)" AS location, qualifications,
                   experience_years, consultation_fee, registration_number,
                   registration_council, document_reference, verification_status,
                   is_verified, rejection_reason, submitted_at, verified_by,
                   verified_at, available_days, available_timings
            FROM "doctors"
            WHERE {" AND ".join(where)}
            ORDER BY
                CASE verification_status
                    WHEN 'Pending Verification' THEN 1
                    WHEN 'Under Review' THEN 2
                    WHEN 'Rejected' THEN 3
                    ELSE 4
                END,
                submitted_at DESC NULLS LAST,
                id DESC
            LIMIT %s;
        '''
        cur.execute(sql, params + [limit])
        rows = _rows_to_dicts(cur)
        con.close()
        return rows
    except Exception as exc:
        print(f"[DB-WARN] Error listing doctor applications: {exc}")
        return []


def get_verification_summary():
    """Counts per verification status for the admin verification dashboard."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT COALESCE(verification_status, 'Approved') AS status, COUNT(*)
            FROM "doctors"
            GROUP BY COALESCE(verification_status, 'Approved');
            """
        )
        counts = {row[0]: row[1] for row in cur.fetchall()}
        con.close()
        return {
            "pending": counts.get(STATUS_PENDING, 0) + counts.get(STATUS_UNDER_REVIEW, 0),
            "approved": counts.get(STATUS_APPROVED, 0),
            "rejected": counts.get(STATUS_REJECTED, 0),
            "suspended": counts.get(STATUS_SUSPENDED, 0),
            "by_status": counts,
        }
    except Exception as exc:
        print(f"[DB-WARN] Error building verification summary: {exc}")
        return {"pending": 0, "approved": 0, "rejected": 0, "suspended": 0, "by_status": {}}


def verify_doctor_application(doctor_id, action, admin_email, reason=None):
    """
    Approve, reject, suspend, reactivate or mark a doctor application under review.
    Returns True when a row was updated.
    """
    action_map = {
        "approve": (STATUS_APPROVED, True),
        "reject": (STATUS_REJECTED, False),
        "suspend": (STATUS_SUSPENDED, False),
        "reactivate": (STATUS_APPROVED, True),
        "under_review": (STATUS_UNDER_REVIEW, False),
    }
    if action not in action_map:
        return False

    new_status, verified_flag = action_map[action]

    try:
        con = get_connection()
        cur = con.cursor()

        if action == "approve":
            cur.execute(
                """
                UPDATE "doctors"
                SET verification_status = %s, is_verified = TRUE,
                    rejection_reason = NULL, verified_by = %s, verified_at = NOW()
                WHERE id = %s RETURNING id;
                """,
                [new_status, admin_email, doctor_id],
            )
        elif action in ("reject", "suspend"):
            default_reason = (
                "Registration credentials could not be verified."
                if action == "reject"
                else "Account suspended pending review."
            )
            cur.execute(
                """
                UPDATE "doctors"
                SET verification_status = %s, is_verified = FALSE,
                    rejection_reason = %s, verified_by = %s, verified_at = NOW()
                WHERE id = %s RETURNING id;
                """,
                [new_status, reason or default_reason, admin_email, doctor_id],
            )
        elif action == "under_review":
            cur.execute(
                """
                UPDATE "doctors"
                SET verification_status = %s, is_verified = FALSE
                WHERE id = %s RETURNING id;
                """,
                [new_status, doctor_id],
            )
        else:
            cur.execute(
                """
                UPDATE "doctors"
                SET verification_status = %s, is_verified = %s, rejection_reason = NULL
                WHERE id = %s RETURNING id;
                """,
                [new_status, verified_flag, doctor_id],
            )

        row = cur.fetchone()
        con.commit()
        con.close()
        return row is not None
    except Exception as exc:
        print(f"[DB-WARN] Error verifying doctor #{doctor_id}: {exc}")
        return False


def get_doctor_verification_record(doctor_id):
    """Return the verification-facing fields of a single doctor record."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, doctor, email, specialization, hospital,
                   "Location (Tamil Nadu)" AS location, qualifications, bio,
                   experience_years, consultation_fee, registration_number,
                   registration_council, document_reference, verification_status,
                   is_verified, rejection_reason, submitted_at, verified_by, verified_at,
                   available_days, available_timings
            FROM "doctors" WHERE id = %s;
            """,
            [doctor_id],
        )
        row = cur.fetchone()
        if not row:
            con.close()
            return None
        record = dict(zip([d[0] for d in cur.description], row))
        con.close()
        return {key: _serialise(val) for key, val in record.items()}
    except Exception as exc:
        print(f"[DB-WARN] Error reading verification record #{doctor_id}: {exc}")
        return None


# ==================== DOCTOR PROFILE CHANGE REQUESTS ====================

def create_profile_change_request(doctor_id, doctor_email, requested_changes, note=""):
    """
    Record a doctor's request to change verified professional details.

    The live profile is not altered: an administrator reviews the request first.
    """
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO doctor_profile_requests
                (doctor_id, doctor_email, requested_changes, request_note, status, created_at)
            VALUES (%s, %s, %s, %s, 'Pending Review', NOW())
            RETURNING id;
            """,
            [doctor_id, doctor_email, requested_changes, note],
        )
        new_id = cur.fetchone()[0]
        con.commit()
        con.close()
        return new_id
    except Exception as exc:
        print(f"[DB-WARN] Error creating profile change request: {exc}")
        return None


def get_profile_change_requests(status=None, limit=50):
    """List doctor profile change requests for administrator review."""
    try:
        con = get_connection()
        cur = con.cursor()
        where = "1=1"
        params = []
        if status:
            where = "r.status = %s"
            params.append(status)

        cur.execute(
            f"""
            SELECT r.id, r.doctor_id, r.doctor_email, r.requested_changes,
                   r.request_note, r.status, r.reviewed_by, r.reviewed_at,
                   r.created_at, d.doctor, d.specialization, d.hospital
            FROM doctor_profile_requests r
            LEFT JOIN "doctors" d ON d.id = r.doctor_id
            WHERE {where}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s;
            """,
            params + [limit],
        )
        rows = _rows_to_dicts(cur)
        con.close()
        return rows
    except Exception as exc:
        print(f"[DB-WARN] Error listing profile change requests: {exc}")
        return []


def resolve_profile_change_request(request_id, action, admin_email, note=None):
    """
    Approve or decline a doctor profile change request.

    Approving copies only the allowed credential fields onto the doctor record,
    so verified professional data changes exclusively through this audited path.
    """
    if action not in ("approve", "decline"):
        return False

    try:
        import json

        con = get_connection()
        cur = con.cursor()
        cur.execute(
            "SELECT doctor_id, requested_changes FROM doctor_profile_requests WHERE id = %s;",
            [request_id],
        )
        row = cur.fetchone()
        if not row:
            con.close()
            return False

        doctor_id, requested_changes = row

        if action == "approve" and requested_changes:
            try:
                changes = json.loads(requested_changes)
            except (ValueError, TypeError):
                changes = {}

            editable_fields = {
                "qualifications",
                "specialization",
                "hospital",
                "experience_years",
                "consultation_fee",
                "bio",
                "available_days",
                "available_timings",
            }
            assignments = []
            values = []
            for field, value in changes.items():
                if field in editable_fields:
                    assignments.append(f'"{field}" = %s')
                    values.append(value)

            if assignments:
                values.append(doctor_id)
                cur.execute(
                    f'UPDATE "doctors" SET {", ".join(assignments)} WHERE id = %s;',
                    values,
                )

        new_status = "Approved" if action == "approve" else "Declined"
        cur.execute(
            """
            UPDATE doctor_profile_requests
            SET status = %s, reviewed_by = %s, reviewed_at = NOW()
            WHERE id = %s;
            """,
            [new_status, admin_email, request_id],
        )
        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[DB-WARN] Error resolving profile change request #{request_id}: {exc}")
        return False


def get_pending_profile_requests_count():
    """Number of doctor profile change requests still awaiting review."""
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM doctor_profile_requests WHERE status = 'Pending Review';")
        count = cur.fetchone()[0]
        con.close()
        return count
    except Exception:
        return 0
