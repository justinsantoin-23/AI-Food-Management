"""Creates the admin and DEMO data. Demo accounts are named 'Demo …'; delete foodwise.db to remove them."""
import os, secrets, datetime as dt
from core import Base, engine, SessionLocal, hash_pw
from models import *
Base.metadata.create_all(engine)
db = SessionLocal(); t = dt.date.today()
if db.query(User).count(): raise SystemExit("Database already has users; seed skipped.")
admin_pw = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(10)
def user(email, role, name, pw, **k): u = User(email=email, role=role, name=name, password_hash=hash_pw(pw), contact="Demo contact", phone="0000000000", **k); db.add(u); return u
user("admin@foodwise.local", "admin", "Administrator", admin_pw)
sm = user("store@demo.local", "supermarket", "Demo Fresh Mart", "Demo@1234", address="100 Main St", lat=12.97, lng=77.59)
user("hope@demo.local", "ngo", "Demo Hope Kitchen", "Demo@1234", address="12 Park Rd", lat=12.99, lng=77.60, needs="Cooked Meals,Bakery,Fruits & Vegetables", capacity=40)
user("seva@demo.local", "ngo", "Demo Seva Trust", "Demo@1234", address="55 Lake View", lat=13.15, lng=77.70, needs="Dairy & Eggs,Grains & Staples", capacity=15)
user("green@demo.local", "ngo", "Demo Green Hands", "Demo@1234", address="9 Hill St", lat=12.93, lng=77.55, needs="", capacity=None)
db.commit()
for n, c, q, u, d, price in [("Bread loaves", "Bakery", 30, "units", 0, 1.5), ("Tomatoes", "Fruits & Vegetables", 25, "kg", 1, 2.0),
                             ("Curd", "Dairy & Eggs", 12, "liters", -1, 2.9), ("Rice", "Grains & Staples", 50, "kg", 120, 1.2), ("Milk", "Dairy & Eggs", 40, "liters", 3, 1.1)]:
    p = Product(owner_id=sm.id, name=n, category=c, quantity=q, unit=u, unit_price=price, purchased=t - dt.timedelta(days=2),
                expiry=t + dt.timedelta(days=d), supplier="Demo Supplier", barcode=f"DEMO{abs(hash(n)) % 10**8}"); db.add(p); db.flush()
    for i in range(1, 8): db.add(Sale(product_id=p.id, qty=max(1, q / 25), day=t - dt.timedelta(days=i)))
db.commit()
print("Seeded. Admin: admin@foodwise.local /", admin_pw, "| Demo store: store@demo.local / Demo@1234 | NGOs: hope|seva|green@demo.local / Demo@1234")
