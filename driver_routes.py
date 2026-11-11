"""Phase 9 - Delivery drivers (like Talabat riders). Payment is cash at the door.

Page:  /driver                                  login + jobs (static/driver.js draws it)
API:   POST /api/driver/login                   {username, password}
       POST /api/driver/logout
       GET  /api/driver/me
       GET  /api/driver/jobs                    jobs waiting for a driver + my jobs
       POST /api/driver/jobs/<id>/take          take a job (first driver wins)
       POST /api/driver/jobs/<id>/release       give a job back (only before the pharmacy hands it over)
       POST /api/driver/jobs/<id>/delivered     {code, cash_collected: true, paper_collected: true}
       POST /api/driver/jobs/<id>/failed        {reason}: couldn't deliver, the bag goes back

How a delivery goes:
  1. The pharmacy confirms (and checks the prescription photo, Phase 8) and packs it.
  2. A driver sees the job (pharmacy, distance, fee; NOT the customer's details yet) and takes it.
  3. Only then the driver sees the customer's name, phone and address.
  4. The pharmacist presses "Given to the driver" -> out for delivery.
  5. At the door the driver: types the customer's 4-digit code (proves it's the right person),
     for prescription medicines checks the ORIGINAL paper matches (doctor, date, patient) and takes it,
     collects the cash -> delivered. Or reports why it couldn't be delivered -> cancelled, boxes go back.

The driver never sees the prescription photo (health information): only the doctor's name, date and
patient's name that the pharmacist wrote down, which is enough to check the paper.
"""
import hmac
from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, jsonify, render_template, request, session

from account_routes import local_format, only_digits
from models import db, Driver, Order, utcnow
from order_routes import drop_photo, error, expire_old_orders, return_stock

bp = Blueprint("driver", __name__)

MAX_ACTIVE_JOBS = 3              # a driver can carry at most this many jobs at once
FAIL_REASONS = ("not_home", "no_paper", "refused", "other")
TAKEABLE = ("confirmed", "ready")   # a job can be taken while the pharmacy packs it, or once it's packed


def current_driver():
    did = session.get("driver_id")
    driver = db.session.get(Driver, did) if did else None
    return driver if driver and driver.active else None


def driver_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method not in ("GET", "HEAD") and request.headers.get("X-Requested-With") != "fetch":
            abort(400, "missing X-Requested-With header")
        driver = current_driver()
        if not driver:
            return jsonify({"error": "not_logged_in"}), 401
        return view(driver, *args, **kwargs)
    return wrapper


def job_summary(o):
    """A job waiting for a driver: NO customer details yet (privacy)."""
    p = o.pharmacy
    return {
        "id": o.id,
        "status": o.status,
        "pharmacy": {"name": p.name, "address": p.address, "latitude": p.latitude, "longitude": p.longitude},
        "delivery_km": o.delivery_km,
        "delivery_fee_iqd": o.delivery_fee_iqd or 0,
        "grand_total_iqd": o.total_iqd + (o.delivery_fee_iqd or 0),
        "boxes": sum(i.quantity for i in o.items),
        "has_prescription": o.prescription is not None,
        "created_at": o.to_dict()["created_at"],
    }


def job_details(o):
    """A job this driver took: everything needed to fetch it and hand it over."""
    data = job_summary(o)
    p, u, rx = o.pharmacy, o.user, o.prescription
    data.update({
        "pharmacy": p.to_dict(),
        "customer": {"name": u.name, "phone": u.phone, "phone_display": local_format(u.phone)},
        "address": o.address,
        "delivery_lat": o.delivery_lat,
        "delivery_lng": o.delivery_lng,
        "items": [{"name": i.medicine.brand_name, "strength": i.medicine.strength, "quantity": i.quantity}
                  for i in o.items],
        # What the driver checks on the original paper (never the photo itself).
        "prescription": ({"doctor_name": rx.doctor_name, "issued_on": rx.issued_on.isoformat() if rx.issued_on else None,
                          "patient": u.name} if rx else None),
        "closed_at": o.to_dict()["closed_at"],
        "cancel_reason": o.cancel_reason,
    })
    return data


def my_job(driver, order_id):
    order = db.session.get(Order, order_id)
    if not order or order.driver_id != driver.id:
        abort(404)
    return order


# ---------------------------------------------------------------- page + login
@bp.route("/driver")
def driver_page():
    return render_template("driver.html")


@bp.route("/api/driver/login", methods=["POST"])
def login():
    if request.headers.get("X-Requested-With") != "fetch":
        abort(400)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()[:40]
    driver = Driver.query.filter_by(username=username).first() if username else None
    if not driver or not driver.active or not driver.check_password(str(data.get("password", ""))[:200]):
        return jsonify({"error": "wrong_login"}), 401
    session["driver_id"] = driver.id    # only the driver part of the session changes
    session.permanent = True
    return jsonify({"driver": driver.to_dict()})


@bp.route("/api/driver/logout", methods=["POST"])
def logout():
    session.pop("driver_id", None)
    return jsonify({"ok": True})


@bp.route("/api/driver/me")
@driver_required
def me(driver):
    return jsonify({"driver": driver.to_dict(), "username": driver.username})


# ---------------------------------------------------------------- jobs
@bp.route("/api/driver/jobs")
@driver_required
def jobs(driver):
    expire_old_orders()
    available = (Order.query
                 .filter(Order.fulfilment == "delivery", Order.status.in_(TAKEABLE), Order.driver_id.is_(None))
                 .order_by(Order.created_at).limit(50).all())
    since = utcnow() - timedelta(hours=24)      # my finished jobs of the last 24 hours
    mine = (Order.query.filter(Order.driver_id == driver.id,
                               db.or_(Order.status.in_(TAKEABLE + ("out_for_delivery",)), Order.closed_at >= since))
            .order_by(Order.created_at.desc()).limit(30).all())
    return jsonify({"available": [job_summary(o) for o in available],
                    "mine": [{**job_details(o), "status": o.status} for o in mine],
                    "max_active": MAX_ACTIVE_JOBS})


@bp.route("/api/driver/jobs/<int:order_id>/take", methods=["POST"])
@driver_required
def take(driver, order_id):
    expire_old_orders()
    active = Order.query.filter(Order.driver_id == driver.id,
                                Order.status.in_(TAKEABLE + ("out_for_delivery",))).count()
    if active >= MAX_ACTIVE_JOBS:
        return error("too_many_jobs", 409, max=MAX_ACTIVE_JOBS)
    # First driver wins: only if it is still a delivery, still waiting, and nobody took it.
    changed = (Order.query
               .filter(Order.id == order_id, Order.fulfilment == "delivery", Order.status.in_(TAKEABLE),
                       Order.driver_id.is_(None))
               .update({Order.driver_id: driver.id, Order.driver_assigned_at: utcnow()}, synchronize_session=False))
    if changed != 1:
        db.session.rollback()
        return error("already_taken", 409)
    db.session.commit()
    return jsonify({"job": job_details(db.session.get(Order, order_id))})


@bp.route("/api/driver/jobs/<int:order_id>/release", methods=["POST"])
@driver_required
def release(driver, order_id):
    my_job(driver, order_id)
    changed = (Order.query.filter(Order.id == order_id, Order.driver_id == driver.id, Order.status.in_(TAKEABLE))
               .update({Order.driver_id: None, Order.driver_assigned_at: None}, synchronize_session=False))
    if changed != 1:
        return error("status_changed", 409)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/driver/jobs/<int:order_id>/delivered", methods=["POST"])
@driver_required
def delivered(driver, order_id):
    order = my_job(driver, order_id)
    body = request.get_json(silent=True) or {}
    if not hmac.compare_digest(only_digits(body.get("code")), order.pickup_code):
        return error("wrong_code")
    if body.get("cash_collected") is not True:
        return error("cash_required")
    if order.prescription and body.get("paper_collected") is not True:
        return error("paper_required")     # no original prescription paper -> no medicine
    changed = (Order.query.filter(Order.id == order.id, Order.status == "out_for_delivery",
                                  Order.driver_id == driver.id)
               .update({Order.status: "delivered", Order.closed_at: utcnow(), Order.cash_collected: True,
                        Order.paper_collected: True if order.prescription else None}, synchronize_session=False))
    if changed != 1:
        return error("status_changed", 409)
    drop_photo(order)
    db.session.commit()
    return jsonify({"job": {**job_details(db.session.get(Order, order_id)), "status": "delivered"}})


@bp.route("/api/driver/jobs/<int:order_id>/failed", methods=["POST"])
@driver_required
def failed(driver, order_id):
    order = my_job(driver, order_id)
    reason = str((request.get_json(silent=True) or {}).get("reason", "other"))
    if reason not in FAIL_REASONS:
        reason = "other"
    changed = (Order.query.filter(Order.id == order.id, Order.status == "out_for_delivery",
                                  Order.driver_id == driver.id)
               .update({Order.status: "cancelled", Order.closed_at: utcnow(), Order.cancelled_by: "driver",
                        Order.cancel_reason: "driver_" + reason}, synchronize_session=False))
    if changed != 1:
        return error("status_changed", 409)
    return_stock(order)          # the driver brings the bag back to the pharmacy
    drop_photo(order)
    db.session.commit()
    return jsonify({"ok": True})
