// PharmaFind - Phase 6: customer accounts (phone number + one-time code).
// Guests can still search and scan without an account. The account is for ordering (Phase 7).
// Uses $, t, openModal, closeModal (app.js) and toast (scan.js).

const account = {
  user: null,          // the logged-in customer, or null for a guest
  step: "phone",       // phone | code | profile
  isNew: false,        // true right after a brand-new account was made (we ask for a name)
  phone: "",           // the number we sent the code to, e.g. +9647701234567
  phoneDisplay: "",    // the same number as people write it, e.g. 0770 123 4567
  testCode: null,      // only in test mode (no SMS yet): the code, shown on the page
  codeUntil: 0,        // when the code stops working (ms)
  resendAt: 0,         // when "Send a new code" can be pressed again (ms)
  timer: null,
  busy: false,
  errors: { phone: null, code: null },
};

// Phone numbers and codes always read left-to-right, even inside a Kurdish/Arabic sentence.
const ltr = (s) => "⁦" + s + "⁩";

// Kurdish/Arabic keyboards type ٠١٢٣ or ۰۱۲۳. Turn them into 0123.
const asciiDigits = (s) => s
  .replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 0x0660)
  .replace(/[۰-۹]/g, (d) => d.charCodeAt(0) - 0x06F0);

async function accountApi(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "X-Requested-With": "fetch", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* not JSON */ }
  return { ok: res.ok, status: res.status, data };
}

function errorText(err) {
  if (!err) return "";
  switch (err.error) {
    case "bad_phone": return t("acc_err_phone", { example: ltr("0770 123 4567") });
    case "wait": return t("acc_err_wait", { n: err.retry_in });
    case "too_many": return t("acc_err_too_many");
    case "expired": return t("acc_err_expired");
    case "wrong_code": return t("acc_err_wrong", { n: err.tries_left });
    case "no_tries": return t("acc_err_no_tries");
    case "bad_code": return t("acc_err_code_len");
    default: return t("acc_err_network");
  }
}

function setError(where, err) {
  account.errors[where] = err;
  const el = $(where === "phone" ? "acc-phone-error" : "acc-code-error");
  el.textContent = errorText(err);
  el.hidden = !err;
}

// ---------------- Drawing ----------------
function renderAccount() {
  const u = account.user;
  $("account-label").textContent = u ? (u.name || t("acc_my_account")) : t("acc_login");
  $("account-btn").classList.toggle("on", !!u);
  $("account-btn").title = u ? t("acc_my_account") : t("acc_login");

  const titles = { phone: "acc_title_login", code: "acc_title_code",
                   profile: account.isNew ? "acc_title_welcome" : "acc_title_account" };
  $("acc-title").textContent = t(titles[account.step]);
  $("acc-sent-to").textContent = t("acc_sent_to", { phone: ltr(account.phoneDisplay) });
  $("acc-test-code").hidden = !account.testCode;
  $("acc-test-code").textContent = account.testCode ? t("acc_test_code", { code: ltr(account.testCode) }) : "";
  $("acc-phone-line").textContent = u ? t("acc_phone_line", { phone: ltr(u.phone_display) }) : "";
  $("acc-skip").hidden = !account.isNew;
  $("acc-logout").hidden = account.isNew;
  setError("phone", account.errors.phone);   // re-translate any message on screen
  setError("code", account.errors.code);
  renderResend();
}
window.renderAccount = renderAccount;

function renderResend() {
  const left = Math.ceil((account.resendAt - Date.now()) / 1000);
  const btn = $("acc-resend");
  btn.disabled = left > 0;
  btn.textContent = left > 0 ? t("acc_resend_in", { n: left }) : t("acc_resend");
}

function startResendTimer(seconds) {
  account.resendAt = Date.now() + seconds * 1000;
  clearInterval(account.timer);
  account.timer = setInterval(() => {
    renderResend();
    if (Date.now() >= account.resendAt) clearInterval(account.timer);
  }, 1000);
  renderResend();
}

function showStep(step) {
  account.step = step;
  $("acc-phone-step").hidden = step !== "phone";
  $("acc-code-step").hidden = step !== "code";
  $("acc-profile-step").hidden = step !== "profile";
  renderAccount();
  const first = { phone: "acc-phone", code: "acc-code", profile: "acc-name" }[step];
  setTimeout(() => $(first).focus(), 60);
}

function setBusy(form, on) {
  account.busy = on;
  form.querySelectorAll("button").forEach((b) => { if (b.id !== "acc-resend") b.disabled = on; });
  if (!on) renderResend();
}

// ---------------- Opening and closing ----------------
function openAccount() {
  setError("phone", null);
  setError("code", null);
  if (account.user) {
    account.isNew = false;
    $("acc-name").value = account.user.name || "";
    showStep("profile");
  } else if (account.step === "code" && Date.now() < account.codeUntil) {
    showStep("code");              // they closed the pop-up while waiting for the SMS
  } else {
    showStep("phone");
  }
  openModal($("account-modal"));
}

window.onAccountClosed = () => {
  if (account.user && account.isNew) {   // closed the "what's your name" step: that's fine
    account.isNew = false;
    toast(t("acc_logged_in"));
  }
};

// ---------------- Step 1: send the code ----------------
async function sendCode(phone, form, errorWhere) {
  if (account.busy) return;
  setError(errorWhere, null);
  setBusy(form, true);
  let r;
  try {
    r = await accountApi("/api/account/send-code", "POST", { phone });
  } catch {
    r = { ok: false, data: { error: "network" } };
  }
  setBusy(form, false);
  if (!r.ok) {
    setError(errorWhere, r.data);
    if (r.data.error === "wait") startResendTimer(r.data.retry_in);
    return;
  }
  account.phone = r.data.phone;
  account.phoneDisplay = r.data.phone_display;
  account.testCode = r.data.test_code || null;
  account.codeUntil = Date.now() + r.data.expires_in * 1000;
  $("acc-code").value = "";
  setError("code", null);
  startResendTimer(r.data.resend_in);
  showStep("code");
}

$("acc-phone-step").addEventListener("submit", (e) => {
  e.preventDefault();
  const phone = asciiDigits($("acc-phone").value).trim();
  if (phone.replace(/\D/g, "").length < 10) return setError("phone", { error: "bad_phone" });
  sendCode(phone, e.currentTarget, "phone");
});

$("acc-resend").addEventListener("click", () => sendCode(account.phone, $("acc-code-step"), "code"));
$("acc-change").addEventListener("click", () => {
  setError("phone", null);
  showStep("phone");
});

// ---------------- Step 2: check the code ----------------
async function verifyCode() {
  if (account.busy) return;
  const code = asciiDigits($("acc-code").value).replace(/\D/g, "");
  if (code.length !== 6) return setError("code", { error: "bad_code" });
  setError("code", null);
  const form = $("acc-code-step");
  setBusy(form, true);
  let r;
  try {
    r = await accountApi("/api/account/verify", "POST", { phone: account.phone, code });
  } catch {
    r = { ok: false, data: { error: "network" } };
  }
  setBusy(form, false);
  if (!r.ok) {
    setError("code", r.data);
    $("acc-code").select();
    return;
  }
  account.user = r.data.user;
  account.isNew = r.data.new;
  account.testCode = null;
  account.codeUntil = 0;
  if (account.isNew) {
    $("acc-name").value = "";
    showStep("profile");          // new account: ask for a name (optional)
  } else {
    account.step = "phone";
    closeModal($("account-modal"));
    toast(t("acc_logged_in"));
  }
  renderAccount();
}

$("acc-code-step").addEventListener("submit", (e) => { e.preventDefault(); verifyCode(); });
// Log in by itself as soon as all 6 digits are typed (or pasted from the SMS).
$("acc-code").addEventListener("input", () => {
  if (asciiDigits($("acc-code").value).replace(/\D/g, "").length === 6) verifyCode();
});

// ---------------- Step 3: name, log out ----------------
$("acc-profile-step").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  setBusy(form, true);
  let r;
  try {
    r = await accountApi("/api/account/me", "PUT", { name: $("acc-name").value });
  } catch {
    r = { ok: false, status: 0, data: {} };
  }
  setBusy(form, false);
  if (r.status === 401) {          // logged out in the meantime (e.g. on another tab)
    account.user = null;
    showStep("phone");
    return;
  }
  if (!r.ok) return toast(t("acc_err_network"));
  account.user = r.data.user;
  account.isNew = false;
  closeModal($("account-modal"));
  toast(t("acc_saved"));
  renderAccount();
});

$("acc-skip").addEventListener("click", () => closeModal($("account-modal")));

$("acc-logout").addEventListener("click", async () => {
  try { await accountApi("/api/account/logout", "POST"); } catch { /* offline: forget it here anyway */ }
  account.user = null;
  account.isNew = false;
  $("acc-phone").value = "";
  closeModal($("account-modal"));
  showStep("phone");
  toast(t("acc_logged_out"));
});

// ---------------- Start ----------------
$("account-btn").addEventListener("click", openAccount);
renderAccount();
accountApi("/api/account/me")
  .then((r) => { account.user = r.ok ? r.data.user : null; renderAccount(); })
  .catch(() => { /* offline: stay a guest */ });
