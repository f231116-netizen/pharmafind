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

Rules:
  - one reservation = one pharmacy; at most 10 different medicines and 5 boxes of each
  - medicines that need a prescription can't be reserved yet (Phase 8 adds the prescription photo)
  - controlled medicines (e.g. tramadol) can never be reserved online
  - a customer can have at most 3 open reservations
  - waiting for the pharmacy for 24 h -> expires. Confirmed and not collected within 24 h -> expires,
    and the boxes go back to the stock. (Checked each time reservations are listed or changed.)
  - the customer pays at the pharmacy when collecting. No online payment (that would be Phase 9).
  - only the customer sees the pickup code. The pharmacist types it in when handing over the medicine.
"""
import hmac
import re
import secrets
from datetime import timedelta

from flask import Blueprint, abort, jsonify, request

from account_routes import local_format, only_digits, user_required
from models import db, Medicine, Order, OrderItem, Pharmacy, Stock, ORDER_OPEN, utcnow
from pharmacy_routes import login_required as pharmacist_required

bp = Blueprint("orders", __name__)

MAX_ITEMS = 10             # different medicines in one reservation
MAX_QTY = 5                # boxes of one medicine
MAX_OPEN_ORDERS = 3        # open reservations per customer
HOLD_HOURS = 24            # a confirmed reservation is kept this long
PENDING_HOURS = 24         # a reservation the pharmacy never answered expires after this
REJECT_REASONS = ("out_of_stock", "other")


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
    return data


# ---------------------------------------------------------------- customer
@bp.route("/api/orders", methods=["POST"])
@user_required
def create_order(user):
    if not user.profile_complete:
        return error("profile_incomplete", 403)
    data = request.get_json(silent=True) or {}
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
    for mid, qty in wanted.items():
        med = db.session.get(Medicine, mid)
        if not med:
            return error("unknown_medicine", 404)
        if med.controlled:
            return error("controlled", medicine=med.to_dict())
        if med.rx_required:
            return error("needs_prescription", medicine=med.to_dict())
        row = stock.get(mid)
        available = row.quantity if row else 0
        if available < qty:
            return error("not_enough", 409, medicine=med.to_dict(), available=available)
        items.append(OrderItem(medicine_id=mid, quantity=qty, price_iqd=row.price_iqd))

    note = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("note") or "")).split())[:200]
    order = Order(user_id=user.id, pharmacy_id=pharmacy.id, status="pending",
                  pickup_code=f"{secrets.randbelow(10 ** 4):04d}", note=note or None,
                  total_iqd=sum(i.quantity * i.price_iqd for i in items), created_at=utcnow(), items=items)
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
    db.session.commit()
    return jsonify({"order": customer_json(order)})


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


@bp.route("/api/pharmacy/orders/<int:order_id>/confirm", methods=["POST"])
@pharmacist_required
def confirm_order(ph, order_id):
    expire_old_orders()
    order = my_pharmacy_order(ph, order_id)
    now = utcnow()
    short = take_stock(order)
    if short is not None:
        db.session.rollback()
        row = Stock.query.filter_by(pharmacy_id=ph.id, medicine_id=short.medicine_id).first()
        return error("not_enough", 409, medicine=short.medicine.to_dict(), available=row.quantity if row else 0)
    if not move(order, ("pending",), "confirmed", confirmed_at=now, hold_until=now + timedelta(hours=HOLD_HOURS)):
        db.session.rollback()          # the customer cancelled meanwhile: give nothing away
        return error("status_changed", 409)
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})


@bp.route("/api/pharmacy/orders/<int:order_id>/reject", methods=["POST"])
@pharmacist_required
def reject_order(ph, order_id):
    order = my_pharmacy_order(ph, order_id)
    reason = str((request.get_json(silent=True) or {}).get("reason", "other"))
    if reason not in REJECT_REASONS:
        reason = "other"
    if not move(order, ("pending",), "cancelled", closed_at=utcnow(), cancelled_by="pharmacy",
                cancel_reason=reason):
        return error("status_changed", 409)
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
    code = only_digits((request.get_json(silent=True) or {}).get("code"))
    if not hmac.compare_digest(code, order.pickup_code):
        return error("wrong_code")
    # The boxes were already taken off the stock when the reservation was confirmed.
    if not move(order, ("confirmed", "ready"), "picked_up", closed_at=utcnow()):
        return error("status_changed", 409)
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
    db.session.commit()
    return jsonify({"order": pharmacist_json(order)})
