"""Phase 7 - Reservations: reserve medicines at ONE pharmacy, then pay and collect them there.

Customer API (logged in, with name, age and gender filled in):
  POST /api/orders                  {pharmacy_id, items: [{medicine_id, quantity}], note}
  GET  /api/orders                  my reservations, newest first
  POST /api/orders/<id>/cancel      cancel my reservation (while it is still open)

Pharmacist API (the pharmacist login from Phase 5):
  GET  /api/pharmacy/orders                  this pharmacy's reservations
  POST /api/pharmacy/orders/<id>/confirm     pending -> confirmed: boxes are taken off the stock and kept 24 h
  POST /api/pharmacy/orders/<id>/reject      pending -> cancelled            {reason}
  POST /api/pharmacy/orders/<id>/ready       confirmed -> ready (packed, waiting at the counter)
  POST /api/pharmacy/orders/<id>/pickup      confirmed/ready -> picked_up    {code}  (the customer's pickup code)
  POST /api/pharmacy/orders/<id>/cancel      confirmed/ready -> cancelled (the boxes go back to the stock)

Phase 8 - prescriptions:
  GET  /api/orders/<id>/prescription            the customer's own prescription photo
  GET  /api/pharmacy/orders/<id>/prescription   the same photo, for the pharmacy of that reservation
  - A reservation with prescription medicines must be sent as a form (multipart) with the photo
    in the field "prescription" and the reservation as JSON in the field "order".
  - Confirming it = approving the prescription: the pharmacist must tick that they checked it and
    write the doctor's name and the prescription date. One prescription = one use.
  - Rejecting can give a prescription reason (unreadable, not valid, doesn't match, already used).
  - At pickup the pharmacist must tick that they took (or stamped) the original paper.
  - The photo is deleted as soon as the reservation is finished (collected, cancelled or expired).

Rules:
  - one reservation = one pharmacy; at most 10 different medicines and 5 boxes of each
  - medicines that need a prescription need a photo of it (Phase 8)
  - controlled medicines (e.g. tramadol) can never be reserved online
  - a customer can have at most 3 open reservations
  - waiting for the pharmacy for 24 h -> expires. Confirmed and not collected within 24 h -> expires,
    and the boxes go back to the stock. (Checked each time reservations are listed or changed.)
  - the customer pays at the pharmacy when collecting. No online payment (that would be Phase 9).
  - only the customer sees the pickup code. The pharmacist types it in when handing over the medicine.
"""
import hmac
import json
import re
import secrets
from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, make_response, request

from account_routes import local_format, only_digits, user_required
from models import db, Medicine, Order, OrderItem, Pharmacy, Prescription, Stock, ORDER_OPEN, iso_utc, utcnow
from pharmacy_routes import login_required as pharmacist_required
from prescriptions import (PhotoError, doctor_key, exact_copy_in_use, process_photo, same_paper_used,
                           similar_in_use)

bp = Blueprint("orders", __name__)

MAX_ITEMS = 10             # different medicines in one reservation
MAX_QTY = 5                # boxes of one medicine
MAX_OPEN_ORDERS = 3        # open reservations per customer
HOLD_HOURS = 24            # a confirmed reservation is kept this long
PENDING_HOURS = 24         # a reservation the pharmacy never answered expires after this
RX_MAX_AGE_DAYS = 30       # an older prescription can't be approved (ask a pharmacist what is right)
RX_REASONS = ("rx_unreadable", "rx_invalid", "rx_mismatch", "rx_used")
REJECT_REASONS = ("out_of_stock", *RX_REASONS, "other")


# ---------------------------------------------------------------- helpers
def error(code, status=400, **extra):
    return jsonify({"error": code, **extra}), status


def move(order, from_statuses, to_status, **fields):
    """Change the status, but only if it is still one of from_statuses.
    (The customer may cancel at the same moment the pharmacist confirms: only one of them wins.)"""
    values = {Order.status: to_status, **{getattr(Order, k): v for k, v in fields.items()}}
    changed = (Order.query.filter(Order.id == order.id, Order.status.in_(from_statuses))
               .update(values, synchronize_session=False))
    return changed == 1


def take_stock(order):
    """Take the reserved boxes off the pharmacy's stock. Returns the first item that
    doesn't have enough boxes (then nothing should be saved), or None if all is fine."""
    for item in order.items:
        changed = (Stock.query
                   .filter(Stock.pharmacy_id == order.pharmacy_id, Stock.medicine_id == item.medicine_id,
                           Stock.quantity >= item.quantity)
                   .update({Stock.quantity: Stock.quantity - item.quantity, Stock.updated_at: utcnow()},
                           synchronize_session=False))
        if changed != 1:
            return item
    return None


def return_stock(order):
    """Put the boxes back (reservation cancelled or not collected)."""
    for item in order.items:
        (Stock.query.filter_by(pharmacy_id=order.pharmacy_id, medicine_id=item.medicine_id)
         .update({Stock.quantity: Stock.quantity + item.quantity, Stock.updated_at: utcnow()},
                 synchronize_session=False))


def drop_photo(order):
    """The reservation is finished: delete the prescription photo (privacy). The fingerprints,
    doctor and date stay, so the same prescription can't be used again."""
    (Prescription.query.filter(Prescription.order_id == order.id, Prescription.photo_deleted_at.is_(None))
     .update({Prescription.photo: None, Prescription.photo_deleted_at: utcnow()}, synchronize_session=False))


def expire_old_orders():
    """Close reservations whose time is up (see the rules at the top)."""
    now = utcnow()
    overdue = Order.query.filter(db.or_(
        db.and_(Order.status == "pending", Order.created_at < now - timedelta(hours=PENDING_HOURS)),
        db.and_(Order.status.in_(("confirmed", "ready")), Order.hold_until < now),
    )).all()
    for order in overdue:
        held = order.status in ("confirmed", "ready")
        if move(order, (order.status,), "expired", closed_at=now, cancelled_by="system",
                cancel_reason="not_collected" if held else "no_answer"):
            if held:
                return_stock(order)
            drop_photo(order)
    if overdue:
        db.session.commit()


def customer_json(order):
    return {**order.to_dict(), "pharmacy": order.pharmacy.to_dict()}


def pharmacist_json(order):
    """What the pharmacist sees. NOT the pickup code: the customer has to show it."""
    data = order.to_dict()
    data.pop("pickup_code")
    u = order.user
    data["customer"] = {"name": u.name, "age": u.age, "gender": u.gender,
                        "phone": u.phone, "phone_display": local_format(u.phone)}
    rx = order.prescription
    if rx and rx.similar_to_id:
        other = db.session.get(Order, rx.similar_to_id)
        if other:   # a photo that looks the same was sent before: warn the pharmacist
            data["prescription"]["similar"] = {"order_id": other.id, "created_at": iso_utc(other.created_at),
                                               "same_pharmacy": other.pharmacy_id == order.pharmacy_id}
    return data


def photo_response(rx):
    """Send a prescription photo. Never cached: it is health information."""
    if rx is None or rx.photo_deleted_at is not None or rx.photo is None:
        abort(404)
    resp = make_response(rx.photo)
    resp.headers["Content-Type"] = "image/jpeg"
    resp.headers["Content-Disposition"] = 'inline; filename="prescription.jpg"'
    resp.headers["Cache-Control"] = "no-store, private"
    return resp


# ---------------------------------------------------------------- customer
@bp.route("/api/orders", methods=["POST"])
@user_required
def create_order(user):
    if not user.profile_complete:
        return error("profile_incomplete", 403)
    if request.mimetype == "multipart/form-data":       # with a prescription photo (Phase 8)
        try:
            data = json.loads(request.form.get("order") or "{}")
        except ValueError:
            return error("bad_request")
        photo_file = request.files.get("prescription")
    else:
        data = request.get_json(silent=True) or {}
        photo_file = None
    if not isinstance(data, dict):
        return error("bad_request")
    try:
        pharmacy_id = int(data.get("pharmacy_id"))
        wanted = {}                                   # medicine id -> boxes
        for item in (data.get("items") or [])[:MAX_ITEMS + 1]:
            mid, qty = int(item["medicine_id"]), int(item["quantity"])
            wanted[mid] = wanted.get(mid, 0) + qty
    except (TypeError, ValueError, KeyError):
        return error("bad_request")
    if not wanted or len(wanted) > MAX_ITEMS:
        return error("bad_items", max=MAX_ITEMS)
    if any(not (1 <= qty <= MAX_QTY) for qty in wanted.values()):
        return error("bad_quantity", max=MAX_QTY)
    pharmacy = db.session.get(Pharmacy, pharmacy_id)
    if not pharmacy:
        return error("unknown_pharmacy", 404)

    expire_old_orders()
    open_now = Order.query.filter(Order.user_id == user.id, Order.status.in_(ORDER_OPEN)).count()
    if open_now >= MAX_OPEN_ORDERS:
        return error("too_many_open", 409, max=MAX_OPEN_ORDERS)

    stock = {s.medicine_id: s for s in
             Stock.query.filter(Stock.pharmacy_id == pharmacy.id, Stock.medicine_id.in_(list(wanted))).all()}
    items = []
    needs_rx = False
    for mid, qty in wanted.items():
        med = db.session.get(Medicine, mid)
        if not med:
            return error("unknown_medicine", 404)
        if med.controlled:
            return error("controlled", medicine=med.to_dict())
        needs_rx = needs_rx or bool(med.rx_required)
        row = stock.get(mid)
        available = row.quantity if row else 0
        if available < qty:
            return error("not_enough", 409, medicine=med.to_dict(), available=available)
        items.append(OrderItem(medicine_id=mid, quantity=qty, price_iqd=row.price_iqd))

    now = utcnow()
    rx = None
    if needs_rx:   # Phase 8: prescription medicines need a photo of the prescription
        if photo_file is None:
            return error("prescription_required")
        try:
            jpeg, sha256, dh = process_photo(photo_file.read())
        except PhotoError as e:
            return error(e.code)
        if exact_copy_in_use(sha256):
            return error("rx_already_used", 409)
        rx = Prescription(user_id=user.id, photo=jpeg, photo_sha256=sha256, photo_dhash=dh,
                          status="waiting", similar_to_id=similar_in_use(dh), created_at=now)
    # (A photo sent without prescription medicines is simply not kept.)

    note = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("note") or "")).split())[:200]
    order = Order(user_id=user.id, pharmacy_id=pharmacy.id, status="pending",
                  pickup_code=f"{secrets.randbelow(10 ** 4):04d}", note=note or None,
                  total_iqd=sum(i.quantity * i.price_iqd for i in items), created_at=now, items=items,
                  prescription=rx)
    db.session.add(order)
    db.session.commit()
    return jsonify({"order": customer_json(order)}), 201


@bp.route("/api/orders")
@user_required
def my_orders(user):
    expire_old_orders()
    orders = (Order.query.filter_by(user_id=user.id)
              .order_by(Order.created_at.desc(), Order.id.desc()).limit(20).all())
    return jsonify({"orders": [customer_json(o) for o in orders], "hold_hours": HOLD_HOURS})


@bp.route("/api/orders/<int:order_id>/cancel", methods=["POST"])
@user_required
def cancel_my_order(user, order_id):
    expire_old_orders()
    order = db.session.get(Order, order_id)
    if not order or order.user_id != user.id:
        return error("not_found", 404)
    fields = dict(closed_at=utcnow(), cancelled_by="customer", cancel_reason="customer")
    # Two steps, so we always know if boxes were already taken off (even if the pharmacist
    # confirms at this very moment): first try "confirmed/ready", then "pending".
    if move(order, ("confirmed", "ready"), "cancelled", **fields):
        return_stock(order)
    elif not move(order, ("pending",), "cancelled", **fields):
        return error("status_changed", 409)
    drop_photo(order)
    db.session.commit()
    return jsonify({"order": customer_json(order)})


@bp.route("/api/orders/<int:order_id>/prescription")
@user_required
def my_prescription_photo(user, order_id):
    order = db.session.get(Order, order_id)
    if not order or order.user_id != user.id:
        abort(404)
    return photo_response(order.prescription)


# ---------------------------------------------------------------- pharmacist
def my_pharmacy_order(ph, order_id):
    order = db.session.get(Order, order_id)
    if not order or order.pharmacy_id != ph.id:
        abort(404)
    return order


@bp.route("/api/pharmacy/orders")
@pharmacist_required
def pharmacy_orders(ph):
    expire_old_orders()
    week_ago = utcnow() - timedelta(days=7)
    orders = (Order.query
              .filter(Order.pharmacy_id == ph.id,
                      db.or_(Order.status.in_(ORDER_OPEN), Order.closed_at >= week_ago))
              .order_by(Order.created_at.desc(), Order.id.desc()).limit(200).all())
    return jsonify({
        "orders": [pharmacist_json(o) for o in orders],
        "pending_count": sum(1 for o in orders if o.status == "pending"),
        "hold_hours": HOLD_HOURS,
    })


@bp.route("/api/pharmacy/orders/<int:order_id>/prescription")
@pharmacist_required
def pharmacy_prescription_photo(ph, order_id):
    return photo_response(my_pharmacy_order(ph, order_id).prescription)


def read_rx_check(rx):
    """The pharmacist's check of a prescription, sent with Confirm:
    {checked: true, doctor_name, issued_on: "2026-11-10"}. Returns (values, None) or (None, error)."""
    body = request.get_json(silent=True) or {}
    doctor = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(body.get("doctor_name") or "")).split())[:80]
    try:
        issued = date.fromisoformat(str(body.get("issued_on") or ""))
    except ValueError:
        issued = None
    today = utcnow().date()
    wrong = []
    if body.get("checked") is not True:
        wrong.append("checked")
    if len(doctor) < 2 or not doctor_key(doctor):
        wrong.append("doctor_name")
    # Not in the future (one day of slack for the time zone), and not too old.
    if issued is None or issued > today + timedelta(days=1):
        wrong.append("issued_on")
    elif issued < today - timedelta(days=RX_MAX_AGE_DAYS):
        wrong.append("too_old")
    if wrong:
        return None, error("rx_check", fields=wrong, max_age_days=RX_MAX_AGE_DAYS)
    twin = same_paper_used(rx, doctor_key(doctor), issued)
    if twin:   # one prescription = one use
        return None, error("rx_already_used", 409, order_id=twin.order_id,
                           pharmacy=twin.order.pharmacy.name, when=iso_utc(twin.order.created_at))
    return {"doctor_name": doctor, "doctor_key": doctor_key(doctor), "issued_on": issued}, None


@bp.route("/api/pharmacy/orders/<int:order_id>/confirm", methods=["POST"])
@pharmacist_required
def confirm_order(ph, order_id):
    expire_old_orders()
    order = my_pharmacy_order(ph, order_id)
    rx = order.prescription
    checked = None
    if rx:                     # confirming = approving the prescription (Phase 8)
        checked, problem = read_rx_check(rx)
        if problem:
            return problem
    now = utcnow()
    short = take_stock(order)
    if short is not None:
        db.session.rollback()
        row = Stock.query.filter_by(pharmacy_id=ph.id, medicine_id=short.medicine_id).first()
        return error("not_enough", 409, medicine=short.medicine.to_dict(), available=row.quantity if row else 0)
    if not move(order, ("pending",), "confirmed", confirmed_at=now, hold_until=now + timedelta(hours=HOLD_HOURS)):
        db.session.rollback()          # the customer cancelled meanwhile: give nothing away
        return error("status_changed", 409)
    if rx:
        rx.status = "approved"
        rx.doctor_name, rx.doctor_key, rx.issued_on = checked["doctor_name"], checked["doctor_key"], checked["issued_on"]
        rx.reviewed_at, rx.reviewed_by = now, ph.id
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})


@bp.route("/api/pharmacy/orders/<int:order_id>/reject", methods=["POST"])
@pharmacist_required
def reject_order(ph, order_id):
    order = my_pharmacy_order(ph, order_id)
    reason = str((request.get_json(silent=True) or {}).get("reason", "other"))
    if reason not in REJECT_REASONS or (reason in RX_REASONS and not order.prescription):
        reason = "other"
    now = utcnow()
    if not move(order, ("pending",), "cancelled", closed_at=now, cancelled_by="pharmacy",
                cancel_reason=reason):
        return error("status_changed", 409)
    if reason in RX_REASONS:          # the prescription itself was not accepted
        rx = order.prescription
        rx.status, rx.reject_reason, rx.reviewed_at, rx.reviewed_by = "rejected", reason, now, ph.id
    drop_photo(order)
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})


@bp.route("/api/pharmacy/orders/<int:order_id>/ready", methods=["POST"])
@pharmacist_required
def ready_order(ph, order_id):
    expire_old_orders()
    order = my_pharmacy_order(ph, order_id)
    if not move(order, ("confirmed",), "ready", ready_at=utcnow()):
        return error("status_changed", 409)
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})


@bp.route("/api/pharmacy/orders/<int:order_id>/pickup", methods=["POST"])
@pharmacist_required
def pickup_order(ph, order_id):
    expire_old_orders()
    order = my_pharmacy_order(ph, order_id)
    body = request.get_json(silent=True) or {}
    code = only_digits(body.get("code"))
    if not hmac.compare_digest(code, order.pickup_code):
        return error("wrong_code")
    # Phase 8: a photo can be faked or reused, the paper is the real proof. The pharmacist keeps or stamps it.
    if order.prescription and body.get("paper_checked") is not True:
        return error("paper_required")
    # The boxes were already taken off the stock when the reservation was confirmed.
    if not move(order, ("confirmed", "ready"), "picked_up", closed_at=utcnow()):
        return error("status_changed", 409)
    drop_photo(order)
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})


@bp.route("/api/pharmacy/orders/<int:order_id>/cancel", methods=["POST"])
@pharmacist_required
def pharmacy_cancel_order(ph, order_id):
    order = my_pharmacy_order(ph, order_id)
    if not move(order, ("confirmed", "ready"), "cancelled", closed_at=utcnow(), cancelled_by="pharmacy",
                cancel_reason="other"):
        return error("status_changed", 409)
    return_stock(order)
    drop_photo(order)
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})
