# 🛡️ EXPayshield — Project Documentation

## 1. Overview
**EXPayshield** is a professional-grade, real-time credit card fraud detection platform. It combines machine learning (ML) with an advanced security pipeline to identify, block, and alert users about fraudulent transactions.

The project transformed a basic ML model into a complete **SaaS-ready application** with secure authentication, live monitoring, and automated SMS alerting.

---

## 2. Key Features
- **Machine Learning Engine**: High-accuracy fraud prediction (ROC-AUC 0.98+) using Random Forest and Anomaly Detection.
- **Hybrid Authentication**: Secure OTP-based login with two modes:
    - **Development Mode**: Free testing with on-screen OTPs (no SMS cost).
    - **Production Mode**: Real SMS delivery via Twilio for live security.
- **Real-Time Transaction Monitor**: A live dashboard that auto-generates and analyzes simulated transactions every few seconds.
- **Automated SMS Alerts**: Real-time alerts sent to the cardholder's mobile number for "Suspicious" or "Fraudulent" activities.
- **Premium Fintech UI**: A modern, responsive dashboard with frosted-glass effects, sticky headers, and real-time analytics cards.
- **Vercel Cloud Support**: Fully optimized for serverless deployment on Vercel.

---

## 3. Technology Stack
| Layer | Technologies |
|---|---|
| **Frontend** | HTML5, CSS3 (Vanilla), JavaScript (ES6+), Google Fonts (Manrope) |
| **Backend** | Python 3.11+, Flask (Framework), Gunicorn (WSGI Server) |
| **Machine Learning** | Scikit-learn (Random Forest, Isolation Forest), SMOTE (Imbalance Handling), Pandas, Joblib |
| **Communication** | Twilio SMS API |
| **Deployment** | Vercel (Serverless), Docker (Containerized) |

---

## 4. How It Works (Architecture)

### 📂 File Structure
- `app.py`: Main entry point for local execution.
- `api/index.py`: Serverless entry point for Vercel.
- `backend/`: 
    - `app.py`: Core Flask logic, routes, and API controllers.
    - `auth.py`: OTP generation, session management, and phone normalization.
    - `transaction_generator.py`: Realistic transaction simulation engine.
    - `fraud.py`: ML pipeline integration and risk assessment.
    - `sms.py`: SMS provider logic (Twilio vs. Dev-Console).
- `frontend/`:
    - `index.html`: Main dashboard UI.
    - `login.html`: Branded login page with mode selector.
    - `style.css`: Premium design system and responsive rules.

### 🔐 Authentication Flow
1. **Login**: User enters a mobile number and selects a mode (Dev/Prod).
2. **OTP Generation**: Backend generates a secure 6-digit code.
3. **Delivery**: 
    - In **Prod**: Sent via Twilio SMS API.
    - In **Dev**: Displayed on a secure card on the OTP page.
4. **Verification**: User enters the code; backend verifies it and creates a secure session.

### 📈 Fraud Detection Pipeline
1. **Input**: Transaction data (amount, location, merchant, time).
2. **Preprocessing**: Normalization and feature scaling.
3. **ML Prediction**: 
    - **Classification**: Is it fraud (0 or 1)?
    - **Anomaly Detection**: Is this transaction behavior outlier-like?
4. **Result**: A Risk Score (Safe, Suspicious, or Fraudulent).
5. **Alert**: If risk is > 0, an SMS alert is triggered.

---

## 5. Deployment & Execution

### 🚀 Local Execution
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train the model (creates fraud_model.pkl)
python train_model.py

# 3. Start the server
python app.py
```

### ☁️ Vercel Deployment
The project is pre-configured for Vercel. Simply run:
```bash
vercel --prod
```
*Note: Large dataset files are automatically excluded to meet Vercel's 250MB limit.*

---

## 6. What We Upgraded
1. **Branding**: Rebranded from "Detector" to **EXPayshield** with a custom logo and tagline.
2. **Infrastructure**: Replaced simple CSV lookups with a **real-time simulation engine**.
3. **Security**: Added **Session-based login** and **masked data** protection.
4. **Resiliency**: Implemented **On-demand transaction generation** for Vercel's serverless architecture.
5. **UI/UX**: Replaced basic forms with a **Premium Sticky Header** and **Mode Selection Cards**.

---

## 7. Configuration
To enable Production Mode (Real SMS), set these environment variables:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `OTP_MODE=twilio`

---
**Developed by Digimartrix — Secure Your Transactions.**
