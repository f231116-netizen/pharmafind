"""Database models for PharmaFind.

Tables:
  pharmacies  - each pharmacy, its location, and its pharmacist login
  medicines   - each product (brand), linked to others by active ingredient
  barcodes    - barcodes printed on medicine boxes
  stock       - which pharmacy has which medicine, at what price
  search_log  - every search (what, how, where), for the pharmacist dashboard
  users       - customer accounts, logged in with phone number + one-time code (Phase 6)
  login_codes - the one-time codes sent to phones (only a hash is stored)  (Phase 6)

seed.py resets only the demo tables. users and login_codes are never wiped by it.
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
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
class User(db.Model):
    """A customer. There is no password: they log in with a one-time code sent to their phone.
    Guests don't need an account; it is only needed to order (Phase 7)."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)  # +9647701234567
    name = db.Column(db.String(80))
    verified = db.Column(db.Boolean, default=False, nullable=False)  # True once a code was confirmed
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "name": self.name,
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


# Tables that hold demo data. seed.py deletes and rebuilds only these.
DEMO_TABLES = [Pharmacy.__table__, Medicine.__table__, Barcode.__table__, Stock.__table__,
               SearchLog.__table__]
