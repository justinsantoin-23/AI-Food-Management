import os, sys, datetime as dt
os.environ["DATABASE_URL"] = "sqlite:///./test_foodwise.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient
from main import app
from core import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

c = TestClient(app)
def reg(role, email, **k):
    r = c.post("/api/auth/register", json=dict(role=role, name="X Org", contact="Ann", phone="12345", email=email, address="Addr", password="secret1", **k))
    assert r.status_code == 201, r.text; return {"Authorization": "Bearer " + r.json()["token"]}
def test_full_flow():
    sm, ngo = reg("supermarket", "sm@t.io", lat=1, lng=1), reg("ngo", "ngo@t.io", lat=1.01, lng=1, needs="Bakery", capacity=10)
    t = dt.date.today()
    mk = lambda days: c.post("/api/inventory", headers=sm, json=dict(name="P", category="Bakery", quantity=10, unit="kg", unit_price=1, purchased=str(t - dt.timedelta(days=3)), expiry=str(t + dt.timedelta(days=days)))).json()
    good, old = mk(1), mk(-1)
    until = (dt.datetime.now() + dt.timedelta(hours=5)).isoformat()
    assert c.post("/api/listings", headers=sm, json=dict(product_id=old["id"], quantity=1, available_until=until)).status_code == 409   # expired
    assert c.post("/api/listings", headers=sm, json=dict(product_id=good["id"], quantity=11, available_until=until)).status_code == 409  # over quantity
    l = c.post("/api/listings", headers=sm, json=dict(product_id=good["id"], quantity=10, available_until=until)).json()
    assert c.get("/api/listings", headers=ngo).json()[0]["score"] > 50
    assert c.post("/api/requests", headers=ngo, json=dict(listing_id=l["id"], quantity=11)).status_code == 409
    r = c.post("/api/requests", headers=ngo, json=dict(listing_id=l["id"], quantity=6)); assert r.status_code == 201
    assert c.post("/api/requests", headers=ngo, json=dict(listing_id=l["id"], quantity=1)).status_code == 409  # duplicate
    rid = c.get("/api/requests", headers=sm).json()[0]["id"]
    assert c.post(f"/api/requests/{rid}/decide", headers=ngo, json=dict(accept=True)).status_code == 403  # role check
    assert c.post(f"/api/requests/{rid}/decide", headers=sm, json=dict(accept=True)).json()["status"] == "accepted"
    assert c.post(f"/api/requests/{rid}/picked-up", headers=sm).json()["status"] == "picked_up"
    assert c.get("/api/impact", headers=sm).json()["kg_diverted"] == 6
