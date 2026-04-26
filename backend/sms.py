"""
SMS module — Hybrid Twilio integration with rate limiting.

Behaviour depends on USE_TWILIO from backend.config:
  • USE_TWILIO=True  → Send real SMS via Twilio API (rate-limited: 3 per 25 min)
  • USE_TWILIO=False → Log the message to console (dry-run), no API call

Rate limiting applies ONLY in production mode to protect Twilio credits.
Development mode has no limits.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from threading import Lock

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from backend.config import USE_TWILIO


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SMS Rate Limiter — 3 messages per 25 minutes per phone number
# Only enforced in production mode (USE_TWILIO=True)
# ---------------------------------------------------------------------------
SMS_RATE_LIMIT = 5                # max messages allowed
SMS_RATE_WINDOW = 5 * 60          # 5 minutes in seconds

_rate_lock = Lock()
_sms_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(phone: str) -> tuple[bool, int, int]:
    """
    Check if a phone number has exceeded the SMS rate limit.

    Returns:
        (allowed, remaining, retry_after_seconds)
        - allowed: True if message can be sent
        - remaining: how many messages left in the window
        - retry_after: seconds until the window resets (0 if allowed)
    """
    now = time.time()
    cutoff = now - SMS_RATE_WINDOW

    with _rate_lock:
        # Remove timestamps outside the current window
        _sms_timestamps[phone] = [
            ts for ts in _sms_timestamps[phone] if ts > cutoff
        ]
        count = len(_sms_timestamps[phone])
        remaining = max(0, SMS_RATE_LIMIT - count)

        if count >= SMS_RATE_LIMIT:
            # Calculate when the oldest message in window expires
            oldest = min(_sms_timestamps[phone])
            retry_after = int(oldest + SMS_RATE_WINDOW - now) + 1
            return False, 0, retry_after

        # Record this send
        _sms_timestamps[phone].append(now)
        return True, remaining - 1, 0


def get_rate_limit_status(phone: str) -> dict:
    """Get the current rate limit status for a phone number (for UI display)."""
    now = time.time()
    cutoff = now - SMS_RATE_WINDOW

    with _rate_lock:
        active = [ts for ts in _sms_timestamps.get(phone, []) if ts > cutoff]

    used = len(active)
    remaining = max(0, SMS_RATE_LIMIT - used)
    if active:
        oldest = min(active)
        resets_in = int(oldest + SMS_RATE_WINDOW - now)
    else:
        resets_in = 0

    return {
        "limit": SMS_RATE_LIMIT,
        "used": used,
        "remaining": remaining,
        "window_minutes": SMS_RATE_WINDOW // 60,
        "resets_in_seconds": max(0, resets_in),
    }


@dataclass
class SMSResult:
    success: bool
    provider: str
    sid: str | None = None
    error: str | None = None
    dry_run: bool = False
    rate_limited: bool = False
    rate_limit_remaining: int = -1
    rate_limit_retry_after: int = 0

    def to_dict(self) -> dict[str, str | bool | None | int]:
        return asdict(self)


def send_sms(phone: str, message: str, *, force_twilio: bool | None = None) -> SMSResult:
    """
    Send an SMS message with rate limiting.

    Args:
        force_twilio: If True, forces Twilio delivery regardless of server config.
                      If False, forces dev dry-run. If None, uses server config.

    Development mode:
      - Logs to console, no Twilio API call, no rate limit

    Production mode:
      - Rate limited to 3 messages per 25 minutes per phone number
      - Sends real SMS via Twilio if within limit
    """
    # Determine effective mode: per-request override > server config
    use_production = force_twilio if force_twilio is not None else USE_TWILIO

    # ── Development mode: skip Twilio entirely, no rate limit ──
    if not use_production:
        logger.info("📱 SMS dry-run to %s: %s", phone, message)
        print(f"  📱 SMS (dev) → {phone}: {message}")
        return SMSResult(success=True, provider="dev-console", dry_run=True)

    # ── Production mode: check rate limit first ──
    allowed, remaining, retry_after = _check_rate_limit(phone)

    if not allowed:
        mins = retry_after // 60
        secs = retry_after % 60
        logger.warning(
            "🚫 SMS rate limit exceeded for %s. Retry in %dm %ds.",
            phone, mins, secs,
        )
        return SMSResult(
            success=False,
            provider="twilio",
            error=f"SMS rate limit reached ({SMS_RATE_LIMIT} messages per {SMS_RATE_WINDOW // 60} minutes). Try again in {mins}m {secs}s.",
            rate_limited=True,
            rate_limit_remaining=0,
            rate_limit_retry_after=retry_after,
        )

    # ── Send via Twilio ──
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not account_sid or not auth_token or not from_number:
        return SMSResult(
            success=False,
            provider="twilio",
            error="Twilio credentials are not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER.",
            rate_limit_remaining=remaining,
        )

    try:
        twilio_message = get_twilio_client().messages.create(
            body=message,
            from_=from_number,
            to=phone,
        )
    except TwilioRestException as exc:
        return SMSResult(
            success=False, provider="twilio", error=str(exc),
            rate_limit_remaining=remaining,
        )
    except Exception as exc:  # pragma: no cover
        return SMSResult(
            success=False, provider="twilio", error=str(exc),
            rate_limit_remaining=remaining,
        )

    logger.info("✅ SMS sent to %s (%d/%d remaining)", phone, remaining, SMS_RATE_LIMIT)
    return SMSResult(
        success=True, provider="twilio", sid=twilio_message.sid,
        rate_limit_remaining=remaining,
    )


@lru_cache(maxsize=1)
def get_twilio_client() -> Client:
    return Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
