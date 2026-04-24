"""
Application configuration module.

Controls the OTP delivery mode and other environment-specific settings.
Switch USE_TWILIO to True for production SMS delivery, or keep False for
development mode where OTPs are displayed on-screen and printed to console.

Usage:
    from backend.config import USE_TWILIO, OTP_MODE_LABEL
"""

from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# OTP Mode Configuration
# ---------------------------------------------------------------------------
# Set USE_TWILIO = True  → Production mode: OTP sent via real Twilio SMS
# Set USE_TWILIO = False → Development mode: OTP shown on screen & console
#
# Can also be controlled via the environment variable OTP_MODE:
#   OTP_MODE=twilio   → production
#   OTP_MODE=dev      → development (default)
# ---------------------------------------------------------------------------
_otp_mode_env = os.getenv("OTP_MODE", "dev").strip().lower()

USE_TWILIO: bool = _otp_mode_env in ("twilio", "production", "true", "1")

# Human-readable labels for the UI
OTP_MODE_LABEL: str = "Production" if USE_TWILIO else "Development"
OTP_MODE_DESCRIPTION: str = (
    "OTP is delivered via Twilio SMS to verified numbers only."
    if USE_TWILIO
    else "OTP is displayed on-screen for testing. No SMS is sent."
)
OTP_MODE_ICON: str = "🔒" if USE_TWILIO else "🛠️"
