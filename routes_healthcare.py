"""
routes_healthcare.py - Role-based routes for the Patient, Doctor and Admin
dashboards.

Every route re-checks the signed-in session on the server. Selecting a role on
the login page is only a convenience for the login form; it is never treated as
authorisation. Each handler below verifies the session role and, where the data
belongs to a specific person, verifies ownership too.
"""

import json
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db_analytics import (
    get_appointment_operations,
    get_audit_logs,
    get_complaint_trends,
    get_dataset_health,
    get_doctor_performance,
    get_hospital_performance,
    get_ml_model_metrics,
)
from db_records import (
    create_review_report,
    get_doctor_improvement_insights,
    get_open_reports_count,
    get_patient_appointment_groups,
    get_patient_dashboard_summary,
    get_patient_feedback_history,
    get_patient_medical_history,
    get_review_reports,
    resolve_review_report,
    search_doctor_appointments,
)
from db_verification import (
    STATUS_PENDING,
    create_profile_change_request,
    get_doctor_applications,
    get_doctor_verification_record,
    get_pending_profile_requests_count,
    get_profile_change_requests,
    get_verification_summary,
    resolve_profile_change_request,
    verify_doctor_application,
)
from db import log_audit_action
from security import mask_email

healthcare = Blueprint("healthcare", __name__)


# ==================== SHARED GUARDS ====================

def _current_role():
    return session.get("user_role")


def _current_email():
    return session.get("user_email", "")


def _login_redirect():
    return redirect(url_for("login", message="Please sign in to continue."))


def _require_patient():
    """Return a redirect for anyone who is not a signed-in patient."""
    if not session.get("logged_in"):
        return _login_redirect()
    if _current_role() not in ("patient", "user"):
        return redirect(url_for("home"))
    return None


def _require_doctor_session():
    if not session.get("logged_in"):
        return _login_redirect()
    if _current_role() != "doctor":
        return redirect(url_for("home"))
    if session.get("doctor_verified") is False:
        return redirect(url_for("healthcare.doctor_pending"))
    return None


def _require_admin_session():
    if not session.get("logged_in"):
        return _login_redirect()
    if _current_role() != "admin":
        return redirect(url_for("home"))
    return None


def _audit(action, details=""):
    try:
        log_audit_action(_current_email() or "unknown", _current_role() or "unknown", action, details)
    except Exception:
        pass


# ==================== PATIENT ROUTES ====================

@healthcare.route("/patient/dashboard")
def patient_dashboard():
    guard = _require_patient()
    if guard:
        return guard

    email = _current_email()
    summary = get_patient_dashboard_summary(email)

    unread = 0
    try:
        from db import get_unread_notification_count
        unread = get_unread_notification_count(email)
    except Exception:
        pass

    return render_template(
        "patient_dashboard.html",
        summary=summary,
        patient_name=session.get("user_name", "Patient"),
        patient_email=email,
        unread_count=unread,
    )


@healthcare.route("/medical-history")
def medical_history():
    guard = _require_patient()
    if guard:
        return guard

    email = _current_email()
    records = get_patient_medical_history(email)
    groups = get_patient_appointment_groups(email)

    return render_template(
        "medical_history.html",
        records=records,
        groups=groups,
        patient_email=email,
    )


@healthcare.route("/my-feedback")
def my_feedback():
    guard = _require_patient()
    if guard:
        return guard

    email = _current_email()
    feedback = get_patient_feedback_history(email)
    summary = get_patient_dashboard_summary(email)

    return render_template(
        "my_feedback.html",
        feedback=feedback,
        awaiting_feedback=summary["awaiting_feedback"],
        patient_email=email,
    )
# ==================== DOCTOR ROUTES ====================

@healthcare.route("/doctor/pending")
def doctor_pending():
    """Landing page for a doctor whose credentials are not yet approved."""
    if not session.get("logged_in"):
        return _login_redirect()

    record = None
    if _current_role() == "doctor" and session.get("doctor_id"):
        record = get_doctor_verification_record(session.get("doctor_id"))

    return render_template(
        "doctor_pending.html",
        record=record,
        doctor_name=session.get("user_name", "Doctor"),
        verification_status=(record or {}).get("verification_status", STATUS_PENDING),
    )


@healthcare.route("/doctor/appointments")
def doctor_appointment_search():
    """Search and filter the signed-in doctor's own appointment record."""
    guard = _require_doctor_session()
    if guard:
        return guard

    doctor_name = session.get("user_name", "")
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    appointments = search_doctor_appointments(
        doctor_name,
        status=status or None,
        search=search or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )

    status_totals = {}
    for apt in search_doctor_appointments(doctor_name):
        key = apt.get("status") or "Unknown"
        status_totals[key] = status_totals.get(key, 0) + 1

    return render_template(
        "doctor_appointment_search.html",
        appointments=appointments,
        status_totals=status_totals,
        filters={
            "status": status,
            "q": search,
            "date_from": date_from,
            "date_to": date_to,
        },
        doctor_name=doctor_name,
    )


@healthcare.route("/doctor/insights")
def doctor_insights():
    """Month-wise sentiment trend and service-quality indicators."""
    guard = _require_doctor_session()
    if guard:
        return guard

    doctor_name = session.get("user_name", "")
    insights = get_doctor_improvement_insights(doctor_name)

    return render_template(
        "doctor_insights.html",
        insights=insights,
        doctor_name=doctor_name,
    )


@healthcare.route("/doctor/profile/request", methods=["POST"])
def doctor_profile_request():
    """
    Submit a change request for verified professional details.

    The live profile is not modified: an administrator reviews the request so
    credential data can never be self-edited without verification.
    """
    guard = _require_doctor_session()
    if guard:
        return guard

    requested = {}
    for field in (
        "qualifications",
        "specialization",
        "hospital",
        "experience_years",
        "consultation_fee",
        "bio",
        "available_days",
        "available_timings",
    ):
        value = request.form.get(field, "").strip()
        if value:
            requested[field] = value

    note = request.form.get("request_note", "").strip()

    if not requested:
        return redirect(url_for("doctor_dashboard", error="Please change at least one field before submitting a request."))

    doctor_id = session.get("doctor_id")
    request_id = create_profile_change_request(
        doctor_id, _current_email(), json.dumps(requested), note
    )
    if not request_id:
        return redirect(url_for("doctor_dashboard", error="Could not submit the profile change request."))

    _audit("Profile Change Requested", f"Doctor #{doctor_id} requested changes to {', '.join(requested.keys())}")
    return redirect(
        url_for(
            "doctor_dashboard",
            success="Your profile change request has been sent to the administrator for verification.",
        )
    )


@healthcare.route("/doctor/review/<int:review_id>/flag", methods=["POST"])
def doctor_flag_review(review_id):
    """Report a review to the administrator without exposing reviewer identity."""
    guard = _require_doctor_session()
    if guard:
        return guard

    reason = request.form.get("reason", "Flagged by practitioner").strip()
    report_id = create_review_report(review_id, "doctor", _current_email(), reason)
    if not report_id:
        return redirect(url_for("doctor_dashboard", error="Could not file the report."))

    _audit("Report Review", f"Doctor reported review #{review_id}: {reason}")
    return redirect(
        url_for(
            "doctor_dashboard",
            success="Review reported. The administrator will investigate without revealing your patient's identity to you, or yours to them.",
        )
    )
# ==================== ADMIN ROUTES ====================

@healthcare.route("/admin/verify", methods=["POST"])
def admin_verify_doctor():
    """
    Approve, reject, suspend, reactivate or mark a doctor application under
    review. This is the only path that can make a doctor publicly visible.
    """
    guard = _require_admin_session()
    if guard:
        return guard

    doctor_id = int(request.form.get("doctor_id", 0) or 0)
    action = request.form.get("action", "").strip()
    reason = request.form.get("reason", "").strip()

    if not doctor_id or action not in ("approve", "reject", "suspend", "reactivate", "under_review"):
        return redirect(url_for("admin_dashboard", error="Invalid verification request."))

    success = verify_doctor_application(doctor_id, action, _current_email(), reason or None)
    if not success:
        return redirect(url_for("admin_dashboard", error=f"Could not update doctor #{doctor_id}."))

    record = get_doctor_verification_record(doctor_id)
    doctor_label = (record or {}).get("doctor") or f"#{doctor_id}"

    action_labels = {
        "approve": "Approved Doctor Registration",
        "reject": "Rejected Doctor Registration",
        "suspend": "Suspended Doctor Account",
        "reactivate": "Reactivated Doctor Account",
        "under_review": "Marked Doctor Under Review",
    }
    details = f"{action_labels[action]}: {doctor_label}"
    if reason:
        details += f" | Reason: {reason}"
    _audit(action_labels[action], details)

    # Notify the doctor so their dashboard reflects the decision immediately.
    try:
        from db import create_notification
        if record and record.get("email"):
            if action == "approve":
                title = "Registration Approved"
                message = (
                    "Your medical registration has been verified. Your profile is now "
                    "eligible to appear in public doctor search results."
                )
            elif action == "reject":
                title = "Registration Not Approved"
                message = f"Your registration could not be verified. Reason: {reason or 'Credentials could not be confirmed.'}"
            elif action == "suspend":
                title = "Account Suspended"
                message = f"Your account has been suspended. Reason: {reason or 'Pending administrative review.'}"
            elif action == "reactivate":
                title = "Account Reactivated"
                message = "Your account has been reactivated and your profile is publicly visible again."
            else:
                title = "Verification Under Review"
                message = "Your registration documents are being reviewed by an administrator."
            create_notification(record["email"], "doctor", title, message, "verification", doctor_id)
    except Exception:
        pass

    messages = {
        "approve": f"{doctor_label} approved and now eligible for public search.",
        "reject": f"{doctor_label} rejected. The reason has been recorded.",
        "suspend": f"{doctor_label} suspended and removed from public search.",
        "reactivate": f"{doctor_label} reactivated.",
        "under_review": f"{doctor_label} marked under review.",
    }
    return redirect(url_for("admin_dashboard", success=messages[action]))


@healthcare.route("/admin/doctor/update", methods=["POST"])
def admin_update_doctor():
    """Edit a doctor's verified professional details."""
    guard = _require_admin_session()
    if guard:
        return guard

    doctor_id = int(request.form.get("doctor_id", 0) or 0)
    if not doctor_id:
        return redirect(url_for("admin_dashboard", error="Doctor ID is required."))

    update_fields = {}
    text_fields = (
        "doctor_name", "specialization", "hospital", "department",
        "location", "qualifications", "bio", "registration_number",
        "registration_council", "available_days", "available_timings",
    )
    column_map = {
        "doctor_name": "doctor",
        "department": "disease",
        "location": 'Location (Tamil Nadu)',
    }
    for field in text_fields:
        if field in request.form:
            value = request.form.get(field, "").strip()
            update_fields[column_map.get(field, field)] = value

    for field in ("experience_years", "consultation_fee"):
        if field in request.form and request.form.get(field, "").strip():
            try:
                update_fields[field] = int(request.form.get(field))
            except (TypeError, ValueError):
                pass

    if not update_fields:
        return redirect(url_for("admin_dashboard", error="No changes were submitted."))

    try:
        from db import update_doctor_details
        success = update_doctor_details(doctor_id, update_fields)
    except Exception as exc:
        print(f"[ADMIN-WARN] Doctor update failed: {exc}")
        success = False

    if not success:
        return redirect(url_for("admin_dashboard", error=f"Could not update doctor #{doctor_id}."))

    _audit(
        "Update Doctor Profile",
        f"Administrator updated doctor #{doctor_id}: {', '.join(update_fields.keys())}",
    )
    return redirect(url_for("admin_dashboard", success=f"Doctor #{doctor_id} updated successfully."))


@healthcare.route("/admin/patient/update", methods=["POST"])
def admin_update_patient():
    """
    Edit permitted patient account fields.

    The stored password hash is never readable here; a reset is issued through
    update_patient_password instead of displaying or overwriting the credential.
    """
    guard = _require_admin_session()
    if guard:
        return guard

    email = request.form.get("email", "").strip().lower()
    if not email:
        return redirect(url_for("admin_dashboard", error="Patient email is required."))

    update_fields = {}
    for field in ("first_name", "last_name", "country"):
        if field in request.form:
            update_fields[field] = request.form.get(field, "").strip()

    if "age" in request.form and request.form.get("age", "").strip():
        try:
            update_fields["age"] = int(request.form.get("age"))
        except (TypeError, ValueError):
            pass

    if update_fields:
        try:
            from db import update_patient_record
            update_patient_record(email, update_fields)
        except Exception as exc:
            print(f"[ADMIN-WARN] Patient update failed: {exc}")

    new_password = request.form.get("new_password", "").strip()
    if new_password:
        from security import validate_password_strength, hash_password
        strength_error = validate_password_strength(new_password)
        if strength_error:
            return redirect(url_for("admin_dashboard", error=strength_error))
        try:
            from db import update_patient_password
            update_patient_password(email, hash_password(new_password))
        except Exception as exc:
            print(f"[ADMIN-WARN] Patient password reset failed: {exc}")

    _audit(
        "Update Patient Account",
        f"Administrator updated patient {email}"
        + (" (password reset issued)" if new_password else ""),
    )
    return redirect(url_for("admin_dashboard", success=f"Patient account {email} updated."))


@healthcare.route("/admin/patient/status", methods=["POST"])
def admin_patient_status():
    """Deactivate or reactivate a patient account instead of erasing history."""
    guard = _require_admin_session()
    if guard:
        return guard

    email = request.form.get("email", "").strip().lower()
    status = request.form.get("status", "").strip().lower()

    if not email or status not in ("active", "inactive", "suspended"):
        return redirect(url_for("admin_dashboard", error="Invalid account status request."))
    if email == "admin@healthcare.com":
        return redirect(url_for("admin_dashboard", error="The primary administrator account cannot be deactivated."))

    try:
        from db import set_patient_status
        set_patient_status(email, status)
    except Exception as exc:
        print(f"[ADMIN-WARN] Patient status change failed: {exc}")
        return redirect(url_for("admin_dashboard", error="Could not update the account status."))

    _audit("Change Patient Status", f"Administrator set {email} to '{status}'")
    return redirect(url_for("admin_dashboard", success=f"Patient {email} is now '{status}'."))


@healthcare.route("/admin/hospital/update", methods=["POST"])
def admin_update_hospital():
    """Edit hospital details, facilities and contact information."""
    guard = _require_admin_session()
    if guard:
        return guard

    hosp_id = int(request.form.get("hospital_id", 0) or 0)
    if not hosp_id:
        return redirect(url_for("admin_dashboard", error="Hospital ID is required."))

    data = {
        "name": request.form.get("name", "").strip(),
        "location": request.form.get("location", "").strip(),
        "facilities": request.form.get("facilities", "").strip(),
        "contact_phone": request.form.get("contact_phone", "").strip(),
        "emergency_available": request.form.get("emergency_available") == "on",
    }

    try:
        from db import update_hospital_record
        success = update_hospital_record(hosp_id, data)
    except Exception as exc:
        print(f"[ADMIN-WARN] Hospital update failed: {exc}")
        success = False

    if not success:
        return redirect(url_for("admin_dashboard", error=f"Could not update hospital #{hosp_id}."))

    _audit("Update Hospital", f"Administrator updated hospital #{hosp_id}: {data['name']}")
    return redirect(url_for("admin_dashboard", success=f"Hospital {data['name']} updated."))


@healthcare.route("/admin/appointments")
def admin_appointments():
    """Operational appointment monitoring (no clinical decision authority)."""
    guard = _require_admin_session()
    if guard:
        return guard

    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()

    operations = get_appointment_operations(limit=150, status=status or None, search=search or None)
    operations["filters"] = {"status": status, "q": search}

    return render_template("admin_appointments.html", operations=operations)


@healthcare.route("/admin/analytics")
def admin_analytics():
    """Hospital-wise and doctor-wise patient-feedback indicators."""
    guard = _require_admin_session()
    if guard:
        return guard

    sort_by = request.args.get("sort", "feedback_rating").strip()

    return render_template(
        "admin_analytics.html",
        hospitals=get_hospital_performance(limit=30),
        doctors=get_doctor_performance(limit=30, sort_by=sort_by),
        trends=get_complaint_trends(),
        sort_by=sort_by,
    )


@healthcare.route("/admin/ml")
def admin_ml_monitoring():
    """Live NLP sentiment-model monitoring and the uncertain-classification queue."""
    guard = _require_admin_session()
    if guard:
        return guard

    return render_template("admin_ml.html", metrics=get_ml_model_metrics())


@healthcare.route("/admin/dataset")
def admin_dataset():
    """Relational dataset inventory and real integrity checks."""
    guard = _require_admin_session()
    if guard:
        return guard

    return render_template("admin_dataset.html", health=get_dataset_health())


@healthcare.route("/admin/security")
def admin_security():
    """Filterable audit trail of administrative, doctor and patient actions."""
    guard = _require_admin_session()
    if guard:
        return guard

    role = request.args.get("role", "").strip()
    search = request.args.get("q", "").strip()

    audit = get_audit_logs(limit=150, role=role or None, search=search or None)
    audit["filters"] = {"role": role, "q": search}
    audit["open_reports"] = get_open_reports_count()

    return render_template(
        "admin_security.html",
        audit=audit,
        reports=get_review_reports(status="Open"),
        profile_requests=get_profile_change_requests(status="Pending Review"),
    )


@healthcare.route("/admin/report/resolve", methods=["POST"])
def admin_resolve_report():
    """
    Close a review report.

    The reviewer's identity is visible here because moderation requires it, and
    the access itself is written to the audit log.
    """
    guard = _require_admin_session()
    if guard:
        return guard

    report_id = int(request.form.get("report_id", 0) or 0)
    action = request.form.get("action", "").strip()
    note = request.form.get("note", "").strip()

    if not report_id or action not in ("uphold", "dismiss"):
        return redirect(url_for("admin_security", error="Invalid moderation request."))

    success = resolve_review_report(report_id, action, _current_email(), note or None)
    if not success:
        return redirect(url_for("admin_security", error=f"Could not resolve report #{report_id}."))

    _audit(
        "Moderate Reported Review",
        f"Administrator {'upheld' if action == 'uphold' else 'dismissed'} report #{report_id}",
    )
    label = "removed from public view" if action == "uphold" else "retained and cleared"
    return redirect(url_for("admin_security", success=f"Report #{report_id} reviewed: review {label}."))


@healthcare.route("/admin/profile-request/resolve", methods=["POST"])
def admin_resolve_profile_request():
    """Approve or decline a doctor's requested change to verified credentials."""
    guard = _require_admin_session()
    if guard:
        return guard

    request_id = int(request.form.get("request_id", 0) or 0)
    action = request.form.get("action", "").strip()

    if not request_id or action not in ("approve", "decline"):
        return redirect(url_for("admin_security", error="Invalid profile request action."))

    success = resolve_profile_change_request(request_id, action, _current_email())
    if not success:
        return redirect(url_for("admin_security", error=f"Could not resolve request #{request_id}."))

    _audit(
        "Resolve Doctor Profile Request",
        f"Administrator {'approved' if action == 'approve' else 'declined'} profile change request #{request_id}",
    )
    return redirect(
        url_for("admin_security", success=f"Profile change request #{request_id} {action}d.")
    )
