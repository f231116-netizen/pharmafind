// PharmaFind - pharmacist dashboard (Phase 5, reservations: Phase 7)
// Login -> Overview (demand near the pharmacy), Reservations (from customers),
// and My stock (edit prices and quantities).
// Uses LANGS and I18N from i18n.js. The language choice is shared with the public app.

const ph = {
  lang: "en",
  days: 7,
  radius: 3,
  tab: "overview",
  insights: null,
  stock: [],
  allMedicines: null,
  saveTimers: new Map(),   // medicine id -> pending save
  orders: null,            // reservations (Phase 7)
  ordersTimer: null,
  lastPending: null,       // to notice new reservations
};

const $ = (id) => document.getElementById(id);

// ---------------- Language ----------------
function t(key, vars = {}) {
  const s = (I18N[ph.lang] || I18N.en)[key] ?? I18N.en[key] ?? key;
  return typeof s === "string" ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "") : s;
}
function loadSavedLang() { try { return localStorage.getItem("pf_lang"); } catch { return null; } }
function saveLang(l) { try { localStorage.setItem("pf_lang", l); } catch { /* ignore */ } }

function setLang(lang, remember = true) {
  ph.lang = lang;
  if (remember) saveLang(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = LANGS[lang].dir;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $("lang-btn").textContent = LANGS[lang].name;
  $("lang-picker").hidden = true;
  fillFilters();
  if (ph.insights) renderOverview();
  if (ph.stock.length || ph.tab === "stock") renderStock();
  if (ph.orders) renderOrders();
}
document.querySelectorAll("#lang-picker [data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
$("lang-btn").addEventListener("click", () => { $("lang-picker").hidden = false; });

function medName(m) {
  if (ph.lang === "ku" && m.name_ku) return m.name_ku;
  if (ph.lang === "ar" && m.name_ar) return m.name_ar;
  return m.brand_name;
}
const formName = (f) => t("forms")[f] || f;

// ---------------- Formatting ----------------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const money = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-US") + " " + t("currency"));

function ago(iso) {
  if (!iso) return "–";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return t("ago_now");
  if (min < 60) return t("ago_min", { n: min });
  const h = Math.round(min / 60);
  if (h < 24) return t("ago_h", { n: h });
  return t("ago_d", { n: Math.round(h / 24) });
}

const STATUS_ICON = { ok: "✓", low: "!", out: "✕", not_carried: "–" };
const statusChip = (s) => `<span class="status st-${s}"><b aria-hidden="true">${STATUS_ICON[s]}</b>${esc(t("st_" + s))}</span>`;

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
  $("dash-view").hidden = true;
  $("logout-btn").hidden = true;
  $("login-view").hidden = false;
  $("login-user").focus();
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").hidden = true;
  try {
    await api("/api/pharmacy/login", {
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
  await api("/api/pharmacy/logout", { method: "POST" }).catch(() => {});
  ph.insights = null;
  ph.stock = [];
  ph.orders = null;
  ph.lastPending = null;
  clearInterval(ph.ordersTimer);
  showLogin();
});

async function start() {
  let me;
  try { me = await api("/api/pharmacy/me"); } catch { return; } // shows the login
  $("login-view").hidden = true;
  $("dash-view").hidden = false;
  $("logout-btn").hidden = false;
  $("ph-name").textContent = me.pharmacy.name;
  $("ph-address").textContent = `${me.pharmacy.address} · ${me.pharmacy.open_hours}`;
  await Promise.all([loadOverview(), loadStock(), loadOrders()]);
  // Check for new reservations every 20 seconds (shows a number on the tab and a message).
  clearInterval(ph.ordersTimer);
  ph.ordersTimer = setInterval(() => loadOrders().catch(() => {}), 20000);
}

// ---------------- Filters & tabs ----------------
function fillFilters() {
  $("f-days").innerHTML = [7, 14].map((n) => `<option value="${n}" ${n === ph.days ? "selected" : ""}>${esc(t("ph_last_days", { n }))}</option>`).join("");
  $("f-radius").innerHTML = [1, 3, 5].map((n) => `<option value="${n}" ${n === ph.radius ? "selected" : ""}>${esc(t("ph_within_km", { n }))}</option>`).join("");
}
$("f-days").addEventListener("change", (e) => { ph.days = +e.target.value; loadOverview(); });
$("f-radius").addEventListener("change", (e) => { ph.radius = +e.target.value; loadOverview(); });

document.querySelectorAll("[data-ptab]").forEach((b) => b.addEventListener("click", () => {
  ph.tab = b.dataset.ptab;
  document.querySelectorAll("[data-ptab]").forEach((x) => x.classList.toggle("on", x === b));
  for (const name of ["overview", "orders", "stock"]) $("tab-" + name).hidden = ph.tab !== name;
  $("ph-filters").hidden = ph.tab !== "overview";     // days / km only matter for the overview
  if (ph.tab === "overview") loadOverview();
  if (ph.tab === "orders") loadOrders();
}));

// ---------------- Reservations (Phase 7) ----------------
const ORDER_GROUPS = [
  ["pending", "ph_new_orders"],
  ["confirmed", "ph_active_orders"],
  ["ready", "ph_ready_orders"],
  ["closed", "ph_done_orders"],
];

async function loadOrders() {
  const data = await api("/api/pharmacy/orders");
  ph.orders = data.orders;
  const pending = data.pending_count;
  if (ph.lastPending !== null && pending > ph.lastPending) toast(t("ph_new_order_toast"));
  ph.lastPending = pending;
  $("orders-badge").textContent = pending;
  $("orders-badge").hidden = pending === 0;
  renderOrders();
}

function fmtTime(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  const sameDay = d.toDateString() === new Date().toDateString();
  return "⁦" + `${pad(d.getHours())}:${pad(d.getMinutes())}` +
    (sameDay ? "" : ` · ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`) + "⁩";
}

function orderActions(o) {
  if (o.status === "pending") return `
    <div class="po-actions">
      <button class="btn-primary" type="button" data-act="confirm">${esc(t("ph_confirm"))}</button>
      <button class="btn-ghost" type="button" data-act="show-reject">${esc(t("ph_reject"))}</button>
    </div>
    <div class="po-reject" hidden>
      <label class="field"><span>${esc(t("ph_reject_reason"))}</span>
        <select data-reason>
          <option value="out_of_stock">${esc(t("reason_out_of_stock"))}</option>
          <option value="other">${esc(t("reason_other"))}</option>
        </select>
      </label>
      <button class="btn-primary danger" type="button" data-act="reject">${esc(t("ph_reject"))}</button>
    </div>`;
  if (o.status === "confirmed") return `
    <div class="po-actions">
      <button class="btn-primary" type="button" data-act="ready">${esc(t("ph_mark_ready"))}</button>
      <button class="btn-ghost" type="button" data-act="cancel">${esc(t("cancel"))}</button>
    </div>`;
  if (o.status === "ready") return `
    <form class="po-pickup" data-pickup>
      <label class="field"><span>${esc(t("ph_enter_code"))}</span>
        <input data-code inputmode="numeric" maxlength="4" dir="ltr" autocomplete="off" placeholder="••••">
      </label>
      <button class="btn-primary" type="submit">${esc(t("ph_picked_up"))}</button>
      <button class="btn-ghost" type="button" data-act="cancel">${esc(t("cancel"))}</button>
    </form>`;
  return "";
}

function orderCardPh(o) {
  const c = o.customer;
  const who = [c.age != null ? t("ph_age", { n: c.age }) : null, c.gender ? t("acc_" + c.gender) : null]
    .filter(Boolean).join(" · ");
  const why = o.status === "cancelled" ? t(o.cancelled_by === "customer" ? "ph_cancelled_by_customer" : "reason_" + o.cancel_reason)
    : o.status === "expired" ? t(o.cancel_reason === "no_answer" ? "ph_expired_no_answer" : "ph_expired_not_collected") : "";
  return `
    <article class="card ph-order ${o.status === "pending" ? "highlight" : ""}" data-id="${o.id}">
      <div class="ord-top">
        <span class="ord-status os-${o.status}">${esc(t("os_" + o.status))}</span>
        <span class="muted small">${esc(t("ord_number", { id: o.id }))} · ${esc(ago(o.created_at))}</span>
      </div>
      <div class="po-customer">
        <b><bdi>${esc(c.name || "–")}</bdi></b>
        ${who ? `<span class="po-who">${esc(who)}</span>` : ""}
        <a href="tel:${esc(c.phone)}" dir="ltr">${esc(c.phone_display)}</a>
      </div>
      <ul class="ord-lines">
        ${o.items.map((i) => `<li><span><bdi>${i.quantity} ×</bdi> ${esc(medName(i.medicine))} <small class="muted"><bdi>${esc(i.medicine.strength)}</bdi></small></span><bdi>${money(i.quantity * i.price_iqd)}</bdi></li>`).join("")}
      </ul>
      <div class="ord-total"><span>${esc(t("ord_total"))}</span><b><bdi>${money(o.total_iqd)}</bdi></b></div>
      ${o.note ? `<p class="po-note"><b>${esc(t("ph_note"))}:</b> <bdi>${esc(o.note)}</bdi></p>` : ""}
      ${o.hold_until && (o.status === "confirmed" || o.status === "ready")
        ? `<p class="muted small">${esc(t("ord_until", { time: fmtTime(o.hold_until) }))}</p>` : ""}
      ${why ? `<p class="muted small">${esc(why)}</p>` : ""}
      <p class="form-error" data-error hidden></p>
      ${orderActions(o)}
    </article>`;
}

function renderOrders() {
  const box = $("orders-list");
  if (!ph.orders) return;
  if (!ph.orders.length) {
    box.innerHTML = `<div class="card"><p class="muted">${esc(t("ph_no_orders"))}</p></div>`;
    return;
  }
  const groupOf = (o) => (["pending", "confirmed", "ready"].includes(o.status) ? o.status : "closed");
  box.innerHTML = ORDER_GROUPS.map(([key, title]) => {
    const list = ph.orders.filter((o) => groupOf(o) === key);
    if (!list.length) return "";
    return `<h3 class="po-group">${esc(t(title))} <span class="count">${list.length}</span></h3>
            <div class="po-grid">${list.map(orderCardPh).join("")}</div>`;
  }).join("");

  box.querySelectorAll(".ph-order").forEach((card) => {
    const id = +card.dataset.id;
    const showError = (text) => { const el = card.querySelector("[data-error]"); el.textContent = text; el.hidden = false; };
    card.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "show-reject") { card.querySelector(".po-reject").hidden = false; b.hidden = true; return; }
      if (act === "cancel" && !confirm(t("ph_cancel_sure"))) return;
      const body = act === "reject" ? { reason: card.querySelector("[data-reason]").value } : undefined;
      await orderAction(id, act, body, showError, b);
    }));
    const pickup = card.querySelector("[data-pickup]");
    if (pickup) pickup.addEventListener("submit", (e) => {
      e.preventDefault();
      const code = pickup.querySelector("[data-code]").value
        .replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 0x0660)
        .replace(/[۰-۹]/g, (d) => d.charCodeAt(0) - 0x06F0);
      orderAction(id, "pickup", { code }, showError, pickup.querySelector("[type=submit]"));
    });
  });
}

async function orderAction(id, act, body, showError, button) {
  button.disabled = true;
  try {
    await api(`/api/pharmacy/orders/${id}/${act}`, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
    toast(t("ph_saved"));
  } catch (err) {
    button.disabled = false;
    const d = err.data || {};
    if (d.error === "wrong_code") return showError(t("ph_wrong_code"));
    if (d.error === "not_enough") return showError(t("ph_not_enough_stock", { name: medName(d.medicine), n: d.available }));
    if (d.error === "status_changed") toast(t("ph_status_changed"));
    else return showError(t("ph_order_error"));
  }
  await loadOrders();
  if (act === "confirm" || act === "cancel") loadStock();   // the stock numbers changed
}

// ---------------- Overview ----------------
async function loadOverview() {
  ph.insights = await api(`/api/pharmacy/insights?days=${ph.days}&radius=${ph.radius}`);
  renderOverview();
}

function renderOverview() {
  const d = ph.insights;
  const k = d.kpis;
  $("kpis").innerHTML = `
    <div class="kpi"><span>${esc(t("kpi_searches"))}</span><b>${k.searches_near}</b><small>${esc(t("kpi_scanner", { n: k.scanner_share }))}</small></div>
    <div class="kpi"><span>${esc(t("kpi_in_stock"))}</span><b>${k.in_stock}</b></div>
    <div class="kpi"><span>${esc(t("kpi_low"))}</span><b>${k.low_stock}</b>${k.low_stock ? statusChip("low") : ""}</div>
    <div class="kpi"><span>${esc(t("kpi_out"))}</span><b>${k.out_of_stock}</b>${k.out_of_stock ? statusChip("out") : ""}</div>`;

  // Missed demand: the most useful card, shown first.
  $("missed-card").innerHTML = `
    <h3>${esc(t("ph_missed_title"))}</h3>
    <p class="muted small">${esc(t("ph_missed_sub"))}</p>
    ${d.missed.length ? `<ul class="rows">${d.missed.map((m) => `
      <li>
        <div class="row-main"><b>${esc(medName(m.medicine))}</b>
          <span class="muted small">${ph.lang === "en" ? "" : `<bdi>${esc(m.medicine.brand_name)}</bdi> · `}${esc(t("ph_searches", { n: m.searches }))}</span></div>
        ${statusChip(m.status)}
        <button class="btn-primary small-btn" data-edit="${m.medicine.id}">${esc(t(m.status === "out" ? "ph_restock" : "ph_add_to_stock"))}</button>
      </li>`).join("")}</ul>` : `<p class="ok-box">${esc(t("ph_missed_none"))}</p>`}`;

  renderDaily(d.daily);

  const max = Math.max(1, ...d.top.map((x) => x.searches));
  $("top-card").innerHTML = `
    <h3>${esc(t("ph_top_title"))}</h3>
    ${d.top.length ? `<ul class="hbars">${d.top.map((x) => `
      <li data-tip="${esc(medName(x.medicine))}: ${esc(t("ph_searches", { n: x.searches }))}">
        <span class="hb-name">${esc(medName(x.medicine))}</span>
        <span class="hb-track"><span class="hb-fill" style="width:${(100 * x.searches / max).toFixed(1)}%"></span></span>
        <span class="hb-val">${x.searches}</span>
        ${statusChip(x.status)}
      </li>`).join("")}</ul>` : `<p class="muted">${esc(t("ph_top_none"))}</p>`}`;

  $("low-card").innerHTML = `
    <h3>${esc(t("ph_low_title"))}</h3>
    ${d.low_stock.length ? `<ul class="rows">${d.low_stock.map((x) => `
      <li>
        <div class="row-main"><b>${esc(medName(x.medicine))}</b><span class="muted small">${esc(t("ph_left", { n: x.quantity }))}</span></div>
        <button class="btn-ghost small-btn" data-edit="${x.medicine.id}">${esc(t("ph_restock"))}</button>
      </li>`).join("")}</ul>` : `<p class="muted">${esc(t("ph_low_none"))}</p>`}`;

  $("nf-card").innerHTML = `
    <h3>${esc(t("ph_nf_title"))}</h3>
    <p class="muted small">${esc(t("ph_nf_sub"))}</p>
    <ul class="rows">${d.not_found.map((x) => `
      <li><div class="row-main"><b dir="ltr">${esc(x.query)}</b></div><span class="muted small">${esc(t("ph_searches", { n: x.searches }))}</span></li>`).join("")}</ul>`;

  document.querySelectorAll("#tab-overview [data-edit]").forEach((b) =>
    b.addEventListener("click", () => openEditor(+b.dataset.edit)));
}

// Column chart: searches per day. One series, so no legend; the title names it.
function renderDaily(daily) {
  const max = Math.max(1, ...daily.map((d) => d.count));
  const peak = daily.reduce((a, b) => (b.count > a.count ? b : a), daily[0]);
  const label = (iso) => { const [, m, day] = iso.split("-"); return `${+day}/${+m}`; };
  $("daily-card").innerHTML = `
    <h3>${esc(t("ph_daily_title"))}</h3>
    <div class="cols" dir="ltr" role="img" aria-label="${esc(t("ph_daily_title"))}">
      ${daily.map((d) => `
        <div class="col" data-tip="${esc(t("ph_chart_tip", { date: label(d.date), n: d.count }))}">
          <span class="col-bar" style="height:${(100 * d.count / max).toFixed(1)}%">${
            d === peak && d.count ? `<span class="col-peak">${d.count}</span>` : ""}</span>
        </div>`).join("")}
    </div>
    <div class="col-labels" dir="ltr">${daily.map((d, i) =>
      `<span>${daily.length > 7 && i % 2 ? "" : label(d.date)}</span>`).join("")}</div>`;
}

// Hover tooltips for both charts.
document.addEventListener("pointermove", (e) => {
  const el = e.target.closest("[data-tip]");
  const tip = $("chart-tip");
  if (!el) { tip.hidden = true; return; }
  tip.textContent = el.dataset.tip;
  tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = (e.clientY - 36) + "px";
});

// ---------------- My stock ----------------
async function loadStock() {
  const data = await api("/api/pharmacy/stock");
  ph.stock = data.stock;
  ph.cityPrices = data.city_prices || {};
  renderStock();
}

function matchesFilter(row, q) {
  if (!q) return true;
  const m = row.medicine;
  return [m.brand_name, m.name_ku, m.name_ar, m.active_ingredient].some((x) => (x || "").toLowerCase().includes(q));
}

function priceNote(row) {
  if (!row.city_avg_price) return "";
  const diff = (row.price_iqd - row.city_avg_price) / row.city_avg_price;
  if (diff > 0.15) return `<span class="note up">▲ ${esc(t("ph_above_avg"))}</span>`;
  if (diff < -0.15) return `<span class="note down">▼ ${esc(t("ph_below_avg"))}</span>`;
  return "";
}

function renderStock() {
  const q = $("stock-filter").value.trim().toLowerCase();
  const rows = ph.stock.filter((r) => matchesFilter(r, q));
  $("stock-body").innerHTML = rows.map((r) => `
    <tr data-id="${r.medicine.id}">
      <td data-label="${esc(t("col_medicine"))}"><b>${esc(medName(r.medicine))}</b>
        <div class="muted small"><bdi>${esc(r.medicine.brand_name)}</bdi> · <bdi>${esc(r.medicine.strength)}</bdi> · ${esc(formName(r.medicine.form))}</div></td>
      <td data-label="${esc(t("col_price"))}"><input class="in-price" type="number" min="0" step="250" inputmode="numeric" value="${r.price_iqd}" aria-label="${esc(t("col_price"))}"></td>
      <td data-label="${esc(t("col_city"))}"><bdi>${money(r.city_avg_price)}</bdi>${priceNote(r)}</td>
      <td data-label="${esc(t("col_qty"))}"><div class="stepper" dir="ltr">
        <button type="button" data-step="-1" aria-label="-1">−</button>
        <input class="in-qty" type="number" min="0" step="1" inputmode="numeric" value="${r.quantity}" aria-label="${esc(t("col_qty"))}">
        <button type="button" data-step="1" aria-label="+1">+</button></div></td>
      <td data-label="${esc(t("col_status"))}">${statusChip(r.status)}</td>
      <td data-label="${esc(t("col_updated"))}" class="muted small upd">${esc(ago(r.updated_at))}</td>
      <td><button class="remove-btn" type="button">${esc(t("ph_remove"))}</button></td>
    </tr>`).join("");
  const empty = $("stock-empty");
  empty.hidden = rows.length > 0;
  empty.textContent = ph.stock.length ? t("ph_no_match") : t("ph_empty_stock");

  $("stock-body").querySelectorAll("tr").forEach((tr) => {
    const id = +tr.dataset.id;
    tr.querySelector(".in-price").addEventListener("input", () => queueSave(id, tr));
    tr.querySelector(".in-qty").addEventListener("input", () => queueSave(id, tr));
    tr.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
      const inp = tr.querySelector(".in-qty");
      inp.value = Math.max(0, (+inp.value || 0) + +b.dataset.step);
      queueSave(id, tr);
    }));
    const rm = tr.querySelector(".remove-btn");
    rm.addEventListener("click", async () => {
      if (!rm.classList.contains("confirm")) {           // first click asks "Sure?"
        rm.classList.add("confirm");
        rm.textContent = t("ph_sure");
        setTimeout(() => { rm.classList.remove("confirm"); rm.textContent = t("ph_remove"); }, 3000);
        return;
      }
      await api(`/api/pharmacy/stock/${id}`, { method: "DELETE" });
      ph.stock = ph.stock.filter((r) => r.medicine.id !== id);
      renderStock();
    });
  });
}
$("stock-filter").addEventListener("input", renderStock);

// Save automatically shortly after the pharmacist stops typing.
function queueSave(id, tr) {
  clearTimeout(ph.saveTimers.get(id));
  tr.querySelector(".upd").textContent = t("ph_saving");
  ph.saveTimers.set(id, setTimeout(() => saveRow(id, tr), 700));
}

async function saveRow(id, tr) {
  const price = +tr.querySelector(".in-price").value;
  const qty = +tr.querySelector(".in-qty").value;
  try {
    const { row } = await api(`/api/pharmacy/stock/${id}`, {
      method: "PUT", body: JSON.stringify({ price_iqd: price, quantity: qty }),
    });
    const i = ph.stock.findIndex((r) => r.medicine.id === id);
    if (i >= 0) ph.stock[i] = row;
    tr.querySelector(".upd").textContent = t("ph_saved") + " ✓";
    tr.querySelector("td:nth-child(5)").innerHTML = statusChip(row.status);
    tr.querySelector("td:nth-child(3)").innerHTML = `<bdi>${money(row.city_avg_price)}</bdi>${priceNote(row)}`;
    tr.classList.remove("error");
  } catch {
    tr.querySelector(".upd").textContent = t("ph_save_error");
    tr.classList.add("error");
  }
}

// ---------------- Add / restock dialog ----------------
async function openEditor(medicineId = null) {
  if (!ph.allMedicines) ph.allMedicines = await (await fetch("/api/medicines")).json();
  const mine = new Map(ph.stock.map((r) => [r.medicine.id, r]));
  const select = $("edit-medicine");
  const options = ph.allMedicines
    .filter((m) => !mine.has(m.id) || m.id === medicineId)
    .sort((a, b) => medName(a).localeCompare(medName(b)));
  select.innerHTML = `<option value="">${esc(t("ph_choose_placeholder"))}</option>` +
    options.map((m) => `<option value="${m.id}">${esc(medName(m))} · ${esc(m.strength)} · ${esc(formName(m.form))}</option>`).join("");
  select.disabled = medicineId !== null;

  const fill = () => {
    const id = +select.value;
    const row = mine.get(id);
    const avg = row?.city_avg_price ?? (ph.cityPrices || {})[id] ?? null;
    $("edit-price").value = row ? row.price_iqd : (avg ? Math.round(avg) : "");
    $("edit-qty").value = row ? Math.max(row.quantity, 10) : 10;
    $("edit-price-hint").textContent = avg ? t("ph_price_hint", { price: money(avg) }) : "";
  };
  select.onchange = fill;
  if (medicineId !== null) select.value = String(medicineId);
  fill();
  $("edit-form").querySelector("h3").textContent = t(medicineId !== null && mine.has(medicineId) ? "ph_restock" : "ph_edit_title");
  $("edit-error").hidden = true;
  $("edit-modal").hidden = false;
  (medicineId !== null ? $("edit-qty") : select).focus();
}
$("add-btn").addEventListener("click", () => openEditor());

$("edit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = +$("edit-medicine").value;
  if (!id) return;
  try {
    const { row } = await api(`/api/pharmacy/stock/${id}`, {
      method: "PUT",
      body: JSON.stringify({ price_iqd: +$("edit-price").value, quantity: +$("edit-qty").value }),
    });
    const i = ph.stock.findIndex((r) => r.medicine.id === id);
    if (i >= 0) ph.stock[i] = row; else ph.stock.push(row);
    ph.stock.sort((a, b) => a.medicine.brand_name.localeCompare(b.medicine.brand_name));
    $("edit-modal").hidden = true;
    renderStock();
    toast(`${medName(row.medicine)}: ${t("ph_saved")} ✓`);
    loadOverview();
  } catch {
    $("edit-error").textContent = t("ph_save_error");
    $("edit-error").hidden = false;
  }
});

document.querySelectorAll(".modal").forEach((m) => m.addEventListener("click", (e) => {
  if (e.target === m || e.target.closest("[data-close]")) m.hidden = true;
}));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".modal").forEach((m) => { m.hidden = true; });
});

let toastTimer;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3000);
}

// ---------------- Start ----------------
const saved = loadSavedLang();
if (saved && LANGS[saved]) setLang(saved);
else { setLang("en", false); $("lang-picker").hidden = false; }
start();
