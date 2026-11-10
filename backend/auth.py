"""Session authentication and short-lived email OTP verification."""

from __future__ import annotations

import hashlib
import os
import random
import re
import time
from functools import wraps
from typing import Any, Callable

from flask import current_app, jsonify, redirect, session, url_for


OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

# The session contains a hashed fallback so verification also works when a
# serverless platform handles the two requests in different function instances.
otp_store: dict[str, dict[str, Any]] = {}


def normalize_mobile_number(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Mobile number must contain between 10 and 15 digits.")
    return f"+{digits}"


def normalize_email_address(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+", value):
        raise ValueError("Enter a valid email address.")
    return value


def mask_phone_number(phone_number: str) -> str:
    digits = "".join(character for character in str(phone_number) if character.isdigit())
    if len(digits) <= 4:
        return f"+{digits}"
    return f"+{digits[:2]}******{digits[-2:]}"


def mask_email_address(email_address: str) -> str:
    local_part, separator, domain = email_address.partition("@")
    if not separator:
        return "your email address"
    visible = local_part[:1] or "*"
    return f"{visible}{'*' * min(max(len(local_part) - 1, 3), 8)}@{domain}"


def _otp_identity(phone_number: str, email_address: str) -> str:
    return f"{phone_number}:{email_address}"


def issue_otp(phone_number: str, email_address: str) -> str:
    """Generate a six-digit OTP, retaining only its hash in server state."""
    cleanup_expired_otps()
    clear_otp_record()

    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    identity = _otp_identity(phone_number, email_address)
    expires_at = time.time() + OTP_TTL_SECONDS
    code_hash = hash_otp_code(identity, code)
    record = {
        "phone_number": phone_number,
        "email_address": email_address,
        "identity": identity,
        "code_hash": code_hash,
        "expires_at": expires_at,
        "attempts_left": OTP_MAX_ATTEMPTS,
    }
    otp_store[identity] = dict(record)
    session["otp_record"] = dict(record)
    return code


def verify_otp_code(
    phone_number: str, email_address: str, otp_code: str
) -> tuple[bool, str | None]:
    cleanup_expired_otps()
    identity = _otp_identity(phone_number, email_address)
    submitted_hash = hash_otp_code(identity, str(otp_code).strip())

    record = otp_store.get(identity) or session.get("otp_record")
    if record is None:
        return False, "OTP not found or expired. Request a new code."

    if record.get("identity") != identity:
        return False, "Verify the code using the same phone number and email address."

    if time.time() >= float(record.get("expires_at", 0)):
        clear_otp_record(identity)
        return False, "OTP expired. Request a new code."

    if submitted_hash != record.get("code_hash"):
        record["attempts_left"] = int(record.get("attempts_left", OTP_MAX_ATTEMPTS)) - 1
        if record["attempts_left"] <= 0:
            clear_otp_record(identity)
            return False, "Too many invalid OTP attempts. Request a new code."
        session["otp_record"] = record
        if identity in otp_store:
            otp_store[identity] = dict(record)
        return False, f"Invalid OTP. {record['attempts_left']} attempts remaining."

    clear_otp_record(identity)
    return True, None


def cleanup_expired_otps() -> None:
    now = time.time()
    expired = [
        identity
        for identity, record in otp_store.items()
        if float(record.get("expires_at", 0)) <= now
    ]
    for identity in expired:
        otp_store.pop(identity, None)

    record = session.get("otp_record")
    if record and float(record.get("expires_at", 0)) <= now:
        clear_otp_record()


def clear_otp_record(identity: str | None = None) -> None:
    record = session.pop("otp_record", None)
    stored_identity = identity or (record.get("identity") if record else None)
    if stored_identity:
        otp_store.pop(str(stored_identity), None)


def hash_otp_code(identity: str, otp_code: str) -> str:
    secret_key = str(current_app.config.get("SECRET_KEY", ""))
    payload = f"{identity}:{otp_code}:{secret_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def set_pending_login(phone_number: str, email_address: str) -> None:
    clear_pending_login()
    session["pending_phone_number"] = phone_number
    session["pending_email_address"] = email_address


def get_pending_phone() -> str | None:
    return session.get("pending_phone_number")


def get_pending_email() -> str | None:
    return session.get("pending_email_address")


def clear_pending_login() -> None:
    clear_otp_record()
    session.pop("pending_phone_number", None)
    session.pop("pending_email_address", None)


def login_user(phone_number: str, email_address: str) -> None:
    session["authenticated"] = True
    session["user_phone_number"] = phone_number
    session["user_email_address"] = email_address
    clear_pending_login()


def logout_user() -> None:
    session.clear()


def is_authenticated() -> bool:
    return bool(
        session.get("authenticated")
        and session.get("user_phone_number")
        and session.get("user_email_address")
    )


def current_user_phone() -> str | None:
    return session.get("user_phone_number")


def current_user_email() -> str | None:
    return session.get("user_email_address")


def login_required_page(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not is_authenticated():
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def login_required_api(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not is_authenticated():
            return jsonify({"ok": False, "errors": ["Authentication required."], "redirect_url": url_for("login")}), 401
        return view(*args, **kwargs)

    return wrapped
