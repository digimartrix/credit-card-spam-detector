from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from train_model import format_metrics_table
from utils import LOCATION_RISK, MERCHANT_RISK, generate_fake_transaction, load_artifact

from backend.auth import mask_phone_number


ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "fraud_model.pkl"


@lru_cache(maxsize=1)
def get_artifact() -> dict[str, Any]:
    return load_artifact(MODEL_PATH)


def get_sample_profiles() -> list[dict[str, str]]:
    return [
        {"value": "Legitimate retail", "label": "Everyday Purchase"},
        {"value": "Borderline foreign", "label": "Travel Review"},
        {"value": "High-risk spike", "label": "Risk Spike"},
    ]


def get_sample_profile_values() -> set[str]:
    return {item["value"] for item in get_sample_profiles()}


def generate_serialized_sample(profile_name: str) -> dict[str, Any]:
    sample = generate_fake_transaction(profile_name)
    return {
        "card_number": sample["card_number"],
        "card_holder_name": sample["card_holder_name"],
        "transaction_amount": float(sample["transaction_amount"]),
        "transaction_time": sample["transaction_time"].strftime("%H:%M"),
        "location": sample["location"],
        "merchant_type": sample["merchant_type"],
    }


def build_dashboard_config(user_phone: str) -> dict[str, Any]:
    artifact = get_artifact()
    profile = artifact["profile"]
    metrics_table = format_metrics_table(artifact["models_metrics"])
    selected_model_metrics = metrics_table.iloc[0].to_dict()

    return {
        "title": "EXPayshield — Fraud Detection Dashboard",
        "hero": {
            "eyebrow": "EXPayshield Dashboard",
            "title": "Review transactions with a secure fraud workflow.",
            "description": (
                "This dashboard keeps fraud review fast and readable while combining the trained fraud model, "
                "anomaly detection, behavior analysis, and SMS alerting."
            ),
        },
        "stats": [
            {"label": "Selected model", "value": artifact["best_model_name"]},
            {"label": "ROC-AUC", "value": f"{selected_model_metrics['roc_auc']:.4f}"},
            {"label": "Fraud ratio", "value": f"{profile['fraud_percentage']:.4f}%"},
            {"label": "Transactions", "value": f"{profile['dataset_shape']['rows']:,}"},
        ],
        "dataset": {
            "normal_count": profile["class_distribution"]["0"],
            "fraud_count": profile["class_distribution"]["1"],
            "fraud_percentage": round(float(profile["fraud_percentage"]), 4),
            "normal_percentage": round(100.0 - float(profile["fraud_percentage"]), 4),
        },
        "metrics_table": metrics_table.to_dict(orient="records"),
        "top_features": artifact["profile"]["top_features"][:5],
        "merchant_options": list(MERCHANT_RISK.keys()),
        "location_options": list(LOCATION_RISK.keys()),
        "sample_profiles": get_sample_profiles(),
        "defaults": {
            "card_number": "4532 1045 8871 3204",
            "card_holder_name": "Daniel Brooks",
            "transaction_amount": 214.75,
            "transaction_time": "14:35",
            "location": "Domestic",
            "merchant_type": "Grocery",
            "sample_profile": "Legitimate retail",
        },
        "session": {
            "user_phone": user_phone,
            "user_phone_masked": mask_phone_number(user_phone),
        },
    }
