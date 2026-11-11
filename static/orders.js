// PharmaFind - Phase 7: basket and reservations. Phase 8: prescription photo.
// Reserve medicines at ONE pharmacy, then pay and collect them there with a pickup code.
// Uses $, t, esc, money, ago, medName, formName, openModal, closeModal, openDirections, state (app.js),
// toast and fileToBlob (scan.js), and requireAccount, accountApi, ltr (account.js).

const MAX_QTY = 5;                 // same limit as the server (order_routes.py)
const OPEN_STATUSES = ["pending", "confirmed", "ready", "out_for_delivery"];
// Phase 9: delivery. The price comes from the server (/api/delivery/quote); payment is cash.
const delivery = { quote: null, key: "", waitingForLocation: false };
const isDelivery = () => basket.fulfilment === "delivery";
const locationIsSet = () => ["loc_ok", "loc_map"].includes(state.loc.key);   // not the city-centre default
const quoteKey = () => (basket.pharmacy ? `${basket.pharmacy.id}:${state.lat}:${state.lng}` : "");
const basket = loadBasket();       // { pharmacy, items: [{ medicine, quantity, price_iqd, available }], note }
const myOrders = { list: [], timer: null, highlight: null, holdHours: 24, error: false };
// The prescription photo stays only in memory (never in the browser's storage), and only until it is sent.
const rxPhoto = { blob: null, url: null };

// Controlled medicines (e.g. tramadol) can never be reserved online.
// Prescription medicines can (Phase 8), with a photo of the prescription.
const canReserve = (m) => !m.controlled;
window.canReserve = canReserve;
const needsRx = () => basket.items.some((i) => i.medicine.rx_required);

function clearRxPhoto() {
  if (rxPhoto.url) URL.revokeObjectURL(rxPhoto.url);
  rxPhoto.blob = null;
  rxPhoto.url = null;
}

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
  clearRxPhoto();
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
  const del = isDelivery();
  const q = del && locationIsSet() && delivery.key === quoteKey() ? delivery.quote : null;
  const fee = q && q.ok ? q.fee_iqd : 0;
  body.innerHTML = `
    <div class="ord-pharmacy">
      <b><bdi>${esc(p.name)}</bdi></b>
      <div class="muted"><bdi>${esc(p.address)}</bdi> · <bdi>${esc(p.open_hours)}</bdi></div>
    </div>
    <ul class="ord-items">
      ${basket.items.map((i, idx) => `
        <li>
          <div class="ord-item-main">
            <b>${esc(medName(i.medicine))} ${i.medicine.rx_required ? `<span class="badge rx">${esc(t("rx_short"))}</span>` : ""}</b>
            <span class="muted"><bdi>${esc(i.medicine.strength)}</bdi> · ${esc(formName(i.medicine.form))} · <bdi>${esc(t("ord_each", { price: money(i.price_iqd) }))}</bdi></span>
          </div>
          <div class="qty" dir="ltr">
            <button type="button" data-dec="${idx}" aria-label="−">−</button>
            <b>${i.quantity}</b>
            <button type="button" data-inc="${idx}" aria-label="+" ${i.quantity >= maxFor(i) ? "disabled" : ""}>+</button>
          </div>
        </li>`).join("")}
    </ul>
    <div class="seg ful-seg">
      <label><input type="radio" name="ful" value="pickup" ${del ? "" : "checked"}><span>${esc(t("ful_pickup"))}</span></label>
      <label><input type="radio" name="ful" value="delivery" ${del ? "checked" : ""}><span>${esc(t("ful_delivery"))}</span></label>
    </div>
    ${del ? `
      <section class="deliv-box">
        <label class="acc-field">
          <span>${esc(t("del_address"))}</span>
          <textarea id="del-address" rows="2" maxlength="200" placeholder="${esc(t("del_address_ph"))}">${esc(basket.address || "")}</textarea>
        </label>
        <div class="del-loc">
          <span>${esc(!locationIsSet() ? t("del_need_location") : q ? t("del_distance", { d: dist(q.km) }) : "…")}</span>
          <button class="link-btn" type="button" id="del-set-loc">${esc(t(locationIsSet() ? "del_change_location" : "del_set_location"))}</button>
        </div>
        ${q && !q.ok ? `<p class="acc-error">${esc(t("del_too_far", { max: q.max_km }))}</p>` : ""}
      </section>` : ""}
    <div class="ord-sum">
      ${del ? `
        <div class="ord-total sub"><span>${esc(t("ord_subtotal"))}</span><bdi>${money(total)}</bdi></div>
        <div class="ord-total sub"><span>${esc(t("del_fee"))}</span><bdi>${q && q.ok ? money(fee) : "–"}</bdi></div>` : ""}
      <div class="ord-total"><span>${esc(t("ord_total"))}</span><b><bdi>${money(total + fee)}</bdi></b></div>
      <p class="pay-line">${esc(t(del ? "pay_cash_driver" : "pay_cash_pharmacy"))}</p>
    </div>
    ${needsRx() ? `
      <section class="rx-box">
        <b>${esc(t("rx_title"))}</b>
        <p class="muted small">${esc(t("rx_how"))}</p>
        <input id="rx-file" type="file" accept="image/*" hidden>
        ${rxPhoto.url ? `
          <div class="rx-preview">
            <img src="${rxPhoto.url}" alt="">
            <div class="rx-preview-actions">
              <label class="link-btn" for="rx-file">${esc(t("rx_change"))}</label>
              <button class="link-btn danger" type="button" id="rx-remove">${esc(t("rx_remove"))}</button>
            </div>
          </div>`
        : `<label class="btn-ghost full rx-pick" for="rx-file">
             <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>
             ${esc(t("rx_add_photo"))}
           </label>`}
        <p class="muted small">${esc(t("rx_privacy"))}</p>
      </section>` : ""}
    <label class="acc-field">
      <span>${esc(t("ord_note"))}</span>
      <input id="basket-note" type="text" maxlength="200" placeholder="${esc(t("ord_note_ph"))}" value="${esc(basket.note || "")}">
    </label>
    <p class="acc-soon">${esc(t(del ? "del_how" : "ord_how", { h: myOrders.holdHours }))}${del && needsRx() ? " " + esc(t("del_have_paper")) : ""}</p>
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

  // Phase 9: pick up or delivery, address and map location
  body.querySelectorAll('input[name="ful"]').forEach((r) => r.addEventListener("change", () => {
    basket.fulfilment = r.value;
    saveBasket();
    renderBasket();
  }));
  if ($("del-address")) $("del-address").addEventListener("input", (e) => { basket.address = e.target.value; saveBasket(); });
  if ($("del-set-loc")) $("del-set-loc").addEventListener("click", () => {
    delivery.waitingForLocation = true;               // come back to the basket once it is set
    closeModal($("basket-modal"));
    openModal($("loc-chooser"));
  });
  refreshQuote();

  // Phase 8: the prescription photo (made smaller first, like the scanner does)
  if ($("rx-file")) $("rx-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const blob = await fileToBlob(file, 2000);
      clearRxPhoto();
      rxPhoto.blob = blob;
      rxPhoto.url = URL.createObjectURL(blob);
      renderBasket();
    } catch {
      showBasketError(t("rx_err_not_photo"));
    }
  });
  if ($("rx-remove")) $("rx-remove").addEventListener("click", () => { clearRxPhoto(); renderBasket(); });
}

function showBasketError(text) {
  $("basket-error").textContent = text;
  $("basket-error").hidden = false;
}

// Ask the server what delivery costs from this pharmacy to the chosen location (once per place).
async function refreshQuote() {
  if (!isDelivery() || !basket.pharmacy || !locationIsSet()) return;
  const key = quoteKey();
  if (delivery.key === key) return;
  delivery.key = key;
  delivery.quote = null;
  try {
    const r = await fetch(`/api/delivery/quote?pharmacy_id=${basket.pharmacy.id}&lat=${state.lat}&lng=${state.lng}`);
    if (r.ok) delivery.quote = await r.json();
  } catch { /* offline: no price shown */ }
  if (delivery.key === key && !$("basket-modal").hidden) renderBasket();
}

window.onLocationSet = () => {
  if (!delivery.waitingForLocation) return;
  delivery.waitingForLocation = false;
  openBasket();
};

function openBasket() {
  delivery.waitingForLocation = false;
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
    case "prescription_required": return t("rx_err_required");
    case "photo_too_small": return t("rx_err_too_small");
    case "photo_too_big": return t("rx_err_too_big");
    case "not_a_photo": return t("rx_err_not_photo");
    case "photo_unavailable": return t("rx_err_unavailable");
    case "rx_already_used": return t("rx_err_used");
    case "bad_address": return t("del_err_address");
    case "bad_location": return t("del_need_location");
    case "too_far": return t("del_too_far", { max: data.max_km });
    default: return t("ord_err_generic");
  }
}

// With prescription medicines the reservation is sent as a form, with the photo attached.
async function postReservation(payload) {
  if (!needsRx()) return accountApi("/api/orders", "POST", payload);
  const form = new FormData();
  form.append("order", JSON.stringify(payload));
  form.append("prescription", rxPhoto.blob, "prescription.jpg");
  const res = await fetch("/api/orders", {
    method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "fetch" }, body: form,
  });
  let data = {};
  try { data = await res.json(); } catch { /* not JSON */ }
  return { ok: res.ok, status: res.status, data };
}

// "Send reservation": log in (and fill in name, age, gender) first if needed, then send.
function sendReservation() {
  if (!basket.items.length) return;
  if (needsRx() && !rxPhoto.blob) return showBasketError(t("rx_err_required"));   // ask before logging in
  if (isDelivery()) {
    if ((basket.address || "").trim().length < 8) return showBasketError(t("del_err_address"));
    if (!locationIsSet()) return showBasketError(t("del_need_location"));
    if (delivery.quote && !delivery.quote.ok) return showBasketError(t("del_too_far", { max: delivery.quote.max_km }));
  }
  closeModal($("basket-modal"));                       // the login pop-up must not be hidden behind it
  window.requireAccount(async () => {
    openBasket();
    const btn = $("basket-send");
    btn.disabled = true;
    let r;
    try {
      r = await postReservation({
        pharmacy_id: basket.pharmacy.id,
        items: basket.items.map((i) => ({ medicine_id: i.medicine.id, quantity: i.quantity })),
        note: basket.note || "",
        fulfilment: isDelivery() ? "delivery" : "pickup",
        ...(isDelivery() ? { address: basket.address, lat: state.lat, lng: state.lng } : {}),
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
      showBasketError(orderErrorText(r.data));
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
  if (o.fulfilment === "delivery") return deliveryHint(o);
  const paper = o.prescription ? " " + t("rx_bring_paper") : "";
  if (o.status === "pending") return t(o.prescription ? "ord_hint_pending_rx" : "ord_hint_pending");
  if (o.status === "confirmed") return t("ord_hint_confirmed", { time: fmtTime(o.hold_until) }) + paper;
  if (o.status === "ready") return t("ord_hint_ready", { time: fmtTime(o.hold_until) }) + paper;
  return cancelHint(o);
}

// Phase 9: what is happening with a delivery
function deliveryHint(o) {
  const name = o.driver ? o.driver.name : "";
  const paper = o.prescription ? " " + t("del_have_paper") : "";
  if (o.status === "pending") return t(o.prescription ? "del_hint_pending_rx" : "del_hint_pending");
  if (o.status === "confirmed" || o.status === "ready") {
    if (o.driver) return t("del_hint_driver_coming", { name });
    return t(o.status === "ready" ? "del_hint_waiting_driver" : "del_hint_confirmed");
  }
  if (o.status === "out_for_delivery") return t("del_hint_on_way", { name, total: money(o.grand_total_iqd) }) + paper;
  return cancelHint(o);
}

function cancelHint(o) {
  if (o.status !== "cancelled") return "";
  if (o.cancelled_by === "pharmacy") return t("ord_by_pharmacy", { reason: t("reason_" + o.cancel_reason) });
  if (o.cancelled_by === "driver") return t("ord_by_driver", { reason: t("reason_" + o.cancel_reason) });
  return "";
}

function orderCard(o) {
  const open = OPEN_STATUSES.includes(o.status);
  const del = o.fulfilment === "delivery";
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
      ${del ? `
        <p class="del-line"><b>${esc(t("del_to"))}</b> <bdi>${esc(o.address)}</bdi></p>
        <div class="ord-total sub"><span>${esc(t("del_fee"))}</span><bdi>${money(o.delivery_fee_iqd)}</bdi></div>` : ""}
      <div class="ord-total"><span>${esc(t("ord_total"))}</span><b><bdi>${money(o.grand_total_iqd)}</bdi></b></div>
      ${o.driver && open ? `
        <p class="del-line">${esc(t("del_driver", { name: o.driver.name }))} ·
          <a href="tel:${esc(o.driver.phone.replace(/\s/g, ""))}" dir="ltr">${esc(o.driver.phone)}</a></p>` : ""}
      ${o.prescription ? `
        <p class="rx-line rx-${o.prescription.status}">
          <span>${esc(t("rx_status_" + o.prescription.status))}</span>
          ${o.prescription.has_photo ? `<a href="/api/orders/${o.id}/prescription" target="_blank" rel="noopener">${esc(t("rx_view"))}</a>` : ""}
        </p>` : ""}
      ${hint ? `<p class="ord-hint ${o.status === "cancelled" ? "bad" : ""}">${esc(hint)}</p>` : ""}
      ${open ? `
        <div class="ord-code">
          <span>${esc(t("ord_code"))}</span>
          <b dir="ltr">${esc(o.pickup_code)}</b>
          <small>${esc(t(del ? "del_code_hint" : "ord_code_hint"))}</small>
        </div>
        <div class="ord-actions">
          <a class="btn-ghost" href="tel:${esc(o.pharmacy.phone.replace(/\s/g, ""))}">${esc(t(del ? "del_call_pharmacy" : "call"))}</a>
          ${del ? "" : `<button class="btn-ghost" type="button" data-dir="${o.id}">${esc(t("directions"))}</button>`}
          ${o.status === "out_for_delivery" ? "" : `<button class="link-btn danger" type="button" data-cancel="${o.id}">${esc(t("ord_cancel"))}</button>`}
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
