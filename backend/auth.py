"""
Authentication module — Hybrid OTP system.

Supports two modes controlled by USE_TWILIO in backend.config:
  • Development (USE_TWILIO=False): OTP stored in-memory dict, shown on screen,
    printed to console. Multiple users can login without Twilio.
  • Production (USE_TWILIO=True): OTP sent via real Twilio SMS. OTP is NEVER
    exposed in the API response for security.

The in-memory otp_store allows concurrent dev logins without session conflicts.
"""

from __future__ import annotations

import logging
import os
import random
import time
import hashlib
from functools import wraps
from typing import Any, Callable

from flask import current_app, jsonify, redirect, session, url_for

from backend.config import USE_TWILIO


logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))


# ---------------------------------------------------------------------------
# In-memory OTP store (used in BOTH modes for multi-user support)
# Format: { phone_number: { "code": "123456", "expires_at": float, "attempts_left": int } }
# ---------------------------------------------------------------------------
otp_store: dict[str, dict[str, Any]] = {}


def normalize_mobile_number(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    digits = "".join(character for character in value if character.isdigit())

    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Mobile number must contain between 10 and 15 digits.")

    return f"+{digits}"


def mask_phone_number(phone_number: str) -> str:
    digits = "".join(character for character in str(phone_number) if character.isdigit())
    if len(digits) <= 4:
        return f"+{digits}"
    return f"+{digits[:2]}******{digits[-2:]}"


def issue_otp(phone_number: str) -> str:
    """
    Generate a 6-digit OTP and store it.

    In development mode: stored in both otp_store (dict) AND session.
    In production mode:  stored in both otp_store (dict) AND session.
    The dict store enables multi-user dev testing.
    """
    # Clean up any expired OTPs first
    cleanup_expired_otps()

    code = f"{random.SystemRandom().randint(0, 999999):06d}"

    # Store in the in-memory dict (supports multiple concurrent users)
    otp_store[phone_number] = {
        "code": code,
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "attempts_left": OTP_MAX_ATTEMPTS,
    }

    # Also store in session (for session-based verification fallback)
    session["otp_record"] = {
        "phone_number": phone_number,
        "code_hash": hash_otp_code(phone_number, code),
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "attempts_left": OTP_MAX_ATTEMPTS,
    }

    # In development mode, print OTP to console for easy access
    if not USE_TWILIO:
        logger.info("═══════════════════════════════════════════")
        logger.info("  🛠️  DEVELOPMENT OTP for %s: %s", phone_number, code)
        logger.info("═══════════════════════════════════════════")
        print(f"\n{'='*50}")
        print(f"  🛠️  DEVELOPMENT OTP for {phone_number}: {code}")
        print(f"{'='*50}\n")

    return code


def verify_otp_code(phone_number: str, otp_code: str) -> tuple[bool, str | None]:
    """
    Verify the OTP code against the stored value.

    Checks the in-memory dict first (multi-user support), then falls
    back to session-based verification.
    """
    cleanup_expired_otps()
    otp_code = str(otp_code).strip()

    # --- Try in-memory dict verification first ---
    record = otp_store.get(phone_number)
    if record:
        if time.time() > float(record["expires_at"]):
            otp_store.pop(phone_number, None)
            clear_otp_record()
            return False, "OTP expired. Request a new code."

        if otp_code == record["code"]:
            # Success — clean up
            otp_store.pop(phone_number, None)
            clear_otp_record()
            return True, None
        else:
            record["attempts_left"] = int(record["attempts_left"]) - 1
            if record["attempts_left"] <= 0:
                otp_store.pop(phone_number, None)
                clear_otp_record()
                return False, "Too many invalid OTP attempts. Request a new code."
            return False, f"Invalid OTP. {record['attempts_left']} attempts remaining."

    # --- Fallback: session-based verification ---
    session_record = session.get("otp_record")
    if session_record is None:
        return False, "OTP not found or expired. Request a new code."

    if session_record.get("phone_number") != phone_number:
        return False, "OTP does not match the current mobile number."

    if time.time() > float(session_record["expires_at"]):
        clear_otp_record()
        return False, "OTP expired. Request a new code."

    if hash_otp_code(phone_number, otp_code) != session_record["code_hash"]:
        session_record["attempts_left"] = int(session_record["attempts_left"]) - 1
        if session_record["attempts_left"] <= 0:
            clear_otp_record()
            return False, "Too many invalid OTP attempts. Request a new code."
        session["otp_record"] = session_record
        return False, f"Invalid OTP. {session_record['attempts_left']} attempts remaining."

    clear_otp_record()
    return True, None


def cleanup_expired_otps() -> None:
    """Remove expired OTPs from both in-memory store and session."""
    now = time.time()

    # Clean in-memory store
    expired_phones = [
        phone for phone, rec in otp_store.items()
        if float(rec.get("expires_at", 0)) <= now
    ]
    for phone in expired_phones:
        otp_store.pop(phone, None)

    # Clean session
    record = session.get("otp_record")
    if record and float(record.get("expires_at", 0)) <= now:
        clear_otp_record()


def clear_otp_record() -> None:
    session.pop("otp_record", None)


def hash_otp_code(phone_number: str, otp_code: str) -> str:
    secret_key = str(current_app.config.get("SECRET_KEY", ""))
    payload = f"{phone_number}:{otp_code}:{secret_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def set_pending_phone(phone_number: str) -> None:
    session["pending_phone_number"] = phone_number


def get_pending_phone() -> str | None:
    return session.get("pending_phone_number")


def clear_pending_phone() -> None:
    session.pop("pending_phone_number", None)
    clear_otp_record()


def login_user(phone_number: str) -> None:
    session["authenticated"] = True
    session["user_phone_number"] = phone_number
    clear_pending_phone()


def logout_user() -> None:
    session.clear()


def is_authenticated() -> bool:
    return bool(session.get("authenticated") and session.get("user_phone_number"))


def current_user_phone() -> str | None:
    return session.get("user_phone_number")


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
