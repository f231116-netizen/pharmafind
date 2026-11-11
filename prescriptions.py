"""Phase 8 - Prescription photos: clean them, fingerprint them, and spot re-use.

The app can't prove a prescription is real; the pharmacist decides. This file only helps:
  - process_photo(): checks it is a real photo, makes it smaller, and saves it again as JPEG.
    Saving it again also removes the hidden information phones put inside photos (EXIF:
    GPS location, phone model, time).
  - Two fingerprints of each photo:
      photo_sha256 - exact: the same file sent again -> blocked straight away
      photo_dhash  - "looks the same": the same photo re-saved or resized -> the pharmacist is warned
  - same_paper_used(): one prescription = one use. Same customer + same doctor + same date,
    already confirmed or collected somewhere -> the pharmacist can't approve it again.
"""
import hashlib
from datetime import timedelta

import numpy as np

from models import Order, Prescription, utcnow
from search import normalize

try:
    import cv2
except ImportError:          # the AI libraries are optional for the rest of the app
    cv2 = None

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB (the page makes photos smaller before sending)
MAX_SIDE = 1600                       # stored photo: at most 1600 px on the long side
MIN_SIDE = 500                        # smaller than this is too blurry to read a prescription
JPEG_QUALITY = 82
SIMILAR_BITS = 6                      # dHash: 6 or fewer different bits out of 64 = "looks the same"
SIMILAR_DAYS = 180                    # compare with prescriptions from the last 6 months
# A reservation in one of these states has "used" its prescription (open, or medicine handed over).
# Cancelled or expired ones haven't: no medicine was given, so the paper can be used again.
USED_STATUSES = ("pending", "confirmed", "ready", "out_for_delivery", "picked_up", "delivered")
APPROVED_USED = ("confirmed", "ready", "out_for_delivery", "picked_up", "delivered")

# Words that are not part of the doctor's name ("Dr. Karwan" = "Karwan").
_TITLES = {normalize(w) for w in ("dr", "doctor", "prof", "د", "دكتور", "الدكتور", "دكتورة", "دکتۆر", "پزیشک")}


class PhotoError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def dhash(img):
    """64-bit "difference hash": shrink to 9x8 grey pixels and note where it gets brighter.
    Re-saving or resizing a photo hardly changes it; a different photo changes many bits."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def dhash_distance(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def process_photo(raw):
    """Uploaded bytes -> (clean JPEG bytes, sha256, dhash). Raises PhotoError(code) if it's not usable."""
    if not raw:
        raise PhotoError("prescription_required")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PhotoError("photo_too_big")
    if cv2 is None:
        raise PhotoError("photo_unavailable")
    # IMREAD_COLOR also turns phone photos the right way up (it reads the EXIF orientation).
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PhotoError("not_a_photo")
    h, w = img.shape[:2]
    if min(h, w) < MIN_SIDE:
        raise PhotoError("photo_too_small")
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise PhotoError("not_a_photo")
    return jpeg.tobytes(), hashlib.sha256(raw).hexdigest(), dhash(img)


def doctor_key(name):
    """'Dr. Karwan  Ahmed' and 'karwan ahmed' -> the same key, to compare doctors."""
    words = [w for w in normalize(name).split() if w not in _TITLES]
    return " ".join(words)[:80]


def exact_copy_in_use(sha256):
    """The very same photo file is in an open or collected reservation -> the Prescription, else None."""
    return (Prescription.query.join(Order)
            .filter(Prescription.photo_sha256 == sha256, Order.status.in_(USED_STATUSES))
            .first())


def similar_in_use(dh, exclude_order_id=None):
    """A photo that looks the same (re-saved/resized) -> its order id, else None. Only a warning:
    prescriptions from the same doctor's pad look alike, so the pharmacist decides."""
    since = utcnow() - timedelta(days=SIMILAR_DAYS)
    rows = (Prescription.query.join(Order)
            .filter(Prescription.photo_dhash.isnot(None), Prescription.created_at >= since,
                    Order.status.in_(USED_STATUSES))
            .with_entities(Prescription.order_id, Prescription.photo_dhash).all())
    for order_id, other in rows:
        if order_id != exclude_order_id and dhash_distance(dh, other) <= SIMILAR_BITS:
            return order_id
    return None


def same_paper_used(rx, key, issued_on):
    """One prescription = one use: same customer, same doctor, same date, already approved for a
    reservation that is confirmed, ready or collected -> that Prescription, else None."""
    return (Prescription.query.join(Order)
            .filter(Prescription.id != rx.id, Prescription.user_id == rx.user_id,
                    Prescription.status == "approved", Prescription.doctor_key == key,
                    Prescription.issued_on == issued_on,
                    Order.status.in_(APPROVED_USED))
            .first())
