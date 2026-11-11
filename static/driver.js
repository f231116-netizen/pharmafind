// PharmaFind - delivery driver page (Phase 9). Like a Talabat rider app, in the browser.
// Login -> my jobs (go to the pharmacy, then to the customer) and jobs waiting for a driver.
// At the door: check the original prescription paper (if any), collect the cash, type the customer's code.
// Uses LANGS and I18N from i18n.js. The language choice is shared with the public app.

const drv = { lang: "en", data: null, sig: null, timer: null };
const FAIL_REASONS = ["not_home", "no_paper", "refused", "other"];
const $ = (id) => document.getElementById(id);

// ---------------- Language ----------------
function t(key, vars = {}) {
  const s = (I18N[drv.lang] || I18N.en)[key] ?? I18N.en[key] ?? key;
  return typeof s === "string" ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "") : s;
}
function loadSavedLang() { try { return localStorage.getItem("pf_lang"); } catch { return null; } }
function saveLang(l) { try { localStorage.setItem("pf_lang", l); } catch { /* ignore */ } }
function setLang(lang, remember = true) {
  drv.lang = lang;
  if (remember) saveLang(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = LANGS[lang].dir;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $("lang-btn").textContent = LANGS[lang].name;
  $("lang-picker").hidden = true;
  if (drv.data) render();
}
document.querySelectorAll("#lang-picker [data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
$("lang-btn").addEventListener("click", () => { $("lang-picker").hidden = false; });

// ---------------- Formatting ----------------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const money = (n) => Math.round(n || 0).toLocaleString("en-US") + " " + t("currency");
const km = (n) => (n || 0).toFixed(1) + " " + t("unit_km");
const tel = (p) => "tel:" + String(p || "").replace(/\s/g, "");
const mapsTo = (lat, lng) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
const asciiDigits = (s) => s.replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 0x0660)
                            .replace(/[۰-۹]/g, (d) => d.charCodeAt(0) - 0x06F0);
function ago(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return t("ago_now");
  if (min < 60) return t("ago_min", { n: min });
  const h = Math.round(min / 60);
  return h < 24 ? t("ago_h", { n: h }) : t("ago_d", { n: Math.round(h / 24) });
}
function fmtTime(iso) {
  const d = new Date(iso);
  return "⁦" + `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` + "⁩";
}
const fmtDay = (iso) => "⁦" + iso.split("-").reverse().join("/") + "⁩";

let toastTimer;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3000);
}

// ---------------- Server calls ----------------
async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "X-Requested-With": "fetch", ...(options.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (res.status === 401 && !path.endsWith("/login")) {
    showLogin();
    throw new Error("not logged in");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "HTTP " + res.status), { data, status: res.status });
  return data;
}

// ---------------- Login / logout ----------------
function showLogin() {
  clearInterval(drv.timer);
  $("jobs-view").hidden = true;
  $("logout-btn").hidden = true;
  $("login-view").hidden = false;
  $("login-user").focus();
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").hidden = true;
  try {
    await api("/api/driver/login", {
      method: "POST",
      body: JSON.stringify({ username: $("login-user").value, password: $("login-pass").value }),
    });
    $("login-pass").value = "";
    start();
  } catch {
    $("login-error").textContent = t("ph_wrong_login");
    $("login-error").hidden = false;
  }
});

$("logout-btn").addEventListener("click", async () => {
  await api("/api/driver/logout", { method: "POST" }).catch(() => {});
  drv.data = null;
  drv.sig = null;
  showLogin();
});

async function start() {
  let me;
  try { me = await api("/api/driver/me"); } catch { return; }   // shows the login
  $("login-view").hidden = true;
  $("jobs-view").hidden = false;
  $("logout-btn").hidden = false;
  $("drv-name").textContent = t("drv_hello", { name: me.driver.name });
  drv.name = me.driver.name;
  await loadJobs();
  clearInterval(drv.timer);
  drv.timer = setInterval(() => loadJobs().catch(() => {}), 15000);   // new jobs appear by themselves
}
$("refresh-btn").addEventListener("click", () => loadJobs(true));

// ---------------- Jobs ----------------
async function loadJobs(force = false) {
  const data = await api("/api/driver/jobs");
  const sig = JSON.stringify(data);
  if (!force && sig === drv.sig) return;      // nothing changed: don't wipe what is being typed
  if (drv.data && data.available.length > drv.data.available.length) toast(t("drv_new_job"));
  drv.sig = sig;
  drv.data = data;
  render();
}

function availableCard(j) {
  return `
    <article class="card drv-job" data-id="${j.id}">
      <div class="ord-top">
        <span>
          <span class="ord-status ${j.status === "ready" ? "os-ready" : "os-confirmed"}">${esc(t(j.status === "ready" ? "drv_packed" : "drv_packing"))}</span>
          ${j.has_prescription ? `<span class="badge rx">${esc(t("rx_short"))}</span>` : ""}
        </span>
        <span class="muted small">#${j.id} · ${esc(ago(j.created_at))}</span>
      </div>
      <p class="drv-from"><b>${esc(t("drv_from"))}</b> <bdi>${esc(j.pharmacy.name)}</bdi> · <bdi>${esc(j.pharmacy.address)}</bdi></p>
      <div class="drv-facts">
        <div><span>${esc(t("drv_distance"))}</span><b><bdi>${km(j.delivery_km)}</bdi></b></div>
        <div><span>${esc(t("drv_fee"))}</span><b><bdi>${money(j.delivery_fee_iqd)}</bdi></b></div>
        <div><span>${esc(t("drv_collect"))}</span><b><bdi>${money(j.grand_total_iqd)}</bdi></b></div>
      </div>
      <p class="muted small">${esc(t("drv_boxes", { n: j.boxes }))}</p>
      <p class="form-error" data-error hidden></p>
      <button class="btn-primary full" type="button" data-act="take">${esc(t("drv_take"))}</button>
    </article>`;
}

function doorForm(j) {
  return `
    <form class="drv-door" data-door>
      <b>${esc(t("drv_at_door"))}</b>
      ${j.prescription ? `<label class="chk paper"><input type="checkbox" data-paper> ${esc(t("drv_paper"))}</label>` : ""}
      <label class="chk"><input type="checkbox" data-cash> ${esc(t("drv_cash", { total: money(j.grand_total_iqd) }))}</label>
      <label class="field"><span>${esc(t("drv_code"))}</span>
        <input data-code inputmode="numeric" maxlength="4" dir="ltr" autocomplete="off" placeholder="••••">
      </label>
      <button class="btn-primary full" type="submit">${esc(t("drv_delivered"))}</button>
      <details class="drv-fail">
        <summary>${esc(t("drv_failed"))}</summary>
        <label class="field"><span>${esc(t("ph_reject_reason"))}</span>
          <select data-reason>${FAIL_REASONS.map((r) => `<option value="${r}">${esc(t("reason_driver_" + r))}</option>`).join("")}</select>
        </label>
        <button class="btn-primary danger full" type="button" data-act="failed">${esc(t("drv_failed_confirm"))}</button>
      </details>
    </form>`;
}

function myCard(j) {
  const onWay = j.status === "out_for_delivery";
  const p = j.pharmacy, c = j.customer, rx = j.prescription;
  return `
    <article class="card drv-job mine ${onWay ? "highlight" : ""}" data-id="${j.id}">
      <div class="ord-top">
        <span class="ord-status ${onWay ? "os-out_for_delivery" : "os-confirmed"}">${esc(t(onWay ? "drv_step_customer" : "drv_step_pharmacy"))}</span>
        <span class="muted small">#${j.id}</span>
      </div>
      <ol class="drv-steps">
        <li class="${onWay ? "done" : "now"}">
          <b>${esc(t("drv_pharmacy"))}</b> <bdi>${esc(p.name)}</bdi> · <bdi>${esc(p.address)}</bdi>
          <div class="drv-links">
            <a class="btn-ghost" href="${tel(p.phone)}">${esc(t("call"))}</a>
            <a class="btn-ghost" href="${mapsTo(p.latitude, p.longitude)}" target="_blank" rel="noopener">${esc(t("directions"))}</a>
          </div>
          ${onWay ? "" : `<p class="muted small">${esc(t(j.status === "ready" ? "drv_at_pharmacy" : "drv_wait_packing"))}</p>`}
        </li>
        <li class="${onWay ? "now" : ""}">
          <b>${esc(t("drv_customer"))}</b> <bdi>${esc(c.name)}</bdi> ·
          <a href="${tel(c.phone)}" dir="ltr">${esc(c.phone_display)}</a>
          <div class="drv-address"><bdi>${esc(j.address)}</bdi></div>
          <div class="drv-links">
            <a class="btn-ghost" href="${tel(c.phone)}">${esc(t("call"))}</a>
            <a class="btn-ghost" href="${mapsTo(j.delivery_lat, j.delivery_lng)}" target="_blank" rel="noopener">${esc(t("directions"))}</a>
          </div>
        </li>
      </ol>
      <ul class="ord-lines">${j.items.map((i) => `<li><span><bdi>${i.quantity} ×</bdi> <bdi>${esc(i.name)}</bdi> <small class="muted"><bdi>${esc(i.strength)}</bdi></small></span></li>`).join("")}</ul>
      <div class="drv-cash"><span>${esc(t("drv_collect"))}</span><b><bdi>${money(j.grand_total_iqd)}</bdi></b></div>
      ${rx ? `
        <div class="drv-rx">
          <b>${esc(t("drv_rx_title"))}</b>
          <p>${esc(t("drv_rx_check", { doctor: rx.doctor_name, date: rx.issued_on ? fmtDay(rx.issued_on) : "–", patient: rx.patient }))}</p>
        </div>` : ""}
      <p class="form-error" data-error hidden></p>
      ${onWay ? doorForm(j) : `<button class="btn-ghost full" type="button" data-act="release">${esc(t("drv_release"))}</button>`}
    </article>`;
}

function doneCard(j) {
  const ok = j.status === "delivered";
  return `
    <article class="card drv-job done" data-id="${j.id}">
      <div class="ord-top">
        <span class="ord-status os-${j.status}">${esc(t("os_" + j.status))}</span>
        <span class="muted small">#${j.id}${j.closed_at ? " · " + fmtTime(j.closed_at) : ""}</span>
      </div>
      <p class="drv-from"><bdi>${esc(j.pharmacy.name)}</bdi> ${LANGS[drv.lang].dir === "rtl" ? "←" : "→"} <bdi>${esc(j.customer.name)}</bdi></p>
      ${ok ? `<div class="drv-cash"><span>${esc(t("drv_cash_collected"))}</span><b><bdi>${money(j.grand_total_iqd)}</bdi></b></div>`
           : `<p class="muted small">${esc(j.cancel_reason ? t("reason_" + j.cancel_reason) : "")}</p>`}
    </article>`;
}

// Keep what was typed or ticked when the list is drawn again (same idea as the pharmacist page).
function saveFormState() {
  const saved = {};
  document.querySelectorAll(".drv-job.mine").forEach((card) => {
    saved[card.dataset.id] = {
      fields: [...card.querySelectorAll("input, select")].map((el) => (el.type === "checkbox" ? el.checked : el.value)),
      failOpen: !!card.querySelector("details[open]"),
    };
  });
  return saved;
}
function restoreFormState(saved) {
  document.querySelectorAll(".drv-job.mine").forEach((card) => {
    const s = saved[card.dataset.id];
    if (!s) return;
    const els = [...card.querySelectorAll("input, select")];
    if (els.length !== s.fields.length) return;
    els.forEach((el, i) => { if (el.type === "checkbox") el.checked = s.fields[i]; else el.value = s.fields[i]; });
    if (s.failOpen && card.querySelector("details")) card.querySelector("details").open = true;
  });
}

function render() {
  const { available, mine } = drv.data;
  const active = mine.filter((j) => ["confirmed", "ready", "out_for_delivery"].includes(j.status));
  const done = mine.filter((j) => !active.includes(j));
  const saved = saveFormState();
  $("drv-name").textContent = t("drv_hello", { name: drv.name });
  $("mine-count").textContent = active.length;
  $("avail-count").textContent = available.length;
  $("my-jobs").innerHTML = active.length ? active.map(myCard).join("")
    : `<div class="card"><p class="muted">${esc(t("drv_none_mine"))}</p></div>`;
  $("available-jobs").innerHTML = available.length ? available.map(availableCard).join("")
    : `<div class="card"><p class="muted">${esc(t("drv_none_available"))}</p></div>`;
  $("done-jobs").innerHTML = done.map(doneCard).join("");
  restoreFormState(saved);

  document.querySelectorAll(".drv-job").forEach((card) => {
    const id = +card.dataset.id;
    const showError = (text) => { const el = card.querySelector("[data-error]"); if (el) { el.textContent = text; el.hidden = false; } };
    card.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      const act = b.dataset.act;
      if (act === "release" && !confirm(t("drv_release_sure"))) return;
      if (act === "failed" && !confirm(t("drv_failed_sure"))) return;
      const body = act === "failed" ? { reason: card.querySelector("[data-reason]").value } : undefined;
      jobAction(id, act, body, showError, b);
    }));
    const door = card.querySelector("[data-door]");
    if (door) door.addEventListener("submit", (e) => {
      e.preventDefault();
      const paper = door.querySelector("[data-paper]");
      if (paper && !paper.checked) return showError(t("drv_err_paper"));
      if (!door.querySelector("[data-cash]").checked) return showError(t("drv_err_cash"));
      const code = asciiDigits(door.querySelector("[data-code]").value);
      jobAction(id, "delivered", { code, cash_collected: true, ...(paper ? { paper_collected: true } : {}) },
                showError, door.querySelector("[type=submit]"));
    });
  });
}

async function jobAction(id, act, body, showError, button) {
  button.disabled = true;
  try {
    await api(`/api/driver/jobs/${id}/${act}`, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
    toast(t(act === "take" ? "drv_taken" : "ph_saved"));
  } catch (err) {
    button.disabled = false;
    const d = err.data || {};
    if (d.error === "wrong_code") return showError(t("drv_err_code"));
    if (d.error === "cash_required") return showError(t("drv_err_cash"));
    if (d.error === "paper_required") return showError(t("drv_err_paper"));
    if (d.error === "too_many_jobs") return showError(t("drv_too_many", { n: d.max }));
    if (d.error === "already_taken") toast(t("drv_already_taken"));
    else if (d.error === "status_changed") toast(t("ph_status_changed"));
    else return showError(t("ph_order_error"));
  }
  await loadJobs(true);
}

// ---------------- Start ----------------
const saved = loadSavedLang();
if (saved && LANGS[saved]) setLang(saved);
else { setLang("en", false); $("lang-picker").hidden = false; }
start();
