from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


RANDOM_STATE = 42
TEST_SIZE = 0.20
SMOTE_STRATEGY = 0.20
DATA_PATH = Path(__file__).resolve().with_name("creditcard.csv")
MODEL_PATH = Path(__file__).resolve().with_name("fraud_model.pkl")


def build_metrics(y_true: pd.Series, y_pred: np.ndarray, y_score: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_score": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
    }


def compute_hourly_profile(data: pd.DataFrame) -> dict[str, Any]:
    hourly = data.copy()
    hourly["Hour"] = (hourly["Time"] // 3600).astype(int) % 24
    summary = (
        hourly.groupby("Hour")
        .agg(
            total_transactions=("Class", "count"),
            fraud_transactions=("Class", "sum"),
            average_amount=("Amount", "mean"),
        )
        .reset_index()
    )
    summary["fraud_rate"] = summary["fraud_transactions"] / summary["total_transactions"]
    summary["average_amount"] = summary["average_amount"].round(2)
    risky_hours = (
        summary.sort_values(["fraud_rate", "fraud_transactions"], ascending=False)["Hour"]
        .head(6)
        .astype(int)
        .tolist()
    )
    return {
        "risky_hours": risky_hours,
        "hourly_rows": summary.to_dict(orient="records"),
    }


def compute_feature_importance(model: Any, feature_columns: list[str]) -> list[dict[str, float]]:
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        values = np.abs(np.asarray(model.coef_[0], dtype=float))
    else:
        values = np.zeros(len(feature_columns), dtype=float)

    ranking = pd.DataFrame({"feature": feature_columns, "importance": values})
    ranking = ranking.sort_values("importance", ascending=False).head(10)
    return ranking.to_dict(orient="records")


def build_artifact(
    data: pd.DataFrame,
    feature_columns: list[str],
    scaler: StandardScaler,
    best_model_name: str,
    best_model: Any,
    models_metrics: dict[str, dict[str, float]],
    isolation_forest: IsolationForest,
    isolation_reference: dict[str, float],
) -> dict[str, Any]:
    legitimate = data[data["Class"] == 0][feature_columns]
    fraudulent = data[data["Class"] == 1][feature_columns]

    amount_stats = data["Amount"].describe(percentiles=[0.50, 0.75, 0.90, 0.95, 0.99]).to_dict()
    time_stats = data["Time"].describe(percentiles=[0.50, 0.75, 0.90, 0.95, 0.99]).to_dict()
    class_distribution = data["Class"].value_counts().sort_index().to_dict()

    bounds = pd.DataFrame(
        {
            "feature": feature_columns,
            "min": data[feature_columns].min().values,
            "max": data[feature_columns].max().values,
        }
    )

    hourly_profile = compute_hourly_profile(data)

    artifact = {
        "best_model_name": best_model_name,
        "best_model": best_model,
        "scaler": scaler,
        "models_metrics": models_metrics,
        "feature_columns": feature_columns,
        "isolation_forest": isolation_forest,
        "isolation_reference": isolation_reference,
        "profile": {
            "dataset_shape": {"rows": int(data.shape[0]), "columns": int(data.shape[1])},
            "class_distribution": {str(int(k)): int(v) for k, v in class_distribution.items()},
            "fraud_percentage": float(data["Class"].mean() * 100.0),
            "amount_stats": {key: float(value) for key, value in amount_stats.items()},
            "time_stats": {key: float(value) for key, value in time_stats.items()},
            "hourly_profile": hourly_profile,
            "legitimate_mean": legitimate.mean().to_dict(),
            "fraud_mean": fraudulent.mean().to_dict(),
            "legitimate_std": legitimate.std().replace(0.0, 1e-6).to_dict(),
            "feature_bounds": bounds.to_dict(orient="records"),
            "top_features": compute_feature_importance(best_model, feature_columns),
        },
    }
    return artifact


def train_and_save_model(data_path: Path = DATA_PATH, model_path: Path = MODEL_PATH) -> dict[str, Any]:
    data = pd.read_csv(data_path)
    feature_columns = [column for column in data.columns if column != "Class"]
    target = data["Class"]
    predictors = data[feature_columns]

    x_train, x_test, y_train, y_test = train_test_split(
        predictors,
        target,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=target,
    )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)

    smote = SMOTE(random_state=RANDOM_STATE, sampling_strategy=SMOTE_STRATEGY)
    x_resampled, y_resampled = smote.fit_resample(x_train_scaled, y_train)

    models: dict[str, Any] = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000,
            random_state=RANDOM_STATE,
            solver="lbfgs",
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=250,
            max_depth=14,
            min_samples_leaf=2,
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
    }

    metrics_by_model: dict[str, dict[str, float]] = {}
    trained_models: dict[str, Any] = {}

    for model_name, model in models.items():
        model.fit(x_resampled, y_resampled)
        probabilities = model.predict_proba(x_test_scaled)[:, 1]
        predictions = (probabilities >= 0.50).astype(int)
        metrics_by_model[model_name] = build_metrics(y_test, predictions, probabilities)
        trained_models[model_name] = model

    best_model_name = max(metrics_by_model, key=lambda name: metrics_by_model[name]["roc_auc"])
    best_model = trained_models[best_model_name]

    legitimate_train_scaled = x_train_scaled[y_train.to_numpy() == 0]
    isolation_forest = IsolationForest(
        n_estimators=250,
        contamination=0.015,
        random_state=RANDOM_STATE,
    )
    isolation_forest.fit(legitimate_train_scaled)

    isolation_scores = isolation_forest.decision_function(legitimate_train_scaled)
    isolation_reference = {
        "median": float(np.median(isolation_scores)),
        "p10": float(np.percentile(isolation_scores, 10)),
        "p05": float(np.percentile(isolation_scores, 5)),
    }

    artifact = build_artifact(
        data=data,
        feature_columns=feature_columns,
        scaler=scaler,
        best_model_name=best_model_name,
        best_model=best_model,
        models_metrics=metrics_by_model,
        isolation_forest=isolation_forest,
        isolation_reference=isolation_reference,
    )
    joblib.dump(artifact, model_path)
    return artifact


def format_metrics_table(models_metrics: dict[str, dict[str, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(models_metrics).T.reset_index().rename(columns={"index": "model"})
    numeric_columns = [column for column in frame.columns if column != "model"]
    frame[numeric_columns] = frame[numeric_columns].astype(float).round(4)
    return frame.sort_values("roc_auc", ascending=False)


def main() -> None:
    artifact = train_and_save_model()
    metrics_table = format_metrics_table(artifact["models_metrics"])

    print("\nCredit Card Fraud Detection Training Complete")
    print("=" * 48)
    print(f"Dataset: {DATA_PATH.name}")
    print(f"Saved model: {MODEL_PATH.name}")
    print(f"Selected model: {artifact['best_model_name']}")
    print("\nEvaluation metrics (test set):")
    print(metrics_table.to_string(index=False))
    print("\nDataset class imbalance:")
    distribution = artifact["profile"]["class_distribution"]
    print(
        f"Normal={distribution['0']}, Fraud={distribution['1']}, "
        f"Fraud %={artifact['profile']['fraud_percentage']:.4f}"
    )


if __name__ == "__main__":
    main()
