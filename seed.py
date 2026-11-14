"""Reset the demo data (pharmacies, medicines, barcodes, stock, search history, reservations).

Run:  python seed.py              delete the demo tables and rebuild them (reset_demo.bat does this)
      python seed.py --if-empty   KEEP everything that is there; only fill what is missing:
                                  an empty database gets all the demo data, a database without
                                  drivers gets the demo drivers. Used by start_showcase.bat
                                  (so closing and opening it keeps all data) and online with PostgreSQL.
Customer accounts (users, login_codes) are NOT touched (Phase 6).
Reservations ARE deleted: they belong to the demo pharmacies (Phase 7).
"""
import random
import sys
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app import create_app
from models import db, Pharmacy, Medicine, Stock, Barcode, SearchLog, Driver, DEMO_TABLES
from seed_data import (PHARMACIES, MEDICINES, USE_TRANSLATIONS, DEMO_OUT_OF_STOCK,
                       DEMO_ALWAYS_IN_STOCK, BARCODES, STICKER_PRICES, DEMO_PASSWORD,
                       DEMO_SEARCH_DAYS, DEMO_SEARCH_COUNT, DEMO_SEARCH_WEIGHTS, DEMO_NOT_FOUND,
                       CONTROLLED_INGREDIENTS, DEMO_DRIVERS, DRIVER_PASSWORD)

# Fixed seed so everyone on the team gets the same demo data.
random.seed(2026)

# Rough demo price ranges in IQD, by form.
PRICE_RANGE = {
    "tablet": (1500, 15000),
    "capsule": (2000, 18000),
    "inhaler": (6000, 12000),
    "oral drops": (2000, 6000),
    "oral suspension": (2500, 7000),
    "injection": (3000, 12000),
    "sachet": (3000, 10000),
}


def is_controlled(ingredient):
    """'Paracetamol + Codeine' -> True if any part is in CONTROLLED_INGREDIENTS."""
    return any(part.strip() in CONTROLLED_INGREDIENTS for part in ingredient.split("+"))


def add_demo_drivers():
    """Phase 9: demo delivery drivers (one password hash for all, like the pharmacists)."""
    driver_hash = Driver(name="", phone="", username="", password_hash="")
    driver_hash.set_password(DRIVER_PASSWORD)
    for name, phone, username in DEMO_DRIVERS:
        db.session.add(Driver(name=name, phone=phone, username=username,
                              password_hash=driver_hash.password_hash))


def seed(if_empty=False):
    app = create_app()
    with app.app_context():
        if if_empty and sa.inspect(db.engine).has_table("pharmacies") and Pharmacy.query.count():
            # Keep everything. Only add what an older database is missing (drivers came in Phase 9).
            if Driver.query.count() == 0:
                add_demo_drivers()
                db.session.commit()
                print(f"Kept all data. Added the {len(DEMO_DRIVERS)} demo drivers (they were missing).")
            else:
                print("Kept all data (reservations, accounts, stock). Nothing was reset.")
            return
        # Only the demo tables are deleted. Accounts stay.
        db.metadata.drop_all(bind=db.engine, tables=DEMO_TABLES)
        db.create_all()

        pharmacies = []
        # Hashing a password is slow on purpose; every demo account has the same password,
        # so we hash it once (each pharmacy still has its own account).
        demo_hash = Pharmacy(name="", latitude=0, longitude=0)
        demo_hash.set_password(DEMO_PASSWORD)
        for name, address, lat, lng, hours, is_24h in PHARMACIES:
            p = Pharmacy(
                name=name, address=address, latitude=lat, longitude=lng,
                open_hours=hours, is_24h=is_24h,
                phone=f"0770 {random.randint(100, 999)} {random.randint(1000, 9999)}",
                username=name.split()[0].lower(),
            )
            p.password_hash = demo_hash.password_hash
            pharmacies.append(p)
        db.session.add_all(pharmacies)

        medicines = []
        missing = sorted({row[7] for row in MEDICINES} - USE_TRANSLATIONS.keys())
        if missing:
            raise SystemExit("Add these to USE_TRANSLATIONS in seed_data.py:\n  " + "\n  ".join(missing))

        for brand, ar, ku, ingredient, strength, form, company, use, rx in MEDICINES:
            use_ar, use_ku = USE_TRANSLATIONS[use]
            m = Medicine(
                brand_name=brand, name_ar=ar, name_ku=ku,
                active_ingredient=ingredient, strength=strength, form=form,
                company=company, general_use=use, rx_required=rx,
                controlled=is_controlled(ingredient),
                general_use_ar=use_ar, general_use_ku=use_ku,
                from_real_box=brand in BARCODES or brand == "Hyoscine-N-Butylbromide",
            )
            for code, kind in BARCODES.get(brand, []):
                m.barcodes.append(Barcode(code=code, kind=kind))
            medicines.append(m)
        db.session.add_all(medicines)
        db.session.flush()  # assigns IDs

        # Each pharmacy carries ~60% of the medicines; ~15% of those are out of stock (qty 0).
        stock_rows = 0
        for p in pharmacies:
            for m in medicines:
                if random.random() < 0.6:
                    low, high = PRICE_RANGE.get(m.form, (2000, 15000))
                    price = round(random.randint(low, high), -2)  # round to 100 IQD
                    price = STICKER_PRICES.get(m.brand_name, price)  # real price from the KMCA sticker
                    qty = 0 if random.random() < 0.15 else random.randint(1, 60)
                    if m.brand_name in DEMO_OUT_OF_STOCK:
                        qty = 0  # sold out everywhere, to demo the alternatives feature
                    if m.brand_name in DEMO_ALWAYS_IN_STOCK and qty == 0:
                        qty = random.randint(5, 40)
                    db.session.add(Stock(pharmacy_id=p.id, medicine_id=m.id,
                                         price_iqd=price, quantity=qty))
                    stock_rows += 1

        searches = seed_searches(pharmacies, medicines)

        add_demo_drivers()

        db.session.commit()
        print(f"Seeded {len(pharmacies)} pharmacies, {len(medicines)} medicines, "
              f"{Barcode.query.count()} barcodes, {stock_rows} stock rows, {searches} demo searches, "
              f"{len(DEMO_DRIVERS)} drivers.")
        print(f"Pharmacist logins (password '{DEMO_PASSWORD}'): " + ", ".join(p.username for p in pharmacies))
        print(f"Driver logins at /driver (password '{DRIVER_PASSWORD}'): " + ", ".join(d[2] for d in DEMO_DRIVERS))


def seed_searches(pharmacies, medicines):
    """Fake search history: people searching near random pharmacies, mostly in the evening."""
    now = datetime.now(timezone.utc)
    weights = [DEMO_SEARCH_WEIGHTS.get(m.brand_name, 1) for m in medicines]
    missing = list(DEMO_NOT_FOUND)
    count = 0
    for i in range(DEMO_SEARCH_COUNT + sum(DEMO_NOT_FOUND.values())):
        near = random.choice(pharmacies)
        lat = round(near.latitude + random.gauss(0, 0.008), 3)   # about 1 km around it
        lng = round(near.longitude + random.gauss(0, 0.008), 3)
        hour = random.choices(range(24), weights=[1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 6, 6, 5, 5, 6, 7, 9, 10, 10, 8, 5, 2])[0]
        day = random.randint(0, DEMO_SEARCH_DAYS - 1)
        when = (now - timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0) \
            + timedelta(hours=hour - 3, minutes=random.randint(0, 59))   # Iraq time = UTC+3
        if when > now:
            when -= timedelta(days=1)
        if i < DEMO_SEARCH_COUNT:
            m = random.choices(medicines, weights=weights)[0]
            method = random.choices(["text", "barcode", "photo"], weights=[65, 25, 10])[0]
            query = m.brand_name if method != "barcode" else (m.barcodes[0].code if m.barcodes else m.brand_name)
            db.session.add(SearchLog(query=query, method=method, medicine_id=m.id, found=True,
                                     latitude=lat, longitude=lng, created_at=when))
        else:
            q = random.choices(missing, weights=[DEMO_NOT_FOUND[k] for k in missing])[0]
            db.session.add(SearchLog(query=q, method="text", medicine_id=None, found=False,
                                     latitude=lat, longitude=lng, created_at=when))
        count += 1
    return count


if __name__ == "__main__":
    seed(if_empty="--if-empty" in sys.argv)
