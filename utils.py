from __future__ import annotations

import hashlib
import re
from datetime import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


MODEL_PATH = Path(__file__).resolve().with_name("fraud_model.pkl")
PRIMARY_BLUE = "#2563EB"
SUCCESS_GREEN = "#16A34A"
WARNING_AMBER = "#F59E0B"
DANGER_RED = "#DC2626"

MERCHANT_RISK = {
    "Grocery": 0.08,
    "Fuel": 0.14,
    "Dining": 0.18,
    "Healthcare": 0.10,
    "Utilities": 0.12,
    "Entertainment": 0.20,
    "Travel": 0.42,
    "Electronics": 0.46,
    "Online Retail": 0.36,
    "Digital Goods": 0.55,
    "Cash Withdrawal": 0.72,
}

LOCATION_RISK = {
    "Domestic": 0.08,
    "International": 0.48,
}

FAKE_NAMES = [
    "Aarav Mehta",
    "Priya Nair",
    "Daniel Brooks",
    "Sophia Carter",
    "Riya Shah",
    "Michael Torres",
]


def load_artifact(model_path: Path = MODEL_PATH) -> dict[str, Any]:
    return joblib.load(model_path)


def clean_card_number(card_number: str) -> str:
    return re.sub(r"\D", "", card_number or "")


def mask_card_number(card_number: str) -> str:
    digits = clean_card_number(card_number)
    if not digits:
        return "**** **** **** ****"
    visible = digits[-4:].rjust(4, "0")
    return f"**** **** **** {visible}"


def card_signature_seed(card_number: str, holder_name: str) -> int:
    base = f"{clean_card_number(card_number)}|{holder_name.strip().lower()}".encode("utf-8")
    digest = hashlib.sha256(base).hexdigest()
    return int(digest[:16], 16)


def unit_interval_seed(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16**12 - 1)


def make_signature_vector(seed: int, size: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    return generator.normal(loc=0.0, scale=1.0, size=size)


def time_to_seconds(value: Any) -> int:
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    if isinstance(value, str):
        pieces = [int(piece) for piece in value.split(":")]
        while len(pieces) < 3:
            pieces.append(0)
        return pieces[0] * 3600 + pieces[1] * 60 + pieces[2]
    raise TypeError("transaction_time must be datetime.time or HH:MM[:SS] string")


def build_bounds_map(profile: dict[str, Any]) -> dict[str, tuple[float, float]]:
    return {row["feature"]: (float(row["min"]), float(row["max"])) for row in profile["feature_bounds"]}


def normalize_anomaly_score(raw_score: float, reference: dict[str, float]) -> float:
    spread = max(reference["median"] - reference["p05"], 1e-6)
    normalized = (reference["median"] - raw_score) / spread
    return float(np.clip(normalized, 0.0, 1.0))


def get_hour_risk_map(profile: dict[str, Any]) -> dict[int, float]:
    return {
        int(row["Hour"]): float(row["fraud_rate"])
        for row in profile["hourly_profile"]["hourly_rows"]
    }


def calculate_behavior_flags(
    transaction: dict[str, Any],
    history: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    profile = artifact["profile"]
    amount_stats = profile["amount_stats"]
    amount = float(transaction["transaction_amount"])
    hour = int(time_to_seconds(transaction["transaction_time"]) // 3600)
    location = str(transaction["location"])
    merchant = str(transaction["merchant_type"])
    card_last4 = clean_card_number(transaction["card_number"])[-4:]

    history_frame = pd.DataFrame(history)
    card_history = history_frame[history_frame["card_last4"] == card_last4] if not history_frame.empty else history_frame

    dataset_mean = float(amount_stats["mean"])
    dataset_std = max(float(amount_stats["std"]), 1e-6)
    q90 = float(amount_stats["90%"])
    q95 = float(amount_stats["95%"])

    card_average = float(card_history["transaction_amount"].mean()) if not card_history.empty else dataset_mean
    amount_zscore = (amount - dataset_mean) / dataset_std
    is_amount_spike = amount > max(q95, card_average * 1.8)

    hour_risk_map = get_hour_risk_map(profile)
    hour_fraud_rate = hour_risk_map.get(hour, 0.0)
    risky_hours = {int(value) for value in profile["hourly_profile"]["risky_hours"]}
    unusual_time = hour in risky_hours or hour < 5

    merchant_risk = MERCHANT_RISK.get(merchant, 0.20)
    location_risk = LOCATION_RISK.get(location, 0.10)
    prior_flags = int((card_history["decision"] != "Transaction Approved").sum()) if not card_history.empty else 0

    behavior_score = (
        0.32 * np.clip(amount_zscore / 4.0, 0.0, 1.0)
        + 0.24 * np.clip(hour_fraud_rate / 0.02, 0.0, 1.0)
        + 0.20 * merchant_risk
        + 0.16 * location_risk
        + 0.08 * np.clip(prior_flags / 3.0, 0.0, 1.0)
    )

    explanations: list[str] = []
    if is_amount_spike:
        explanations.append("High transaction amount compared with typical dataset and card-level spending patterns.")
    if unusual_time:
        explanations.append("Transaction was initiated during hours with elevated fraud activity.")
    if location == "International":
        explanations.append("Foreign transaction increased risk because it differs from lower-risk domestic patterns.")
    if merchant_risk >= 0.45:
        explanations.append("Merchant category has a higher fraud exposure profile in this simulator.")
    if prior_flags >= 2:
        explanations.append("Recent transaction history for this card already contains multiple flagged events.")

    if not explanations:
        explanations.append("Transaction aligns with expected spending behavior, timing, and location patterns.")

    return {
        "hour": hour,
        "amount_zscore": float(amount_zscore),
        "amount_spike": bool(is_amount_spike),
        "unusual_time": bool(unusual_time),
        "hour_fraud_rate": float(hour_fraud_rate),
        "merchant_risk": float(merchant_risk),
        "location_risk": float(location_risk),
        "behavior_score": float(np.clip(behavior_score, 0.0, 1.0)),
        "card_average_amount": float(card_average),
        "explanations": explanations,
    }


def simulate_feature_vector(
    transaction: dict[str, Any],
    artifact: dict[str, Any],
    behavior: dict[str, Any],
) -> pd.DataFrame:
    feature_columns = artifact["feature_columns"]
    profile = artifact["profile"]
    legitimate_mean = profile["legitimate_mean"]
    fraud_mean = profile["fraud_mean"]
    legitimate_std = profile["legitimate_std"]
    bounds = build_bounds_map(profile)

    card_seed = card_signature_seed(transaction["card_number"], transaction["card_holder_name"])
    card_vector = make_signature_vector(card_seed, len(feature_columns))
    merchant_vector = make_signature_vector(
        int(unit_interval_seed(str(transaction["merchant_type"]), str(transaction["location"])) * 10_000_000),
        len(feature_columns),
    )

    fraud_pull = (
        0.45 * behavior["behavior_score"]
        + 0.20 * float(behavior["amount_spike"])
        + 0.15 * float(transaction["location"] == "International")
        + 0.10 * np.clip(behavior["hour_fraud_rate"] / 0.02, 0.0, 1.0)
        + 0.10 * np.clip(behavior["merchant_risk"], 0.0, 1.0)
    )
    fraud_pull = float(np.clip(fraud_pull, 0.0, 1.0))

    values: dict[str, float] = {}
    transaction_seconds = float(time_to_seconds(transaction["transaction_time"]))
    values["Time"] = transaction_seconds
    values["Amount"] = float(transaction["transaction_amount"])

    for index, feature_name in enumerate(feature_columns):
        if feature_name in {"Time", "Amount"}:
            continue

        base_value = float(legitimate_mean[feature_name])
        fraud_direction = float(fraud_mean[feature_name]) - base_value
        feature_std = max(float(legitimate_std[feature_name]), 1e-6)
        feature_value = (
            base_value
            + fraud_pull * fraud_direction
            + 0.08 * card_vector[index] * feature_std
            + 0.05 * merchant_vector[index] * feature_std
        )

        if behavior["amount_spike"]:
            feature_value += 0.04 * np.sign(fraud_direction or 1.0) * feature_std
        if transaction["location"] == "International":
            feature_value += 0.05 * np.sign(fraud_direction or 1.0) * feature_std

        lower_bound, upper_bound = bounds[feature_name]
        values[feature_name] = float(np.clip(feature_value, lower_bound, upper_bound))

    time_min, time_max = bounds["Time"]
    amount_min, amount_max = bounds["Amount"]
    values["Time"] = float(np.clip(values["Time"], time_min, time_max))
    values["Amount"] = float(np.clip(values["Amount"], amount_min, amount_max))

    ordered = pd.DataFrame([{feature: values[feature] for feature in feature_columns}])
    return ordered


def convert_probability_to_score(probability: float) -> float:
    return float(np.clip(probability, 0.0, 1.0) * 100.0)


def classify_risk(risk_score: float) -> dict[str, str]:
    if risk_score < 30:
        return {
            "risk_band": "Safe",
            "decision": "Transaction Approved",
            "color": SUCCESS_GREEN,
        }
    if risk_score < 70:
        return {
            "risk_band": "Suspicious",
            "decision": "OTP Verification Required",
            "color": WARNING_AMBER,
        }
    return {
        "risk_band": "Fraud",
        "decision": "Transaction Blocked",
        "color": DANGER_RED,
    }


def score_transaction(
    transaction: dict[str, Any],
    artifact: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    history = history or []
    behavior = calculate_behavior_flags(transaction, history, artifact)
    feature_frame = simulate_feature_vector(transaction, artifact, behavior)

    scaled = artifact["scaler"].transform(feature_frame[artifact["feature_columns"]])
    model_probability = float(artifact["best_model"].predict_proba(scaled)[0, 1])
    anomaly_raw = float(artifact["isolation_forest"].decision_function(scaled)[0])
    anomaly_risk = normalize_anomaly_score(anomaly_raw, artifact["isolation_reference"])
    anomaly_flag = artifact["isolation_forest"].predict(scaled)[0] == -1

    combined_probability = (
        0.58 * model_probability
        + 0.22 * behavior["behavior_score"]
        + 0.20 * anomaly_risk
    )
    combined_probability = float(np.clip(combined_probability, 0.0, 1.0))
    risk_score = round(convert_probability_to_score(combined_probability), 1)
    classification = classify_risk(risk_score)

    explanations = list(behavior["explanations"])
    if anomaly_flag:
        explanations.append("Isolation Forest marked the transaction as anomalous relative to normal transaction patterns.")
    if model_probability >= 0.70:
        explanations.append("The selected machine learning model assigned a high fraud probability to the synthesized feature profile.")

    if classification["risk_band"] == "Safe" and len(explanations) > 1:
        explanations = explanations[:1]

    return {
        "card_holder_name": transaction["card_holder_name"].strip(),
        "card_masked": mask_card_number(transaction["card_number"]),
        "card_last4": clean_card_number(transaction["card_number"])[-4:],
        "transaction_amount": float(transaction["transaction_amount"]),
        "transaction_time": str(transaction["transaction_time"]),
        "location": transaction["location"],
        "merchant_type": transaction["merchant_type"],
        "risk_score": risk_score,
        "risk_band": classification["risk_band"],
        "decision": classification["decision"],
        "color": classification["color"],
        "model_name": artifact["best_model_name"],
        "model_probability": round(model_probability * 100.0, 2),
        "anomaly_risk": round(anomaly_risk * 100.0, 2),
        "anomaly_detected": bool(anomaly_flag),
        "behavior_score": round(behavior["behavior_score"] * 100.0, 2),
        "hour": behavior["hour"],
        "hour_fraud_rate": round(behavior["hour_fraud_rate"] * 100.0, 4),
        "reasons": explanations,
    }


def generate_fake_transaction(profile_name: str) -> dict[str, Any]:
    profile_name = profile_name.strip()
    base_seed = int(unit_interval_seed(profile_name, "fraud-simulator") * 10_000_000)
    generator = np.random.default_rng(base_seed + np.random.randint(1, 999_999))

    scenarios = {
        "Legitimate retail": {
            "amount_range": (18.0, 220.0),
            "hour_range": (9, 20),
            "location": "Domestic",
            "merchant_choices": ["Grocery", "Dining", "Fuel", "Utilities"],
        },
        "Borderline foreign": {
            "amount_range": (220.0, 360.0),
            "hour_range": (18, 21),
            "location": "International",
            "merchant_choices": ["Travel"],
        },
        "High-risk spike": {
            "amount_range": (1800.0, 5800.0),
            "hour_range": (0, 4),
            "location": "International",
            "merchant_choices": ["Cash Withdrawal", "Digital Goods", "Electronics"],
        },
    }

    scenario = scenarios.get(profile_name, scenarios["Legitimate retail"])
    amount = round(float(generator.uniform(*scenario["amount_range"])), 2)
    hour = int(generator.integers(scenario["hour_range"][0], scenario["hour_range"][1] + 1))
    minute = int(generator.integers(0, 60))
    merchant = str(generator.choice(scenario["merchant_choices"]))
    holder_name = str(generator.choice(FAKE_NAMES))
    card_number = "".join(str(int(digit)) for digit in generator.integers(0, 10, size=16))

    return {
        "card_number": card_number,
        "card_holder_name": holder_name,
        "transaction_amount": amount,
        "transaction_time": time(hour=hour, minute=minute),
        "location": scenario["location"],
        "merchant_type": merchant,
    }


def history_to_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    if not history:
        return pd.DataFrame(
            columns=[
                "card_masked",
                "card_holder_name",
                "transaction_amount",
                "transaction_time",
                "location",
                "merchant_type",
                "risk_band",
                "risk_score",
                "decision",
            ]
        )

    frame = pd.DataFrame(history)
    ordered_columns = [
        "card_masked",
        "card_holder_name",
        "transaction_amount",
        "transaction_time",
        "location",
        "merchant_type",
        "risk_band",
        "risk_score",
        "decision",
    ]
    frame = frame[ordered_columns].rename(
        columns={
            "card_masked": "Card",
            "card_holder_name": "Card Holder",
            "transaction_amount": "Amount",
            "transaction_time": "Time",
            "location": "Location",
            "merchant_type": "Merchant Type",
            "risk_band": "Risk Band",
            "risk_score": "Risk Score",
            "decision": "Decision",
        }
    )
    frame["Amount"] = frame["Amount"].map(lambda value: f"${value:,.2f}")
    frame["Risk Score"] = frame["Risk Score"].map(lambda value: f"{value:.1f}")
    return frame
