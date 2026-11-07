"""Barcode reading with zxing-cpp (EAN-13, Code 128, QR, GS1 DataMatrix...)."""
import re

import cv2
import numpy as np
import zxingcpp


def _gtin_to_ean13(text):
    """GS1 DataMatrix codes contain '(01)' + a 14-digit GTIN; the box's EAN-13 is that minus the leading 0."""
    m = re.search(r"(?:\(01\)|^01)(\d{14})", text)
    if m and m.group(1).startswith("0"):
        return m.group(1)[1:]
    return None


def read_codes(img_bgr, thorough=False):
    """Return a list of product codes (digits only) found in the image, best first.

    thorough=False: one quick pass (for live camera frames, several per second).
    thorough=True:  also tries an enlarged, sharpened copy (for single photos).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    variants = [gray]
    if thorough:
        big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        sharp = cv2.addWeighted(big, 1.8, cv2.GaussianBlur(big, (0, 0), 3), -0.8, 0)
        variants += [big, sharp]

    codes = []
    for v in variants:
        for r in zxingcpp.read_barcodes(v):
            if not r.valid:
                continue
            text = r.text.strip()
            fmt = r.format.name
            gtin = _gtin_to_ean13(text)
            if gtin:
                code = gtin
            elif fmt in ("EAN13", "EAN8", "UPCA", "UPCE", "Code128", "ITF") and text.isdigit():
                code = text
            else:
                continue  # QR codes with web links (e.g. the KMCA price sticker) are not product codes
            if code not in codes:
                codes.append(code)
        if codes:
            break
    return codes
