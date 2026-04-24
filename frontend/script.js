/* ================================================================
   Credit Card Fraud Detection — Frontend Controller
   ================================================================
   Handles three pages: login, OTP verification, and dashboard.
   The dashboard includes both manual transaction review AND
   a real-time live transaction monitor that auto-polls every 3s.
   ================================================================ */

const page = document.body.dataset.page;
const config = window.PAGE_CONFIG || {};

if (page === "login") {
    initializeLoginPage();
} else if (page === "otp") {
    initializeOtpPage();
} else if (page === "dashboard") {
    initializeDashboardPage();
}


/* ================================================================
   LOGIN PAGE — Interactive Mode Selector + Hybrid OTP
   Users can click on Dev or Prod cards to choose their mode.
   Production errors are translated to friendly messages.
   ================================================================ */
function initializeLoginPage() {
    const loginForm = document.getElementById("login-form");
    const mobileNumberInput = document.getElementById("mobile-number");
    const sendOtpButton = document.getElementById("send-otp-button");
    const feedback = document.getElementById("auth-feedback");

    // Mode selector elements
    const modeCardDev = document.getElementById("mode-card-dev");
    const modeCardProd = document.getElementById("mode-card-prod");
    const modeTagDev = document.getElementById("mode-tag-dev");
    const modeTagProd = document.getElementById("mode-tag-prod");
    const envBadge = document.getElementById("env-badge");
    const envBadgeIcon = document.getElementById("env-badge-icon");
    const envBadgeTitle = document.getElementById("env-badge-title");
    const envBadgeDesc = document.getElementById("env-badge-desc");
    const fieldNoteText = document.getElementById("field-note-text");

    // Current selected mode — starts at "dev"
    let selectedMode = "dev";

    // ── Mode configs for dynamic UI updates ──
    const MODE_UI = {
        dev: {
            badgeClass: "env-development",
            icon: "🛠️",
            title: "Development Mode Selected",
            desc: "OTP is displayed on-screen for testing. No SMS is sent.",
            fieldNote: "Enter any valid phone number. OTP will be shown on screen — no SMS is sent.",
            buttonLabel: "🛠️ Generate OTP",
            buttonLoading: "Generating OTP...",
        },
        twilio: {
            badgeClass: "env-production",
            icon: "🔒",
            title: "Production Mode Selected",
            desc: "OTP will be sent as a real SMS via Twilio to verified numbers.",
            fieldNote: "Use international format (e.g. +91XXXXXXXXXX). Only Twilio-verified numbers will receive SMS. Limited to 3 SMS per 25 minutes.",
            buttonLabel: "📲 Send OTP via SMS",
            buttonLoading: "Sending SMS...",
        },
    };

    // ── Apply mode visuals ──
    function applyModeUI(mode) {
        const ui = MODE_UI[mode];

        // Cards
        modeCardDev.classList.toggle("mode-card-active", mode === "dev");
        modeCardProd.classList.toggle("mode-card-active", mode === "twilio");
        if (modeTagDev) modeTagDev.hidden = mode !== "dev";
        if (modeTagProd) modeTagProd.hidden = mode !== "twilio";

        // Badge
        envBadge.className = "env-badge " + ui.badgeClass;
        envBadgeIcon.textContent = ui.icon;
        envBadgeTitle.textContent = ui.title;
        envBadgeDesc.textContent = ui.desc;

        // Field note
        if (fieldNoteText) fieldNoteText.textContent = ui.fieldNote;

        // Button
        sendOtpButton.innerHTML = ui.buttonLabel;

        // Clear any previous feedback
        clearFeedback(feedback);
    }

    // ── Click handlers for mode cards ──
    function selectMode(mode) {
        selectedMode = mode;
        applyModeUI(mode);
    }

    modeCardDev.addEventListener("click", () => selectMode("dev"));
    modeCardProd.addEventListener("click", () => selectMode("twilio"));

    // Keyboard accessibility
    modeCardDev.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectMode("dev"); } });
    modeCardProd.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectMode("twilio"); } });

    // ── Form submit ──
    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearFeedback(feedback);
        const ui = MODE_UI[selectedMode];
        setButtonState(sendOtpButton, true, ui.buttonLoading);

        try {
            const response = await fetch("/send-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    mobile_number: mobileNumberInput.value.trim(),
                    mode: selectedMode,
                }),
            });
            const payload = await response.json();

            if (!response.ok || !payload.ok) {
                // Check if it's a production SMS error — show friendly message
                if (payload.error_type === "production_sms_failed") {
                    showFeedback(feedback, [
                        ...payload.errors,
                        "💡 Tip: Switch to Development Mode (click the card above) to test without SMS."
                    ], "error");
                } else {
                    showFeedback(feedback, payload.errors || ["Unable to send OTP."], "error");
                }
                return;
            }

            // Store dev OTP for the OTP verification page
            if (payload.development_otp) {
                window.sessionStorage.setItem("development-otp", payload.development_otp);
            }
            // Store the mode the user chose
            window.sessionStorage.setItem("selected-mode", selectedMode);

            // Show appropriate feedback
            const messages = [payload.message || "OTP sent."];
            if (payload.development_otp) {
                messages.push(`Your OTP is: ${payload.development_otp}`);
            }
            showFeedback(
                feedback,
                messages,
                payload.development_otp ? "warning" : "success"
            );

            // Redirect to OTP page
            const delay = payload.development_otp ? 1200 : 650;
            window.setTimeout(() => {
                window.location.href = payload.redirect_url || "/otp";
            }, delay);
        } catch (error) {
            showFeedback(feedback, ["Unable to reach the OTP service. Please check your connection."], "error");
        } finally {
            setButtonState(sendOtpButton, false, ui.buttonLabel);
        }
    });
}


/* ================================================================
   OTP VERIFICATION PAGE — Hybrid OTP
   In development mode: shows the OTP in a prominent card with
   auto-fill capability. In production mode: standard OTP entry.
   ================================================================ */
function initializeOtpPage() {
    const otpForm = document.getElementById("otp-form");
    const otpInput = document.getElementById("otp-code");
    const verifyOtpButton = document.getElementById("verify-otp-button");
    const feedback = document.getElementById("auth-feedback");
    const devOtpDisplay = document.getElementById("dev-otp-display");
    const devOtpCode = document.getElementById("dev-otp-code");
    const devOtpAutofill = document.getElementById("dev-otp-autofill");
    const resendButton = document.getElementById("resend-otp-button");

    const useTwilio = config.use_twilio || false;
    const developmentOtp = window.sessionStorage.getItem("development-otp");

    // ── Show dev OTP display card if in development mode ──
    if (!useTwilio && developmentOtp && devOtpDisplay && devOtpCode) {
        devOtpDisplay.hidden = false;
        devOtpCode.textContent = developmentOtp;

        // Auto-fill button: fills the OTP input and submits the form
        if (devOtpAutofill) {
            devOtpAutofill.addEventListener("click", () => {
                otpInput.value = developmentOtp;
                otpForm.dispatchEvent(new Event("submit", { cancelable: true }));
            });
        }
    } else if (useTwilio) {
        // Production mode — hide the dev display
        if (devOtpDisplay) devOtpDisplay.hidden = true;
        showFeedback(feedback, ["📲 Check your phone for the SMS with your verification code."], "success");
    }

    // ── OTP Verification Form ──
    otpForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearFeedback(feedback);
        setButtonState(verifyOtpButton, true, "Verifying...");

        try {
            const response = await fetch("/verify-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    mobile_number: config.pending_phone,
                    otp: otpInput.value.trim(),
                }),
            });
            const payload = await response.json();

            if (!response.ok || !payload.ok) {
                showFeedback(feedback, payload.errors || ["OTP verification failed."], "error");
                return;
            }

            showFeedback(feedback, [payload.message || "Login successful. Redirecting..."], "success");
            window.sessionStorage.removeItem("development-otp");
            window.setTimeout(() => {
                window.location.href = payload.redirect_url || "/dashboard";
            }, 500);
        } catch (error) {
            showFeedback(feedback, ["Unable to reach the verification service."], "error");
        } finally {
            setButtonState(verifyOtpButton, false, "🔐 Verify OTP");
        }
    });

    // ── Resend OTP button ──
    if (resendButton) {
        let resendCooldown = 0;
        let cooldownTimer = null;

        resendButton.addEventListener("click", async () => {
            if (resendCooldown > 0) return;

            resendButton.disabled = true;
            resendButton.textContent = "Sending...";

            try {
                const response = await fetch("/send-otp", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "same-origin",
                    body: JSON.stringify({
                        mobile_number: config.pending_phone,
                    }),
                });
                const payload = await response.json();

                if (!response.ok || !payload.ok) {
                    showFeedback(feedback, payload.errors || ["Unable to resend OTP."], "error");
                    resendButton.disabled = false;
                    resendButton.textContent = "Resend OTP";
                    return;
                }

                // Update dev OTP display if in dev mode
                if (payload.development_otp) {
                    window.sessionStorage.setItem("development-otp", payload.development_otp);
                    if (devOtpDisplay && devOtpCode) {
                        devOtpDisplay.hidden = false;
                        devOtpCode.textContent = payload.development_otp;
                    }
                }

                showFeedback(
                    feedback,
                    [payload.development_otp
                        ? `New OTP generated: ${payload.development_otp}`
                        : "New OTP sent to your phone."],
                    payload.development_otp ? "warning" : "success"
                );

                // 30-second cooldown
                resendCooldown = 30;
                cooldownTimer = setInterval(() => {
                    resendCooldown--;
                    if (resendCooldown <= 0) {
                        clearInterval(cooldownTimer);
                        resendButton.disabled = false;
                        resendButton.textContent = "Resend OTP";
                    } else {
                        resendButton.textContent = `Resend in ${resendCooldown}s`;
                    }
                }, 1000);
            } catch (error) {
                showFeedback(feedback, ["Unable to reach the OTP service."], "error");
                resendButton.disabled = false;
                resendButton.textContent = "Resend OTP";
            }
        });
    }
}


/* ================================================================
   DASHBOARD PAGE (Manual Review + Live Monitor)
   ================================================================ */
function initializeDashboardPage() {
    const storageKey = buildHistoryStorageKey(config.session?.user_phone || "authenticated");
    const state = {
        history: loadHistory(storageKey),
        latestResult: null,
    };

    // --- Manual review DOM references ---
    const form = document.getElementById("transaction-form");
    const cardNumberInput = document.getElementById("card-number");
    const cardHolderInput = document.getElementById("card-holder-name");
    const amountInput = document.getElementById("transaction-amount");
    const timeInput = document.getElementById("transaction-time");
    const locationInput = document.getElementById("location");
    const merchantInput = document.getElementById("merchant-type");
    const sampleProfileInput = document.getElementById("sample-profile");
    const loadSampleButton = document.getElementById("load-sample");
    const analyzeButton = document.getElementById("analyze-button");
    const logoutButton = document.getElementById("logout-button");
    const feedback = document.getElementById("form-feedback");
    const resultEmpty = document.getElementById("result-empty");
    const resultPanel = document.getElementById("result-panel");
    const decisionBanner = document.getElementById("decision-banner");
    const riskChip = document.getElementById("risk-chip");
    const decisionTitle = document.getElementById("decision-title");
    const decisionSummary = document.getElementById("decision-summary");
    const riskScoreValue = document.getElementById("risk-score-value");
    const riskScoreBar = document.getElementById("risk-score-bar");
    const mlProbability = document.getElementById("ml-probability");
    const behaviorScore = document.getElementById("behavior-score");
    const anomalyScore = document.getElementById("anomaly-score");
    const reasonList = document.getElementById("reason-list");
    const decisionGuidance = document.getElementById("decision-guidance");
    const alertStatus = document.getElementById("alert-status");
    const sessionDistribution = document.getElementById("session-distribution");
    const historyBody = document.getElementById("history-body");
    const historyEmpty = document.getElementById("history-empty");
    const downloadReportButton = document.getElementById("download-report");

    if (state.history.length > 0) {
        state.latestResult = state.history[0];
        renderResult(state.latestResult, null);
    }

    renderHistory();
    renderSessionDistribution();

    form.addEventListener("submit", handleAnalyze);
    loadSampleButton.addEventListener("click", handleLoadSample);
    downloadReportButton.addEventListener("click", downloadReport);
    logoutButton.addEventListener("click", handleLogout);
    cardNumberInput.addEventListener("input", handleCardNumberInput);

    // --- Initialize the live monitor ---
    initializeLiveMonitor(state, storageKey);

    /* ------------------------------------------------------------ */
    /* Manual review helpers                                        */
    /* ------------------------------------------------------------ */

    function loadHistory(key) {
        try {
            const raw = window.localStorage.getItem(key);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) { return []; }
    }

    function saveHistory() {
        window.localStorage.setItem(storageKey, JSON.stringify(state.history.slice(0, 25)));
    }

    function handleCardNumberInput(event) {
        const digits = onlyDigits(event.target.value).slice(0, 19);
        event.target.value = formatCardNumber(digits);
    }

    async function handleLoadSample() {
        setButtonState(loadSampleButton, true, "Loading...");
        clearFeedback(feedback);
        try {
            const response = await fetch("/api/sample", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ profile: sampleProfileInput.value }),
            });
            const payload = await response.json();
            if (response.status === 401) { redirectToLogin(payload.redirect_url); return; }
            if (!response.ok || !payload.ok) {
                showFeedback(feedback, payload.errors || ["Unable to load sample transaction."], "error");
                return;
            }
            applyTransactionToForm(payload.transaction);
            showFeedback(feedback, ["Sample transaction loaded."], "success");
        } catch (error) {
            showFeedback(feedback, ["Unable to reach the sample transaction service."], "error");
        } finally {
            setButtonState(loadSampleButton, false, "Load sample");
        }
    }

    async function handleAnalyze(event) {
        event.preventDefault();
        clearFeedback(feedback);
        setButtonState(analyzeButton, true, "Analyzing...");
        try {
            const response = await fetch("/api/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ transaction: collectFormData(), history: state.history }),
            });
            const payload = await response.json();
            if (response.status === 401) { redirectToLogin(payload.redirect_url); return; }
            if (!response.ok || !payload.ok) {
                showFeedback(feedback, payload.errors || ["Unable to analyze this transaction."], "error");
                return;
            }
            state.latestResult = payload.result;
            state.history = [payload.result, ...state.history].slice(0, 25);
            saveHistory();
            renderResult(state.latestResult, payload.alert);
            renderHistory();
            renderSessionDistribution();
            const messages = ["Transaction analyzed successfully."];
            if (payload.alert?.sms?.success) {
                messages.push(payload.alert.sms.dry_run ? "SMS alert simulated in dry-run mode." : "SMS alert sent.");
            }
            if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
                messages.push(...payload.warnings);
            }
            showFeedback(feedback, messages, payload.warnings?.length ? "warning" : "success");
        } catch (error) {
            showFeedback(feedback, ["Unable to reach the fraud analysis service."], "error");
        } finally {
            setButtonState(analyzeButton, false, "Analyze transaction");
        }
    }

    async function handleLogout() {
        setButtonState(logoutButton, true, "Logging out...");
        try {
            const response = await fetch("/logout", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
            });
            const payload = await response.json();
            window.location.href = payload.redirect_url || "/login";
        } catch (error) {
            window.location.href = "/login";
        }
    }

    function collectFormData() {
        return {
            card_number: cardNumberInput.value,
            card_holder_name: cardHolderInput.value.trim(),
            transaction_amount: amountInput.value,
            transaction_time: timeInput.value,
            location: locationInput.value,
            merchant_type: merchantInput.value,
        };
    }

    function applyTransactionToForm(transaction) {
        cardNumberInput.value = formatCardNumber(onlyDigits(transaction.card_number));
        cardHolderInput.value = transaction.card_holder_name;
        amountInput.value = Number(transaction.transaction_amount).toFixed(2);
        timeInput.value = transaction.transaction_time;
        locationInput.value = transaction.location;
        merchantInput.value = transaction.merchant_type;
    }

    function renderResult(result, alert) {
        resultEmpty.hidden = true;
        resultPanel.hidden = false;
        const bandClass = normalizeBand(result.risk_band);
        decisionBanner.className = `decision-banner ${bandClass}`;
        riskChip.className = `risk-chip ${bandClass}`;
        riskChip.textContent = result.risk_band;
        decisionTitle.textContent = result.decision;
        decisionSummary.textContent = `${result.card_masked} · ${result.card_holder_name} · ${result.merchant_type} · ${result.location}`;
        riskScoreValue.textContent = `${result.risk_score.toFixed(1)} / 100`;
        riskScoreBar.style.width = `${Math.min(result.risk_score, 100)}%`;
        riskScoreBar.style.background = result.color;
        mlProbability.textContent = `${result.model_probability.toFixed(2)}%`;
        behaviorScore.textContent = `${result.behavior_score.toFixed(2)}%`;
        anomalyScore.textContent = `${result.anomaly_risk.toFixed(2)}%`;
        reasonList.innerHTML = result.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
        decisionGuidance.textContent = guidanceForDecision(result.decision);
        renderAlertStatus(alert);
    }

    function renderAlertStatus(alert) {
        if (!alert) {
            alertStatus.hidden = true;
            alertStatus.className = "alert-status";
            alertStatus.innerHTML = "";
            return;
        }
        const sms = alert.sms || {};
        const type = sms.success ? "success" : "error";
        const lines = [`<strong>SMS alert</strong>`, `<p>${escapeHtml(alert.message)}</p>`];
        if (sms.success) {
            lines.push(`<p>${sms.dry_run ? "Simulated SMS delivery in dry-run mode." : `Delivered via ${escapeHtml(sms.provider || "twilio")}.`}</p>`);
        } else {
            lines.push(`<p>${escapeHtml(sms.error || "SMS delivery failed.")}</p>`);
        }
        alertStatus.hidden = false;
        alertStatus.className = `alert-status ${type}`;
        alertStatus.innerHTML = lines.join("");
    }

    function renderSessionDistribution() {
        const counts = { Safe: 0, Suspicious: 0, Fraud: 0 };
        state.history.forEach((item) => {
            if (counts[item.risk_band] !== undefined) counts[item.risk_band] += 1;
        });
        const total = state.history.length;
        if (total === 0) {
            sessionDistribution.innerHTML = `<div class="distribution-empty">No session transactions yet.</div>`;
            return;
        }
        const rows = [
            { label: "Safe", className: "safe", count: counts.Safe },
            { label: "Suspicious", className: "suspicious", count: counts.Suspicious },
            { label: "Fraud", className: "fraud", count: counts.Fraud },
        ];
        sessionDistribution.innerHTML = rows.map((row) => {
            const percent = (row.count / total) * 100;
            return `<div class="distribution-row"><div class="distribution-key"><span class="distribution-dot ${row.className}"></span><span>${row.label}</span></div><div class="distribution-meta"><div class="distribution-track"><div class="distribution-fill ${row.className}" style="width: ${percent}%"></div></div><strong>${row.count}</strong></div></div>`;
        }).join("");
    }

    function renderHistory() {
        if (state.history.length === 0) {
            historyBody.innerHTML = "";
            historyEmpty.hidden = false;
            downloadReportButton.disabled = true;
            return;
        }
        historyEmpty.hidden = true;
        downloadReportButton.disabled = false;
        historyBody.innerHTML = state.history.map((item) => {
            const bandClass = normalizeBand(item.risk_band);
            return `<tr class="history-row-${bandClass}"><td>${escapeHtml(item.card_masked)}</td><td>${escapeHtml(item.card_holder_name)}</td><td>${formatCurrency(item.transaction_amount)}</td><td>${escapeHtml(item.merchant_type)}</td><td><span class="history-risk-pill ${bandClass}">${escapeHtml(item.risk_band)}</span></td><td>${escapeHtml(item.decision)}</td></tr>`;
        }).join("");
    }

    function downloadReport() {
        if (state.history.length === 0) return;
        const headers = ["Card","Card Holder","Amount","Time","Location","Merchant Type","Risk Band","Risk Score","Decision","ML Probability","Behavior Score","Anomaly Risk","Reasons"];
        const rows = state.history.map((item) => [item.card_masked,item.card_holder_name,item.transaction_amount,item.transaction_time,item.location,item.merchant_type,item.risk_band,item.risk_score,item.decision,item.model_probability,item.behavior_score,item.anomaly_risk,item.reasons.join(" | ")]);
        const csv = [headers, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "fraud_detection_report.csv";
        link.click();
        URL.revokeObjectURL(url);
    }
}


/* ================================================================
   LIVE TRANSACTION MONITOR
   Polls /live-transaction every 3 seconds, displays the incoming
   transaction, sends it to /api/analyze-live for ML scoring, and
   updates the live feed table with results.
   ================================================================ */
function initializeLiveMonitor(state, storageKey) {
    const POLL_INTERVAL = 3000;

    // DOM references
    const toggleBtn = document.getElementById("toggle-live");
    const indicator = document.getElementById("live-indicator");
    const totalCount = document.getElementById("live-total-count");
    const safeCount = document.getElementById("live-safe-count");
    const suspiciousCount = document.getElementById("live-suspicious-count");
    const fraudCount = document.getElementById("live-fraud-count");
    const currentEmpty = document.getElementById("live-current-empty");
    const currentActive = document.getElementById("live-current-active");
    const txMerchant = document.getElementById("live-tx-merchant");
    const txDetails = document.getElementById("live-tx-details");
    const txAmount = document.getElementById("live-tx-amount");
    const txCard = document.getElementById("live-tx-card");
    const txHolder = document.getElementById("live-tx-holder");
    const txTime = document.getElementById("live-tx-time");
    const txResult = document.getElementById("live-tx-result");
    const liveRiskChip = document.getElementById("live-risk-chip");
    const liveRiskScore = document.getElementById("live-risk-score");
    const liveRiskBar = document.getElementById("live-risk-bar");
    const liveDecision = document.getElementById("live-decision-text");
    const liveAlertBadge = document.getElementById("live-alert-badge");
    const liveAnalyzing = document.getElementById("live-analyzing");
    const liveFeedBody = document.getElementById("live-feed-body");
    const liveFeedEmpty = document.getElementById("live-feed-empty");

    let isRunning = true;
    let lastTxId = null;
    let pollTimer = null;
    const liveCounts = { total: 0, Safe: 0, Suspicious: 0, Fraud: 0 };
    const liveFeed = []; // Array of analyzed results for the feed table

    // Toggle pause/resume
    toggleBtn.addEventListener("click", () => {
        isRunning = !isRunning;
        toggleBtn.textContent = isRunning ? "Pause" : "Resume";
        indicator.className = isRunning ? "live-indicator" : "live-indicator paused";
        if (isRunning) startPolling();
        else stopPolling();
    });

    function startPolling() {
        if (pollTimer) return;
        poll(); // Immediate first poll
        pollTimer = setInterval(poll, POLL_INTERVAL);
    }

    function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    async function poll() {
        if (!isRunning) return;

        try {
            // 1. Fetch the latest live transaction
            const res = await fetch("/live-transaction", { credentials: "same-origin" });
            if (res.status === 401) { redirectToLogin(); return; }
            const data = await res.json();
            if (!data.ok || !data.transaction) return;

            const tx = data.transaction;

            // Skip if we've already processed this transaction
            if (tx.id === lastTxId) return;
            lastTxId = tx.id;

            // 2. Display the incoming transaction
            showIncomingTransaction(tx);

            // 3. Send to ML model for analysis
            liveAnalyzing.hidden = false;
            txResult.hidden = true;

            const analyzeRes = await fetch("/api/analyze-live", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    transaction: {
                        card_number: tx.card_number,
                        card_holder_name: tx.card_holder_name,
                        transaction_amount: tx.transaction_amount,
                        transaction_time: tx.transaction_time,
                        location: tx.location,
                        merchant_type: tx.merchant_type,
                    },
                    history: state.history,
                }),
            });

            if (analyzeRes.status === 401) { redirectToLogin(); return; }
            const analyzeData = await analyzeRes.json();

            liveAnalyzing.hidden = true;

            if (!analyzeData.ok) return;

            // 4. Show the result
            const result = analyzeData.result;
            showTransactionResult(result, analyzeData.alert, tx);

            // 5. Update counters
            liveCounts.total++;
            if (liveCounts[result.risk_band] !== undefined) liveCounts[result.risk_band]++;
            updateLiveCounters();

            // 6. Add to live feed
            liveFeed.unshift({ ...result, merchant_name: tx.merchant_name, city: tx.city, alert: analyzeData.alert });
            if (liveFeed.length > 25) liveFeed.length = 25;
            renderLiveFeed();

            // 7. Also add to main history for session distribution
            state.history = [result, ...state.history].slice(0, 25);
            window.localStorage.setItem(storageKey, JSON.stringify(state.history.slice(0, 25)));

        } catch (err) {
            console.error("Live monitor error:", err);
        }
    }

    function showIncomingTransaction(tx) {
        currentEmpty.hidden = true;
        currentActive.hidden = false;

        txMerchant.textContent = tx.merchant_name || tx.merchant_type;
        txDetails.textContent = `${tx.city || tx.location} · ${tx.merchant_type}`;
        txAmount.textContent = formatCurrency(tx.transaction_amount);
        txCard.textContent = tx.card_masked || `**** **** **** ${tx.card_number.slice(-4)}`;
        txHolder.textContent = tx.card_holder_name;
        txTime.textContent = tx.timestamp || tx.transaction_time;

        txResult.hidden = true;
        liveAlertBadge.hidden = true;
    }

    function showTransactionResult(result, alert, tx) {
        txResult.hidden = false;
        const bandClass = normalizeBand(result.risk_band);

        liveRiskChip.className = `risk-chip ${bandClass}`;
        liveRiskChip.textContent = result.risk_band;
        liveRiskScore.textContent = `${result.risk_score.toFixed(1)} / 100`;
        liveRiskBar.style.width = `${Math.min(result.risk_score, 100)}%`;
        liveRiskBar.style.background = result.color;
        liveDecision.textContent = result.decision;

        // SMS alert badge
        if (alert) {
            liveAlertBadge.hidden = false;
            const sms = alert.sms || {};
            if (sms.success && sms.dry_run) {
                liveAlertBadge.className = "live-alert-badge sms-dry";
                liveAlertBadge.textContent = `📱 SMS simulated: ${alert.message}`;
            } else if (sms.success) {
                liveAlertBadge.className = "live-alert-badge sms-sent";
                liveAlertBadge.textContent = `📱 SMS sent: ${alert.message}`;
            } else {
                liveAlertBadge.className = "live-alert-badge sms-failed";
                liveAlertBadge.textContent = `⚠ SMS failed: ${sms.error || "Delivery error"}`;
            }
        } else {
            liveAlertBadge.hidden = true;
        }
    }

    function updateLiveCounters() {
        totalCount.textContent = liveCounts.total;
        safeCount.textContent = liveCounts.Safe;
        suspiciousCount.textContent = liveCounts.Suspicious;
        fraudCount.textContent = liveCounts.Fraud;
    }

    function renderLiveFeed() {
        if (liveFeed.length === 0) {
            liveFeedBody.innerHTML = "";
            liveFeedEmpty.hidden = false;
            return;
        }
        liveFeedEmpty.hidden = true;
        liveFeedBody.innerHTML = liveFeed.map((item, idx) => {
            const bandClass = normalizeBand(item.risk_band);
            const isNew = idx === 0 ? " history-row-new" : "";
            const smsIcon = item.alert
                ? (item.alert.sms?.success ? "✅" : "❌")
                : "—";
            return `<tr class="history-row-${bandClass}${isNew}"><td>${liveCounts.total - idx}</td><td>${escapeHtml(item.card_masked)}</td><td>${escapeHtml(item.card_holder_name)}</td><td>${escapeHtml(item.merchant_name || item.merchant_type)}</td><td>${escapeHtml(item.city || item.location)}</td><td>${formatCurrency(item.transaction_amount)}</td><td><span class="history-risk-pill ${bandClass}">${escapeHtml(item.risk_band)}</span></td><td>${escapeHtml(item.decision)}</td><td>${smsIcon}</td></tr>`;
        }).join("");
    }

    // Start polling on load
    startPolling();
}


/* ================================================================
   SHARED UTILITY FUNCTIONS
   ================================================================ */

function buildHistoryStorageKey(value) {
    return `fraud-detection-history:${String(value || "authenticated").replace(/[^a-zA-Z0-9]/g, "_")}`;
}

function redirectToLogin(target) {
    window.location.href = target || "/login";
}

function guidanceForDecision(decision) {
    if (decision === "Transaction Approved") {
        return "Approve the payment and allow the customer to continue without additional friction.";
    }
    if (decision === "OTP Verification Required") {
        return "Hold the transaction briefly and request OTP verification before settlement.";
    }
    return "Block the payment, flag the attempt, and route it for manual fraud review if needed.";
}

function normalizeBand(band) {
    return String(band || "").trim().toLowerCase().replace(/\s+/g, "-");
}

function setButtonState(button, disabled, label) {
    button.disabled = disabled;
    button.textContent = label;
}

function showFeedback(element, messages, type) {
    element.hidden = false;
    element.className = `feedback ${type}`;
    element.innerHTML = Array.isArray(messages)
        ? messages.map((message) => `<div>${escapeHtml(message)}</div>`).join("")
        : `<div>${escapeHtml(String(messages))}</div>`;
}

function clearFeedback(element) {
    element.hidden = true;
    element.className = "feedback";
    element.innerHTML = "";
}

function onlyDigits(value) {
    return String(value || "").replace(/\D/g, "");
}

function formatCardNumber(value) {
    return value.match(/.{1,4}/g)?.join(" ") || "";
}

function formatCurrency(value) {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
    }).format(Number(value || 0));
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
