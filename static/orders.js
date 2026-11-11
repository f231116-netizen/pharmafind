// PharmaFind - Phase 7: basket and reservations.
// Reserve medicines at ONE pharmacy, then pay and collect them there with a pickup code.
// Uses $, t, esc, money, ago, medName, formName, openModal, closeModal, openDirections, state (app.js),
// toast (scan.js), and requireAccount, accountApi, ltr (account.js).

const MAX_QTY = 5;                 // same limit as the server (order_routes.py)
const OPEN_STATUSES = ["pending", "confirmed", "ready"];
const basket = loadBasket();       // { pharmacy, items: [{ medicine, quantity, price_iqd, available }], note }
const myOrders = { list: [], timer: null, highlight: null, holdHours: 24, error: false };

// A medicine can be reserved online if it needs no prescription and isn't controlled.
const canReserve = (m) => !m.rx_required && !m.controlled;
window.canReserve = canReserve;

// ---------------- Basket (kept in this browser only) ----------------
function loadBasket() {
  try {
    const b = JSON.parse(localStorage.getItem("pf_basket"));
    if (b && b.pharmacy && Array.isArray(b.items)) return b;
  } catch { /* nothing saved, or storage blocked */ }
  return { pharmacy: null, items: [], note: "" };
}
function saveBasket() {
  try { localStorage.setItem("pf_basket", JSON.stringify(basket)); } catch { /* ignore */ }
}
function emptyBasket() {
  basket.pharmacy = null;
  basket.items = [];
  basket.note = "";
  saveBasket();
}

const maxFor = (item) => Math.min(MAX_QTY, item.available);

function addToBasket(medicine, p) {
  if (basket.items.length && basket.pharmacy.id !== p.id) {
    // One reservation = one pharmacy.
    if (!confirm(t("ord_other_pharmacy", { old: basket.pharmacy.name, new: p.name }))) return;
    emptyBasket();
  }
  const { id, name, address, phone, open_hours, latitude, longitude } = p;
  basket.pharmacy = { id, name, address, phone, open_hours, latitude, longitude };
  let item = basket.items.find((i) => i.medicine.id === medicine.id);
  if (!item) {
    const { brand_name, name_ar, name_ku, strength, form, rx_required, controlled } = medicine;
    item = { medicine: { id: medicine.id, brand_name, name_ar, name_ku, strength, form, rx_required, controlled },
             quantity: 0, price_iqd: p.price_iqd, available: p.quantity };
    basket.items.push(item);
  }
  item.available = p.quantity;
  item.price_iqd = p.price_iqd;
  if (item.quantity >= maxFor(item)) {
    toast(t("ord_max_qty", { n: maxFor(item) }));
  } else {
    item.quantity += 1;
    toast(t("ord_added"));
  }
  saveBasket();
  renderBasketFab();
}
window.addToBasket = addToBasket;

function renderBasketFab() {
  const count = basket.items.reduce((n, i) => n + i.quantity, 0);
  $("basket-fab").hidden = count === 0;
  $("basket-fab-label").textContent = t("ord_basket");
  $("basket-fab-count").textContent = count;
}

function renderBasket() {
  const body = $("basket-body");
  if (!basket.items.length) {
    body.innerHTML = `<p class="muted">${esc(t("ord_empty_basket"))}</p>`;
    return;
  }
  const p = basket.pharmacy;
  const total = basket.items.reduce((s, i) => s + i.quantity * i.price_iqd, 0);
  body.innerHTML = `
    <div class="ord-pharmacy">
      <b><bdi>${esc(p.name)}</bdi></b>
      <div class="muted"><bdi>${esc(p.address)}</bdi> · <bdi>${esc(p.open_hours)}</bdi></div>
    </div>
    <ul class="ord-items">
      ${basket.items.map((i, idx) => `
        <li>
          <div class="ord-item-main">
            <b>${esc(medName(i.medicine))}</b>
            <span class="muted"><bdi>${esc(i.medicine.strength)}</bdi> · ${esc(formName(i.medicine.form))} · <bdi>${esc(t("ord_each", { price: money(i.price_iqd) }))}</bdi></span>
          </div>
          <div class="qty" dir="ltr">
            <button type="button" data-dec="${idx}" aria-label="−">−</button>
            <b>${i.quantity}</b>
            <button type="button" data-inc="${idx}" aria-label="+" ${i.quantity >= maxFor(i) ? "disabled" : ""}>+</button>
          </div>
        </li>`).join("")}
    </ul>
    <div class="ord-total"><span>${esc(t("ord_total"))}</span><b><bdi>${money(total)}</bdi></b></div>
    <label class="acc-field">
      <span>${esc(t("ord_note"))}</span>
      <input id="basket-note" type="text" maxlength="200" placeholder="${esc(t("ord_note_ph"))}" value="${esc(basket.note || "")}">
    </label>
    <p class="acc-soon">${esc(t("ord_how", { h: myOrders.holdHours }))}</p>
    <p id="basket-error" class="acc-error" role="alert" hidden></p>
    <button id="basket-send" class="btn-primary full" type="button">${esc(t("ord_send"))}</button>`;

  body.querySelectorAll("[data-dec]").forEach((b) => b.addEventListener("click", () => {
    const item = basket.items[+b.dataset.dec];
    item.quantity -= 1;
    if (item.quantity <= 0) basket.items.splice(+b.dataset.dec, 1);   // − at 1 removes it
    if (!basket.items.length) emptyBasket();
    saveBasket();
    renderBasket();
    renderBasketFab();
  }));
  body.querySelectorAll("[data-inc]").forEach((b) => b.addEventListener("click", () => {
    const item = basket.items[+b.dataset.inc];
    if (item.quantity < maxFor(item)) item.quantity += 1;
    saveBasket();
    renderBasket();
    renderBasketFab();
  }));
  $("basket-note").addEventListener("input", (e) => { basket.note = e.target.value; saveBasket(); });
  $("basket-send").addEventListener("click", sendReservation);
}

function openBasket() {
  renderBasket();
  openModal($("basket-modal"));
}
$("basket-fab").addEventListener("click", openBasket);

function orderErrorText(data) {
  const name = data.medicine ? medName(data.medicine) : "";
  switch (data.error) {
    case "not_enough": return t("ord_err_not_enough", { name, n: data.available });
    case "too_many_open": return t("ord_err_too_many_open", { n: data.max });
    case "needs_prescription": return t("ord_err_rx", { name });
    case "controlled": return t("ord_controlled_note");
    case "bad_quantity": return t("ord_max_qty", { n: data.max });
    default: return t("ord_err_generic");
  }
}

// "Send reservation": log in (and fill in name, age, gender) first if needed, then send.
function sendReservation() {
  if (!basket.items.length) return;
  closeModal($("basket-modal"));                       // the login pop-up must not be hidden behind it
  window.requireAccount(async () => {
    openBasket();
    const btn = $("basket-send");
    btn.disabled = true;
    let r;
    try {
      r = await accountApi("/api/orders", "POST", {
        pharmacy_id: basket.pharmacy.id,
        items: basket.items.map((i) => ({ medicine_id: i.medicine.id, quantity: i.quantity })),
        note: basket.note || "",
      });
    } catch {
      r = { ok: false, status: 0, data: {} };
    }
    btn.disabled = false;
    if (r.status === 401 || r.data.error === "profile_incomplete") {
      if (r.status === 401) account.user = null;
      else account.user.profile_complete = false;
      return sendReservation();                           // log in / finish details, then try again
    }
    if (!r.ok) {
      if (r.data.error === "not_enough" && r.data.medicine) {   // remember how many are really left
        const item = basket.items.find((i) => i.medicine.id === r.data.medicine.id);
        if (item) { item.available = r.data.available; saveBasket(); renderBasket(); }
      }
      $("basket-error").textContent = orderErrorText(r.data);
      $("basket-error").hidden = false;
      return;
    }
    emptyBasket();
    renderBasketFab();
    closeModal($("basket-modal"));
    toast(t("ord_sent"));
    openOrders(r.data.order.id);
  });
}

// ---------------- My reservations ----------------
function fmtTime(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  const sameDay = d.toDateString() === new Date().toDateString();
  return ltr(`${pad(d.getHours())}:${pad(d.getMinutes())}` + (sameDay ? "" : ` · ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`));
}

function kmBetween(lat1, lng1, lat2, lng2) {
  const r = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * r / 2) ** 2 +
            Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lng2 - lng1) * r / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}

function statusHint(o) {
  if (o.status === "pending") return t("ord_hint_pending");
  if (o.status === "confirmed") return t("ord_hint_confirmed", { time: fmtTime(o.hold_until) });
  if (o.status === "ready") return t("ord_hint_ready", { time: fmtTime(o.hold_until) });
  if (o.status === "cancelled" && o.cancelled_by === "pharmacy") {
    return t("ord_by_pharmacy", { reason: t("reason_" + o.cancel_reason) });
  }
  return "";
}

function orderCard(o) {
  const open = OPEN_STATUSES.includes(o.status);
  const hint = statusHint(o);
  return `
    <article class="ord ${open ? "" : "closed"} ${o.id === myOrders.highlight ? "new" : ""}">
      <div class="ord-top">
        <span class="ord-status os-${o.status}">${esc(t("os_" + o.status))}</span>
        <span class="muted small">${esc(t("ord_number", { id: o.id }))} · ${esc(ago(o.created_at))}</span>
      </div>
      <b><bdi>${esc(o.pharmacy.name)}</bdi></b>
      <ul class="ord-lines">
        ${o.items.map((i) => `<li><span><bdi>${i.quantity} ×</bdi> ${esc(medName(i.medicine))}</span><bdi>${money(i.quantity * i.price_iqd)}</bdi></li>`).join("")}
      </ul>
      <div class="ord-total"><span>${esc(t("ord_total"))}</span><b><bdi>${money(o.total_iqd)}</bdi></b></div>
      ${hint ? `<p class="ord-hint ${o.status === "cancelled" ? "bad" : ""}">${esc(hint)}</p>` : ""}
      ${open ? `
        <div class="ord-code">
          <span>${esc(t("ord_code"))}</span>
          <b dir="ltr">${esc(o.pickup_code)}</b>
          <small>${esc(t("ord_code_hint"))}</small>
        </div>
        <div class="ord-actions">
          <a class="btn-ghost" href="tel:${esc(o.pharmacy.phone.replace(/\s/g, ""))}">${esc(t("call"))}</a>
          <button class="btn-ghost" type="button" data-dir="${o.id}">${esc(t("directions"))}</button>
          <button class="link-btn danger" type="button" data-cancel="${o.id}">${esc(t("ord_cancel"))}</button>
        </div>` : ""}
    </article>`;
}

function renderOrders() {
  const body = $("orders-body");
  if (myOrders.error) {
    body.innerHTML = `<p class="acc-error">${esc(t("acc_err_network"))}</p>`;
    return;
  }
  body.innerHTML = myOrders.list.length
    ? myOrders.list.map(orderCard).join("")
    : `<p class="muted">${esc(t("ord_none"))}</p>`;

  body.querySelectorAll("[data-cancel]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(t("ord_cancel_sure"))) return;
    b.disabled = true;
    const r = await accountApi(`/api/orders/${b.dataset.cancel}/cancel`, "POST").catch(() => ({ ok: false }));
    if (r.ok) toast(t("ord_cancelled_toast"));
    await loadOrders();
  }));
  body.querySelectorAll("[data-dir]").forEach((b) => b.addEventListener("click", () => {
    const o = myOrders.list.find((x) => x.id === +b.dataset.dir);
    if (!o) return;
    closeModal($("orders-modal"));
    openDirections({ ...o.pharmacy, price_iqd: o.total_iqd,
                     distance_km: kmBetween(state.lat, state.lng, o.pharmacy.latitude, o.pharmacy.longitude) });
  }));
}

async function loadOrders() {
  let r;
  try { r = await accountApi("/api/orders"); } catch { r = { ok: false, status: 0, data: {} }; }
  if (r.status === 401) {                       // logged out meanwhile
    closeModal($("orders-modal"));
    account.user = null;
    renderAccount();
    return window.requireAccount(() => openOrders());
  }
  myOrders.error = !r.ok;
  if (r.ok) {
    myOrders.list = r.data.orders;
    myOrders.holdHours = r.data.hold_hours;
  }
  renderOrders();
}

function openOrders(highlightId = null) {
  myOrders.highlight = highlightId;
  myOrders.list = [];
  $("orders-body").innerHTML = `<p class="muted">…</p>`;
  openModal($("orders-modal"));
  loadOrders();
  clearInterval(myOrders.timer);
  myOrders.timer = setInterval(loadOrders, 20000);    // see "Confirmed" appear without reloading
}
window.openOrders = openOrders;
window.onOrdersClosed = () => clearInterval(myOrders.timer);

// Language changed: redraw what is on screen.
window.renderOrdersUi = () => {
  renderBasketFab();
  if (!$("basket-modal").hidden) renderBasket();
  if (!$("orders-modal").hidden) renderOrders();
};

renderBasketFab();
