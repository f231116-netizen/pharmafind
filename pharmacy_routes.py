"""Phase 5 - Pharmacist dashboard.

Pages:  /pharmacy                      login + dashboard (static/pharmacy.js draws it)
API:    POST /api/pharmacy/login        {username, password}
        POST /api/pharmacy/logout
        GET  /api/pharmacy/me
        GET  /api/pharmacy/stock         this pharmacy's stock + the city's average price
        PUT  /api/pharmacy/stock/<id>    {price_iqd, quantity}  (adds the medicine if new)
        DELETE /api/pharmacy/stock/<id>  stop selling a medicine
        GET  /api/pharmacy/insights?days=7&radius=3   what people near you search for

Security: passwords are stored hashed; the login is a signed session cookie (SameSite=Lax);
requests that change data must send the header "X-Requested-With: fetch" (blocks
forged cross-site form posts); all queries only touch the logged-in pharmacy's rows.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, session, abort

from models import db, Pharmacy, Medicine, Stock, SearchLog
from search import haversine_km, normalize

bp = Blueprint("pharmacy", __name__)

LOCAL_TZ = timezone(timedelta(hours=3))   # Iraq: UTC+3, no daylight saving
LOW_STOCK = 5                             # this many boxes or fewer = "low stock"


def current_pharmacy():
    pid = session.get("pharmacy_id")
    return db.session.get(Pharmacy, pid) if pid else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method not in ("GET", "HEAD") and request.headers.get("X-Requested-With") != "fetch":
            abort(400, "missing X-Requested-With header")
        ph = current_pharmacy()
        if not ph:
            return jsonify({"error": "not_logged_in"}), 401
        return view(ph, *args, **kwargs)
    return wrapper


def stock_status(row):
    if row is None:
        return "not_carried"
    if row.quantity <= 0:
        return "out"
    return "low" if row.quantity <= LOW_STOCK else "ok"


def as_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ---------------------------------------------------------------- pages
@bp.route("/pharmacy")
def dashboard_page():
    return render_template("pharmacy.html")


# ---------------------------------------------------------------- login
@bp.route("/api/pharmacy/login", methods=["POST"])
def login():
    if request.headers.get("X-Requested-With") != "fetch":
        abort(400)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()[:40]
    password = str(data.get("password", ""))[:200]
    ph = Pharmacy.query.filter_by(username=username).first() if username else None
    if not ph or not ph.check_password(password):
        return jsonify({"error": "wrong_login"}), 401
    session.clear()
    session["pharmacy_id"] = ph.id
    session.permanent = True
    return jsonify({"pharmacy": ph.to_dict()})


@bp.route("/api/pharmacy/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/pharmacy/me")
@login_required
def me(ph):
    return jsonify({"pharmacy": ph.to_dict(), "username": ph.username})


# ---------------------------------------------------------------- stock
def city_prices():
    """medicine_id -> (average price, lowest price) over pharmacies that have it in stock.
    If it's sold out everywhere, use every pharmacy that lists it."""
    in_stock, listed = defaultdict(list), defaultdict(list)
    for mid, price, qty in db.session.query(Stock.medicine_id, Stock.price_iqd, Stock.quantity):
        listed[mid].append(price)
        if qty > 0:
            in_stock[mid].append(price)
    return {mid: (round(sum(p) / len(p), -2), min(p))
            for mid, p in ((m, in_stock.get(m) or listed[m]) for m in listed)}


def stock_row(row, prices):
    avg, low = prices.get(row.medicine_id, (None, None))
    return {
        "medicine": row.medicine.to_dict(),
        "price_iqd": row.price_iqd,
        "quantity": row.quantity,
        "status": stock_status(row),
        "updated_at": row.to_dict()["updated_at"],
        "city_avg_price": avg,
        "city_min_price": low,
    }


@bp.route("/api/pharmacy/stock")
@login_required
def list_stock(ph):
    prices = city_prices()
    rows = Stock.query.filter_by(pharmacy_id=ph.id).join(Medicine).order_by(Medicine.brand_name).all()
    return jsonify({"stock": [stock_row(r, prices) for r in rows], "low_stock_limit": LOW_STOCK,
                    "city_prices": {mid: avg for mid, (avg, _low) in prices.items()}})


@bp.route("/api/pharmacy/stock/<int:medicine_id>", methods=["PUT"])
@login_required
def update_stock(ph, medicine_id):
    med = db.session.get(Medicine, medicine_id) or abort(404)
    data = request.get_json(silent=True) or {}
    row = Stock.query.filter_by(pharmacy_id=ph.id, medicine_id=med.id).first()
    try:
        price = int(data["price_iqd"]) if "price_iqd" in data else (row.price_iqd if row else None)
        qty = int(data["quantity"]) if "quantity" in data else (row.quantity if row else 0)
    except (TypeError, ValueError):
        return jsonify({"error": "numbers_only"}), 400
    if price is None:
        return jsonify({"error": "price_required"}), 400
    if not (0 < price <= 10_000_000) or not (0 <= qty <= 100_000):
        return jsonify({"error": "out_of_range"}), 400
    if row is None:
        row = Stock(pharmacy_id=ph.id, medicine_id=med.id, price_iqd=price, quantity=qty)
        db.session.add(row)
    else:
        row.price_iqd, row.quantity = price, qty
        row.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"row": stock_row(row, city_prices())})


@bp.route("/api/pharmacy/stock/<int:medicine_id>", methods=["DELETE"])
@login_required
def remove_stock(ph, medicine_id):
    row = Stock.query.filter_by(pharmacy_id=ph.id, medicine_id=medicine_id).first() or abort(404)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- insights
@bp.route("/api/pharmacy/insights")
@login_required
def insights(ph):
    try:
        days = min(max(int(request.args.get("days", 7)), 1), 60)
        radius = min(max(float(request.args.get("radius", 3)), 0.5), 50)
    except ValueError:
        abort(400)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    # (SearchLog has a column called "query", so we use db.select instead of SearchLog.query)
    logs = db.session.execute(
        db.select(SearchLog).where(SearchLog.created_at >= since.replace(tzinfo=None))).scalars().all()

    near = [l for l in logs if l.latitude is not None
            and haversine_km(ph.latitude, ph.longitude, l.latitude, l.longitude) <= radius]

    my_rows = {r.medicine_id: r for r in Stock.query.filter_by(pharmacy_id=ph.id).all()}
    prices = city_prices()
    meds = {m.id: m for m in Medicine.query.all()}

    # Searches per day (local time), oldest first, including days with zero searches.
    per_day = Counter(as_utc(l.created_at).astimezone(LOCAL_TZ).date() for l in near)
    today = now.astimezone(LOCAL_TZ).date()
    daily = [{"date": (today - timedelta(days=i)).isoformat(), "count": per_day.get(today - timedelta(days=i), 0)}
             for i in range(days - 1, -1, -1)]

    # Most searched medicines near this pharmacy, and whether it has them.
    counts = Counter(l.medicine_id for l in near if l.found and l.medicine_id)
    top = []
    for mid, n in counts.most_common(20):
        row = my_rows.get(mid)
        top.append({
            "medicine": meds[mid].to_dict(),
            "searches": n,
            "status": stock_status(row),
            "quantity": row.quantity if row else None,
            "price_iqd": row.price_iqd if row else None,
            "city_avg_price": prices.get(mid, (None,))[0],
        })
    missed = [t for t in top if t["status"] in ("out", "not_carried")][:5]

    # What people want that isn't in PharmaFind at all (whole city).
    nf = Counter()
    label = {}
    for l in logs:
        if not l.found and l.method == "text" and l.query:
            key = normalize(l.query)
            nf[key] += 1
            label.setdefault(key, l.query)
    not_found = [{"query": label[k], "searches": n} for k, n in nf.most_common(6)]

    low = sorted((r for r in my_rows.values() if 0 < r.quantity <= LOW_STOCK), key=lambda r: r.quantity)
    methods = Counter(l.method for l in near)

    return jsonify({
        "days": days, "radius_km": radius,
        "kpis": {
            "searches_near": len(near),
            "in_stock": sum(1 for r in my_rows.values() if r.quantity > 0),
            "low_stock": len(low),
            "out_of_stock": sum(1 for r in my_rows.values() if r.quantity <= 0),
            "scanner_share": round(100 * (methods["barcode"] + methods["photo"]) / len(near)) if near else 0,
        },
        "methods": {k: methods.get(k, 0) for k in ("text", "barcode", "photo")},
        "daily": daily,
        "top": top[:8],
        "missed": missed,
        "not_found": not_found,
        "low_stock": [{"medicine": meds[r.medicine_id].to_dict(), "quantity": r.quantity,
                       "price_iqd": r.price_iqd} for r in low[:8]],
    })
