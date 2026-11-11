// PharmaFind - front end
// Language picker -> search with live suggestions -> pharmacies sorted by distance.
// The map is only shown in a pop-up: for directions, or to pick your location by hand.

const state = {
  lang: null,
  lat: window.PF_DEFAULT.lat,
  lng: window.PF_DEFAULT.lng,
  medicineId: null,
  sort: "distance",
  suggestions: [],
  activeIndex: -1,
  tab: "pharmacies",                    // pharmacies | alternatives | about
  lastData: null,                       // last results, so we can re-render after a language change
  loc: { key: "loc_default", vars: {} }, // current location message
};

const $ = (id) => document.getElementById(id);
const input = $("q");
const sugBox = $("suggestions");

// ---------------- Language ----------------
// Translate a key, filling {placeholders}.
function t(key, vars = {}) {
  const s = (I18N[state.lang] || I18N.en)[key] ?? I18N.en[key] ?? key;
  return typeof s === "string" ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "") : s;
}

// Saved language survives page reloads. Storage can fail (private mode), so it's wrapped.
function loadSavedLang() {
  try { return localStorage.getItem("pf_lang"); } catch { return null; }
}
function saveLang(lang) {
  try { localStorage.setItem("pf_lang", lang); } catch { /* ignore */ }
}

function setLang(lang, remember = true) {
  state.lang = lang;
  if (remember) saveLang(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = LANGS[lang].dir;

  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nLabel)); });
  $("lang-btn").textContent = LANGS[lang].name;
  renderLoc();
  renderChips();
  if (youMarker) youMarker.setTooltipContent(t("you_here"));

  $("lang-picker").hidden = true;
  if (state.lastData) renderResults(state.lastData);
  if (!$("map-modal").hidden) renderMapFoot();
  if (window.renderScanText) window.renderScanText();
  if (window.renderAccount) window.renderAccount();
  if (window.renderOrdersUi) window.renderOrdersUi();
}

function openLangPicker() { $("lang-picker").hidden = false; }

document.querySelectorAll("#lang-picker [data-lang]").forEach((b) =>
  b.addEventListener("click", () => setLang(b.dataset.lang))
);
$("lang-btn").addEventListener("click", openLangPicker);

// Medicine name in the chosen language (brand name as fallback).
function medName(m) {
  if (state.lang === "ku" && m.name_ku) return m.name_ku;
  if (state.lang === "ar" && m.name_ar) return m.name_ar;
  return m.brand_name;
}
function medUse(m) {
  if (state.lang === "ku" && m.general_use_ku) return m.general_use_ku;
  if (state.lang === "ar" && m.general_use_ar) return m.general_use_ar;
  return m.general_use;
}
const formName = (f) => t("forms")[f] || f;

// ---------------- Formatting ----------------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
// "5 min ago", "2 h ago"... in the chosen language.
function ago(iso) {
  if (!iso) return "–";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return t("ago_now");
  if (min < 60) return t("ago_min", { n: min });
  const h = Math.round(min / 60);
  return h < 24 ? t("ago_h", { n: h }) : t("ago_d", { n: Math.round(h / 24) });
}
const money = (n) => n.toLocaleString("en-US") + " " + t("currency");
const dist = (d) => (d < 1 ? Math.round(d * 1000) + " " + t("unit_m") : d.toFixed(1) + " " + t("unit_km"));

// ---------------- Pop-ups (modals) ----------------
function openModal(el) { el.hidden = false; }
function closeModal(el) {
  el.hidden = true;
  if (el.id === "map-modal") onMapClosed();
  if (el.id === "scan-modal" && window.onScanClosed) window.onScanClosed();
  if (el.id === "account-modal" && window.onAccountClosed) window.onAccountClosed();
  if (el.id === "orders-modal" && window.onOrdersClosed) window.onOrdersClosed();
}
document.querySelectorAll(".modal").forEach((m) => {
  m.addEventListener("click", (e) => {
    if (e.target === m || e.target.closest("[data-close]")) closeModal(m); // backdrop or close button
  });
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".modal:not([hidden])").forEach(closeModal);
});

// ---------------- Location ----------------
function setLocMessage(key, vars = {}) {
  state.loc = { key, vars };
  renderLoc();
}
function renderLoc() { $("loc-status").textContent = t(state.loc.key, state.loc.vars); }

function setLocation(lat, lng, key, vars) {
  state.lat = lat;
  state.lng = lng;
  setLocMessage(key, vars);
  if (state.medicineId) loadPharmacies(); // distances change, so reload the results
}

// "Set my location" -> choose how.
$("locate").addEventListener("click", () => openModal($("loc-chooser")));
$("loc-device").addEventListener("click", () => { closeModal($("loc-chooser")); useDeviceLocation(); });
$("loc-manual").addEventListener("click", () => { closeModal($("loc-chooser")); startManualPick(); });

// Option 1: the computer's / phone's own location.
function useDeviceLocation() {
  if (!navigator.geolocation) { setLocMessage("loc_unsupported"); return; }
  setLocMessage("loc_finding");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const a = Math.round(pos.coords.accuracy);
      setLocation(pos.coords.latitude, pos.coords.longitude, "loc_ok",
        { acc: a < 1000 ? a + " " + t("unit_m") : (a / 1000).toFixed(1) + " " + t("unit_km") });
    },
    (err) => {
      setLocMessage("loc_err" + (err.code >= 1 && err.code <= 3 ? err.code : 2));
      console.warn("Geolocation error", err.code, err.message);
    },
    // Laptops have no GPS: low accuracy (Wi-Fi based) is faster and more reliable.
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 }
  );
}

// ---------------- Map (inside the pop-up only) ----------------
// The map is created the first time the pop-up opens, not on page load.
let map = null, youMarker = null, mapLayer = null;
const mapState = {
  mode: null,        // "pick" (choose your location) | "route" (directions to a pharmacy)
  pick: null,        // {lat, lng} chosen in pick mode
  pharmacy: null,    // pharmacy shown in route mode
  route: null,       // "loading" | "straight" | {km, min}
  requestId: 0,      // ignore route answers that arrive after the user moved on
};

function ensureMap() {
  if (map) return;
  // Give the map a view right away: Leaflet only finishes adding markers once the map has one.
  map = L.map("map").setView([state.lat, state.lng], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  mapLayer = L.layerGroup().addTo(map);
  youMarker = L.marker([state.lat, state.lng], {
    icon: L.divIcon({ className: "", html: '<div class="you-dot"></div>', iconSize: [18, 18] }),
    zIndexOffset: 1000,
  }).addTo(map).bindTooltip(t("you_here"));

  map.on("click", (e) => { if (mapState.mode === "pick") setPick(e.latlng.lat, e.latlng.lng); });
  youMarker.on("dragend", () => { const ll = youMarker.getLatLng(); setPick(ll.lat, ll.lng); });
}

function openMap(mode) {
  mapState.mode = mode;
  openModal($("map-modal"));
  ensureMap();
  map.invalidateSize(); // the map was hidden, so Leaflet has to re-measure its box
  mapLayer.clearLayers();
  youMarker.setLatLng([state.lat, state.lng]);
}

function onMapClosed() {
  mapState.mode = null;
  mapState.requestId++; // cancel any route still loading
  if (youMarker) youMarker.dragging.disable();
}

// Option 2: choose your location by hand.
function startManualPick() {
  openMap("pick");
  mapState.pick = { lat: state.lat, lng: state.lng };
  youMarker.dragging.enable();
  map.setView([state.lat, state.lng], 15);
  renderMapFoot();
}

function setPick(lat, lng) {
  mapState.pick = { lat, lng };
  youMarker.setLatLng([lat, lng]);
}

// Directions: your location -> the pharmacy, with the road route when available.
function openDirections(p) {
  openMap("route");
  youMarker.dragging.disable();
  mapState.pharmacy = p;
  mapState.route = "loading";

  L.circleMarker([p.latitude, p.longitude], {
    radius: 11, color: "#fff", weight: 3, fillColor: "#12925c", fillOpacity: 1,
  }).addTo(mapLayer).bindTooltip(esc(p.name), { permanent: true, direction: "top", offset: [0, -12] });
  map.fitBounds([[state.lat, state.lng], [p.latitude, p.longitude]], { padding: [60, 60], maxZoom: 16 });

  renderMapFoot();
  drawRoute(p);
}

// Road route from the free OSRM demo server (needs internet).
// If it fails or is slow, we draw a dashed straight line instead.
async function drawRoute(p) {
  const id = ++mapState.requestId;
  const url = `https://router.project-osrm.org/route/v1/driving/` +
    `${state.lng},${state.lat};${p.longitude},${p.latitude}?overview=full&geometries=geojson`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 6000);
  let route = null;
  try {
    const data = await (await fetch(url, { signal: ctrl.signal })).json();
    if (data.code === "Ok" && data.routes && data.routes.length) route = data.routes[0];
  } catch (e) {
    console.warn("Route service unavailable, using a straight line", e);
  }
  clearTimeout(timer);
  if (id !== mapState.requestId) return; // pop-up closed or another pharmacy opened

  let line;
  if (route) {
    const points = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    line = L.polyline(points, { color: "#5b2be0", weight: 6, opacity: 0.85 });
    mapState.route = { km: route.distance / 1000, min: Math.max(1, Math.round(route.duration / 60)) };
    map.fitBounds(points, { padding: [50, 50], maxZoom: 17 });
  } else {
    line = L.polyline([[state.lat, state.lng], [p.latitude, p.longitude]],
      { color: "#5b2be0", weight: 4, dashArray: "6 10" });
    mapState.route = "straight";
  }
  line.addTo(mapLayer).bringToBack();
  renderMapFoot();
}

// Title and bottom bar of the map pop-up, in the current language.
function renderMapFoot() {
  const foot = $("map-foot");
  if (mapState.mode === "pick") {
    $("map-title").textContent = t("pick_title");
    foot.innerHTML = `
      <p class="muted">${esc(t("pick_hint"))}</p>
      <div class="map-actions">
        <button class="btn-ghost" type="button" data-close>${esc(t("cancel"))}</button>
        <button class="btn-primary" type="button" id="pick-confirm">${esc(t("pick_confirm"))}</button>
      </div>`;
    $("pick-confirm").addEventListener("click", () => {
      const { lat, lng } = mapState.pick;
      closeModal($("map-modal"));
      setLocation(lat, lng, "loc_map");
    });
    return;
  }

  const p = mapState.pharmacy;
  const r = mapState.route;
  $("map-title").textContent = t("dir_title", { name: p.name });
  const routeText = r === "loading" ? t("dir_loading")
    : r === "straight" ? t("dir_straight", { d: dist(p.distance_km) })
    : t("dir_route", { d: dist(r.km), min: r.min });
  const gmaps = `https://www.google.com/maps/dir/?api=1&origin=${state.lat},${state.lng}` +
    `&destination=${p.latitude},${p.longitude}`;
  foot.innerHTML = `
    <div class="route-info">
      <div>
        <b><bdi>${esc(p.name)}</bdi></b>
        <div class="muted"><bdi>${esc(p.address)}</bdi> · <bdi>${esc(p.open_hours)}</bdi> · <bdi>${money(p.price_iqd)}</bdi></div>
      </div>
      <div class="route-stat ${r === "loading" ? "loading" : ""}"><bdi>${esc(routeText)}</bdi></div>
    </div>
    <div class="map-actions">
      <a class="btn-ghost" href="tel:${esc(p.phone.replace(/\s/g, ""))}">${esc(t("call"))} <bdi>${esc(p.phone)}</bdi></a>
      <a class="btn-primary" target="_blank" rel="noopener" href="${gmaps}">${esc(t("open_gmaps"))}</a>
    </div>`;
}

// ---------------- Suggestions ----------------
let debounceTimer;
input.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fetchSuggestions, 180);
});

async function fetchSuggestions() {
  const q = input.value.trim();
  if (!q) { hideSuggestions(); return; }
  const data = await (await fetch("/api/search?q=" + encodeURIComponent(q))).json();
  if (data.query !== input.value.trim()) return; // a newer request is coming
  state.suggestions = data.results;
  state.activeIndex = data.results.length ? 0 : -1;
  renderSuggestions();
}

function renderSuggestions() {
  if (!state.suggestions.length) {
    sugBox.innerHTML = `<li class="s-none">${esc(t("no_match"))}</li>`;
  } else {
    sugBox.innerHTML = state.suggestions.map((m, i) => `
      <li role="option" data-i="${i}" class="${i === state.activeIndex ? "active" : ""}">
        <div>
          <div class="s-name">${esc(medName(m))} <span class="s-meta">${esc(m.strength)} · ${esc(formName(m.form))}</span></div>
          <div class="s-meta">${state.lang === "en" ? "" : `<bdi>${esc(m.brand_name)}</bdi> · `}<bdi>${esc(m.active_ingredient)}</bdi> · <bdi>${esc(m.company)}</bdi></div>
        </div>
      </li>`).join("");
  }
  sugBox.hidden = false;
}

function hideSuggestions() { sugBox.hidden = true; state.activeIndex = -1; }

sugBox.addEventListener("mousedown", (e) => {
  const li = e.target.closest("li[data-i]");
  if (li) { e.preventDefault(); pick(state.suggestions[+li.dataset.i]); }
});

input.addEventListener("keydown", (e) => {
  const n = state.suggestions.length;
  if (e.key === "ArrowDown" && n) {
    e.preventDefault(); state.activeIndex = (state.activeIndex + 1) % n; renderSuggestions();
  } else if (e.key === "ArrowUp" && n) {
    e.preventDefault(); state.activeIndex = (state.activeIndex - 1 + n) % n; renderSuggestions();
  } else if (e.key === "Enter") {
    e.preventDefault(); submitSearch();
  } else if (e.key === "Escape") {
    hideSuggestions();
  }
});
input.addEventListener("blur", () => setTimeout(hideSuggestions, 120));

// Enter: log the search, then pick the highlighted (or best) match.
async function submitSearch() {
  const q = input.value.trim();
  if (!q) return;
  const data = await (await fetch(`/api/search?log=1&lat=${state.lat}&lng=${state.lng}&q=` + encodeURIComponent(q))).json();
  state.suggestions = data.results;
  if (!data.results.length) { renderSuggestions(); return; }
  const i = state.activeIndex >= 0 && state.activeIndex < data.results.length ? state.activeIndex : 0;
  pick(data.results[i]);
}

function renderChips() {
  $("chips").innerHTML = t("examples")
    .map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
  $("chips").querySelectorAll(".chip").forEach((b) =>
    b.addEventListener("click", () => { input.value = b.dataset.q; state.activeIndex = -1; submitSearch(); })
  );
}

function pick(medicine) {
  hideSuggestions();
  input.value = medName(medicine);
  state.medicineId = medicine.id;
  loadPharmacies(true);
}

// ---------------- Results ----------------
// One medicine -> two requests in parallel: pharmacies that have it, and its alternatives.
async function loadPharmacies(resetTab = false) {
  const q = `lat=${state.lat}&lng=${state.lng}`;
  const [data, alts] = await Promise.all([
    fetch(`/api/medicines/${state.medicineId}/pharmacies?${q}&sort=${state.sort}`).then((r) => r.json()),
    fetch(`/api/medicines/${state.medicineId}/alternatives?${q}`).then((r) => r.json()),
  ]);
  data.alts = alts;
  if (resetTab) state.tab = "pharmacies";
  state.lastData = data;
  renderResults(data);
}

function renderResults(data) {
  const m = data.medicine;
  const alts = data.alts || { exact: [], similar: [], available_exact_count: 0 };
  const altCount = alts.exact.length + alts.similar.length;
  const soldOut = data.available_count === 0;

  $("empty").hidden = true;
  const box = $("results");
  box.hidden = false;
  box.innerHTML = `
    <div class="med">
      <div class="med-top">
        <div>
          <h2>${esc(medName(m))}</h2>
          <div class="names"><bdi>${esc(state.lang === "en" ? m.active_ingredient : m.brand_name)}</bdi> · <bdi>${esc(m.strength)}</bdi> · ${esc(formName(m.form))}</div>
        </div>
        <span class="badge ${m.rx_required ? "rx" : "otc"}">${esc(t(m.rx_required ? "rx" : "otc"))}</span>
      </div>
      <p class="use">${esc(medUse(m))}</p>
      ${soldOut ? `
        <div class="alert">
          <b>${esc(t("out_banner", { name: medName(m) }))}</b>
          ${alts.available_exact_count ? `
            <span>${esc(t("none_alt", { n: alts.available_exact_count }))}</span>
            <button class="alert-btn" data-tab="alternatives">${esc(t("show_alts"))}</button>` : ""}
        </div>` : ""}
    </div>
    <nav class="tabs">
      <button data-tab="pharmacies" class="${state.tab === "pharmacies" ? "on" : ""}">${esc(t("tab_pharmacies"))} <span class="count">${data.available_count}</span></button>
      <button data-tab="alternatives" class="${state.tab === "alternatives" ? "on" : ""}">${esc(t("tab_alternatives"))} <span class="count">${altCount}</span></button>
      <button data-tab="about" class="${state.tab === "about" ? "on" : ""}">${esc(t("tab_about"))}</button>
    </nav>
    <div class="tab-body">
      ${state.tab === "alternatives" ? renderAlternatives(alts)
        : state.tab === "about" ? renderAbout(m)
        : renderPharmacyTab(data)}
    </div>
  `;

  box.querySelectorAll("[data-tab]").forEach((b) =>
    b.addEventListener("click", () => { state.tab = b.dataset.tab; renderResults(state.lastData); })
  );
  box.querySelectorAll(".sort button").forEach((b) =>
    b.addEventListener("click", () => { state.sort = b.dataset.sort; loadPharmacies(); })
  );
  box.querySelectorAll(".dir-btn").forEach((b) =>
    b.addEventListener("click", () => {
      const p = state.lastData.pharmacies.find((x) => x.id === +b.dataset.id);
      if (p) openDirections(p);
    })
  );
  // Phase 7: put this medicine from this pharmacy in the basket
  box.querySelectorAll(".reserve-btn").forEach((b) =>
    b.addEventListener("click", () => {
      const p = state.lastData.pharmacies.find((x) => x.id === +b.dataset.id);
      if (p && window.addToBasket) window.addToBasket(state.lastData.medicine, p);
    })
  );
  box.querySelectorAll(".alt").forEach((el) =>
    el.addEventListener("click", () => {
      const all = [...alts.exact, ...alts.similar];
      const med = all.find((a) => a.id === +el.dataset.id);
      if (med) pick(med);
    })
  );
}

function renderPharmacyTab(data) {
  const pr = data.price_range;
  const nearest = data.pharmacies.length ? Math.min(...data.pharmacies.map((p) => p.distance_km)) : null;
  // Phase 7/8: controlled medicines can't be reserved; prescription ones can, with a photo
  const m = data.medicine;
  const reservable = window.canReserve ? window.canReserve(m) : false;
  const whyNot = m.controlled ? t("ord_controlled_note") : m.rx_required ? t("ord_rx_note") : "";
  return `
    <div class="summary pad">
      <div class="stat"><b>${data.available_count}</b><span>${esc(t("s_have"))}</span></div>
      <div class="stat"><b><bdi>${nearest !== null ? dist(nearest) : "–"}</bdi></b><span>${esc(t("s_nearest"))}</span></div>
      <div class="stat"><b><bdi>${pr ? (pr.min / 1000).toFixed(1) + "–" + (pr.max / 1000).toFixed(1) + "k" : "–"}</bdi></b><span>${esc(t("s_price"))}</span></div>
    </div>
    ${data.pharmacies.length ? `
      <div class="sort">
        <span>${esc(t("pharmacies"))}</span>
        <button data-sort="distance" class="${state.sort === "distance" ? "on" : ""}">${esc(t("sort_near"))}</button>
        <button data-sort="price" class="${state.sort === "price" ? "on" : ""}">${esc(t("sort_cheap"))}</button>
      </div>
      ${whyNot ? `<p class="reserve-note ${m.controlled ? "" : "info"}">${esc(whyNot)}</p>` : ""}
      <ul class="ph-list">
        ${data.pharmacies.map((p) => `
          <li class="ph" data-id="${p.id}">
            <div class="ph-name"><bdi>${esc(p.name)}</bdi>
              ${p.is_24h ? `<span class="badge h24">${esc(t("h24"))}</span>` : ""}
              ${p.distance_km === nearest ? `<span class="nearest-tag">${esc(t("nearest_tag"))}</span>` : ""}
            </div>
            <div class="ph-price"><bdi>${money(p.price_iqd)}</bdi></div>
            <div class="ph-sub"><bdi>${dist(p.distance_km)}</bdi> · <bdi>${esc(p.address)}</bdi> · <bdi>${esc(p.open_hours)}</bdi></div>
            <div class="ph-sub">${esc(t("in_stock", { n: p.quantity }))} · ${esc(t("updated_ago", { ago: ago(p.updated_at) }))}</div>
            <div class="ph-actions">
              <a href="tel:${esc(p.phone.replace(/\s/g, ""))}">${esc(t("call"))} <bdi>${esc(p.phone)}</bdi></a>
              <button class="dir-btn" type="button" data-id="${p.id}">${esc(t("directions"))}</button>
              ${reservable ? `<button class="reserve-btn" type="button" data-id="${p.id}">${esc(t("ord_reserve"))}</button>` : ""}
            </div>
          </li>`).join("")}
      </ul>` : `<div class="none-box">${esc(t("none", { name: medName(state.lastData.medicine) }))}</div>`}
    ${data.out_of_stock_count && data.pharmacies.length
      ? `<div class="none-box">${esc(t("out_other", { n: data.out_of_stock_count }))}</div>` : ""}
  `;
}

function altCard(a) {
  const available = a.available_count > 0;
  const diffs = (a.differences || []).map((d) => `<span class="badge warn">${esc(t("diff_" + d))}</span>`).join(" ");
  return `
    <button class="alt ${available ? "" : "dim"}" data-id="${a.id}">
      <div class="alt-main">
        <div class="alt-name">${esc(medName(a))} ${diffs}</div>
        <div class="ph-sub">${state.lang === "en" ? "" : `<bdi>${esc(a.brand_name)}</bdi> · `}<bdi>${esc(a.company)}</bdi> · <bdi>${esc(a.strength)}</bdi> · ${esc(formName(a.form))}</div>
        <div class="alt-avail ${available ? "ok" : ""}">
          ${available
            ? `${esc(t("alt_avail", { n: a.available_count, d: dist(a.nearest_km) }))} · <bdi>${esc(t("alt_from", { price: money(a.min_price_iqd) }))}</bdi>`
            : esc(t("alt_unavailable"))}
        </div>
      </div>
      <span class="alt-go">${esc(t("view"))}</span>
    </button>`;
}

function renderAlternatives(alts) {
  if (!alts.exact.length && !alts.similar.length) {
    return `<div class="none-box">${esc(t("alt_none"))}</div>`;
  }
  return `
    ${alts.exact.length ? `
      <section class="alt-group">
        <h3>${esc(t("alt_exact_title"))}</h3>
        <p class="muted">${esc(t("alt_exact_desc"))}</p>
        ${alts.exact.map(altCard).join("")}
      </section>` : ""}
    ${alts.similar.length ? `
      <section class="alt-group">
        <h3>${esc(t("alt_similar_title"))}</h3>
        <p class="warn-box">${esc(t("alt_similar_warn"))}</p>
        ${alts.similar.map(altCard).join("")}
      </section>` : ""}
  `;
}

function renderAbout(m) {
  const parts = m.active_ingredient.split(/\s*\+\s*/);
  return `
    <div class="about">
      <dl class="facts">
        <div><dt>${esc(t("f_ingredient"))}</dt><dd><bdi>${esc(m.active_ingredient)}</bdi></dd></div>
        <div><dt>${esc(t("f_strength"))}</dt><dd><bdi>${esc(m.strength)}</bdi></dd></div>
        <div><dt>${esc(t("f_form"))}</dt><dd>${esc(formName(m.form))}</dd></div>
        <div><dt>${esc(t("f_company"))}</dt><dd><bdi>${esc(m.company)}</bdi></dd></div>
      </dl>
      ${parts.length > 1 ? `
        <h3>${esc(t("about_contains"))}</h3>
        <ul class="contains">${parts.map((p) => `<li><bdi>${esc(p)}</bdi></li>`).join("")}</ul>` : ""}
      <p class="use">${esc(medUse(m))}</p>
      <p class="${m.rx_required ? "warn-box" : "ok-box"}">${esc(t(m.rx_required ? "rx_yes" : "rx_no"))}</p>
      <p class="muted small">${esc(t("about_disclaimer"))}</p>
    </div>`;
}

// ---------------- Start ----------------
const saved = loadSavedLang();
if (saved && LANGS[saved]) setLang(saved);
else { setLang("en", false); openLangPicker(); } // fill the page behind the picker, then ask
