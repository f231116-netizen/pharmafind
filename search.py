"""Search helpers for PharmaFind (Phase 2).

- normalize():  makes spelling differences not matter (case, Arabic/Kurdish letter variants)
- score_medicine(): how well a query matches a medicine (0-100), typo tolerant
- search_medicines(): ranked list of matching medicines
- haversine_km(): distance between two GPS points
"""
import math
import re
import unicodedata
from difflib import SequenceMatcher

# Arabic and Kurdish (Sorani) letters that people type in different ways.
# Everything is mapped to one form so "كوزار" and "کۆزار" can match.
LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ة": "ه", "ە": "ه", "ھ": "ه",
    "ى": "ي", "ی": "ي", "ێ": "ي", "ې": "ي",
    "ك": "ك", "ک": "ك", "گ": "ك",
    "ۆ": "و", "ۊ": "و", "ؤ": "و",
    "ڵ": "ل", "ڕ": "ر", "ڤ": "ف", "پ": "ب", "چ": "ج", "ژ": "ز",
    "ئ": "", "ء": "", "ـ": "",
})

MIN_SCORE = 60  # below this, a result is not shown


def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    # remove Arabic diacritics (harakat)
    text = re.sub(r"[ً-ْٰ]", "", text)
    text = text.translate(LETTER_MAP)
    # keep letters, digits and spaces only
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(q, name):
    """Score 0-100 between a normalized query and a normalized name."""
    if not q or not name:
        return 0
    if q == name:
        return 100
    if name.startswith(q):
        return 92 if len(q) >= 3 else 70
    if q in name:
        return 85 if len(q) >= 3 else 60
    # typo tolerance: compare against the full name and against each word
    best = SequenceMatcher(None, q, name).ratio()
    for word in name.split():
        best = max(best, SequenceMatcher(None, q, word).ratio())
    return round(best * 100)


def score_medicine(query, medicine):
    """Return (score, field_that_matched)."""
    q = normalize(query)
    fields = {
        "brand": medicine.brand_name,
        "arabic": medicine.name_ar,
        "kurdish": medicine.name_ku,
        "ingredient": medicine.active_ingredient,
    }
    best_score, best_field = 0, None
    for field, value in fields.items():
        s = _similarity(q, normalize(value))
        # a brand-name hit should rank above an ingredient hit with the same score
        if field != "ingredient":
            s += 1
        if s > best_score:
            best_score, best_field = s, field
    return min(best_score, 100), best_field


def search_medicines(query, medicines, limit=8):
    """Rank all medicines against the query. Fine for a few hundred medicines."""
    if not normalize(query):
        return []
    results = []
    for m in medicines:
        score, field = score_medicine(query, m)
        if score >= MIN_SCORE:
            results.append((score, field, m))
    results.sort(key=lambda r: (-r[0], r[2].brand_name))
    return results[:limit]


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in kilometres between two (lat, lng) points."""
    r = 6371.0  # Earth radius in km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------- Alternatives (Phase 3) ----------------

def ingredient_key(active_ingredient):
    """'Amoxicillin + Clavulanic acid' -> frozenset({'amoxicillin', 'clavulanic acid'}).
    Order and capitalisation don't matter; combinations must match exactly."""
    parts = re.split(r"\s*\+\s*|\s*/\s*|\s*,\s*", active_ingredient or "")
    return frozenset(normalize(p) for p in parts if p.strip())


def strength_key(strength):
    """'500 mg' and '500mg' are the same strength."""
    return re.sub(r"\s+", "", (strength or "").lower())


def compare_medicines(a, b):
    """How medicine b relates to medicine a.
    Returns None (unrelated), 'exact' (same ingredients, strength and form),
    or a list of differences like ['strength'] / ['form'] / ['strength', 'form']."""
    if a.id == b.id or ingredient_key(a.active_ingredient) != ingredient_key(b.active_ingredient):
        return None
    diffs = []
    if strength_key(a.strength) != strength_key(b.strength):
        diffs.append("strength")
    if normalize(a.form) != normalize(b.form):
        diffs.append("form")
    return "exact" if not diffs else diffs
