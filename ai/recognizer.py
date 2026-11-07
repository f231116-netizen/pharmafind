"""Recognize a medicine from a photo by combining three methods:

  1. Barcode  (zxing-cpp)        - exact. If a known barcode is found, we're done.
  2. Text     (PP-OCRv3 OCR)     - reads the brand name, strength and ingredient
                                   from the box and compares them with the database.
                                   Works for boxes we never photographed.
  3. Visual   (SIFT matching)    - compares the image with our reference photos.
                                   Works for boxes whose name OCR can't read (Arabic).

The text and visual scores are combined into one confidence per medicine.
"""
import os
import re
import threading
from difflib import SequenceMatcher

from .barcodes import read_codes

HIGH, MEDIUM = 0.8, 0.55       # confidence thresholds
# Small servers (Render's free plan has 1/10 of a CPU): use one thread, and skip the
# visual matching when the text on the box already gives a clear answer.
LOW_CPU = os.environ.get("PHARMAFIND_LOW_CPU") == "1"
MIN_SHOWN = 0.45               # below this we say "not recognized"
VISUAL_FULL = 40               # this many matching points = full visual score
# A visual match counts ON ITS OWN only if it is strong and clearly better than the
# next box. Measured on our photos: 20 points and 2x the runner-up kept 60/71 real
# matches and 0/42 false ones (photos of boxes removed from the index, and posters).
VISUAL_ALONE_MIN, VISUAL_ALONE_RATIO = 20, 2.0


def _norm(text):
    text = (text or "").lower().replace("™", " ").replace("®", " ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _tokens(text):
    return [t for t in _norm(text).split() if len(t) >= 2]


class Recognizer:
    def __init__(self, photo_dir, folder_to_brand, cache_file):
        self.photo_dir, self.folder_to_brand, self.cache_file = photo_dir, folder_to_brand, cache_file
        self.reader = None
        self.matcher = None
        self.status = {"ocr": "not loaded", "visual": "not loaded"}
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()   # one photo at a time (OpenCV models aren't thread-safe)
        self._started = False

    # ---------------------------------------------------------------- loading
    def warm_up(self):
        """Load the AI models in the background, so the web page isn't blocked."""
        with self._lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._load, daemon=True).start()

    def load_now(self):
        """Load everything right now (used by prepare.py when building the website)."""
        with self._lock:
            self._started = True
        self._load()

    def _load(self):
        if LOW_CPU:
            import cv2
            cv2.setNumThreads(1)   # extra threads only cost memory on a tiny server
        self.status["ocr"] = "loading"
        try:
            from .ocr import TextReader
            self.reader = TextReader()
            self.status["ocr"] = "ready"
        except Exception as e:                 # missing opencv / model files
            self.status["ocr"] = f"unavailable: {e}"
        self.status["visual"] = "building index (first time can take ~30 s)"
        try:
            from .visual import BoxMatcher
            m = BoxMatcher(self.photo_dir, self.folder_to_brand, self.cache_file)
            self.matcher = m if m.ready else None
            self.status["visual"] = f"ready ({len(m.refs)} reference photos)" if m.ready else "no photos found"
        except Exception as e:
            self.status["visual"] = f"unavailable: {e}"

    # ---------------------------------------------------------------- scoring
    @staticmethod
    def line_weights(results, img_shape):
        """Big text in the middle of the photo (the brand name on the box being shown)
        counts fully; small text near the edges (other boxes in the background) counts less."""
        if not results:
            return []
        h_img, w_img = img_shape[:2]
        heights = []
        for _t, _c, box in results:
            b = [tuple(p) for p in box]
            heights.append(min(((b[0][0] - b[3][0]) ** 2 + (b[0][1] - b[3][1]) ** 2) ** 0.5,
                               ((b[0][0] - b[1][0]) ** 2 + (b[0][1] - b[1][1]) ** 2) ** 0.5))
        tallest = max(heights) or 1
        lines = []
        for (text, conf, box), h in zip(results, heights):
            cx = sum(p[0] for p in box) / 4 / w_img
            cy = sum(p[1] for p in box) / 4 / h_img
            size_w = 0.4 + 0.6 * (h / tallest)
            pos_w = 1.0 if (0.1 <= cx <= 0.9 and 0.2 <= cy <= 0.95) else 0.6
            lines.append((text, conf, size_w * pos_w))
        return lines

    @staticmethod
    def text_scores(lines, medicines):
        """lines: [(text, confidence, weight)] from OCR.
        Returns {medicine_id: (score, number of matched letters)}."""
        parsed = []                 # (words, squashed text, weight)
        numbers = set()
        for line in lines:
            text, weight = line[0], (line[2] if len(line) > 2 else 1.0)
            n = _norm(text)
            parsed.append(([w for w in n.split() if len(w) >= 3], n.replace(" ", ""), weight))
            numbers.update(re.findall(r"\d+", n))

        def word_match(tok):
            """Best (similarity x line weight) for one word of the medicine name."""
            if tok.isdigit():
                return 1.0 if tok in numbers else 0.0
            best = 0.0
            for words, squashed, weight in parsed:
                sim = max((SequenceMatcher(None, tok, w).ratio() for w in words), default=0.0)
                if len(tok) >= 4 and tok in squashed:          # "BRUFEN400" contains "brufen"
                    sim = 1.0
                if sim >= 0.84:                                # "lbuprofen" ~ "ibuprofen", not "adol" ~ "avodol"
                    best = max(best, sim * weight)
            return best

        scores = {}
        for m in medicines:
            toks = _tokens(m["brand_name"])
            alpha = [t for t in toks if not t.isdigit()]
            digits = [t for t in toks if t.isdigit()]
            if not alpha:
                continue
            got = {t: word_match(t) for t in alpha}
            total = sum(len(t) for t in alpha)
            score = sum(len(t) * got[t] for t in alpha) / total
            if score < 0.5:
                continue
            for d in digits:                       # "Brufen 600" needs a 600 on the box
                score += 0.05 if word_match(d) else -0.2
            strength_nums = re.findall(r"\d+", m.get("strength") or "")
            if strength_nums and strength_nums[0] in numbers:
                score += 0.05
            ingredient = set(_tokens(m["active_ingredient"]))
            if set(alpha) <= ingredient:          # generic name, e.g. "Paracetamol"
                score *= 0.6                      # weaker than a real brand name on the box
            matched_letters = sum(len(t) for t in alpha if got[t])
            scores[m["id"]] = (max(0.0, min(1.0, score)), matched_letters)
        return scores

    # ---------------------------------------------------------------- main
    def recognize(self, img_bgr, medicines, barcode_lookup, exclude_file=None,
                  use_barcode=True, use_visual=True):
        with self._run_lock:
            return self._recognize(img_bgr, medicines, barcode_lookup, exclude_file, use_barcode, use_visual)

    def _recognize(self, img_bgr, medicines, barcode_lookup, exclude_file, use_barcode, use_visual):
        """medicines: list of medicine dicts.  barcode_lookup(code) -> medicine dict or None."""
        by_id = {m["id"]: m for m in medicines}
        unknown_codes = []

        # 1. Barcode
        if use_barcode:
            for code in read_codes(img_bgr, thorough=True):
                med = barcode_lookup(code)
                if med:
                    return {"found": True, "method": "barcode", "code": code,
                            "candidates": [self._cand(med, 1.0, ["barcode"])], "text": []}
                unknown_codes.append(code)

        # 2. Text (OCR)
        lines = []
        if self.reader:
            lines = self.line_weights(self.reader.read(img_bgr), img_bgr.shape)
        text = self.text_scores(lines, medicines) if lines else {}

        # 3. Visual
        visual, strong = {}, set()
        if LOW_CPU and text:
            ranked_text = sorted((v[0] for v in text.values()), reverse=True)
            if ranked_text[0] >= 0.9 and (len(ranked_text) == 1 or ranked_text[0] - ranked_text[1] >= 0.2):
                use_visual = False          # the name on the box is clear enough
        if self.matcher and use_visual:
            brand_to_id = {m["brand_name"]: m["id"] for m in medicines}
            ranked = [(brand_to_id[b], n) for b, n, _f in self.matcher.match(img_bgr, exclude_file=exclude_file, top=5)
                      if b in brand_to_id]
            for i, (mid, n) in enumerate(ranked):
                visual[mid] = min(1.0, n / VISUAL_FULL)
                runner_up = ranked[1][1] if len(ranked) > 1 else 0
                if i == 0 and n >= VISUAL_ALONE_MIN and n >= VISUAL_ALONE_RATIO * runner_up:
                    strong.add(mid)

        # Combine: the stronger signal counts fully; when both agree the other adds a bonus.
        # A weak visual match never counts alone, only as support for what the text says.
        combined = []
        for mid in set(text) | set(visual):
            t, letters = text.get(mid, (0.0, 0))
            v = visual.get(mid, 0.0) * 0.9        # visual is a little less trusted than reading the name
            alone = v if mid in strong else 0.0
            support = v if (mid in strong or t >= 0.5) else 0.0
            raw = max(t, alone) + 0.25 * min(t, support)
            if raw <= 0:
                continue
            reasons = (["text"] if t >= 0.5 else []) + (["visual"] if (alone or (support and t >= 0.5)) else [])
            combined.append({"raw": raw, "letters": letters, "v": v, "id": mid, "reasons": reasons})
        # Best first; on a tie, the more specific name ("Adol Drops" beats "Adol") and the better photo match win.
        combined.sort(key=lambda c: (-round(c["raw"], 3), -c["letters"], -c["v"]))

        candidates = []
        for i, c in enumerate(combined[:3]):
            if c["raw"] < MIN_SHOWN:
                continue
            score = min(1.0, c["raw"])
            level = "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"
            # Two answers almost equally likely: be honest and lower the top one's confidence.
            if i == 0 and len(combined) > 1 and c["raw"] - combined[1]["raw"] < 0.1 and level == "high":
                level = "medium"
            candidates.append({"medicine": by_id[c["id"]], "score": round(score, 2),
                               "confidence": level, "reasons": c["reasons"]})
        return {
            "found": bool(candidates),
            "method": "photo",
            "candidates": candidates,
            "text": [l[0] for l in lines][:20],     # what the OCR read, shown to the user
            "unknown_codes": unknown_codes,
        }

    @staticmethod
    def _cand(med, score, reasons):
        return {"medicine": med, "score": round(score, 2), "confidence": "high", "reasons": reasons}
