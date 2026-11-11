"""Phase 6 - Customer accounts: log in with a phone number + a one-time code.

Guests can still do everything they could before (search, scan, alternatives, info).
An account is only needed to order medicines (Phase 7).
Logging in and signing up are the same thing: the first time a number logs in, its account is made.

API:  POST /api/account/send-code   {phone}          send a 6-digit code to this phone
      POST /api/account/verify      {phone, code}    check the code and log in
      GET  /api/account/me                           who is logged in ({"user": null} for guests)
      PUT  /api/account/me          {name}           change your name
      POST /api/account/logout

How the code reaches the phone (the OTP_PROVIDER setting):
  console  (default) the code is printed in the terminal (the black window).
           For testing: on your laptop the page also shows it in a yellow "test mode" box.
           On the live website (PHARMAFIND_PRODUCTION=1) it is NOT shown on the page,
           unless you also set OTP_SHOW_CODE=1 (only for a demo, never with real users).
  Later: an SMS or WhatsApp provider. Add it in deliver() below.

Security:
  - the code is random (Python's secrets module), 6 digits, works for 5 minutes, and only once
  - only a hash of the code is saved (HMAC-SHA256 with the app's secret key), never the code
  - 5 wrong tries and the code stops working; you have to ask for a new one
  - limits: 1 code per number per minute, 5 per number per hour, 20 per internet address per hour
    (so nobody can make us send thousands of SMS, which would cost money)
  - the same signed session cookie and X-Requested-With check as the pharmacist login
"""
import hashlib
import hmac
import math
import os
import re
import secrets
from datetime import timedelta, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request, session

from models import db, User, LoginCode, utcnow

bp = Blueprint("account", __name__)

PRODUCTION = os.environ.get("PHARMAFIND_PRODUCTION") == "1"
PROVIDERS = ("console",)
OTP_PROVIDER = os.environ.get("OTP_PROVIDER", "console").strip().lower()
if OTP_PROVIDER not in PROVIDERS:
    print(f"[PharmaFind] Unknown OTP_PROVIDER '{OTP_PROVIDER}', using 'console' instead.", flush=True)
    OTP_PROVIDER = "console"
SHOW_CODE_ON_PAGE = OTP_PROVIDER == "console" and (not PRODUCTION or os.environ.get("OTP_SHOW_CODE") == "1")

CODE_DIGITS = 6
CODE_MINUTES = 5          # a code works for this long
MAX_ATTEMPTS = 5          # wrong tries allowed per code
RESEND_SECONDS = 60       # wait this long before asking for another code
PER_PHONE_PER_HOUR = 5
PER_IP_PER_HOUR = 20

# Kurdish and Arabic keyboards type these digits. Turn them into 0-9.
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# ---------------------------------------------------------------- helpers
def as_utc(dt):
    """SQLite gives times back without a time zone; they are always UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def only_digits(text):
    return re.sub(r"[^0-9]", "", str(text or "").translate(DIGITS))


def normalize_phone(raw):
    """'0770 123 4567', '+964 770 123 4567', '٠٧٧٠١٢٣٤٥٦٧'  ->  '+9647701234567'.
    Returns None if it is not an Iraqi mobile number (7 and then 9 more digits)."""
    digits = only_digits(raw)
    for prefix in ("00964", "964"):          # country code
        if digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    if digits.startswith("0"):               # 0770... (also catches +964 0770...)
        digits = digits[1:]
    return "+964" + digits if re.fullmatch(r"7\d{9}", digits) else None


def local_format(phone):
    """'+9647701234567' -> '0770 123 4567' (how people in Iraq write it)."""
    d = "0" + phone[4:]
    return f"{d[:4]} {d[4:7]} {d[7:]}"


def hash_code(phone, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def user_json(user):
    return {**user.to_dict(), "phone_display": local_format(user.phone)}


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def fetch_only(view):
    """Requests that change something must come from our own page (blocks forged form posts)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method not in ("GET", "HEAD") and request.headers.get("X-Requested-With") != "fetch":
            abort(400, "missing X-Requested-With header")
        return view(*args, **kwargs)
    return wrapper


def user_required(view):
    """For pages and API calls that need a logged-in customer (Phase 7 orders will use this too)."""
    @wraps(view)
    @fetch_only
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "not_logged_in"}), 401
        return view(user, *args, **kwargs)
    return wrapper


def deliver(phone, code):
    """Send the code to the phone. Today: print it. Later: call an SMS/WhatsApp provider here."""
    if OTP_PROVIDER == "console":
        print(f"[PharmaFind] Login code for {local_format(phone)}: {code}  (works for {CODE_MINUTES} min)",
              flush=True)


# ---------------------------------------------------------------- API
@bp.route("/api/account/send-code", methods=["POST"])
@fetch_only
def send_code():
    data = request.get_json(silent=True) or {}
    phone = normalize_phone(data.get("phone"))
    if not phone:
        return jsonify({"error": "bad_phone"}), 400

    now = utcnow()
    hour_ago = now - timedelta(hours=1)
    ip = (request.remote_addr or "")[:45]

    recent = (LoginCode.query.filter(LoginCode.phone == phone, LoginCode.created_at >= hour_ago)
              .order_by(LoginCode.created_at.desc()).all())
    if recent:
        wait = RESEND_SECONDS - (now - as_utc(recent[0].created_at)).total_seconds()
        if wait > 0:
            return jsonify({"error": "wait", "retry_in": math.ceil(wait)}), 429
    from_ip = LoginCode.query.filter(LoginCode.ip == ip, LoginCode.created_at >= hour_ago).count()
    if len(recent) >= PER_PHONE_PER_HOUR or from_ip >= PER_IP_PER_HOUR:
        return jsonify({"error": "too_many"}), 429

    # Only the newest code works: older ones for this number are switched off.
    # (synchronize_session=False: let the database do it. Comparing in Python fails on SQLite,
    #  which forgets the time zone of stored times.)
    LoginCode.query.filter_by(phone=phone, used=False).update({LoginCode.used: True},
                                                              synchronize_session=False)
    # Tidy up: codes older than a day are not needed any more.
    LoginCode.query.filter(LoginCode.created_at < now - timedelta(days=1)).delete(synchronize_session=False)

    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    db.session.add(LoginCode(phone=phone, code_hash=hash_code(phone, code), ip=ip,
                             created_at=now, expires_at=now + timedelta(minutes=CODE_MINUTES)))
    db.session.commit()
    deliver(phone, code)

    result = {"ok": True, "phone": phone, "phone_display": local_format(phone),
              "expires_in": CODE_MINUTES * 60, "resend_in": RESEND_SECONDS}
    if SHOW_CODE_ON_PAGE:
        result["test_code"] = code
    return jsonify(result)


@bp.route("/api/account/verify", methods=["POST"])
@fetch_only
def verify():
    data = request.get_json(silent=True) or {}
    phone = normalize_phone(data.get("phone"))
    code = only_digits(data.get("code"))
    if not phone or len(code) != CODE_DIGITS:
        return jsonify({"error": "bad_code"}), 400

    now = utcnow()
    row = (LoginCode.query.filter_by(phone=phone, used=False)
           .order_by(LoginCode.created_at.desc()).first())
    if not row or as_utc(row.expires_at) < now:
        return jsonify({"error": "expired"}), 400

    # Count this try in the database itself, so two tries at the same moment can't both slip through.
    counted = (LoginCode.query
               .filter(LoginCode.id == row.id, LoginCode.used.is_(False), LoginCode.attempts < MAX_ATTEMPTS)
               .update({LoginCode.attempts: LoginCode.attempts + 1}, synchronize_session=False))
    db.session.commit()
    if not counted:
        return jsonify({"error": "no_tries"}), 400

    if not hmac.compare_digest(row.code_hash, hash_code(phone, code)):
        tries_left = MAX_ATTEMPTS - row.attempts   # row is re-read from the database here
        if tries_left <= 0:
            return jsonify({"error": "no_tries"}), 400
        return jsonify({"error": "wrong_code", "tries_left": tries_left}), 400

    # Right code. Mark it used (only once, even if the same code is sent twice at the same moment).
    claimed = (LoginCode.query.filter(LoginCode.id == row.id, LoginCode.used.is_(False))
               .update({LoginCode.used: True}, synchronize_session=False))
    if not claimed:
        db.session.rollback()
        return jsonify({"error": "expired"}), 400

    user = User.query.filter_by(phone=phone).first()
    is_new = user is None
    if is_new:
        user = User(phone=phone, created_at=now)
        db.session.add(user)
    user.verified = True
    user.last_login_at = now
    db.session.commit()

    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"user": user_json(user), "new": is_new})


@bp.route("/api/account/me", methods=["GET"])
def me():
    user = current_user()
    if not user and "user_id" in session:
        session.pop("user_id")   # the account no longer exists
    return jsonify({"user": user_json(user) if user else None})


@bp.route("/api/account/me", methods=["PUT"])
@user_required
def update_me(user):
    data = request.get_json(silent=True) or {}
    # Keep letters, spaces and normal punctuation; drop invisible control characters.
    name = re.sub(r"[\x00-\x1f\x7f]", "", str(data.get("name", "")))
    name = " ".join(name.split())[:80]
    user.name = name or None
    db.session.commit()
    return jsonify({"user": user_json(user)})


@bp.route("/api/account/logout", methods=["POST"])
@fetch_only
def logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})
