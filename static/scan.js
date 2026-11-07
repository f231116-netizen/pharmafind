// PharmaFind - AI scanner (Phase 4)
// 1. Live camera: a few frames per second go to /api/scan/frame, which looks for a barcode.
// 2. "Recognize the box" / "Upload a photo": one photo goes to /api/scan/photo, which tries
//    the barcode, then reads the text on the box (OCR) and compares it with our box photos.
// Uses helpers from app.js: $, t, esc, pick, openModal, closeModal, medName, formName.

const scan = {
  stream: null,        // camera stream
  timer: null,         // next frame check
  busy: false,         // a request is in progress
  open: false,
  status: { key: "scan_point", vars: {} },
  lastResult: null,    // last photo result, re-drawn when the language changes
  unknownShown: null,  // don't repeat the same "unknown barcode" message
};

const video = $("scan-video");
const preview = $("scan-preview");

// ---------------- Open / close ----------------
$("scan-btn").addEventListener("click", () => { unlockSound(); openScanner(); });

async function openScanner() {
  scan.open = true;
  scan.lastResult = null;
  scan.unknownShown = null;
  $("scan-result").innerHTML = "";
  showPreview(null);
  setScanStatus("scan_point");
  openModal($("scan-modal"));

  try {
    const s = await (await fetch("/api/scan/status")).json();
    if (!s.available) {
      setScanStatus("scan_unavailable");
      return;
    }
  } catch { /* server unreachable: the photo request will show the error */ }
  startCamera();
}

// Called by closeModal() in app.js.
window.onScanClosed = function () {
  scan.open = false;
  stopCamera();
};

// ---------------- Camera ----------------
async function startCamera() {
  const msg = $("scan-cam-msg");
  msg.hidden = true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    // Browsers only allow the camera on https:// or on localhost.
    msg.textContent = t("scan_cam_unsupported");
    msg.hidden = false;
    return;
  }
  try {
    scan.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    if (!scan.open) { stopCamera(); return; } // closed while the permission prompt was open
    video.srcObject = scan.stream;
    await video.play();
    scheduleFrame();
  } catch (e) {
    console.warn("Camera error", e);
    msg.textContent = t(e && e.name === "NotAllowedError" ? "scan_cam_denied" : "scan_cam_none");
    msg.hidden = false;
  }
}

function stopCamera() {
  clearTimeout(scan.timer);
  if (scan.stream) scan.stream.getTracks().forEach((tr) => tr.stop());
  scan.stream = null;
  video.srcObject = null;
}

// ---------------- Live barcode scanning ----------------
function scheduleFrame() {
  clearTimeout(scan.timer);
  if (scan.open && scan.stream) scan.timer = setTimeout(checkFrame, 350);
}

async function checkFrame() {
  if (!scan.open || !scan.stream) return;
  if (scan.busy || video.readyState < 2 || !preview.hidden) { scheduleFrame(); return; }
  scan.busy = true;
  try {
    const blob = await frameToBlob(960, 0.8);
    const data = await postImage("/api/scan/frame", blob);
    if (data.found) {
      found(data.medicine, "barcode");
      return;
    }
    const code = (data.unknown_codes || [])[0];
    if (code && code !== scan.unknownShown) {
      scan.unknownShown = code;
      setScanStatus("scan_unknown_code", { code });
    }
  } catch (e) {
    console.warn("Frame check failed", e);
  } finally {
    scan.busy = false;
  }
  scheduleFrame();
}

// ---------------- Photo recognition ----------------
$("scan-capture").addEventListener("click", async () => {
  if (scan.busy && !preview.hidden) return;
  if (!scan.stream || video.readyState < 2) {
    $("scan-file").click(); // no camera: fall back to choosing a photo
    return;
  }
  const blob = await frameToBlob(1280, 0.9);
  recognizePhoto(blob);
});

$("scan-file").addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = ""; // allow choosing the same file again
  if (!file) return;
  try {
    recognizePhoto(await fileToBlob(file, 1600));
  } catch {
    setScanStatus("scan_bad_file");
  }
});

async function recognizePhoto(blob) {
  // wait for a live-frame request to finish
  for (let i = 0; scan.busy && i < 40; i++) await new Promise((r) => setTimeout(r, 50));
  scan.busy = true;
  showPreview(blob);
  $("scan-busy").hidden = false;
  $("scan-result").innerHTML = "";
  setScanStatus("scan_analyzing");
  // On the free online server this can take a while: tell the user after 6 seconds.
  const slowTimer = setTimeout(() => setScanStatus("scan_slow"), 6000);
  try {
    const data = await postImage("/api/scan/photo", blob);
    clearTimeout(slowTimer);
    if (data.method === "barcode" && data.found) {
      found(data.candidates[0].medicine, "barcode");
      return;
    }
    scan.lastResult = data;
    $("scan-busy").hidden = true;
    renderScanResult();
    setScanStatus(data.found ? "scan_results_title" : "scan_not_found");
  } catch (e) {
    clearTimeout(slowTimer);
    console.warn("Recognition failed", e);
    setScanStatus("scan_error");
  } finally {
    $("scan-busy").hidden = true;
    scan.busy = false;
  }
}

function renderScanResult() {
  const data = scan.lastResult;
  const box = $("scan-result");
  if (!data) { box.innerHTML = ""; return; }

  const cands = (data.candidates || []).map((c, i) => `
    <button class="cand ${i === 0 ? "best" : ""}" data-i="${i}" type="button">
      <span class="cand-main">
        <b>${esc(medName(c.medicine))}</b>
        <span class="muted"><bdi>${esc(c.medicine.brand_name)}</bdi> · <bdi>${esc(c.medicine.strength)}</bdi> · ${esc(formName(c.medicine.form))}</span>
        <span class="chips-row">${c.reasons.map((r) => `<span class="reason">${esc(t("reason_" + r))}</span>`).join("")}</span>
      </span>
      <span class="conf conf-${c.confidence}">${esc(t("conf_" + c.confidence))}<small>${Math.round(c.score * 100)}%</small></span>
    </button>`).join("");

  const read = (data.text || []).filter((x) => x.length > 2).slice(0, 8);
  box.innerHTML = `
    ${cands ? `<div class="cands">${cands}</div>` : ""}
    ${(data.unknown_codes || []).length ? `<p class="muted small">${esc(t("scan_unknown_code", { code: data.unknown_codes[0] }))}</p>` : ""}
    ${data.status && /building|loading/.test(data.status.visual || "") ? `<p class="muted small">${esc(t("scan_loading"))}</p>` : ""}
    ${read.length ? `<details class="ocr-read"><summary>${esc(t("scan_read"))}</summary><p dir="ltr">${read.map(esc).join(" · ")}</p></details>` : ""}
    <button class="btn-ghost small-btn" type="button" id="scan-retry">${esc(t("scan_retry"))}</button>
  `;
  box.querySelectorAll(".cand").forEach((b) =>
    b.addEventListener("click", () => found(data.candidates[+b.dataset.i].medicine, "photo"))
  );
  $("scan-retry").addEventListener("click", () => {
    scan.lastResult = null;
    box.innerHTML = "";
    showPreview(null);
    setScanStatus("scan_point");
    scheduleFrame();
  });
}

// ---------------- Found ----------------
function found(medicine, method) {
  beep();
  closeModal($("scan-modal"));
  pick(medicine);
  toast(t(method === "barcode" ? "scan_found_barcode" : "scan_found_photo", { name: medName(medicine) }));
}

// ---------------- Helpers ----------------
function setScanStatus(key, vars = {}) {
  scan.status = { key, vars };
  $("scan-status").textContent = t(key, vars);
}

// Re-draw the scanner's text after a language change (called from setLang in app.js).
window.renderScanText = function () {
  if (!scan.open) return;
  $("scan-status").textContent = t(scan.status.key, scan.status.vars);
  renderScanResult();
};

function showPreview(blob) {
  if (preview.src) URL.revokeObjectURL(preview.src);
  if (blob) {
    preview.src = URL.createObjectURL(blob);
    preview.hidden = false;
  } else {
    preview.removeAttribute("src");
    preview.hidden = true;
  }
}

function frameToBlob(maxSide, quality) {
  const s = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
  const c = document.createElement("canvas");
  c.width = Math.round(video.videoWidth * s);
  c.height = Math.round(video.videoHeight * s);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return new Promise((res) => c.toBlob(res, "image/jpeg", quality));
}

// Shrink big phone photos before uploading (and keep them the right way up).
async function fileToBlob(file, maxSide) {
  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    // Older Safari: load it as a normal image instead (it is turned the right way up automatically).
    bmp = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = URL.createObjectURL(file);
    });
  }
  const w = bmp.naturalWidth || bmp.width;
  const h = bmp.naturalHeight || bmp.height;
  const s = Math.min(1, maxSide / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * s);
  c.height = Math.round(h * s);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  if (bmp.src) URL.revokeObjectURL(bmp.src);
  return new Promise((res) => c.toBlob(res, "image/jpeg", 0.9));
}

async function postImage(url, blob) {
  const form = new FormData();
  form.append("image", blob, "photo.jpg");
  form.append("lat", state.lat);   // approximate location, for the pharmacies' "searches near you"
  form.append("lng", state.lng);
  const res = await fetch(url, { method: "POST", body: form });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

// iPhones only allow sound that was "unlocked" by a tap, so we prepare it when Scan is pressed.
let audioCtx = null;
function unlockSound() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch { /* sound is optional */ }
}

function beep() {
  try {
    navigator.vibrate && navigator.vibrate(80);
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = 1100;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.12);
  } catch { /* sound is optional */ }
}

let toastTimer;
function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}
