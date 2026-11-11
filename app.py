"""PharmaFind - Flask app.

Phase 1: database + test endpoints
Phase 2: search (typo tolerant, EN/AR/KU), distance sorting, map interface
Phase 3: alternatives (same active ingredient), medicine info
Phase 4: AI scanner - barcode, text reading (OCR) and visual matching of box photos
Phase 5: pharmacist dashboard (pharmacy_routes.py) - login, stock, demand insights
Phase 6: customer accounts (account_routes.py) - phone number + one-time code; PostgreSQL support

Run:  python app.py   then open http://127.0.0.1:5000
"""
import os
import secrets
from datetime import timedelta

import numpy as np
from flask import Flask, jsonify, render_template, abort, request

from models import db, Pharmacy, Medicine, Stock, SearchLog, Barcode, iso_utc
from search import search_medicines, haversine_km, compare_medicines
from seed_data import PHOTO_FOLDERS
from pharmacy_routes import bp as pharmacy_bp
from account_routes import bp as account_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Set to 1 on the live website (the Dockerfile does this). Locally it stays off.
PRODUCTION = os.environ.get("PHARMAFIND_PRODUCTION") == "1"

# Default location when the user doesn't share theirs: central Sulaymaniyah.
DEFAULT_LAT, DEFAULT_LNG = 35.5613, 45.4300

# ---------- AI scanner (Phase 4) ----------
# The AI libraries are optional: if they aren't installed, the rest of the app still works.
try:
    import cv2
    from ai.barcodes import read_codes
    from ai.recognizer import Recognizer
    recognizer = Recognizer(os.path.join(BASE_DIR, "photo"), PHOTO_FOLDERS,
                            os.path.join(BASE_DIR, "instance", "visual_index.pkl"))
    AI_ERROR = None
except ImportError as e:
    recognizer, AI_ERROR = None, f"{e}. Run: pip install -r requirements.txt"


def create_app():
    app = Flask(__name__)
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"], app.config["SQLALCHEMY_ENGINE_OPTIONS"] = database_settings()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.json.ensure_ascii = False  # keep Arabic/Kurdish readable in JSON
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # photo uploads up to 12 MB
    # Logins (pharmacists: Phase 5, customers: Phase 6): sessions are signed with a secret key kept in instance/.
    app.config["SECRET_KEY"] = load_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Customers stay logged in for 30 days (pharmacist logins still end after 12 hours,
    # see PHARMACIST_LOGIN_HOURS in pharmacy_routes.py).
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    if PRODUCTION:
        # The website is https-only. SameSite=None lets the login also work when Hugging Face
        # shows the app inside its own page (an iframe). Forged requests are still blocked by
        # the X-Requested-With header check in pharmacy_routes.py.
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "None"
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    db.init_app(app)
    with app.app_context():
        db.create_all()

    register_routes(app)
    app.register_blueprint(pharmacy_bp)
    app.register_blueprint(account_bp)
    return app


def database_settings():
    """Which database to use, and its connection options.

    On your laptop: nothing to set. It uses the SQLite file instance/pharmafind.db.
    Online: set DATABASE_URL to a PostgreSQL address. Then accounts are kept when the
    website restarts (Render's free plan wipes the SQLite file on every restart).
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        path = os.path.join(BASE_DIR, "instance", "pharmafind.db")
        # Several people at once: wait up to 15 s for the database instead of failing.
        return "sqlite:///" + path, {"connect_args": {"timeout": 15}}
    # Hosts give "postgres://..." or "postgresql://...". Tell SQLAlchemy to use the psycopg 3 driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    # pre_ping: test the connection before using it (free databases close idle connections).
    return url, {"pool_pre_ping": True, "pool_recycle": 280, "pool_size": 5, "max_overflow": 5}


def load_secret_key():
    """A random key made once and saved in instance/secret_key (not in Git).
    On the website it can also come from the SECRET_KEY setting (a Hugging Face "secret")."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(BASE_DIR, "instance", "secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    return key


def get_location():
    """Read ?lat=&lng= from the URL, falling back to the city centre."""
    try:
        lat = float(request.args.get("lat", DEFAULT_LAT))
        lng = float(request.args.get("lng", DEFAULT_LNG))
    except ValueError:
        abort(400, "lat and lng must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        abort(400, "lat/lng out of range")
    return lat, lng


def log_search(query, method, medicine_id, found):
    """Save a search. The user's location (if the page sent it) is rounded to ~100 m
    for privacy; it lets each pharmacy see what people NEAR it are looking for."""
    src = request.form if request.method == "POST" else request.args
    try:
        lat, lng = round(float(src.get("lat")), 3), round(float(src.get("lng")), 3)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            lat = lng = None
    except (TypeError, ValueError):
        lat = lng = None
    db.session.add(SearchLog(query=(query or "")[:200], method=method, medicine_id=medicine_id,
                             found=found, latitude=lat, longitude=lng))
    db.session.commit()


def register_routes(app):
    # ---------- Pages ----------
    @app.route("/")
    def index():
        if recognizer:
            recognizer.warm_up()   # load the AI models in the background
        return render_template("index.html", default_lat=DEFAULT_LAT, default_lng=DEFAULT_LNG)

    @app.route("/share")
    def share():
        """A big QR code of this website's address, to show on a screen or print."""
        return render_template("share.html")

    @app.route("/healthz")
    def healthz():
        """Quick check used by the hosting service to see that the site is up."""
        return jsonify({"ok": True})

    @app.route("/favicon.ico")
    def favicon():
        return app.send_static_file("icons/favicon.png")

    @app.route("/check")
    def check():
        """Phase 1 check page: database counts and medicine table."""
        counts = {
            "pharmacies": Pharmacy.query.count(),
            "medicines": Medicine.query.count(),
            "stock": Stock.query.count(),
        }
        medicines = Medicine.query.order_by(Medicine.active_ingredient, Medicine.brand_name).all()
        return render_template("check.html", counts=counts, medicines=medicines)

    # ---------- API ----------
    @app.route("/api/pharmacies")
    def list_pharmacies():
        return jsonify([p.to_dict() for p in Pharmacy.query.order_by(Pharmacy.name).all()])

    @app.route("/api/medicines")
    def list_medicines():
        return jsonify([m.to_dict() for m in Medicine.query.order_by(Medicine.brand_name).all()])

    @app.route("/api/medicines/<int:medicine_id>")
    def medicine_detail(medicine_id):
        m = db.session.get(Medicine, medicine_id) or abort(404)
        return jsonify(m.to_dict())

    @app.route("/api/search")
    def search():
        """Typo-tolerant medicine search.  /api/search?q=panadl&log=1"""
        q = request.args.get("q", "").strip()[:100]
        if not q:
            return jsonify({"query": q, "results": []})

        matches = search_medicines(q, Medicine.query.all())

        # Only log final searches (when the user presses Enter / picks a result),
        # not every keystroke of the autocomplete.
        if request.args.get("log") == "1":
            log_search(q, "text", matches[0][2].id if matches else None, bool(matches))

        return jsonify({
            "query": q,
            "results": [
                {**m.to_dict(), "score": score, "matched_on": field}
                for score, field, m in matches
            ],
        })

    @app.route("/api/barcode/<code>")
    def barcode_lookup(code):
        """Which medicine has this barcode?  /api/barcode/8002660035349"""
        digits = "".join(ch for ch in code if ch.isdigit())[:64]
        b = Barcode.query.filter_by(code=digits).first() if digits else None
        log_search(digits or code[:64], "barcode", b.medicine_id if b else None, bool(b))
        if not b:
            return jsonify({"code": digits, "found": False}), 404
        return jsonify({"code": digits, "found": True, "kind": b.kind, "medicine": b.medicine.to_dict()})

    # ---------- AI scanner ----------
    def read_upload():
        """Decode the uploaded image (form field 'image') into an OpenCV image."""
        if not recognizer:
            abort(503, AI_ERROR)
        f = request.files.get("image")
        if not f:
            abort(400, "send an image in the 'image' field")
        img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            abort(400, "this file is not an image")
        return img

    def find_by_barcode(code):
        b = Barcode.query.filter_by(code=code).first()
        return b.medicine.to_dict() if b else None

    @app.route("/api/scan/status")
    def scan_status():
        if not recognizer:
            return jsonify({"available": False, "error": AI_ERROR})
        recognizer.warm_up()
        return jsonify({"available": True, **recognizer.status})

    @app.route("/api/scan/frame", methods=["POST"])
    def scan_frame():
        """Fast: look for a barcode in one camera frame (called several times per second)."""
        img = read_upload()
        codes = read_codes(img)
        for code in codes:
            med = find_by_barcode(code)
            if med:
                log_search(code, "barcode", med["id"], True)
                return jsonify({"found": True, "method": "barcode", "code": code, "medicine": med})
        return jsonify({"found": False, "unknown_codes": codes})

    @app.route("/api/scan/photo", methods=["POST"])
    def scan_photo():
        """Full recognition of one photo: barcode, then text (OCR) + visual matching."""
        img = read_upload()
        recognizer.warm_up()
        medicines = [m.to_dict() for m in Medicine.query.all()]
        result = recognizer.recognize(img, medicines, find_by_barcode)
        top = result["candidates"][0] if result["candidates"] else None
        log_search(" ".join(result["text"][:5]) or "(photo)", "photo",
                   top["medicine"]["id"] if top else None, bool(top))
        result["status"] = recognizer.status
        return jsonify(result)

    @app.route("/api/medicines/<int:medicine_id>/pharmacies")
    def pharmacies_for_medicine(medicine_id):
        """Pharmacies that have this medicine, nearest first.
        /api/medicines/1/pharmacies?lat=35.56&lng=45.43&sort=distance|price
        """
        m = db.session.get(Medicine, medicine_id) or abort(404)
        lat, lng = get_location()
        sort = request.args.get("sort", "distance")

        rows = Stock.query.filter_by(medicine_id=m.id).join(Pharmacy).all()

        available, out_of_stock = [], 0
        for s in rows:
            if s.quantity <= 0:
                out_of_stock += 1
                continue
            p = s.pharmacy
            available.append({
                **p.to_dict(),
                "price_iqd": s.price_iqd,
                "quantity": s.quantity,
                "updated_at": iso_utc(s.updated_at),
                "distance_km": round(haversine_km(lat, lng, p.latitude, p.longitude), 2),
            })

        if sort == "price":
            available.sort(key=lambda r: (r["price_iqd"], r["distance_km"]))
        else:
            available.sort(key=lambda r: (r["distance_km"], r["price_iqd"]))

        prices = [r["price_iqd"] for r in available]
        return jsonify({
            "medicine": m.to_dict(),
            "user_location": {"lat": lat, "lng": lng},
            "sort": sort,
            "available_count": len(available),
            "out_of_stock_count": out_of_stock,
            "price_range": {"min": min(prices), "max": max(prices)} if prices else None,
            "pharmacies": available,
        })

    @app.route("/api/medicines/<int:medicine_id>/alternatives")
    def alternatives(medicine_id):
        """Other products with the same active ingredient(s), with nearby availability.
        /api/medicines/12/alternatives?lat=35.56&lng=45.43

        exact   = same ingredients + strength + form  (a direct swap)
        similar = same ingredients, different strength and/or form (ask the pharmacist)
        """
        m = db.session.get(Medicine, medicine_id) or abort(404)
        lat, lng = get_location()

        related = []  # (medicine, relation)
        for other in Medicine.query.all():
            relation = compare_medicines(m, other)
            if relation is not None:
                related.append((other, relation))

        # Availability for all related medicines in one query.
        ids = [o.id for o, _ in related]
        stock = (
            Stock.query.filter(Stock.medicine_id.in_(ids), Stock.quantity > 0).join(Pharmacy).all()
            if ids else []
        )
        by_med = {}
        for s in stock:
            by_med.setdefault(s.medicine_id, []).append(s)

        exact, similar = [], []
        for other, relation in related:
            rows = by_med.get(other.id, [])
            distances = [haversine_km(lat, lng, s.pharmacy.latitude, s.pharmacy.longitude) for s in rows]
            item = {
                **other.to_dict(),
                "available_count": len(rows),
                "nearest_km": round(min(distances), 2) if distances else None,
                "min_price_iqd": min(s.price_iqd for s in rows) if rows else None,
                "differences": [] if relation == "exact" else relation,
            }
            (exact if relation == "exact" else similar).append(item)

        # Available ones first, then nearest, then real photographed boxes, then cheapest.
        def order(i):
            return (i["available_count"] == 0, i["nearest_km"] or 0,
                    not i["from_real_box"], i["min_price_iqd"] or 0)
        exact.sort(key=order)
        similar.sort(key=order)

        return jsonify({
            "medicine": m.to_dict(),
            "exact": exact,
            "similar": similar,
            "available_exact_count": sum(1 for i in exact if i["available_count"]),
        })


app = create_app()

if PRODUCTION and recognizer:
    recognizer.warm_up()   # load the AI as soon as the website starts, not on the first visit

if __name__ == "__main__":
    app.run(debug=True)
