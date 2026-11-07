"""Measure how well PharmaFind recognizes the box photos in photo/.

Run:  python evaluate.py
      python evaluate.py --photos path/to/other/photos

For each photo it runs the real recognizer and checks the top answer.
Visual matching is "leave-one-out": the photo being tested is removed from the
reference set, so the app can't simply recognize the identical picture.
(Photos taken seconds apart look very similar, so real-life accuracy with a
new camera and background can be lower. Test with a webcam too.)
"""
import argparse
import os
import time
from collections import defaultdict

import cv2
import numpy as np

from app import create_app, BASE_DIR
from models import Medicine, Barcode
from seed_data import PHOTO_FOLDERS
from ai.recognizer import Recognizer


MODES = (
    ("full (barcode + text + visual)", True, True),
    ("box front only (text + visual)", False, True),
    ("reading the name only (OCR)", False, False),   # like a box we never photographed
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", default=os.path.join(BASE_DIR, "photo"))
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        medicines = [m.to_dict() for m in Medicine.query.all()]
        codes = {b.code: b.medicine.to_dict() for b in Barcode.query.all()}

    rec = Recognizer(args.photos, PHOTO_FOLDERS, os.path.join(BASE_DIR, "instance", "visual_index.pkl"))
    print("Loading models and building the visual index...")
    rec._load()
    print("  OCR:", rec.status["ocr"], "| visual:", rec.status["visual"])

    files = []
    for folder in sorted(os.listdir(args.photos)):
        brand = PHOTO_FOLDERS.get(folder)
        path = os.path.join(args.photos, folder)
        if brand and os.path.isdir(path):
            files += [(brand, folder, f) for f in sorted(os.listdir(path))
                      if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]

    stats = defaultdict(lambda: [0, 0])          # name -> [correct, total]
    by_method = defaultdict(int)
    mistakes = []
    times = []
    for brand, folder, f in files:
        img = cv2.imdecode(np.fromfile(os.path.join(args.photos, folder, f), np.uint8), cv2.IMREAD_COLOR)
        key = f"{folder}/{f}"
        for mode, use_bc, use_vis in MODES:
            t = time.time()
            r = rec.recognize(img, medicines, codes.get, exclude_file=key, use_barcode=use_bc, use_visual=use_vis)
            if use_bc and use_vis:
                times.append(time.time() - t)
            top = r["candidates"][0]["medicine"]["brand_name"] if r["candidates"] else None
            ok = top == brand
            stats[mode][0] += ok
            stats[mode][1] += 1
            if use_bc and use_vis:
                stats[brand][0] += ok
                stats[brand][1] += 1
                by_method[r["method"] if ok else "wrong / not found"] += 1
                if not ok:
                    mistakes.append((key, brand, top))

    print(f"\nTested {len(files)} photos of {len({b for b, _, _ in files})} medicines "
          f"(average {np.mean(times):.2f} s per photo)\n")
    for mode, _, _ in MODES:
        c, n = stats[mode]
        print(f"  {mode:34} {c}/{n} correct = {c / n:.0%}")
    print("\n  Solved by: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_method.items())))
    print("\nPer medicine (full):")
    for brand in sorted({b for b, _, _ in files}):
        c, n = stats[brand]
        print(f"  {brand:26} {c}/{n}")
    if mistakes:
        print("\nMistakes:")
        for key, truth, got in mistakes:
            print(f"  {key}: expected {truth}, got {got or 'nothing'}")


if __name__ == "__main__":
    main()
