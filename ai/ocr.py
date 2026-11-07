"""Text reading (OCR) for medicine boxes.

Uses the PP-OCRv3 deep-learning models (from PaddleOCR / RapidOCR, Apache-2.0),
run with OpenCV's DNN module, so it only needs opencv + numpy (works on Python 3.15).

Two neural networks:
  1. detector   - finds WHERE the text is (a "probability map" of text pixels)
  2. recognizer - reads WHAT each piece of text says (CRNN + CTC decoding)

Reads Latin letters and digits well. It does not read Arabic/Kurdish script.
"""
import math
import os
from pathlib import Path

import cv2
import numpy as np

MODELS = Path(__file__).resolve().parent / "models"
# Longest side of the image the text detector looks at. Smaller = faster and less memory
# (used on small servers, e.g. Render's free plan: PHARMAFIND_LOW_CPU=1).
MAX_SIDE = 960 if os.environ.get("PHARMAFIND_LOW_CPU") == "1" else 1280


class TextReader:
    def __init__(self):
        self.det = cv2.dnn.readNetFromONNX(str(MODELS / "ch_PP-OCRv3_det_infer.onnx"))
        self.rec = cv2.dnn.readNetFromONNX(str(MODELS / "ch_PP-OCRv3_rec_infer.onnx"))
        chars = (MODELS / "ppocr_keys.txt").read_text(encoding="utf-8").splitlines()
        self.charset = ["<blank>"] + chars + [" "]   # index 0 = CTC blank

    # ------------------------------------------------------------ public
    def read(self, img_bgr, min_score=0.5):
        """Return a list of (text, confidence, box) found in a BGR image."""
        boxes = self._detect(img_bgr)
        # top-to-bottom, left-to-right, like reading a page
        boxes = sorted(boxes, key=lambda b: (b[0][1], b[0][0]))
        results = []
        for box in boxes:
            crop = self._crop(img_bgr, box)
            if crop is None:
                continue
            text, conf = self._recognize(crop)
            if text.strip() and conf >= min_score:
                results.append((text.strip(), float(conf), box.tolist()))
        return results

    # ------------------------------------------------------------ detection
    def _detect(self, img, limit_side=736, thresh=0.3, box_thresh=0.5, unclip_ratio=1.6):
        h, w = img.shape[:2]
        # Resize so the short side is at least 736 px, both sides multiples of 32.
        ratio = limit_side / min(h, w) if min(h, w) < limit_side else 1.0
        # ...and never more than MAX_SIDE px on the long side (keeps it fast).
        ratio = min(ratio, MAX_SIDE / max(h, w)) if max(h, w) * ratio > MAX_SIDE else ratio
        rh = max(32, int(round(h * ratio / 32) * 32))
        rw = max(32, int(round(w * ratio / 32) * 32))
        x = cv2.resize(img, (rw, rh)).astype(np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        self.det.setInput(x.transpose(2, 0, 1)[None])
        pred = self.det.forward()[0, 0]                      # (rh, rw) text probability

        mask = cv2.dilate((pred > thresh).astype(np.uint8), np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(mask * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours[:1000]:
            rect = cv2.minAreaRect(c)
            if min(rect[1]) < 3:
                continue
            if self._box_score(pred, cv2.boxPoints(rect)) < box_thresh:
                continue
            # "unclip": grow the box, because the detector predicts a shrunk text region
            (cx, cy), (bw, bh), ang = rect
            d = (bw * bh) * unclip_ratio / (2 * (bw + bh))
            grown = ((cx, cy), (bw + 2 * d, bh + 2 * d), ang)
            if min(grown[1]) < 5:
                continue
            pts = self._order(cv2.boxPoints(grown))
            pts[:, 0] = np.clip(np.round(pts[:, 0] / rw * w), 0, w)
            pts[:, 1] = np.clip(np.round(pts[:, 1] / rh * h), 0, h)
            boxes.append(pts.astype(np.float32))
        return boxes

    @staticmethod
    def _box_score(pred, pts):
        h, w = pred.shape
        x0, x1 = np.clip([int(np.floor(pts[:, 0].min())), int(np.ceil(pts[:, 0].max()))], 0, w - 1)
        y0, y1 = np.clip([int(np.floor(pts[:, 1].min())), int(np.ceil(pts[:, 1].max()))], 0, h - 1)
        m = np.zeros((y1 - y0 + 1, x1 - x0 + 1), np.uint8)
        cv2.fillPoly(m, [(pts - [x0, y0]).astype(np.int32)], 1)
        return cv2.mean(pred[y0:y1 + 1, x0:x1 + 1], m)[0]

    @staticmethod
    def _order(pts):
        """Order 4 corners as top-left, top-right, bottom-right, bottom-left."""
        pts = sorted(pts.tolist(), key=lambda p: p[0])
        left = sorted(pts[:2], key=lambda p: p[1])
        right = sorted(pts[2:], key=lambda p: p[1])
        return np.array([left[0], right[0], right[1], left[1]], np.float32)

    # ------------------------------------------------------------ recognition
    @staticmethod
    def _crop(img, pts):
        w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
        h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
        if w < 4 or h < 4:
            return None
        M = cv2.getPerspectiveTransform(pts, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
        crop = cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)
        if h / w >= 1.5:           # vertical text on the side of a box
            crop = np.rot90(crop)
        return crop

    def _recognize(self, crop, height=48):
        h, w = crop.shape[:2]
        ratio = w / h
        img_w = int(height * max(320 / 48, ratio))
        new_w = min(img_w, int(math.ceil(height * ratio)))
        x = cv2.resize(crop, (new_w, height)).astype(np.float32).transpose(2, 0, 1) / 255.0
        x = (x - 0.5) / 0.5
        padded = np.zeros((3, height, img_w), np.float32)
        padded[:, :, :new_w] = x
        self.rec.setInput(padded[None])
        probs = self.rec.forward()[0]                        # (time steps, classes)
        idx, p = probs.argmax(1), probs.max(1)
        chars, confs, prev = [], [], -1
        for i, k in enumerate(idx):                         # CTC greedy decoding
            if k != 0 and k != prev:
                chars.append(self.charset[k])
                confs.append(p[i])
            prev = k
        return "".join(chars), (float(np.mean(confs)) if confs else 0.0)
