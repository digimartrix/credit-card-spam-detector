from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from backend.config import USE_TWILIO, OTP_MODE_LABEL, OTP_MODE_DESCRIPTION, OTP_MODE_ICON

from backend.auth import (
    clear_pending_phone,
    current_user_phone,
    get_pending_phone,
    is_authenticated,
    issue_otp,
    login_required_api,
    login_required_page,
    login_user,
    mask_phone_number,
    logout_user,
    normalize_mobile_number,
    set_pending_phone,
    verify_otp_code,
)
from backend.fraud import build_alert_message, normalize_transaction_payload, sanitize_history
from backend.model_loader import build_dashboard_config, generate_serialized_sample, get_artifact, get_sample_profile_values
from backend.sms import send_sms
from backend.transaction_generator import (
    generate_live_transaction,
    get_transaction_buffer,
    start_generator,
)
from utils import score_transaction


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
MODEL_PATH = ROOT_DIR / "fraud_model.pkl"


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(FRONTEND_DIR),
        static_folder=str(FRONTEND_DIR),
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
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

    # -----------------------------------------------------------------------
    # Page routes
    # -----------------------------------------------------------------------

    @app.get("/")
    def home():
        if is_authenticated():
            return redirect(url_for("dashboard"))
        if get_pending_phone():
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
                "use_twilio": USE_TWILIO,
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
        if not pending_phone:
            return redirect(url_for("login"))

        return render_template(
            "otp.html",
            config={
                "title": "OTP Verification",
                "pending_phone": pending_phone,
                "pending_phone_masked": mask_phone_number(pending_phone),
                "use_twilio": USE_TWILIO,
                "otp_mode": OTP_MODE_LABEL,
                "otp_mode_desc": OTP_MODE_DESCRIPTION,
                "otp_mode_icon": OTP_MODE_ICON,
            },
        )

    @app.get("/dashboard")
    @login_required_page
    def dashboard():
        return render_template("index.html", config=build_dashboard_config(current_user_phone() or ""))

    @app.get("/health")
    def health():
        buffer = get_transaction_buffer()
        return jsonify({
            "status": "ok",
            "model_loaded": True,
            "selected_model": get_artifact()["best_model_name"],
            "live_transactions_generated": buffer.count(),
        })

    # -----------------------------------------------------------------------
    # Auth API routes
    # -----------------------------------------------------------------------

    @app.post("/send-otp")
    def send_otp_route():
        """
        POST /send-otp — Hybrid OTP delivery with per-request mode override.

        The frontend can send { "mode": "dev" | "twilio" } to choose the mode
        at login time, allowing users to try both without restarting the server.

        Development mode (mode=dev):
          - OTP is returned in the JSON response under "development_otp"
          - OTP is printed to console
          - No SMS is sent (dry-run)

        Production mode (mode=twilio):
          - OTP is sent via Twilio SMS
          - OTP is NEVER returned in the response
          - Twilio errors are translated to friendly user messages
        """
        payload = request.get_json(silent=True) or {}
        raw_mobile = payload.get("mobile_number")

        # Allow per-request mode override from the frontend
        requested_mode = str(payload.get("mode", "")).strip().lower()
        use_production = requested_mode == "twilio"

        try:
            mobile_number = normalize_mobile_number(raw_mobile)
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

        otp_code = issue_otp(mobile_number)
        set_pending_phone(mobile_number)

        # Remember mode choice so fraud alerts use the same delivery method
        session["sms_mode"] = "twilio" if use_production else "dev"

        if use_production:
            # ── Production: send real SMS via Twilio ──
            sms_result = send_sms(
                mobile_number,
                f"Your fraud detection login OTP is {otp_code}. It expires in 5 minutes.",
                force_twilio=True,
            )

            if not sms_result.success:
                clear_pending_phone()
                # Log raw error for debugging (server-side only)
                print(f"\n  ❌ TWILIO ERROR for {mobile_number}: {sms_result.error}")
                print(f"     Rate limited: {sms_result.rate_limited}")
                print(f"     Provider: {sms_result.provider}\n")
                # Translate raw Twilio errors to user-friendly messages
                friendly_error = _friendly_sms_error(sms_result)
                return jsonify({
                    "ok": False,
                    "errors": [friendly_error],
                    "error_type": "production_sms_failed",
                }), 422

            return jsonify({
                "ok": True,
                "message": "OTP sent via SMS successfully.",
                "redirect_url": url_for("otp_page"),
                "sms": sms_result.to_dict(),
                "use_twilio": True,
            })
        else:
            # ── Development: dry-run, show OTP on screen ──
            from backend.sms import SMSResult
            print(f"\n{'='*50}")
            print(f"  🛠️  DEV OTP for {mobile_number}: {otp_code}")
            print(f"{'='*50}\n")

            return jsonify({
                "ok": True,
                "message": "OTP generated (development mode).",
                "redirect_url": url_for("otp_page"),
                "sms": {"success": True, "provider": "dev-console", "dry_run": True},
                "use_twilio": False,
                "development_otp": otp_code,
            })


    def _friendly_sms_error(sms_result) -> str:
        """
        Convert raw Twilio/SMS errors into user-friendly messages.
        Users should never see raw API error strings.
        """
        raw = str(sms_result.error or "").lower()

        # Rate limited (our app-level limit)
        if getattr(sms_result, "rate_limited", False):
            return (
                "You've reached the SMS limit (3 messages per 25 minutes). "
                "Please wait a while before trying again, or switch to Development Mode."
            )

        # Twilio Trial daily message limit (50 messages/day)
        if "daily" in raw and "limit" in raw or "exceeded" in raw and "limit" in raw or "63038" in raw:
            return (
                "Your Twilio Trial account has reached its daily SMS limit (50 messages/day). "
                "The limit resets tomorrow. Please use Development Mode for now, "
                "or upgrade your Twilio account at twilio.com for unlimited messaging."
            )

        # Twilio queue/throttle limits
        if "queue" in raw or "throttle" in raw or "too many" in raw:
            return (
                "Too many SMS requests — Twilio is throttling your account. "
                "Please wait a moment and try again, or use Development Mode."
            )

        # Unverified number (Twilio trial restriction)
        if "unverified" in raw or "not a valid" in raw or "is not verified" in raw:
            return (
                "This number is not verified for Production Mode. "
                "Your payment or Twilio account isn't set up for this number yet. "
                "Please verify your number at twilio.com or use Development Mode to test."
            )

        # Number not reachable / invalid format
        if "invalid" in raw or "not a mobile" in raw or "phone number" in raw:
            return (
                "This phone number cannot receive SMS. "
                "Please check the format and try again, or switch to Development Mode."
            )

        # Twilio credentials not configured
        if "credentials" in raw or "authenticate" in raw or "account_sid" in raw:
            return (
                "Production Mode is not available — Twilio credentials are not configured. "
                "Please use Development Mode for now."
            )

        # Permission / billing issues
        if "permission" in raw or "billing" in raw or "suspend" in raw:
            return (
                "Your Twilio account doesn't have permission to send SMS. "
                "This may be a billing or plan issue. Please use Development Mode."
            )

        # Generic fallback — still friendly
        return (
            "Unable to send SMS in Production Mode. "
            "Your number may not be verified or your Twilio plan may not support it. "
            "Please try Development Mode instead."
        )

    @app.post("/verify-otp")
    def verify_otp_route():
        payload = request.get_json(silent=True) or {}
        raw_mobile = payload.get("mobile_number") or get_pending_phone()
        otp_code = str(payload.get("otp", "")).strip()

        try:
            mobile_number = normalize_mobile_number(raw_mobile)
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

        pending_phone = get_pending_phone()
        if pending_phone and mobile_number != pending_phone:
            return jsonify({"ok": False, "errors": ["Verify the OTP for the same mobile number that requested it."]}), 400

        if not otp_code:
            return jsonify({"ok": False, "errors": ["OTP is required."]}), 400

        verified, error_message = verify_otp_code(mobile_number, otp_code)
        if not verified:
            return jsonify({"ok": False, "errors": [error_message or "OTP verification failed."]}), 400

        login_user(mobile_number)
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
            sms_result = send_sms(current_user_phone() or "", alert_message)
            alert_response = {
                "message": alert_message,
                "sms": sms_result.to_dict(),
            }
            if not sms_result.success:
                warnings.append("Prediction completed, but the SMS alert could not be delivered.")

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
        # Throttled to once every 10 seconds to manage SMS costs and API limits
        if os.getenv("VERCEL"):
            last_gen_time = getattr(app, "_last_gen_time", 0)
            if time.time() - last_gen_time >= 10:
                from backend.transaction_generator import generate_live_transaction
                tx = generate_live_transaction()
                buffer.push(tx)
                app._last_gen_time = time.time()

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
        detection pipeline, and sends SMS alerts if needed. This is the
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

        # Send SMS alerts for fraud/suspicious transactions
        alert_message = build_alert_message(result)
        alert_response: dict[str, Any] | None = None
        warnings: list[str] = []

        if alert_message:
            user_phone = current_user_phone() or ""
            if user_phone:
                # Use the same SMS mode the user chose at login
                use_twilio_for_alerts = session.get("sms_mode") == "twilio"
                sms_result = send_sms(
                    user_phone, alert_message,
                    force_twilio=use_twilio_for_alerts,
                )
                alert_response = {
                    "message": alert_message,
                    "sms": sms_result.to_dict(),
                }
                if not sms_result.success:
                    warnings.append("Fraud detected but SMS alert could not be delivered.")
            else:
                alert_response = {
                    "message": alert_message,
                    "sms": {"success": False, "error": "No phone number in session."},
                }

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
