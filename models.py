"""Database models for PharmaFind.

Tables:
  pharmacies  - each pharmacy, its location, and its pharmacist login
  medicines   - each product (brand), linked to others by active ingredient
  barcodes    - barcodes printed on medicine boxes
  stock       - which pharmacy has which medicine, at what price
  search_log  - every search (what, how, where), for the pharmacist dashboard
  users       - customer accounts, logged in with phone number + one-time code (Phase 6)
  login_codes - the one-time codes sent to phones (only a hash is stored)  (Phase 6)
  orders      - reservations: a customer reserves medicines at one pharmacy and picks them up (Phase 7)
  order_items - the medicines in each reservation, with the price at that moment  (Phase 7)
  prescriptions - the photo of a doctor's prescription for a reservation, and the pharmacist's check (Phase 8)
  drivers     - delivery drivers who bring reservations to the customer (Phase 9)

seed.py resets the demo tables (and the reservations, which belong to the demo pharmacies).
users and login_codes are never wiped by it.
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import deferred
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    """SQLite forgets the time zone, so mark stored times as UTC explicitly ("...Z")."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Pharmacy(db.Model):
    __tablename__ = "pharmacies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200))
    city = db.Column(db.String(60), nullable=False, default="Sulaymaniyah")
    phone = db.Column(db.String(30))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    open_hours = db.Column(db.String(60))
    is_24h = db.Column(db.Boolean, default=False)
    # Pharmacist login (Phase 5). Only a hash of the password is stored, never the password.
    username = db.Column(db.String(40), unique=True, index=True)
    password_hash = db.Column(db.String(256))

    stock_items = db.relationship("Stock", back_populates="pharmacy", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "phone": self.phone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "open_hours": self.open_hours,
            "is_24h": self.is_24h,
        }


class Medicine(db.Model):
    __tablename__ = "medicines"

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(120), nullable=False, index=True)
    name_ar = db.Column(db.String(120))          # Arabic spelling, for search
    name_ku = db.Column(db.String(120))          # Kurdish (Sorani) spelling, for search
    active_ingredient = db.Column(db.String(120), nullable=False, index=True)
    strength = db.Column(db.String(40), nullable=False)   # e.g. "500 mg"
    form = db.Column(db.String(40), nullable=False)       # tablet, capsule, syrup, inhaler...
    company = db.Column(db.String(120))
    general_use = db.Column(db.String(255))     # English
    general_use_ar = db.Column(db.String(255))  # Arabic
    general_use_ku = db.Column(db.String(255))  # Kurdish (Sorani)
    rx_required = db.Column(db.Boolean, default=False)    # needs a prescription
    controlled = db.Column(db.Boolean, default=False)     # e.g. tramadol: never reserved online (Phase 7)
    from_real_box = db.Column(db.Boolean, default=False)  # True = we photographed this box

    stock_items = db.relationship("Stock", back_populates="medicine", cascade="all, delete-orphan")
    barcodes = db.relationship("Barcode", back_populates="medicine", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "brand_name": self.brand_name,
            "name_ar": self.name_ar,
            "name_ku": self.name_ku,
            "active_ingredient": self.active_ingredient,
            "strength": self.strength,
            "form": self.form,
            "company": self.company,
            "general_use": self.general_use,
            "general_use_ar": self.general_use_ar,
            "general_use_ku": self.general_use_ku,
            "rx_required": self.rx_required,
            "controlled": bool(self.controlled),
            "from_real_box": self.from_real_box,
            "barcodes": [b.code for b in self.barcodes],
        }


class Barcode(db.Model):
    """A barcode printed on a medicine box. One medicine can have several
    (different pack sizes, or an EAN-13 plus another code on the same box)."""
    __tablename__ = "barcodes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)  # digits only
    kind = db.Column(db.String(20), default="EAN-13")                         # EAN-13, Code 128...
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False)

    medicine = db.relationship("Medicine", back_populates="barcodes")


class Stock(db.Model):
    __tablename__ = "stock"
    __table_args__ = (db.UniqueConstraint("pharmacy_id", "medicine_id", name="uq_pharmacy_medicine"),)

    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id"), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False)
    price_iqd = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    pharmacy = db.relationship("Pharmacy", back_populates="stock_items")
    medicine = db.relationship("Medicine", back_populates="stock_items")

    def to_dict(self):
        return {
            "pharmacy_id": self.pharmacy_id,
            "medicine_id": self.medicine_id,
            "price_iqd": self.price_iqd,
            "quantity": self.quantity,
            "in_stock": self.quantity > 0,
            "updated_at": iso_utc(self.updated_at),
        }


class SearchLog(db.Model):
    __tablename__ = "search_log"

    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(20), default="text")     # text | photo | barcode
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"))  # what it matched, if anything
    found = db.Column(db.Boolean, default=False)
    latitude = db.Column(db.Float)      # where the user was (approximate), for "searches near you"
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------- Phase 6: customer accounts
GENDERS = ("male", "female")


class User(db.Model):
    """A customer. There is no password: they log in with a one-time code sent to their phone.
    Guests don't need an account; it is only needed to reserve medicines (Phase 7).
    Name, age and gender are required before reserving: the pharmacist needs them to check
    that a medicine is safe for this person."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)  # +9647701234567
    name = db.Column(db.String(80))
    # We ask for the age, but save the year of birth, so the age is still right next year.
    birth_year = db.Column(db.Integer)
    gender = db.Column(db.String(10))     # "male" or "female"
    verified = db.Column(db.Boolean, default=False, nullable=False)  # True once a code was confirmed
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))

    @property
    def age(self):
        return utcnow().year - self.birth_year if self.birth_year else None

    @property
    def profile_complete(self):
        return bool(self.name and self.birth_year and self.gender in GENDERS)

    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "profile_complete": self.profile_complete,
            "verified": self.verified,
            "created_at": iso_utc(self.created_at),
        }


class LoginCode(db.Model):
    """A one-time login code. We keep only a hash of it (like a password), when it expires,
    and how many wrong tries were made, so nobody can guess it."""
    __tablename__ = "login_codes"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    ip = db.Column(db.String(45))            # who asked for it (limits how many codes one person can request)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)


# ---------------------------------------------------------------- Phase 9: delivery drivers
class Driver(db.Model):
    """A delivery driver (like a Talabat rider). Drivers aren't tied to one pharmacy: they see the
    delivery jobs that are packed and waiting, take one, fetch it from the pharmacy and bring it
    to the customer. They collect the cash and, for prescription medicines, the original paper."""
    __tablename__ = "drivers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "phone": self.phone}


# ---------------------------------------------------------------- Phase 7: reservations
# How a reservation moves:
#   pick up at the pharmacy:  pending -> confirmed -> ready -> picked_up
#   delivery (Phase 9):       pending -> confirmed -> ready -> out_for_delivery -> delivered
#   any time before that:     -> cancelled (customer, pharmacy or driver) / expired
ORDER_OPEN = ("pending", "confirmed", "ready", "out_for_delivery")
ORDER_CLOSED = ("picked_up", "delivered", "cancelled", "expired")


class Order(db.Model):
    """A reservation: medicines from ONE pharmacy. Collected at the pharmacy, or (Phase 9)
    brought by a driver. Paid in cash either way. Stock is taken off when the pharmacist
    confirms, and given back if it is cancelled or not collected in time."""
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacies.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    pickup_code = db.Column(db.String(8), nullable=False)   # the customer shows it at the pharmacy
    note = db.Column(db.String(200))                        # optional message to the pharmacist
    total_iqd = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    confirmed_at = db.Column(db.DateTime(timezone=True))
    ready_at = db.Column(db.DateTime(timezone=True))
    hold_until = db.Column(db.DateTime(timezone=True))       # after this, a confirmed order expires
    closed_at = db.Column(db.DateTime(timezone=True))        # picked up, cancelled or expired
    cancelled_by = db.Column(db.String(10))                  # customer | pharmacy | driver | system
    cancel_reason = db.Column(db.String(30))                 # out_of_stock | other | not_collected | ...
    # Phase 9: delivery
    fulfilment = db.Column(db.String(10), default="pickup")  # pickup | delivery
    address = db.Column(db.String(200))                      # "Salim Street, near ..., house 12"
    delivery_lat = db.Column(db.Float)
    delivery_lng = db.Column(db.Float)
    delivery_km = db.Column(db.Float)                        # pharmacy -> customer, straight line
    delivery_fee_iqd = db.Column(db.Integer, default=0)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), index=True)
    driver_assigned_at = db.Column(db.DateTime(timezone=True))
    out_for_delivery_at = db.Column(db.DateTime(timezone=True))
    cash_collected = db.Column(db.Boolean)                  # the driver ticked "cash collected"
    paper_collected = db.Column(db.Boolean)                 # the driver took the original prescription

    user = db.relationship("User")
    pharmacy = db.relationship("Pharmacy")
    driver = db.relationship("Driver")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan",
                            order_by="OrderItem.id")
    prescription = db.relationship("Prescription", back_populates="order", uselist=False,
                                   cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "pickup_code": self.pickup_code,
            "note": self.note,
            "total_iqd": self.total_iqd,
            "created_at": iso_utc(self.created_at),
            "confirmed_at": iso_utc(self.confirmed_at),
            "ready_at": iso_utc(self.ready_at),
            "hold_until": iso_utc(self.hold_until),
            "closed_at": iso_utc(self.closed_at),
            "cancelled_by": self.cancelled_by,
            "cancel_reason": self.cancel_reason,
            "items": [i.to_dict() for i in self.items],
            "prescription": self.prescription.to_dict() if self.prescription else None,
            # Phase 9: delivery (payment is always cash)
            "fulfilment": self.fulfilment or "pickup",
            "address": self.address,
            "delivery_km": self.delivery_km,
            "delivery_fee_iqd": self.delivery_fee_iqd or 0,
            "grand_total_iqd": self.total_iqd + (self.delivery_fee_iqd or 0),
            "driver": self.driver.to_dict() if self.driver else None,
            "out_for_delivery_at": iso_utc(self.out_for_delivery_at),
            "cash_collected": self.cash_collected,
            "paper_collected": self.paper_collected,
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_iqd = db.Column(db.Integer, nullable=False)   # price per box when the reservation was made

    order = db.relationship("Order", back_populates="items")
    medicine = db.relationship("Medicine")

    def to_dict(self):
        return {"medicine": self.medicine.to_dict(), "quantity": self.quantity, "price_iqd": self.price_iqd}


# ---------------------------------------------------------------- Phase 8: prescriptions
class Prescription(db.Model):
    """The photo of a doctor's prescription, sent with a reservation that has prescription medicines.

    The app can't prove a prescription is real. The PHARMACIST checks it (stamp, signature, date,
    patient's name, medicine), writes down the doctor's name and date, and approves or rejects it.
    At pickup the customer shows the original paper, and the pharmacist keeps or stamps it.

    Privacy: the photo is kept inside the database (never at a public address), only the customer
    and that one pharmacy can open it, and it is deleted as soon as the reservation is finished.
    The fingerprints (photo_sha256, photo_dhash) and doctor/date stay, so the same prescription
    can't be used twice."""
    __tablename__ = "prescriptions"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    photo = deferred(db.Column(db.LargeBinary))       # JPEG; None once deleted. Loaded only when asked for.
    photo_sha256 = db.Column(db.String(64), index=True)   # exact fingerprint of the uploaded file
    photo_dhash = db.Column(db.String(16), index=True)    # "looks the same" fingerprint (survives re-saving)
    similar_to_id = db.Column(db.Integer)             # another reservation with a photo that looks the same
    status = db.Column(db.String(10), nullable=False, default="waiting")   # waiting | approved | rejected
    doctor_name = db.Column(db.String(80))            # written by the pharmacist when approving
    doctor_key = db.Column(db.String(80), index=True)  # the same name, simplified, to compare
    issued_on = db.Column(db.Date)                    # date on the prescription
    reject_reason = db.Column(db.String(30))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by = db.Column(db.Integer, db.ForeignKey("pharmacies.id"))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    photo_deleted_at = db.Column(db.DateTime(timezone=True))

    order = db.relationship("Order", back_populates="prescription")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "doctor_name": self.doctor_name,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "reject_reason": self.reject_reason,
            "has_photo": self.photo_deleted_at is None,
            "photo_deleted_at": iso_utc(self.photo_deleted_at),
        }


# Tables that seed.py deletes and rebuilds. Reservations (and their prescriptions) are included
# because they point at demo pharmacies and medicines (after a reset those ids belong to other rows).
DEMO_TABLES = [Pharmacy.__table__, Medicine.__table__, Barcode.__table__, Stock.__table__,
               SearchLog.__table__, Order.__table__, OrderItem.__table__, Prescription.__table__,
               Driver.__table__]   # the drivers are demo accounts too (Phase 9)


def add_missing_columns(engine):
    """A very small "migration": when we add a new column to a model (like users.gender),
    an existing database doesn't have it yet. This adds it, so old databases keep working.
    (New tables are made by db.create_all(); this only handles new columns.)"""
    inspector = sa.inspect(engine)
    with engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    col_type = col.type.compile(dialect=engine.dialect)
                    conn.execute(sa.text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
                    print(f"[PharmaFind] Added new column {table.name}.{col.name}", flush=True)
