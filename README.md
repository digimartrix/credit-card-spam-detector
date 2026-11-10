# 🛡️ EXPayshield — Real-Time Fraud Detection Platform

[![Vercel Deployment](https://img.shields.io/badge/Deploy-Vercel-black?logo=vercel)](https://credit-card-detector-liart.vercel.app)
[![Tech Stack](https://img.shields.io/badge/Stack-Python%20%7C%20Flask%20%7C%20ML-blue)](https://github.com/digimartrix/credit-card-spam-detector)

**EXPayshield** is a professional-grade credit card fraud detection system. It uses machine learning to analyze transactions in real time, provide risk scores, and send email alerts for suspicious activity.

---

## 🚀 Live Demo
Access the production dashboard here:  
👉 **[EXPayshield Live Dashboard](https://credit-card-detector-liart.vercel.app)**

---

## ✨ Key Features
- **🧠 Advanced ML Engine**: Real-time fraud scoring using Random Forest and Anomaly Detection.
- **✉️ Email OTP Auth**: Sign in with a mobile number and email address; verification codes can be sent through Google Apps Script or Gmail SMTP. Local development can display OTPs on-screen.
- **⏱️ Live Monitor**: Continuous transaction generation and analysis simulation.
- **🚨 Instant Alerts**: Email notifications for high-risk or suspicious transactions.
- **💎 Premium UI**: Clean, responsive fintech dashboard with dark-mode accents and sticky navigation.
- **☁️ Cloud Ready**: Optimized for serverless deployment on Vercel.

---

## 🛠️ Tech Stack
- **Backend**: Python, Flask, Gunicorn
- **Machine Learning**: Scikit-learn, SMOTE, Pandas
- **Frontend**: Vanilla JS, CSS3, HTML5
- **Services**: Google Apps Script or Gmail SMTP, Vercel

---

## 📖 Documentation
Detailed information about the architecture, development process, and how it works can be found in:  
📄 **[PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md)**

---

## 🏗️ Local Setup
```bash
# Clone the repository
git clone https://github.com/digimartrix/credit-card-spam-detector.git
cd credit-card-spam-detector

# Install requirements
pip install -r requirements.txt

# Train the model
python train_model.py

# Run locally
python app.py
```

## ✉️ Email Configuration

For email OTPs and fraud alerts, set `OTP_MODE=email` and `FLASK_SECRET_KEY`.
The recommended domain-free option is Google Apps Script: set
`EMAIL_PROVIDER=apps_script`, `APPS_SCRIPT_URL`, and `APPS_SCRIPT_SECRET`.
See [the Apps Script setup guide](./apps_script/README.md). The Gmail SMTP
alternative uses `EMAIL_PROVIDER=gmail_smtp`, `GMAIL_USERNAME`, and
`GMAIL_APP_PASSWORD` (a Google App Password, not your regular password).
Add production values in the Vercel project's Environment Variables settings,
then redeploy for changes to take effect.

To use the free on-screen OTP locally, leave `OTP_MODE=dev`.

---

## 🤝 Developed by
**Digimartrix** — *Engineering Secure Financial Futures.*
