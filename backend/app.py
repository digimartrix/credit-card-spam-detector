from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from backend.config import (
    ALLOW_DEV_OTP,
    DEFAULT_OTP_MODE,
    OTP_MODE_DESCRIPTION,
    OTP_MODE_ICON,
    OTP_MODE_LABEL,
)

from backend.auth import (
    clear_pending_login,
    current_user_email,
    current_user_phone,
    get_pending_email,
    get_pending_phone,
    is_authenticated,
    issue_otp,
    login_required_api,
    login_required_page,
    login_user,
    mask_email_address,
    mask_phone_number,
    logout_user,
    normalize_email_address,
    normalize_mobile_number,
    set_pending_login,
    verify_otp_code,
)
from backend.fraud import build_alert_message, normalize_transaction_payload, sanitize_history
from backend.model_loader import build_dashboard_config, generate_serialized_sample, get_artifact, get_sample_profile_values
from backend.email_service import EmailResult, send_email
from backend.transaction_generator import (
    generate_live_transaction,
    get_transaction_buffer,
    start_generator,
)
from utils import score_transaction


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
MODEL_PATH = ROOT_DIR / "fraud_model.pkl"


# Track email delivery stats for the health check.
email_stats = {
    "total_sent": 0,
    "total_failed": 0,
    "last_error": None
}


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(FRONTEND_DIR),
        static_folder=str(FRONTEND_DIR),
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    flask_secret = os.getenv("FLASK_SECRET_KEY")
    if os.getenv("VERCEL") and not flask_secret:
        raise RuntimeError("Set FLASK_SECRET_KEY in the Vercel project environment before deployment.")
    app.config["SECRET_KEY"] = flask_secret or "dev-secret-change-me"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "fraud_model.pkl is missing. Run `python3 train_model.py` before starting the application."
        )

    # -----------------------------------------------------------------------
    # Start the real-time transaction generator on app creation
    # Generates a new transaction every 3–5 seconds in a background thread
    # Skip on serverless (Vercel) — background threads don't persist
    # -----------------------------------------------------------------------
    if not os.getenv("VERCEL"):
        start_generator(interval_min=3.0, interval_max=5.0)

    def deliver_fraud_alert_email(message: str) -> EmailResult:
        recipient = current_user_email()
        if not recipient:
            return EmailResult(
                success=False,
                provider="email",
                error="No email address is attached to this session.",
            )

        send_live_email = session.get("otp_delivery_mode") == "email"
        now = time.time()
        cooldown_seconds = max(0, int(os.getenv("EMAIL_ALERT_COOLDOWN_SECONDS", "300")))
        last_sent = float(session.get("last_fraud_email_at", 0))
        if send_live_email and cooldown_seconds and now - last_sent < cooldown_seconds:
            return EmailResult(success=True, provider="email", skipped=True)

        result = send_email(
            recipient,
            "EXPayshield transaction risk alert",
            message,
            force_send=send_live_email,
        )
        if result.success and not result.dry_run and not result.skipped:
            session["last_fraud_email_at"] = now
            email_stats["total_sent"] += 1
        elif not result.success:
            email_stats["total_failed"] += 1
            email_stats["last_error"] = result.error
        return result

    # -----------------------------------------------------------------------
    # Page routes
    # -----------------------------------------------------------------------

    @app.get("/")
    def home():
        if is_authenticated():
            return redirect(url_for("dashboard"))
        if get_pending_phone() and get_pending_email():
            return redirect(url_for("otp_page"))
        return redirect(url_for("login"))

    @app.get("/login")
    def login():
        if is_authenticated():
            return redirect(url_for("dashboard"))
        return render_template(
            "login.html",
            config={
                "title": "Secure Login",
                "default_phone": "+91",
                "default_otp_mode": DEFAULT_OTP_MODE,
                "allow_dev_mode": ALLOW_DEV_OTP,
                "otp_mode": OTP_MODE_LABEL,
                "otp_mode_desc": OTP_MODE_DESCRIPTION,
                "otp_mode_icon": OTP_MODE_ICON,
            },
        )

    @app.get("/otp")
    def otp_page():
        if is_authenticated():
            return redirect(url_for("dashboard"))

        pending_phone = get_pending_phone()
        pending_email = get_pending_email()
        if not pending_phone or not pending_email:
            return redirect(url_for("login"))

        delivery_mode = session.get("otp_delivery_mode", DEFAULT_OTP_MODE)
        use_email = delivery_mode == "email"

        return render_template(
            "otp.html",
            config={
                "title": "OTP Verification",
                "pending_phone": pending_phone,
                "pending_phone_masked": mask_phone_number(pending_phone),
                "pending_email": pending_email,
                "pending_email_masked": mask_email_address(pending_email),
                "use_email": use_email,
                "otp_mode": "Email OTP" if use_email else "Development",
                "otp_mode_desc": (
                    "The verification code was sent to your email."
                    if use_email
                    else "The verification code is displayed for local testing."
                ),
                "otp_mode_icon": "✉️" if use_email else "🛠️",
            },
        )

    @app.get("/dashboard")
    @login_required_page
    def dashboard():
        return render_template(
            "index.html",
            config=build_dashboard_config(
                current_user_phone() or "", current_user_email() or ""
            ),
        )

    @app.get("/health")
    def health():
        buffer = get_transaction_buffer()
        return jsonify({
            "status": "ok",
            "model_loaded": True,
            "selected_model": get_artifact()["best_model_name"],
            "live_transactions_generated": buffer.count(),
            "email_stats": email_stats,
            "session_mode": session.get("otp_delivery_mode"),
            "is_auth": is_authenticated()
        })

    # -----------------------------------------------------------------------
    # Auth API routes
    # -----------------------------------------------------------------------

    @app.post("/send-otp")
    def send_otp_route():
        payload = request.get_json(silent=True) or {}
        raw_mobile = payload.get("mobile_number")
        raw_email = payload.get("email_address") or get_pending_email()
        requested_mode = str(
            payload.get("mode") or session.get("otp_delivery_mode") or DEFAULT_OTP_MODE
        ).strip().lower()

        if requested_mode not in {"dev", "email"}:
            return jsonify({"ok": False, "errors": ["Choose a valid OTP delivery mode."]}), 400
        if requested_mode == "dev" and not ALLOW_DEV_OTP:
            return jsonify({"ok": False, "errors": ["Development OTP mode is disabled on this deployment."]}), 403

        try:
            mobile_number = normalize_mobile_number(raw_mobile)
            email_address = normalize_email_address(raw_email)
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

        if requested_mode == "email":
            resend_wait = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))
            last_otp_sent = float(session.get("last_otp_sent_at", 0))
            remaining = resend_wait - (time.time() - last_otp_sent)
            if remaining > 0:
                return jsonify({
                    "ok": False,
                    "errors": [f"Please wait {int(remaining) + 1} seconds before requesting another code."],
                }), 429

        set_pending_login(mobile_number, email_address)
        session["otp_delivery_mode"] = requested_mode
        otp_code = issue_otp(mobile_number, email_address)

        if requested_mode == "email":
            result = send_email(
                email_address,
                "Your EXPayshield login code",
                f"Your EXPayshield login code is {otp_code}. It expires in 5 minutes.\n\nIf you did not request this code, you can ignore this email.",
                force_send=True,
            )
            if not result.success:
                clear_pending_login()
                email_stats["total_failed"] += 1
                email_stats["last_error"] = result.error
                return jsonify({"ok": False, "errors": [result.error or "Could not send the verification email."]}), 503

            email_stats["total_sent"] += 1
            session["last_otp_sent_at"] = time.time()
            return jsonify({
                "ok": True,
                "message": "Verification code sent to your email.",
                "redirect_url": url_for("otp_page"),
                "delivery": "email",
            })

        return jsonify({
            "ok": True,
            "message": "OTP generated for development mode.",
            "redirect_url": url_for("otp_page"),
            "delivery": "development",
            "development_otp": otp_code,
        })

    @app.post("/verify-otp")
    def verify_otp_route():
        payload = request.get_json(silent=True) or {}
        raw_mobile = payload.get("mobile_number") or get_pending_phone()
        raw_email = payload.get("email_address") or get_pending_email()
        otp_code = str(payload.get("otp", "")).strip()

        try:
            mobile_number = normalize_mobile_number(raw_mobile)
            email_address = normalize_email_address(raw_email)
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

        pending_phone = get_pending_phone()
        pending_email = get_pending_email()
        if pending_phone and mobile_number != pending_phone:
            return jsonify({"ok": False, "errors": ["Verify the OTP for the same mobile number that requested it."]}), 400
        if pending_email and email_address != pending_email:
            return jsonify({"ok": False, "errors": ["Verify the OTP using the same email address that requested it."]}), 400

        if not otp_code:
            return jsonify({"ok": False, "errors": ["OTP is required."]}), 400

        verified, error_message = verify_otp_code(mobile_number, email_address, otp_code)
        if not verified:
            return jsonify({"ok": False, "errors": [error_message or "OTP verification failed."]}), 400

        login_user(mobile_number, email_address)
        return jsonify({"ok": True, "message": "Login successful.", "redirect_url": url_for("dashboard")})

    @app.post("/logout")
    def logout_route():
        logout_user()
        return jsonify({"ok": True, "redirect_url": url_for("login")})

    # -----------------------------------------------------------------------
    # Transaction API routes
    # -----------------------------------------------------------------------

    @app.post("/api/sample")
    @login_required_api
    def sample_transaction():
        payload = request.get_json(silent=True) or {}
        profile = str(payload.get("profile", "Legitimate retail"))
        if profile not in get_sample_profile_values():
            return jsonify({"ok": False, "errors": ["Unknown sample profile."]}), 400

        return jsonify({"ok": True, "transaction": generate_serialized_sample(profile)})

    @app.post("/api/analyze")
    @login_required_api
    def analyze_transaction():
        payload = request.get_json(silent=True) or {}
        transaction_payload = payload.get("transaction") or {}
        history_payload = payload.get("history") or []

        transaction, errors = normalize_transaction_payload(transaction_payload)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400

        history = sanitize_history(history_payload)
        result = score_transaction(transaction, get_artifact(), history)

        alert_message = build_alert_message(result)
        alert_response: dict[str, Any] | None = None
        warnings: list[str] = []

        if alert_message:
            email_result = deliver_fraud_alert_email(alert_message)
            alert_response = {
                "message": alert_message,
                "email": email_result.to_dict(),
            }
            if not email_result.success:
                warnings.append("Prediction completed, but the email alert could not be delivered.")

        return jsonify(
            {
                "ok": True,
                "result": result,
                "alert": alert_response,
                "warnings": warnings,
            }
        )

    # -----------------------------------------------------------------------
    # Real-time transaction API routes
    # -----------------------------------------------------------------------

    @app.get("/live-transaction")
    @login_required_api
    def live_transaction():
        """
        GET /live-transaction

        Returns the latest auto-generated transaction from the real-time
        simulation engine. The frontend polls this endpoint every 3 seconds
        to display live incoming transactions on the dashboard.

        On Vercel (serverless), generates a fresh transaction on-demand since
        background threads cannot persist between invocations.
        """
        buffer = get_transaction_buffer()

        # Serverless mode: generate a transaction on-demand per poll
        if os.getenv("VERCEL"):
            from backend.transaction_generator import generate_live_transaction
            tx = generate_live_transaction()
            buffer.push(tx)

        latest = buffer.latest()

        if not latest:
            return jsonify({"ok": True, "transaction": None, "message": "No transactions generated yet."})

        return jsonify({
            "ok": True,
            "transaction": latest,
            "total_generated": buffer.count(),
        })

    @app.get("/live-transactions")
    @login_required_api
    def live_transactions():
        """
        GET /live-transactions?count=20

        Returns the most recent N auto-generated transactions for bulk display.
        """
        count = min(int(request.args.get("count", 20)), 50)
        buffer = get_transaction_buffer()

        return jsonify({
            "ok": True,
            "transactions": buffer.recent(count),
            "total_generated": buffer.count(),
        })

    @app.post("/api/analyze-live")
    @login_required_api
    def analyze_live_transaction():
        """
        POST /api/analyze-live

        Accepts a live-generated transaction, runs it through the ML fraud
        detection pipeline, and sends email alerts if needed. This is the
        endpoint the frontend uses for real-time fraud scoring.
        """
        payload = request.get_json(silent=True) or {}
        transaction_payload = payload.get("transaction") or {}
        history_payload = payload.get("history") or []

        # Normalize the live transaction for ML model consumption
        transaction, errors = normalize_transaction_payload(transaction_payload)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400

        history = sanitize_history(history_payload)
        result = score_transaction(transaction, get_artifact(), history)

        # Send email alerts for fraud/suspicious transactions.
        alert_message = build_alert_message(result)
        alert_response: dict[str, Any] | None = None
        warnings: list[str] = []

        if alert_message:
            email_result = deliver_fraud_alert_email(alert_message)
            alert_response = {
                "message": alert_message,
                "email": email_result.to_dict(),
            }
            if not email_result.success:
                warnings.append("Fraud detected but the email alert could not be delivered.")

        return jsonify({
            "ok": True,
            "result": result,
            "alert": alert_response,
            "warnings": warnings,
        })

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port, debug=False)
