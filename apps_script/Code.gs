/**
 * Sends application email through the Google account that deployed this web app.
 * Set the APP_SHARED_SECRET script property before deploying.
 */
function doPost(e) {
  const expectedSecret = PropertiesService.getScriptProperties()
    .getProperty("APP_SHARED_SECRET") || "";

  let request;
  try {
    request = JSON.parse((e && e.postData && e.postData.contents) || "{}");
  } catch (_error) {
    return jsonResponse({ ok: false, error: "invalid_request" });
  }
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    return jsonResponse({ ok: false, error: "invalid_request" });
  }

  const suppliedSecret = String(request.secret || "");
  if (!expectedSecret || !constantTimeEquals(suppliedSecret, expectedSecret)) {
    return jsonResponse({ ok: false, error: "unauthorized" });
  }

  const to = String(request.to || "").trim();
  const subject = String(request.subject || "").trim();
  const body = String(request.body || "");
  if (
    !isValidEmail(to) ||
    !subject || subject.length > 200 || /[\r\n]/.test(subject) ||
    !body || body.length > 10000
  ) {
    return jsonResponse({ ok: false, error: "invalid_request" });
  }

  try {
    MailApp.sendEmail({
      to: to,
      subject: subject,
      body: body,
      name: "EXPayshield",
    });
    return jsonResponse({ ok: true });
  } catch (_error) {
    return jsonResponse({ ok: false, error: "send_failed" });
  }
}

// Run this function once from the editor to authorize MailApp before deploying.
function authorizeMail() {
  MailApp.getRemainingDailyQuota();
}

function isValidEmail(value) {
  return value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function constantTimeEquals(left, right) {
  let difference = left.length ^ right.length;
  for (let i = 0; i < right.length; i += 1) {
    difference |= right.charCodeAt(i) ^ (left.charCodeAt(i) || 0);
  }
  return difference === 0;
}

function jsonResponse(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
