"""Business logic: expiry status, waste-risk forecast, NGO matching, allocation, impact."""
import os, math, datetime as dt
from sqlalchemy import func
from core import now
from models import *

CATS = ["Dairy & Eggs", "Bakery", "Fruits & Vegetables", "Meat & Fish", "Cooked Meals",
        "Grains & Staples", "Packaged", "Beverages", "Other"]
UNIT_KG = {"kg": 1, "g": .001, "liters": 1, "units": .5}  # units -> kg is an assumption
MEAL_KG = float(os.getenv("MEAL_KG", "0.5"))
CO2_PER_KG = float(os.getenv("CO2_PER_KG", "2.5"))
MAX_KM = 25

def today(): return dt.date.today()
def days_left(p): return (p.expiry - today()).days
def status(p):
    d = days_left(p)
    return "expired" if d < 0 else "today" if d == 0 else "soon" if d <= 3 else "fresh"

def notify(db, uid, text): db.add(Notification(user_id=uid, text=text))

def user_out(u):
    return dict(id=u.id, email=u.email, role=u.role, name=u.name, contact=u.contact, phone=u.phone,
                address=u.address, lat=u.lat, lng=u.lng, needs=[n for n in u.needs.split(",") if n], capacity=u.capacity)

# Waste risk: moving-average demand vs. stock over the days left (Prophet/LSTM are NOT integrated)
def forecast(db, p):
    since = today() - dt.timedelta(days=14)
    sold = db.query(func.coalesce(func.sum(Sale.qty), 0)).filter(Sale.product_id == p.id, Sale.day >= since).scalar()
    rate = sold / 14
    d = days_left(p)
    if d < 0: return dict(risk=100, daily_demand=round(rate, 2), reorder=0, confidence="n/a")
    excess = max(0, p.quantity - rate * d)
    ratio = excess / p.quantity if p.quantity > 0 else 0
    pressure = 1 if d == 0 else max(0, 1 - d / 7)
    reorder = max(0, math.ceil(rate * 7 - p.quantity))
    return dict(risk=round(100 * (0.6 * ratio + 0.4 * pressure)), daily_demand=round(rate, 2),
                reorder=reorder, confidence="moderate" if sold > 0 else "low (no sales recorded)")

def picked(db, l):
    return db.query(func.coalesce(func.sum(DonationRequest.quantity), 0)).filter(
        DonationRequest.listing_id == l.id, DonationRequest.status == "picked_up").scalar()

def remaining(db, l):
    used = db.query(func.coalesce(func.sum(DonationRequest.quantity), 0)).filter(
        DonationRequest.listing_id == l.id, DonationRequest.status.in_(["accepted", "picked_up"])).scalar()
    return max(0.0, l.quantity - used)

def committed(db, p):
    ls = db.query(Listing).filter(Listing.product_id == p.id, Listing.status.in_(["open", "allocated"])).all()
    return sum(l.quantity - picked(db, l) for l in ls)

def sweep(db):
    """Server-side expiry: close listings past their window or product expiry; expire their pending requests."""
    for l in db.query(Listing).filter(Listing.status.in_(["open", "allocated"])).all():
        p = db.get(Product, l.product_id)
        if p.expiry < today() or l.available_until <= now():
            l.status = "expired"
            for r in db.query(DonationRequest).filter_by(listing_id=l.id, status="pending"):
                r.status = "expired"
    db.commit()

def product_out(db, p):
    f = forecast(db, p); free = max(0, p.quantity - committed(db, p))
    return dict(id=p.id, name=p.name, barcode=p.barcode, category=p.category, quantity=p.quantity, unit=p.unit,
                unit_price=p.unit_price, purchased=str(p.purchased), expiry=str(p.expiry), supplier=p.supplier,
                storage=p.storage, days_left=days_left(p), status=status(p),
                donable=status(p) != "expired" and free > 0, free_quantity=free, **f)

def km(a, b):
    if None in (a.lat, a.lng, b.lat, b.lng): return None
    r = 6371; p1, p2 = math.radians(a.lat), math.radians(b.lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b.lng - a.lng) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))

def score(p, donor, ngo, rem):
    """35% category fit, 25% quantity fit, 25% proximity, 15% expiry urgency; returns score and reasons."""
    why = []
    needs = [n for n in ngo.needs.split(",") if n]
    if not needs: c = .6; why.append("No category preference set")
    elif p.category in needs: c = 1; why.append(f"{p.category} is on the needs list")
    else: c = 0; why.append(f"{p.category} is not on the needs list")
    if ngo.capacity: q = min(1, ngo.capacity / rem); why.append(f"Capacity {ngo.capacity:g} covers {round(q*100)}% of {rem:g} {p.unit}")
    else: q = .6; why.append("No capacity set")
    d = km(donor, ngo)
    if d is None: prox = .5; why.append("Distance unknown (location not set)")
    else: prox = max(0, 1 - d / MAX_KM); why.append(f"{d:.1f} km away")
    dl = days_left(p); urg = max(0, 1 - dl / 7)
    why.append("Expires today" if dl == 0 else f"Expires in {dl} day(s)")
    return round(100 * (.35 * c + .25 * q + .25 * prox + .15 * urg)), why, d

def listing_out(db, l, viewer=None):
    p = db.get(Product, l.product_id); donor = db.get(User, l.owner_id); rem = remaining(db, l)
    o = dict(id=l.id, product=p.name, category=p.category, unit=p.unit, quantity=l.quantity, remaining=rem,
             expiry=str(p.expiry), days_left=days_left(p), available_until=l.available_until.isoformat(),
             pickup_address=l.pickup_address, status=l.status, donor=donor.name, storage=p.storage)
    if viewer is not None and viewer.role == "ngo" and rem > 0:
        s, why, d = score(p, donor, viewer, rem); o.update(score=s, reasons=why, distance_km=d)
    return o

def impact(db, reqs):
    kg = 0; cat = {}; month = {}
    for r in reqs:
        if r.status != "picked_up": continue
        l = db.get(Listing, r.listing_id); p = db.get(Product, l.product_id)
        w = r.quantity * UNIT_KG.get(p.unit, .5); kg += w
        cat[p.category] = cat.get(p.category, 0) + w
        m = r.created_at.strftime("%Y-%m"); month[m] = month.get(m, 0) + w
    return dict(kg_diverted=round(kg, 1), meals=round(kg / MEAL_KG), co2_kg=round(kg * CO2_PER_KG, 1),
                by_category={k: round(v, 1) for k, v in cat.items()}, by_month=dict(sorted({k: round(v, 1) for k, v in month.items()}.items())),
                note="Estimates: 1 unit≈0.5 kg; meals and CO₂ use MEAL_KG and CO2_PER_KG from .env")
