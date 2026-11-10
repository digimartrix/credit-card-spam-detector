"""Application configuration for email OTP delivery."""

from __future__ import annotations

import os


_default_mode = "email" if os.getenv("VERCEL") else "dev"
OTP_MODE = os.getenv("OTP_MODE", _default_mode).strip().lower()
if OTP_MODE in {"production", "true", "1"}:
    OTP_MODE = "email"
elif OTP_MODE in {"development", "false", "0"}:
    OTP_MODE = "dev"

if OTP_MODE not in {"dev", "email"}:
    raise ValueError("OTP_MODE must be 'dev' or 'email'.")

USE_EMAIL: bool = OTP_MODE == "email"
DEFAULT_OTP_MODE: str = OTP_MODE
ALLOW_DEV_OTP: bool = (
    not bool(os.getenv("VERCEL"))
    or os.getenv("ALLOW_DEV_OTP", "").strip().lower() in {"true", "1", "yes"}
)

OTP_MODE_LABEL: str = "Email OTP" if USE_EMAIL else "Development"
OTP_MODE_DESCRIPTION: str = (
    "OTP is sent to your email address using the configured email provider."
    if USE_EMAIL
    else "OTP is displayed on-screen for local testing. No email is sent."
)
OTP_MODE_ICON: str = "✉️" if USE_EMAIL else "🛠️"
