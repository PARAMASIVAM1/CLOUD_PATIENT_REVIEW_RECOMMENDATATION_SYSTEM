"""
security.py - Password hashing, verification and login rate limiting.

Passwords are never stored in plain text. New accounts store PBKDF2-HMAC-SHA256
hashes in the form  pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>.

Legacy plain-text records created before this module existed are still accepted
once so that existing accounts keep working, and are transparently upgraded to a
hash the next time the owner logs in successfully.
"""

import hashlib
import hmac
import os
import re
import time
from datetime import datetime, timedelta

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260000
SALT_BYTES = 16
HASH_NAME = "sha256"

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300
LOGIN_LOCKOUT_SECONDS = 300

_LOGIN_ATTEMPTS = {}

PASSWORD_MIN_LENGTH = 10


def hash_password(raw_password):
    """Return a salted PBKDF2 hash string for the supplied password."""
    if raw_password is None:
        raw_password = ""
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        HASH_NAME, str(raw_password).encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "{}${}${}${}".format(
        PBKDF2_ALGORITHM,
        PBKDF2_ITERATIONS,
        salt.hex(),
        derived.hex(),
    )


def is_hashed(value):
    """True when the stored value already looks like a generated hash."""
    if not value:
        return False
    return str(value).startswith(PBKDF2_ALGORITHM + "$") and str(value).count("$") == 3


def verify_password(raw_password, stored_value):
    """
    Check a candidate password against the stored value.

    Returns (is_valid, needs_upgrade). ``needs_upgrade`` is True when the stored
    value was legacy plain text and should be replaced by a hash.
    """
    if raw_password is None or stored_value is None:
        return False, False

    stored_text = str(stored_value)

    if not is_hashed(stored_text):
        # Legacy plain-text record: constant-time compare then request an upgrade.
        valid = hmac.compare_digest(stored_text, str(raw_password))
        return valid, valid

    try:
        _, iterations_text, salt_hex, expected_hex = stored_text.split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, TypeError):
        return False, False

    derived = hashlib.pbkdf2_hmac(
        HASH_NAME, str(raw_password).encode("utf-8"), salt, iterations
    )
    valid = hmac.compare_digest(derived.hex(), expected_hex)
    needs_upgrade = valid and iterations < PBKDF2_ITERATIONS
    return valid, needs_upgrade


def validate_password_strength(raw_password):
    """Return an error message when the password is too weak, otherwise None."""
    password = str(raw_password or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one symbol (like @ or #)."
    return None


def _attempt_key(identifier, client_ip):
    return "{}|{}".format(str(identifier or "").strip().lower(), str(client_ip or "unknown"))


def register_failed_login(identifier, client_ip):
    """Record a failed login attempt and return the remaining attempts."""
    key = _attempt_key(identifier, client_ip)
    now = time.time()
    entry = _LOGIN_ATTEMPTS.get(key) or {"count": 0, "first": now, "locked_until": 0}

    if now - entry["first"] > LOGIN_WINDOW_SECONDS:
        entry = {"count": 0, "first": now, "locked_until": 0}

    entry["count"] += 1
    if entry["count"] >= LOGIN_MAX_ATTEMPTS:
        entry["locked_until"] = now + LOGIN_LOCKOUT_SECONDS
    _LOGIN_ATTEMPTS[key] = entry
    return max(LOGIN_MAX_ATTEMPTS - entry["count"], 0)


def clear_login_attempts(identifier, client_ip):
    """Reset the failure counter after a successful authentication."""
    _LOGIN_ATTEMPTS.pop(_attempt_key(identifier, client_ip), None)


def is_login_locked(identifier, client_ip):
    """Return seconds remaining in a lockout, or 0 when the account is free."""
    entry = _LOGIN_ATTEMPTS.get(_attempt_key(identifier, client_ip))
    if not entry:
        return 0
    remaining = int(entry.get("locked_until", 0) - time.time())
    if remaining > 0:
        return remaining
    if time.time() - entry.get("first", 0) > LOGIN_WINDOW_SECONDS:
        _LOGIN_ATTEMPTS.pop(_attempt_key(identifier, client_ip), None)
    return 0


def login_lockout_message(seconds_remaining):
    minutes = max(1, int(round(seconds_remaining / 60.0)))
    return (
        "Too many failed sign-in attempts. Please wait about "
        f"{minutes} minute(s) before trying again."
    )


def mask_email(email):
    """Mask an email address so it can be shown without exposing the identity."""
    text = str(email or "").strip()
    if "@" not in text:
        return "Hidden"
    local, _, domain = text.partition("@")
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


def anonymised_reviewer_label(patient_email):
    """Stable, non-reversible reviewer label used on doctor-facing screens."""
    digest = hashlib.sha256(str(patient_email or "anonymous").encode("utf-8")).hexdigest()
    return "Verified Patient #" + digest[:6].upper()


def audit_timestamp():
    return datetime.now().isoformat(timespec="seconds")


def retention_cutoff(days):
    return datetime.now() - timedelta(days=days)
