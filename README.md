---
title: Credit Card Fraud Detection System
sdk: docker
app_port: 7860
---

# Credit Card Fraud Detection System

A custom Flask-based credit card fraud detection system with:

- trained ML fraud model
- secure mobile OTP login
- Twilio SMS integration
- protected fraud analysis APIs
- custom frontend pages for login, OTP verification, and dashboard access

## Updated project structure

```text
project/
├── backend/
│   ├── __init__.py
│   ├── app.py
│   ├── auth.py
│   ├── fraud.py
│   ├── model_loader.py
│   └── sms.py
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── otp.html
│   ├── script.js
│   └── style.css
├── app.py
├── train_model.py
├── utils.py
├── fraud_model.pkl
├── creditcard.csv
├── requirements.txt
├── Dockerfile
└── README.md
```

## Backend architecture

Frontend pages call backend APIs, and the backend is now split into focused modules:

- `backend/auth.py`
  - phone normalization
  - OTP generation
  - temporary OTP storage
  - verification
  - session login protection

- `backend/sms.py`
  - `send_sms(phone, message)`
  - Twilio integration
  - dry-run fallback for local development

- `backend/model_loader.py`
  - ML model loading
  - dashboard config building
  - sample transaction generation

- `backend/fraud.py`
  - transaction payload validation
  - transaction history sanitization
  - fraud alert message selection

- `backend/app.py`
  - page routes
  - auth routes
  - protected fraud analysis routes

## Authentication flow

### 1. Send OTP

`POST /send-otp`

Request:

```json
{
  "mobile_number": "+14155550123"
}
```

Behavior:

- normalizes the phone number
- generates a 6-digit OTP
- stores it temporarily in memory
- sends the OTP using Twilio SMS
- stores pending login state in Flask session

### 2. Verify OTP

`POST /verify-otp`

Request:

```json
{
  "mobile_number": "+14155550123",
  "otp": "123456"
}
```

Behavior:

- verifies the submitted OTP
- creates a logged-in session on success
- redirects the user to the dashboard

## Protected fraud detection

The following routes now require login:

- `GET /dashboard`
- `POST /api/sample`
- `POST /api/analyze`

If the session is missing or expired, the API returns `401` and the frontend redirects back to login.

## SMS alert logic

After fraud prediction:

- if transaction is blocked / risk is high:
  - SMS: `Fraud detected. Transaction blocked.`
- if transaction is suspicious:
  - SMS: `Suspicious transaction. OTP verification required.`
- if transaction is safe:
  - no SMS alert is sent

Prediction still completes even if SMS delivery fails. The response includes warning details instead of breaking the fraud detection result.

## Twilio configuration

Set these environment variables for real SMS delivery:

```bash
export FLASK_SECRET_KEY="change-this-in-production"
export TWILIO_ACCOUNT_SID="your_twilio_account_sid"
export TWILIO_AUTH_TOKEN="your_twilio_auth_token"
export TWILIO_PHONE_NUMBER="+1234567890"
export SMS_DRY_RUN="false"
```

### Local development mode

If Twilio credentials are not configured, the app uses dry-run mode by default:

- OTP and alert messages are simulated
- login flow still works locally
- the OTP is included in the `/send-otp` response only in development mode for testing

## Frontend flow

### Login page

- enter mobile number
- click `Send OTP`

### OTP page

- enter the 6-digit code
- click `Verify OTP`

### Dashboard

- existing fraud review UI remains available after login
- sample transactions still work
- fraud analysis still uses the same ML model
- SMS alerts are triggered from backend logic

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 train_model.py
python3 app.py
```

Open:

```text
http://127.0.0.1:7860
```

## Production run

```bash
gunicorn --bind 0.0.0.0:7860 app:app
```

## Docker deployment

```bash
docker build -t fraud-detection-system .
docker run -p 7860:7860 fraud-detection-system
```

## ML pipeline summary

The fraud model remains unchanged:

- Kaggle `creditcard.csv`
- 80/20 train-test split
- `StandardScaler`
- `SMOTE`
- Logistic Regression
- Random Forest
- automatic ROC-AUC-based selection
- `IsolationForest` anomaly detection

## Important note

This upgrade extends the existing project instead of replacing the fraud engine. The trained model, prediction flow, scoring, explanations, and transaction review logic are preserved while secure authentication and SMS delivery are added around them.
