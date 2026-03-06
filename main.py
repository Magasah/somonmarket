"""Somon Market backend (FastAPI + SQLAlchemy).

Run locally:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import base64 as _b64
from collections.abc import Generator
from datetime import datetime
import hmac
import logging
import os
import secrets

import urllib.request as _urllib_request
import json as _json_mod

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Admin secret token — read from .env, fallback to random per-session
_ADMIN_TOKEN: str = os.getenv("ADMIN_SECRET", secrets.token_hex(16))


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


DATABASE_URL = "sqlite:///./somon_market.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    """Marketplace user entity."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tg_id: Mapped[int] = mapped_column("telegram_id", Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    role: Mapped[str] = mapped_column(String(20), default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    face_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    kyc_status: Mapped[str] = mapped_column(String(20), default="none")  # none | pending | approved | rejected
    kyc_photo_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    referral_code: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    referred_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Item(Base):
    """Marketplace item listed by a seller."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    game_category: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float)
    secret_data: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Order(Base):
    """Purchase order connecting buyer → item."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), index=True)
    seller_id: Mapped[int] = mapped_column(Integer, index=True)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    # PENDING → PAID → DELIVERED → COMPLETED | DISPUTED
    secret_data: Mapped[str] = mapped_column(Text, default="")  # копия при создании
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Review(Base):
    """Review left by buyer after order completion."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), unique=True)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)   # 1-5
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BalanceDeposit(Base):
    """Manual receipt-based balance top-up request."""

    __tablename__ = "deposits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    receipt_path: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str


class GameItem(BaseModel):
    """Single game catalog entry returned to frontend."""

    name: str
    isNew: bool = False


class GamesResponse(BaseModel):
    """Games catalog grouped by platform/application type."""

    model_config = ConfigDict(extra="forbid")

    pc_games: list[GameItem]
    mobile_games: list[GameItem]
    apps: list[GameItem]


class UserCreate(BaseModel):
    """Schema for telegram user sync from frontend."""

    tg_id: int
    username: str


class UserResponse(BaseModel):
    """Schema for returning user data to frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tg_id: int
    username: str | None
    balance: float
    role: str
    face_verified: bool = False
    kyc_status: str = "none"
    sales_count: int = 0
    avg_rating: float | None = None


class ItemCreate(BaseModel):
    """Schema for creating a marketplace item."""

    game_category: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    secret_data: str = Field(..., min_length=1)
    seller_id: int


class ItemResponse(BaseModel):
    """Schema for returning item data without sensitive secret payload."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    game_category: str
    title: str
    description: str
    price: float
    status: str
    created_at: datetime | None = None


class OrderCreate(BaseModel):
    buyer_id: int
    item_id: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    buyer_id: int
    item_id: int
    seller_id: int
    price: float
    status: str
    secret_data: str = ""
    created_at: datetime | None = None


class ReviewCreate(BaseModel):
    order_id: int
    buyer_id: int
    rating: int   # 1-5
    comment: str = ""


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    buyer_id: int
    seller_id: int
    rating: int
    comment: str
    created_at: datetime | None = None


# ── Deposit schemas ────────────────────────────────────────────────────────────

class DepositCreate(BaseModel):
    user_id: int
    amount: float = Field(..., gt=0, le=100_000)
    receipt_base64: str  # data:image/jpeg;base64,...

    @field_validator("receipt_base64")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        raw = v.split(",", 1)[1] if "," in v else v
        try:
            _b64.b64decode(raw, validate=True)
        except Exception:
            raise ValueError("Invalid base64 image data")
        return v


class DepositResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: float
    status: str
    created_at: datetime


app = FastAPI(title="Somon Market API")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# CORS: Telegram WebApp запросы идут с origin telegram.org / web.telegram.org
# Для локальной разработки разрешаем все, в продакшене укажите точные origins в .env
_ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://web.telegram.org,https://telegram.org,http://localhost:8000,http://127.0.0.1:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def verify_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """FastAPI dependency — проверяет admin-token из заголовка X-Admin-Token."""
    if not x_admin_token or not hmac.compare_digest(x_admin_token, _ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden: invalid admin token")

# Create tables on startup/first run.
Base.metadata.create_all(bind=engine)


def ensure_users_table_columns() -> None:
    """Patch legacy SQLite users schema to required columns for current API."""
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        ).scalar()
        if not exists:
            return

        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}

        if "balance" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN balance FLOAT NOT NULL DEFAULT 0.0"))

        if "role" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'USER'"))

        if "is_active" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

        if "face_verified" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN face_verified BOOLEAN NOT NULL DEFAULT 0"))

        if "kyc_status" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN kyc_status VARCHAR(20) NOT NULL DEFAULT 'none'"))

        if "kyc_photo_path" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN kyc_photo_path VARCHAR(300)"))

        if "created_at" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
            conn.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

        if "referral_code" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR(16)"))
        if "referred_by" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN referred_by INTEGER"))


def ensure_items_table_columns() -> None:
    """Patch legacy SQLite items schema to required columns for current API.

    NOTE: If you still face SQLite column mismatch errors after updates,
    delete somon_market.db and restart the app to recreate the schema from scratch.
    """
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        ).scalar()
        if not exists:
            return

        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(items)"))}

        if "seller_id" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN seller_id INTEGER NOT NULL DEFAULT 0"))

        if "game_category" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN game_category VARCHAR(120) NOT NULL DEFAULT ''"))

        if "title" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"))

        if "description" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN description TEXT NOT NULL DEFAULT ''"))

        if "price" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN price FLOAT NOT NULL DEFAULT 0"))

        if "secret_data" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN secret_data TEXT NOT NULL DEFAULT ''"))

        if "status" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'"))


ensure_users_table_columns()
ensure_items_table_columns()


def ensure_items_extra_columns() -> None:
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        ).scalar()
        if not exists:
            return
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(items)"))}
        if "created_at" not in columns:
            conn.execute(text("ALTER TABLE items ADD COLUMN created_at DATETIME"))
            conn.execute(text("UPDATE items SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))


ensure_items_extra_columns()


def ensure_orders_table() -> None:
    """Patch items and ensure orders table has all required columns."""
    with engine.begin() as conn:
        # ── items: migrate old schema (price_tjs → price) ─────────────────────
        items_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(items)"))}
        if "price_tjs" in items_cols and "price" not in items_cols:
            logger.info("Migrating items table: price_tjs → price")
            conn.execute(text("""
                CREATE TABLE items_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL REFERENCES users(id),
                    game_category VARCHAR(120) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL,
                    price FLOAT NOT NULL DEFAULT 0,
                    secret_data TEXT NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                    created_at DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO items_new (id, seller_id, game_category, title, description,
                                       price, secret_data, status, created_at)
                SELECT id, seller_id, game_category, title, description,
                       COALESCE(price_tjs, 0),
                       COALESCE(secret_data, ''),
                       COALESCE(status, 'ACTIVE'),
                       created_at
                FROM items
            """))
            conn.execute(text("DROP TABLE items"))
            conn.execute(text("ALTER TABLE items_new RENAME TO items"))
            logger.info("items table migrated successfully")
        elif "price_tjs" in items_cols or "is_sold" in items_cols:
            # Old schema columns exist — recreate the table with fresh schema
            logger.info("Migrating items table: removing legacy columns (price_tjs/is_sold)")
            price_col = "price_tjs" if "price_tjs" in items_cols and "price" not in items_cols else "price"
            conn.execute(text("""
                CREATE TABLE items_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL REFERENCES users(id),
                    game_category VARCHAR(120) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price FLOAT NOT NULL DEFAULT 0,
                    secret_data TEXT NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                    created_at DATETIME
                )
            """))
            conn.execute(text(f"""
                INSERT INTO items_new (id, seller_id, game_category, title, description,
                                       price, secret_data, status, created_at)
                SELECT id, seller_id, game_category, title,
                       COALESCE(description, ''),
                       COALESCE({price_col}, 0),
                       COALESCE(secret_data, ''),
                       COALESCE(status, 'ACTIVE'),
                       created_at
                FROM items
            """))
            conn.execute(text("DROP TABLE items"))
            conn.execute(text("ALTER TABLE items_new RENAME TO items"))
            logger.info("items table migrated successfully")

        # items: добавляем created_at если нет
        items_cols2 = {row[1] for row in conn.execute(text("PRAGMA table_info(items)"))}
        if "created_at" not in items_cols2:
            conn.execute(text("ALTER TABLE items ADD COLUMN created_at DATETIME"))
            conn.execute(text("UPDATE items SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

        # ── orders: миграция/создание таблицы ────────────────────────────────────
        orders_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        ).scalar()
        if orders_exists:
            ord_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(orders)"))}
            legacy_cols = {"listing_id", "price_tjs", "manual_payment_details"}
            if legacy_cols & ord_cols:
                # Old schema detected — recreate orders with current schema
                logger.info("Migrating orders table: removing legacy columns")
                price_col = "price_tjs" if "price_tjs" in ord_cols and "price" not in ord_cols else "COALESCE(price, 0)"
                item_col  = "listing_id" if "listing_id" in ord_cols and "item_id" not in ord_cols else "COALESCE(item_id, 0)"
                conn.execute(text("""
                    CREATE TABLE orders_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        buyer_id INTEGER NOT NULL REFERENCES users(id),
                        item_id INTEGER NOT NULL DEFAULT 0,
                        seller_id INTEGER NOT NULL DEFAULT 0,
                        price FLOAT NOT NULL DEFAULT 0,
                        status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
                        secret_data TEXT NOT NULL DEFAULT '',
                        created_at DATETIME,
                        confirmed_at DATETIME
                    )
                """))
                conn.execute(text(f"""
                    INSERT INTO orders_new
                        (id, buyer_id, item_id, seller_id, price, status,
                         secret_data, created_at, confirmed_at)
                    SELECT id, buyer_id,
                           COALESCE({item_col}, 0),
                           COALESCE(seller_id, 0),
                           COALESCE({price_col}, 0),
                           COALESCE(status, 'PENDING'),
                           COALESCE(secret_data, ''),
                           created_at,
                           confirmed_at
                    FROM orders
                """))
                conn.execute(text("DROP TABLE orders"))
                conn.execute(text("ALTER TABLE orders_new RENAME TO orders"))
                logger.info("orders table migrated successfully")
            else:
                # Table exists with correct schema — add any missing columns
                if "secret_data" not in ord_cols:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN secret_data TEXT NOT NULL DEFAULT ''"))
                if "confirmed_at" not in ord_cols:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN confirmed_at DATETIME"))
                if "created_at" not in ord_cols:
                    conn.execute(text("ALTER TABLE orders ADD COLUMN created_at DATETIME"))
                    conn.execute(text("UPDATE orders SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))


ensure_orders_table()


@app.get("/", response_class=HTMLResponse)
def serve_index(request: Request) -> HTMLResponse:
    """Serve the SPA — main entry point for Telegram WebApp and browsers."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health_check() -> HealthResponse:
    """Simple health endpoint."""
    return HealthResponse(status="Somon Market Backend is running!")


@app.get("/api/admin/check")
def admin_check_token(token: str = "") -> dict:
    """validate admin token — used by WebApp for auto-login via URL param ?at=TOKEN."""
    if not token or token != _ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return {"ok": True, "role": "admin"}


@app.get("/web", response_class=HTMLResponse)
def render_webapp(request: Request) -> HTMLResponse:
    """Render the SPA for Telegram WebApp and browser testing."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/games", response_model=GamesResponse)
def get_games(_: Session = Depends(get_db)) -> GamesResponse:
    """Return MARKET_DATA-like catalog for frontend Home sections."""
    return GamesResponse(
        pc_games=[
            GameItem(name="Counter-Strike 2", isNew=False),
            GameItem(name="Roblox", isNew=True),
            GameItem(name="Resident Evil Requiem", isNew=True),
            GameItem(name="Genshin Impact", isNew=True),
            GameItem(name="Fortnite", isNew=False),
            GameItem(name="Valorant", isNew=False),
            GameItem(name="Minecraft", isNew=False),
            GameItem(name="GTA 5 Online", isNew=False),
            GameItem(name="Dota 2", isNew=False),
            GameItem(name="Rust", isNew=False),
            GameItem(name="PUBG", isNew=False),
            GameItem(name="Танки ПК", isNew=True),
        ],
        mobile_games=[
            GameItem(name="PUBG Mobile", isNew=False),
            GameItem(name="Brawl Stars", isNew=False),
            GameItem(name="Clash Royale", isNew=True),
            GameItem(name="Clash of Clans", isNew=False),
            GameItem(name="Standoff 2", isNew=True),
            GameItem(name="Mobile Legends", isNew=True),
            GameItem(name="Free Fire", isNew=False),
            GameItem(name="Call of Duty: Mobile", isNew=False),
            GameItem(name="Black Russia", isNew=False),
            GameItem(name="Rush Royale", isNew=False),
        ],
        apps=[
            GameItem(name="Telegram", isNew=False),
            GameItem(name="Steam", isNew=False),
            GameItem(name="PlayStation", isNew=False),
            GameItem(name="TikTok", isNew=False),
            GameItem(name="Spotify", isNew=False),
            GameItem(name="App Store", isNew=False),
            GameItem(name="Discord", isNew=False),
            GameItem(name="YouTube", isNew=False),
            GameItem(name="Midjourney", isNew=False),
            GameItem(name="Razer Gold", isNew=True),
            GameItem(name="EA Play", isNew=True),
            GameItem(name="Epic Games", isNew=True),
            GameItem(name="Copilot", isNew=True),
        ],
    )


@app.post("/api/auth/telegram", response_model=UserResponse)
def auth_telegram(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Sync telegram user into local DB and return user profile."""
    user = db.query(User).filter(User.tg_id == payload.tg_id).first()

    if user is None:
        user = User(
            tg_id=payload.tg_id,
            username=payload.username,
            balance=0.0,
            role="USER",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if payload.username:
        user.username = payload.username
        db.commit()
        db.refresh(user)

    return user


@app.post("/api/items", response_model=ItemResponse)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemResponse:
    """Create a new marketplace item."""
    item = Item(
        seller_id=payload.seller_id,
        game_category=payload.game_category,
        title=payload.title,
        description=payload.description,
        price=payload.price,
        secret_data=payload.secret_data,
        status="ACTIVE",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/items", response_model=list[ItemResponse])
def get_items(game_category: str | None = None, db: Session = Depends(get_db)) -> list[ItemResponse]:
    """Return active marketplace items with optional category filter."""
    query = db.query(Item).filter(Item.status == "ACTIVE")
    if game_category:
        query = query.filter(Item.game_category == game_category)
    return query.order_by(Item.id.desc()).all()


@app.get("/api/items/{item_id}", response_model=ItemResponse)
def get_item_by_id(item_id: int, db: Session = Depends(get_db)) -> ItemResponse:
    """Return one marketplace item by id."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/api/users/{user_id}/items", response_model=list[ItemResponse])
def get_user_items(user_id: int, db: Session = Depends(get_db)) -> list[ItemResponse]:
    """Return all items for the seller dashboard, regardless of item status."""
    return db.query(Item).filter(Item.seller_id == user_id).order_by(Item.id.desc()).all()


@app.delete("/api/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Delete marketplace item by ID."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()
    return {"detail": "Item deleted"}


# ── Admin endpoints ────────────────────────────────────────────────────────────

@app.get("/api/admin/users", response_model=list[UserResponse])
def admin_get_users(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
) -> list[UserResponse]:
    """Return all users for admin panel. Requires X-Admin-Token header."""
    return db.query(User).order_by(User.id.desc()).all()


@app.patch("/api/admin/users/{user_id}/ban")
def admin_ban_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
) -> dict[str, str]:
    """Ban a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"detail": f"User {user_id} banned"}


@app.patch("/api/admin/users/{user_id}/unban")
def admin_unban_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
) -> dict[str, str]:
    """Unban a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"detail": f"User {user_id} unbanned"}


# ── KYC endpoints ───────────────────────────────────────────────────────────────────

class KycSubmit(BaseModel):
    """KYC face photo submission."""
    user_id: int
    photo_base64: str  # data:image/jpeg;base64,...


@app.post("/api/kyc/submit")
def kyc_submit(payload: KycSubmit, db: Session = Depends(get_db)) -> dict:
    """Save face photo and mark user as KYC pending."""
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Decode and save photo
    import base64 as _b64
    try:
        raw = payload.photo_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        photo_bytes = _b64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")

    os.makedirs("uploads/faces", exist_ok=True)
    filename = f"kyc_{user.id}_{int(datetime.utcnow().timestamp())}.jpg"
    filepath = f"uploads/faces/{filename}"
    with open(filepath, "wb") as f:
        f.write(photo_bytes)

    user.kyc_status = "pending"
    user.kyc_photo_path = filepath
    db.commit()
    return {"ok": True, "status": "pending"}


@app.get("/api/kyc/pending")
def kyc_pending(db: Session = Depends(get_db)) -> list:
    """Admin: return all users with pending KYC."""
    users = db.query(User).filter(User.kyc_status == "pending").all()
    result = []
    for u in users:
        result.append({
            "id": u.id, "username": u.username, "tg_id": u.tg_id,
            "kyc_status": u.kyc_status,
            "photo_url": f"/{u.kyc_photo_path}" if u.kyc_photo_path else None,
        })
    return result


@app.post("/api/kyc/{user_id}/approve")
def kyc_approve(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Admin: approve user KYC, mark face_verified=True."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.kyc_status = "approved"
    user.face_verified = True
    db.commit()
    return {"ok": True}


@app.post("/api/kyc/{user_id}/reject")
def kyc_reject(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Admin: reject user KYC."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.kyc_status = "rejected"
    user.face_verified = False
    db.commit()
    return {"ok": True}


@app.get("/uploads/faces/{filename}")
def serve_kyc_photo(filename: str) -> object:
    """Serve KYC photos (admin only — no auth guard for now)."""
    from fastapi.responses import FileResponse
    path = f"uploads/faces/{filename}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)


# ── Search endpoint ─────────────────────────────────────────────────────────────

@app.get("/api/search")
def search_items(q: str = "", db: Session = Depends(get_db)) -> list:
    """Full-text search across items by title, description, game_category."""
    if not q.strip():
        return []
    pattern = f"%{q.strip()}%"
    items = db.query(Item).filter(
        Item.status == "ACTIVE",
        (Item.title.ilike(pattern)) | (Item.description.ilike(pattern)) | (Item.game_category.ilike(pattern))
    ).order_by(Item.id.desc()).limit(30).all()
    return [
        {"id": it.id, "title": it.title, "game_category": it.game_category,
         "price": it.price, "status": it.status}
        for it in items
    ]


# ── User profile endpoint ───────────────────────────────────────────────────────

@app.get("/api/users/by_tg/{tg_id}")
def get_user_by_tg(tg_id: int, db: Session = Depends(get_db)) -> dict:
    """Return user profile by Telegram ID, including computed stats."""
    user = db.query(User).filter(User.tg_id == tg_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    sales_count = db.query(Order).filter(
        Order.seller_id == user.id, Order.status == "COMPLETED"
    ).count()
    reviews = db.query(Review).filter(Review.seller_id == user.id).all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return {
        "id": user.id,
        "tg_id": user.tg_id,
        "username": user.username,
        "balance": user.balance,
        "role": user.role,
        "face_verified": user.face_verified,
        "kyc_status": user.kyc_status,
        "sales_count": sales_count,
        "avg_rating": avg_rating,
    }


@app.get("/api/users/{user_id}")
def get_user_by_id(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Return user profile by internal ID (used by seller page, product page)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    sales_count = db.query(Order).filter(
        Order.seller_id == user.id, Order.status == "COMPLETED"
    ).count()
    reviews = db.query(Review).filter(Review.seller_id == user.id).all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return {
        "id": user.id,
        "tg_id": user.tg_id,
        "username": user.username,
        "balance": user.balance,
        "role": user.role,
        "face_verified": user.face_verified,
        "kyc_status": user.kyc_status,
        "sales_count": sales_count,
        "avg_rating": avg_rating,
    }


# ── Orders ──────────────────────────────────────────────────────────────────────

@app.post("/api/orders", response_model=OrderResponse)
def create_order(payload: OrderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> OrderResponse:
    """Buyer purchases an item. Deducts balance, marks item SOLD, copies secret_data."""
    item = db.query(Item).filter(Item.id == payload.item_id, Item.status == "ACTIVE").first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found or already sold")

    buyer = db.query(User).filter(User.id == payload.buyer_id).first()
    if buyer is None:
        raise HTTPException(status_code=404, detail="Buyer not found")

    if buyer.id == item.seller_id:
        raise HTTPException(status_code=400, detail="Cannot buy your own item")

    if buyer.balance < item.price:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    # Deduct balance from buyer
    buyer.balance -= item.price

    # Credit seller (minus 5% commission)
    seller = db.query(User).filter(User.id == item.seller_id).first()
    if seller:
        seller.balance += round(item.price * 0.95, 2)

    # Mark item sold
    item.status = "SOLD"

    order = Order(
        buyer_id=payload.buyer_id,
        item_id=payload.item_id,
        seller_id=item.seller_id,
        price=item.price,
        status="PAID",
        secret_data=item.secret_data,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    # Notify seller and buyer via Telegram (fire-and-forget)
    if seller and seller.tg_id:
        background_tasks.add_task(
            _telegram_notify, seller.tg_id,
            f"💰 *Продан товар!*\n\n«{item.title}»\nПокупатель оплатил {item.price:.0f} TJS\nВам начислено {item.price * 0.95:.0f} TJS после подтверждения."
        )
    if buyer.tg_id:
        background_tasks.add_task(
            _telegram_notify, buyer.tg_id,
            f"✅ *Покупка оформлена!*\n\n«{item.title}»\nСумма: {item.price:.0f} TJS\nОткройте маркетплейс чтобы подтвердить получение."
        )
    return order


@app.get("/api/orders/buyer/{buyer_id}", response_model=list[OrderResponse])
def get_buyer_orders(buyer_id: int, db: Session = Depends(get_db)) -> list[OrderResponse]:
    """Return all orders for a buyer."""
    return db.query(Order).filter(Order.buyer_id == buyer_id).order_by(Order.id.desc()).all()


@app.get("/api/orders/seller/{seller_id}", response_model=list[OrderResponse])
def get_seller_orders(seller_id: int, db: Session = Depends(get_db)) -> list[OrderResponse]:
    """Return all orders where user is seller (without secret_data)."""
    orders = db.query(Order).filter(Order.seller_id == seller_id).order_by(Order.id.desc()).all()
    # Strip secret_data for seller view
    result = []
    for o in orders:
        d = OrderResponse.model_validate(o)
        d.secret_data = ""
        result.append(d)
    return result


@app.post("/api/orders/{order_id}/confirm")
def confirm_order(order_id: int, buyer_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    """Buyer confirms order received — marks COMPLETED."""
    order = db.query(Order).filter(Order.id == order_id, Order.buyer_id == buyer_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in ("PAID", "DELIVERED"):
        raise HTTPException(status_code=400, detail=f"Cannot confirm order in status {order.status}")
    order.status = "COMPLETED"
    order.confirmed_at = datetime.utcnow()
    db.commit()
    # Notify seller that funds are confirmed
    seller = db.query(User).filter(User.id == order.seller_id).first()
    if seller and seller.tg_id:
        item = db.query(Item).filter(Item.id == order.item_id).first()
        background_tasks.add_task(
            _telegram_notify, seller.tg_id,
            f"✅ *Сделка завершена!*\n\n«{item.title if item else 'Товар'}»\n"
            f"Покупатель подтвердил получение.\nВам начислено {order.price * 0.95:.0f} TJS."
        )
    return {"ok": True, "status": "COMPLETED"}


@app.post("/api/orders/{order_id}/dispute")
def dispute_order(order_id: int, buyer_id: int, db: Session = Depends(get_db)) -> dict:
    """Buyer opens a dispute."""
    order = db.query(Order).filter(Order.id == order_id, Order.buyer_id == buyer_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = "DISPUTED"
    db.commit()
    return {"ok": True, "status": "DISPUTED"}


# ── Reviews ─────────────────────────────────────────────────────────────────────

@app.post("/api/reviews", response_model=ReviewResponse)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)) -> ReviewResponse:
    """Leave a review after a completed order."""
    order = db.query(Order).filter(
        Order.id == payload.order_id,
        Order.buyer_id == payload.buyer_id,
        Order.status == "COMPLETED"
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Completed order not found")

    existing = db.query(Review).filter(Review.order_id == payload.order_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Review already exists")

    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    review = Review(
        order_id=payload.order_id,
        buyer_id=payload.buyer_id,
        seller_id=order.seller_id,
        rating=payload.rating,
        comment=payload.comment[:500],
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@app.get("/api/reviews/seller/{seller_id}", response_model=list[ReviewResponse])
def get_seller_reviews(seller_id: int, db: Session = Depends(get_db)) -> list[ReviewResponse]:
    """Return reviews for a seller."""
    return db.query(Review).filter(Review.seller_id == seller_id).order_by(Review.id.desc()).all()


# ── Topup (demo) ────────────────────────────────────────────────────────────────

@app.post("/api/users/{user_id}/topup")
def topup_balance(user_id: int, amount: float, db: Session = Depends(get_db)) -> dict:
    """Add balance to user (demo — no real payment)."""
    if amount <= 0 or amount > 100000:
        raise HTTPException(status_code=400, detail="Invalid amount")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.balance = round(user.balance + amount, 2)
    db.commit()
    return {"ok": True, "balance": user.balance}


# ── Admin stats extended ────────────────────────────────────────────────────────

@app.get("/api/admin/orders")
def admin_get_orders(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
) -> list:
    """Return recent orders for admin finance panel."""
    orders = db.query(Order).order_by(Order.id.desc()).limit(100).all()
    result = []
    for o in orders:
        buyer = db.query(User).filter(User.id == o.buyer_id).first()
        seller = db.query(User).filter(User.id == o.seller_id).first()
        item = db.query(Item).filter(Item.id == o.item_id).first()
        result.append({
            "id": o.id,
            "buyer": f"@{buyer.username}" if buyer else f"#{o.buyer_id}",
            "seller": f"@{seller.username}" if seller else f"#{o.seller_id}",
            "item_title": item.title if item else "—",
            "price": o.price,
            "status": o.status,
            "created_at": o.created_at.isoformat() if getattr(o, 'created_at', None) else None,
        })
    return result


class AdminBalancePayload(BaseModel):
    balance: float


@app.patch("/api/admin/users/{user_id}/balance")
def admin_set_balance(
    user_id: int,
    payload: AdminBalancePayload,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
) -> dict:
    """Admin: directly set user balance."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.balance = round(payload.balance, 2)
    db.commit()
    return {"ok": True, "balance": user.balance}


@app.get("/api/admin/stats")
def admin_stats(db: Session = Depends(get_db)) -> dict:
    """Quick platform statistics."""
    users_total   = db.query(User).count()
    items_active  = db.query(Item).filter(Item.status == "ACTIVE").count()
    items_total   = db.query(Item).count()
    orders_total  = db.query(Order).count()
    orders_done   = db.query(Order).filter(Order.status == "COMPLETED").count()
    revenue       = db.query(Order).filter(Order.status == "COMPLETED").all()
    revenue_total = round(sum(o.price for o in revenue), 2)
    return {
        "users_total":   users_total,
        "items_active":  items_active,
        "items_total":   items_total,
        "orders_total":  orders_total,
        "orders_done":   orders_done,
        "revenue_total": revenue_total,
    }


# ── Telegram notify helper (fire-and-forget, no new deps) ──────────────────────

def _telegram_notify(tg_id: int, text: str) -> None:
    """Send a Telegram message to a user via Bot API (synchronous, background task)."""
    token = os.getenv("BOT_TOKEN", "")
    if not token or not tg_id:
        return
    try:
        data = _json_mod.dumps({"chat_id": tg_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = _urllib_request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urllib_request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.warning("Telegram notify failed for tg_id=%s: %s", tg_id, exc)


# ── Transaction history ───────────────────────────────────────────────────────

@app.get("/api/users/{user_id}/history")
def get_user_history(user_id: int, db: Session = Depends(get_db)) -> list:
    """Return transaction history: purchases + completed sales + approved topups."""
    events: list[dict] = []

    # Покупки (пользователь — покупатель)
    for o in db.query(Order).filter(Order.buyer_id == user_id).all():
        item = db.query(Item).filter(Item.id == o.item_id).first()
        events.append({
            "title": f"Покупка: {item.title if item else 'Товар'}",
            "method": "Somon Market",
            "amount": -round(o.price, 2),
            "status": "Успешно",
            "statusType": "success",
            "type": "expense",
            "date": o.created_at.isoformat() if getattr(o, "created_at", None) else "",
        })

    # Продажи (пользователь — продавец, заказ завершён)
    for o in db.query(Order).filter(Order.seller_id == user_id, Order.status == "COMPLETED").all():
        item = db.query(Item).filter(Item.id == o.item_id).first()
        ts = getattr(o, "confirmed_at", None) or getattr(o, "created_at", None)
        events.append({
            "title": f"Продажа: {item.title if item else 'Товар'}",
            "method": "Somon Market",
            "amount": round(o.price * 0.95, 2),
            "status": "Начислено",
            "statusType": "success",
            "type": "income",
            "date": ts.isoformat() if ts else "",
        })

    # Одобренные пополнения
    for d in db.query(BalanceDeposit).filter(
        BalanceDeposit.user_id == user_id, BalanceDeposit.status == "approved"
    ).all():
        events.append({
            "title": "Пополнение баланса",
            "method": "Квитанция",
            "amount": round(d.amount, 2),
            "status": "Успешно",
            "statusType": "success",
            "type": "income",
            "date": d.created_at.isoformat() if getattr(d, "created_at", None) else "",
        })

    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# ── Referral system ───────────────────────────────────────────────────────────

class ReferralUsePayload(BaseModel):
    code: str


@app.get("/api/users/{user_id}/referral")
def get_referral_info(user_id: int, db: Session = Depends(get_db)) -> dict:
    """Return or generate user's referral code + stats."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.referral_code:
        user.referral_code = secrets.token_hex(6).upper()  # 12-char hex
        db.commit()
    invited_count = db.query(User).filter(User.referred_by == user_id).count()
    return {
        "referral_code": user.referral_code,
        "invited_count": invited_count,
        "bonus_per_invite": 20,
        "new_user_bonus": 10,
    }


@app.post("/api/referral/use")
def use_referral(user_id: int, payload: ReferralUsePayload, db: Session = Depends(get_db)) -> dict:
    """Apply referral code: +20 TJS to referrer, +10 TJS to new user."""
    code = payload.code.strip().upper()
    referrer = db.query(User).filter(User.referral_code == code).first()
    if referrer is None:
        raise HTTPException(status_code=404, detail="Referral code not found")
    if referrer.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot use your own referral code")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.referred_by is not None:
        raise HTTPException(status_code=400, detail="Referral code already used")
    user.referred_by = referrer.id
    user.balance = round(user.balance + 10, 2)
    referrer.balance = round(referrer.balance + 20, 2)
    db.commit()
    return {"ok": True, "bonus": 10}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

