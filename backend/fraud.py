from __future__ import annotations

from datetime import datetime
from typing import Any

from utils import LOCATION_RISK, MERCHANT_RISK, clean_card_number


MAX_HISTORY_ITEMS = 25


def parse_time_value(raw_value: Any):
    if raw_value is None:
        raise ValueError("Transaction time is required.")

    value = str(raw_value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError("Transaction time must be in HH:MM format.")


def normalize_transaction_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    card_number = str(payload.get("card_number", "")).strip()
    holder_name = str(payload.get("card_holder_name", "")).strip()
    location = str(payload.get("location", "")).strip()
    merchant_type = str(payload.get("merchant_type", "")).strip()

    try:
        amount = float(payload.get("transaction_amount", 0))
    except (TypeError, ValueError):
        amount = 0.0
        errors.append("Transaction amount must be numeric.")

    try:
        transaction_time = parse_time_value(payload.get("transaction_time"))
    except ValueError as exc:
        errors.append(str(exc))
        transaction_time = None

    digits = clean_card_number(card_number)
    if len(digits) < 13 or len(digits) > 19:
        errors.append("Card number must contain between 13 and 19 digits.")
    if not holder_name:
        errors.append("Card holder name is required.")
    if amount <= 0:
        errors.append("Transaction amount must be greater than zero.")
    if location not in LOCATION_RISK:
        errors.append("Location must be either Domestic or International.")
    if merchant_type not in MERCHANT_RISK:
        errors.append("Select a valid merchant type.")

    if errors:
        return None, errors

    return (
        {
            "card_number": card_number,
            "card_holder_name": holder_name,
            "transaction_amount": amount,
            "transaction_time": transaction_time,
            "location": location,
            "merchant_type": merchant_type,
        },
        [],
    )


def sanitize_history(history_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(history_payload, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for item in history_payload[:MAX_HISTORY_ITEMS]:
        if not isinstance(item, dict):
            continue

        card_last4 = str(item.get("card_last4", "")).strip()
        if not card_last4:
            masked = str(item.get("card_masked", "")).strip()
            card_last4 = clean_card_number(masked)[-4:]

        try:
            amount = float(item.get("transaction_amount", 0))
        except (TypeError, ValueError):
            continue

        decision = str(item.get("decision", "")).strip()
        if not card_last4 or not decision:
            continue

        cleaned.append(
            {
                "card_last4": card_last4[-4:],
                "transaction_amount": amount,
                "decision": decision,
            }
        )
    return cleaned


def build_alert_message(result: dict[str, Any]) -> str | None:
    risk_score = float(result.get("risk_score", 0.0))

    if risk_score > 70 or result.get("decision") == "Transaction Blocked":
        return "Fraud detected. Transaction blocked."
    if 30 <= risk_score < 70 or result.get("decision") == "OTP Verification Required":
        return "Suspicious transaction. OTP verification required."
    return None
