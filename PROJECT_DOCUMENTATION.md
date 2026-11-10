# 🛡️ EXPayshield — Project Documentation

## 1. Overview
**EXPayshield** is a professional-grade, real-time credit card fraud detection platform. It combines machine learning (ML) with an advanced security pipeline to identify, block, and alert users about fraudulent transactions.

The project transformed a basic ML model into a complete application with email OTP authentication, live monitoring, and email fraud alerts.

---

## 2. Key Features
- **Machine Learning Engine**: High-accuracy fraud prediction (ROC-AUC 0.98+) using Random Forest and Anomaly Detection.
- **Email Authentication**: Login asks for a mobile number and email address. The OTP verifies email access.
    - **Development Mode**: Free local testing with on-screen OTPs.
    - **Email Mode**: Sends OTPs through Gmail SMTP using a Google App Password.
- **Real-Time Transaction Monitor**: A live dashboard that auto-generates and analyzes simulated transactions every few seconds.
- **Automated Email Alerts**: Alerts are sent to the email used for login. Repeated live alerts have a five-minute cooldown by default.
- **Premium Fintech UI**: A modern, responsive dashboard with frosted-glass effects, sticky headers, and real-time analytics cards.
- **Vercel Cloud Support**: Fully optimized for serverless deployment on Vercel.

---

## 3. Technology Stack
| Layer | Technologies |
|---|---|
| **Frontend** | HTML5, CSS3 (Vanilla), JavaScript (ES6+), Google Fonts (Manrope) |
| **Backend** | Python 3.11+, Flask (Framework), Gunicorn (WSGI Server) |
| **Machine Learning** | Scikit-learn (Random Forest, Isolation Forest), SMOTE (Imbalance Handling), Pandas, Joblib |
| **Communication** | Gmail SMTP |
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
    - `email_service.py`: Gmail SMTP delivery for OTPs and fraud alerts.
- `frontend/`:
    - `index.html`: Main dashboard UI.
    - `login.html`: Branded login page with mode selector.
    - `style.css`: Premium design system and responsive rules.

### 🔐 Authentication Flow
1. **Login**: User enters a mobile number and email, then selects Development or Email OTP.
2. **OTP Generation**: Backend generates a secure 6-digit code.
3. **Delivery**: 
    - In **Email Mode**: Sent to the provided email through Gmail SMTP.
    - In **Development Mode**: Displayed on the OTP page.
4. **Verification**: User enters the code; backend verifies it and creates a secure session.

### 📈 Fraud Detection Pipeline
1. **Input**: Transaction data (amount, location, merchant, time).
2. **Preprocessing**: Normalization and feature scaling.
3. **ML Prediction**: 
    - **Classification**: Is it fraud (0 or 1)?
    - **Anomaly Detection**: Is this transaction behavior outlier-like?
4. **Result**: A Risk Score (Safe, Suspicious, or Fraudulent).
5. **Alert**: If risk is elevated, an email alert is sent to the logged-in email address.

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
To enable email OTP and email alerts, set these environment variables:
- `GMAIL_USERNAME` — the Gmail sender address
- `GMAIL_APP_PASSWORD` — a Google App Password, never the regular account password
- `OTP_MODE=email`
- `FLASK_SECRET_KEY` — a long random secret, required on Vercel
- `EMAIL_FROM_NAME=EXPayshield` (optional)

Enable 2-Step Verification on the Google account before creating its App Password. The App Password must be stored as a deployment secret, never in source code.

---
**Developed by Digimartrix — Secure Your Transactions.**
