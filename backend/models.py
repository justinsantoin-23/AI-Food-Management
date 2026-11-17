import datetime as dt
from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from core import Base, now

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # supermarket | ngo | admin
    name: Mapped[str] = mapped_column(String(200))
    contact: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs: Mapped[str] = mapped_column(Text, default="")        # NGO: comma-separated categories
    capacity: Mapped[float | None] = mapped_column(Float, nullable=True)  # NGO: max quantity per pickup
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

class Product(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(60))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="units")
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    purchased: Mapped[dt.date] = mapped_column(Date)
    expiry: Mapped[dt.date] = mapped_column(Date, index=True)
    supplier: Mapped[str] = mapped_column(String(200), default="")
    storage: Mapped[str] = mapped_column(String(300), default="")

class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)
    qty: Mapped[float] = mapped_column(Float)
    day: Mapped[dt.date] = mapped_column(Date)

class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    available_until: Mapped[dt.datetime] = mapped_column(DateTime)
    pickup_address: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|allocated|expired
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

class DonationRequest(Base):
    __tablename__ = "donation_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted|rejected|picked_up|expired
    pickup_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(String(400))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
