"""Visual matching: "does this camera image look like one of our box photos?"

Computer vision with SIFT features (OpenCV):
  1. Find distinctive points (corners, logo edges, letters) in each reference photo
     in photo/<folder>/ and describe each one with a 128-number "fingerprint".
  2. For a new image, find the same kind of points and match fingerprints
     against every reference photo (Lowe's ratio test removes weak matches).
  3. Check the matches agree on one geometric transform (RANSAC homography),
     because a real box match moves all points together. The number of
     agreeing points ("inliers") is the score.

Works for boxes whose text OCR can't read (Arabic-only fronts), but only for
boxes we photographed. The fingerprints are cached in instance/visual_index.pkl.
"""
import pickle
from pathlib import Path

import cv2
import numpy as np

LONG_SIDE = 640          # images are shrunk to this size first (speed)
REF_FEATURES = 500       # points kept per reference photo
QUERY_FEATURES = 1000    # points kept for the camera image
MIN_INLIERS = 12         # fewer agreeing points than this = no match


def _prepare(img_bgr):
    h, w = img_bgr.shape[:2]
    s = LONG_SIDE / max(h, w)
    if s < 1:
        img_bgr = cv2.resize(img_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)  # even out lighting


class BoxMatcher:
    def __init__(self, photo_dir, folder_to_brand, cache_file):
        self.photo_dir = Path(photo_dir)
        self.folder_to_brand = folder_to_brand
        self.cache_file = Path(cache_file)
        self.sift_ref = cv2.SIFT_create(nfeatures=REF_FEATURES)
        self.sift_query = cv2.SIFT_create(nfeatures=QUERY_FEATURES)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.refs = self._load_or_build()

    @property
    def ready(self):
        return len(self.refs) > 0

    def _photo_files(self):
        files = []
        if not self.photo_dir.is_dir():
            return files
        for folder in sorted(self.photo_dir.iterdir()):
            brand = self.folder_to_brand.get(folder.name)
            if not folder.is_dir() or not brand:
                continue
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    files.append((brand, f))
        return files

    def _load_or_build(self):
        files = self._photo_files()
        signature = [(str(f), f.stat().st_mtime, f.stat().st_size, b) for b, f in files]
        if self.cache_file.exists():
            try:
                cached = pickle.loads(self.cache_file.read_bytes())
                if cached["signature"] == signature:
                    return cached["refs"]
            except Exception:
                pass  # broken cache: rebuild
        refs = []
        for brand, f in files:
            img = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)  # works with non-ASCII paths
            if img is None:
                continue
            gray = _prepare(img)
            # Ignore the top quarter: in our photos it shows other boxes on the counter.
            mask = np.zeros_like(gray)
            mask[int(gray.shape[0] * 0.25):, :] = 255
            kps, desc = self.sift_ref.detectAndCompute(gray, mask)
            if desc is None or len(kps) < 10:
                continue
            refs.append({"brand": brand, "file": f"{f.parent.name}/{f.name}",
                         "pts": np.float32([k.pt for k in kps]), "desc": desc})
        refs = self._remove_background(refs)
        for r in refs:   # SIFT values are whole numbers 0-255: store as bytes (4x less memory)
            r["desc"] = np.clip(np.rint(r["desc"]), 0, 255).astype(np.uint8)
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_bytes(pickle.dumps({"signature": signature, "refs": refs}))
        except OSError:
            pass
        return refs

    def _remove_background(self, refs):
        """All our photos share the same counter, pen, hand and light reflections.
        Points that also match a photo of a DIFFERENT medicine are background,
        not the box, so we delete them. (Runs once, then the result is cached.)"""
        drop = [np.zeros(len(r["pts"]), bool) for r in refs]
        for i, a in enumerate(refs):
            for b in refs:
                if b["brand"] == a["brand"]:
                    continue
                inl, idx = self._inliers(a["desc"], a["pts"], b)
                if inl is not None and inl.sum() >= 6:
                    drop[i][idx[inl]] = True
        cleaned = []
        for r, d in zip(refs, drop):
            keep = ~d
            if keep.sum() >= 15:
                cleaned.append({**r, "pts": r["pts"][keep], "desc": r["desc"][keep]})
        return cleaned

    def _inliers(self, desc, pts, ref, ratio=0.75):
        """Match descriptors against one reference; return (inlier mask, query indexes)."""
        ref_desc = ref["desc"] if ref["desc"].dtype == np.float32 else ref["desc"].astype(np.float32)
        pairs = self.matcher.knnMatch(desc, ref_desc, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < ratio * n.distance]
        if len(good) < 6:
            return None, None
        qi = np.array([m.queryIdx for m in good])
        src = pts[qi]
        dst = ref["pts"][[m.trainIdx for m in good]]
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
        if inl is None:
            return None, None
        return inl.ravel().astype(bool), qi

    def match(self, img_bgr, exclude_file=None, top=3):
        """Return [(brand, inliers, reference_file)] best first, one entry per brand."""
        if not self.refs:
            return []
        gray = _prepare(img_bgr)
        kps, desc = self.sift_query.detectAndCompute(gray, None)
        if desc is None or len(kps) < 10:
            return []
        qpts = np.float32([k.pt for k in kps])

        best = {}  # brand -> (inliers, file)
        for ref in self.refs:
            if exclude_file and ref["file"] == exclude_file:
                continue
            inl, _ = self._inliers(desc, qpts, ref)
            n = int(inl.sum()) if inl is not None else 0
            if n >= MIN_INLIERS and n > best.get(ref["brand"], (0, None))[0]:
                best[ref["brand"]] = (n, ref["file"])
        ranked = sorted(((b, n, f) for b, (n, f) in best.items()), key=lambda r: -r[1])
        return ranked[:top]
