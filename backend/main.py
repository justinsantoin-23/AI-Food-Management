import os, datetime as dt
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from core import Base, engine, get_db, hash_pw, check_pw, make_token, current_user, require, now
from models import *
import services as S

Base.metadata.create_all(engine)  # for production use Alembic migrations
app = FastAPI(title="FoodWise AI Backend", version="1.0.0",
              description="Surplus identification and redistribution for supermarkets and NGOs")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])

def err(code, msg): raise HTTPException(code, msg)

# ---------- Auth ----------
class Reg(BaseModel):
    role: Literal["supermarket", "ngo"]
    name: str = Field(min_length=2); contact: str = Field(min_length=2); phone: str = Field(min_length=5)
    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"); address: str = Field(min_length=3); password: str = Field(min_length=6)
    lat: float | None = Field(None, ge=-90, le=90); lng: float | None = Field(None, ge=-180, le=180)
    needs: str = ""; capacity: float | None = Field(None, gt=0)

class Login(BaseModel): email: str; password: str

@app.post("/api/auth/register", status_code=201, tags=["Authentication"])
def register(b: Reg, db=Depends(get_db)):
    email = b.email.lower()
    if db.query(User).filter_by(email=email).first(): err(409, "That email is already registered.")
    u = User(email=email, password_hash=hash_pw(b.password), **b.model_dump(exclude={"email", "password"}))
    db.add(u); db.commit()
    return {"token": make_token(u.id), "user": S.user_out(u)}

@app.post("/api/auth/login", tags=["Authentication"])
def login(b: Login, db=Depends(get_db)):
    u = db.query(User).filter_by(email=b.email.lower()).first()
    if not u or not check_pw(b.password, u.password_hash): err(401, "Email or password is incorrect.")
    return {"token": make_token(u.id), "user": S.user_out(u)}

@app.get("/api/auth/me", tags=["Authentication"])
def me(u=Depends(current_user)): return S.user_out(u)

# ---------- Inventory ----------
class ProductIn(BaseModel):
    name: str = Field(min_length=1); barcode: str | None = None; category: str
    quantity: float = Field(gt=0); unit: Literal["units", "kg", "g", "liters"] = "units"
    unit_price: float = Field(ge=0); purchased: dt.date; expiry: dt.date; supplier: str = ""; storage: str = ""

def check_product(b: ProductIn):
    if b.category not in S.CATS: err(422, "Choose a valid category.")
    if b.expiry < b.purchased: err(422, "Expiry date can't be before the purchase date.")

def owned(db, u, pid):
    p = db.get(Product, pid)
    if not p or p.owner_id != u.id: err(404, "Product not found.")
    return p

SM = Depends(require("supermarket"))

@app.get("/api/categories", tags=["Inventory"])
def cats(): return S.CATS

@app.post("/api/inventory", status_code=201, tags=["Inventory"])
def add_product(b: ProductIn, u=SM, db=Depends(get_db)):
    check_product(b); p = Product(owner_id=u.id, **b.model_dump()); db.add(p); db.commit()
    return S.product_out(db, p)

@app.get("/api/inventory", tags=["Inventory"])
def list_products(q: str = "", u=SM, db=Depends(get_db)):
    ps = db.query(Product).filter_by(owner_id=u.id).order_by(Product.expiry).all()
    ql = q.lower()
    return [S.product_out(db, p) for p in ps if ql in p.name.lower() or ql in (p.supplier or "").lower() or ql in p.category.lower()]

@app.get("/api/inventory/barcode/{code}", tags=["Inventory"])
def by_barcode(code: str, u=SM, db=Depends(get_db)):
    p = db.query(Product).filter_by(owner_id=u.id, barcode=code).first()
    if not p and code.isdigit(): p = db.get(Product, int(code))
    if not p or p.owner_id != u.id: err(404, "No product with that barcode or ID.")
    return S.product_out(db, p)

@app.put("/api/inventory/{pid}", tags=["Inventory"])
def edit_product(pid: int, b: ProductIn, u=SM, db=Depends(get_db)):
    check_product(b); p = owned(db, u, pid)
    if b.quantity < S.committed(db, p): err(409, "Quantity is below what's already promised to donations.")
    for k, v in b.model_dump().items(): setattr(p, k, v)
    db.commit(); return S.product_out(db, p)

@app.delete("/api/inventory/{pid}", tags=["Inventory"])
def delete_product(pid: int, u=SM, db=Depends(get_db)):
    p = owned(db, u, pid)
    if db.query(Listing).filter_by(product_id=pid).first(): err(409, "This product has donation listings and can't be deleted.")
    db.query(Sale).filter_by(product_id=pid).delete(); db.delete(p); db.commit(); return {"ok": True}

class SaleIn(BaseModel): qty: float = Field(gt=0)

@app.post("/api/inventory/{pid}/sale", tags=["Inventory"])
def record_sale(pid: int, b: SaleIn, u=SM, db=Depends(get_db)):
    p = owned(db, u, pid)
    if b.qty > p.quantity - S.committed(db, p): err(409, "Not enough unreserved stock for that sale.")
    p.quantity -= b.qty; db.add(Sale(product_id=pid, qty=b.qty, day=S.today())); db.commit()
    return S.product_out(db, p)

@app.get("/api/alerts", tags=["Alerts"])
def alerts(u=SM, db=Depends(get_db)):
    out = []
    for p in db.query(Product).filter_by(owner_id=u.id).order_by(Product.expiry):
        s = S.status(p); d = S.days_left(p)
        if s == "fresh": continue
        msg = {"expired": f"Expired {-d} day(s) ago. Unsafe for consumption and must not be donated.",
               "today": "Expires today. Donate or discount it now.",
               "soon": f"Expires in {d} day(s). Plan a donation or markdown."}[s]
        out.append(dict(product_id=p.id, name=p.name, category=p.category, status=s, days_left=d,
                        quantity=p.quantity, unit=p.unit, message=f"{p.quantity:g} {p.unit} of '{p.name}': {msg}"))
    return out

@app.get("/api/dashboard", tags=["Dashboard"])
def dashboard(u=SM, db=Depends(get_db)):
    S.sweep(db)
    ps = db.query(Product).filter_by(owner_id=u.id).all()
    counts = {"fresh": 0, "soon": 0, "today": 0, "expired": 0}; cat = {}
    for p in ps:
        counts[S.status(p)] += 1; c = cat.setdefault(p.category, {"category": p.category, "items": 0, "units": 0}); c["items"] += 1; c["units"] += p.quantity
    urgent = sorted((S.product_out(db, p) for p in ps), key=lambda x: (-x["risk"], x["days_left"]))[:5]
    reqs = db.query(DonationRequest).join(Listing).filter(Listing.owner_id == u.id).all()
    return dict(products=len(ps), units=sum(p.quantity for p in ps), value=round(sum(p.quantity * p.unit_price for p in ps), 2),
                counts=counts, by_category=list(cat.values()), urgent=urgent,
                pending_requests=sum(r.status == "pending" for r in reqs), impact=S.impact(db, reqs))

# ---------- Listings & matching ----------
class ListingIn(BaseModel):
    product_id: int; quantity: float = Field(gt=0); available_until: dt.datetime; pickup_address: str = ""

@app.post("/api/listings", status_code=201, tags=["Redistribution"])
def create_listing(b: ListingIn, u=SM, db=Depends(get_db)):
    S.sweep(db); p = owned(db, u, b.product_id)
    if S.status(p) == "expired": err(409, "Expired food can't be listed.")
    if b.available_until <= now(): err(422, "Pickup window must end in the future.")
    if b.available_until.date() > p.expiry: err(422, "Pickup window can't end after the expiry date.")
    free = p.quantity - S.committed(db, p)
    if b.quantity > free: err(409, f"Only {free:g} {p.unit} is unreserved.")
    l = Listing(product_id=p.id, owner_id=u.id, quantity=b.quantity, available_until=b.available_until,
                pickup_address=b.pickup_address or u.address)
    db.add(l); db.commit()
    if S.days_left(p) <= 1:
        for n in db.query(User).filter_by(role="ngo"): S.notify(db, n.id, f"Urgent: {b.quantity:g} {p.unit} of {p.name} from {u.name} expires {'today' if S.days_left(p)==0 else 'tomorrow'}.")
        db.commit()
    return S.listing_out(db, l)

@app.get("/api/listings", tags=["Redistribution"])
def listings(u=Depends(require("supermarket", "ngo", "admin")), db=Depends(get_db)):
    S.sweep(db); q = db.query(Listing)
    if u.role == "supermarket": q = q.filter_by(owner_id=u.id)
    elif u.role == "ngo": q = q.filter_by(status="open")
    out = [S.listing_out(db, l, u) for l in q.order_by(Listing.created_at.desc())]
    if u.role == "ngo": out = [o for o in out if o["remaining"] > 0]; out.sort(key=lambda o: -o.get("score", 0))
    return out

@app.get("/api/listings/{lid}/matches", tags=["Redistribution"])
def matches(lid: int, u=SM, db=Depends(get_db)):
    S.sweep(db); l = db.get(Listing, lid)
    if not l or l.owner_id != u.id: err(404, "Listing not found.")
    p = db.get(Product, l.product_id); rem = S.remaining(db, l)
    if rem <= 0 or l.status != "open": return []
    out = []
    for n in db.query(User).filter_by(role="ngo"):
        s, why, d = S.score(p, u, n, rem); out.append(dict(ngo_id=n.id, ngo=n.name, score=s, reasons=why, distance_km=d))
    return sorted(out, key=lambda x: -x["score"])

class ReqIn(BaseModel): listing_id: int; quantity: float = Field(gt=0)

@app.post("/api/requests", status_code=201, tags=["Redistribution"])
def create_request(b: ReqIn, u=Depends(require("ngo")), db=Depends(get_db)):
    S.sweep(db); l = db.query(Listing).filter_by(id=b.listing_id).with_for_update().first()
    if not l or l.status != "open": err(409, "This listing is no longer available.")
    p = db.get(Product, l.product_id)
    if S.status(p) == "expired": err(409, "Expired food can't be requested.")
    if b.quantity > S.remaining(db, l): err(409, f"Only {S.remaining(db, l):g} {p.unit} left.")
    if db.query(DonationRequest).filter(DonationRequest.listing_id == l.id, DonationRequest.ngo_id == u.id,
                                        DonationRequest.status.in_(["pending", "accepted"])).first():
        err(409, "You already have an active request for this listing.")
    r = DonationRequest(listing_id=l.id, ngo_id=u.id, quantity=b.quantity); db.add(r)
    S.notify(db, l.owner_id, f"{u.name} requested {b.quantity:g} {p.unit} of {p.name}."); db.commit()
    return {"id": r.id}

def req_out(db, r):
    l = db.get(Listing, r.listing_id); p = db.get(Product, l.product_id)
    return dict(id=r.id, listing_id=l.id, product=p.name, unit=p.unit, quantity=r.quantity, status=r.status,
                ngo=db.get(User, r.ngo_id).name, donor=db.get(User, l.owner_id).name, pickup_address=l.pickup_address,
                pickup_time=r.pickup_time.isoformat() if r.pickup_time else None, created_at=r.created_at.isoformat())

@app.get("/api/requests", tags=["Redistribution"])
def requests_(u=Depends(require("supermarket", "ngo")), db=Depends(get_db)):
    S.sweep(db); q = db.query(DonationRequest)
    q = q.filter_by(ngo_id=u.id) if u.role == "ngo" else q.join(Listing).filter(Listing.owner_id == u.id)
    return [req_out(db, r) for r in q.order_by(DonationRequest.created_at.desc())]

class Decide(BaseModel): accept: bool; pickup_time: dt.datetime | None = None

def own_request(db, u, rid):
    r = db.get(DonationRequest, rid)
    if not r or db.get(Listing, r.listing_id).owner_id != u.id: err(404, "Request not found.")
    return r

@app.post("/api/requests/{rid}/decide", tags=["Redistribution"])
def decide(rid: int, b: Decide, u=SM, db=Depends(get_db)):
    S.sweep(db); r = own_request(db, u, rid)
    if r.status != "pending": err(409, f"This request is already {r.status}.")
    l = db.query(Listing).filter_by(id=r.listing_id).with_for_update().one(); p = db.get(Product, l.product_id)
    if b.accept:
        if l.status != "open": err(409, "Listing is no longer open.")
        if r.quantity > S.remaining(db, l): err(409, "Not enough quantity left to accept this request.")
        pt = b.pickup_time or l.available_until
        if pt <= now() or pt > l.available_until: err(422, "Pickup time must be in the future and inside the pickup window.")
        r.status, r.pickup_time = "accepted", pt
        if S.remaining(db, l) <= 0: l.status = "allocated"
        S.notify(db, r.ngo_id, f"{u.name} accepted your request for {p.name}. Pickup {pt:%d %b %H:%M} at {l.pickup_address}.")
    else:
        r.status = "rejected"; S.notify(db, r.ngo_id, f"{u.name} declined your request for {p.name}.")
    db.commit(); return req_out(db, r)

@app.post("/api/requests/{rid}/picked-up", tags=["Redistribution"])
def picked_up(rid: int, u=SM, db=Depends(get_db)):
    r = own_request(db, u, rid)
    if r.status != "accepted": err(409, "Only accepted requests can be marked picked up.")
    l = db.get(Listing, r.listing_id); p = db.get(Product, l.product_id)
    r.status = "picked_up"; p.quantity = max(0, p.quantity - r.quantity)
    S.notify(db, r.ngo_id, f"Pickup of {p.name} confirmed. Thank you."); db.commit(); return req_out(db, r)

# ---------- Impact, notifications, admin ----------
@app.get("/api/impact", tags=["Analytics"])
def impact(u=Depends(require("supermarket", "ngo", "admin")), db=Depends(get_db)):
    q = db.query(DonationRequest)
    if u.role == "ngo": q = q.filter_by(ngo_id=u.id)
    elif u.role == "supermarket": q = q.join(Listing).filter(Listing.owner_id == u.id)
    return S.impact(db, q.all())

@app.get("/api/notifications", tags=["Notifications"])
def notifications(u=Depends(current_user), db=Depends(get_db)):
    ns = db.query(Notification).filter_by(user_id=u.id).order_by(Notification.created_at.desc()).limit(30).all()
    return [dict(id=n.id, text=n.text, read=n.read, created_at=n.created_at.isoformat()) for n in ns]

@app.post("/api/notifications/read-all", tags=["Notifications"])
def read_all(u=Depends(current_user), db=Depends(get_db)):
    db.query(Notification).filter_by(user_id=u.id, read=False).update({"read": True}); db.commit(); return {"ok": True}

@app.get("/api/admin/overview", tags=["Admin"])
def admin(u=Depends(require("admin")), db=Depends(get_db)):
    S.sweep(db); cnt = lambda m, **f: db.query(m).filter_by(**f).count()
    return dict(users=[dict(id=x.id, name=x.name, email=x.email, role=x.role, created_at=x.created_at.isoformat()) for x in db.query(User).order_by(User.id)],
                supermarkets=cnt(User, role="supermarket"), ngos=cnt(User, role="ngo"), products=cnt(Product),
                listings={s: cnt(Listing, status=s) for s in ("open", "allocated", "expired")},
                requests={s: cnt(DonationRequest, status=s) for s in ("pending", "accepted", "picked_up", "rejected", "expired")},
                impact=S.impact(db, db.query(DonationRequest).all()))

@app.get("/health", tags=["Health"])
def health(): return {"status": "ok"}

_fe = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_fe): app.mount("/", StaticFiles(directory=_fe, html=True), name="frontend")
