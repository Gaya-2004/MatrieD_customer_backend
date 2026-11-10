import os
import traceback
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, menu, orders, table, inventory, restaurants, reports, customer, recipes, customer_delivery, delivery_assignments, delivery_tracking, payments, rider, catering, admin_catering, data_management, waiter, chat
from .mcp import router as mcp_router

import logging

logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
def startup_event():
    skip_migrations = os.getenv("SKIP_AUTO_MIGRATION", "false").lower() in ("true", "1", "yes")
    skip_seed = os.getenv("SKIP_DEFAULT_SEEDING", "false").lower() in ("true", "1", "yes")

    if not skip_migrations:
        try:
            from .migrations import create_tables
            create_tables()
        except Exception as e:
            logger.warning(f"Auto-migration skipped or failed: {e}")
    else:
        logger.info("Auto-migration skipped to avoid altering database.")

    if not skip_seed:
        try:
            from .seed_defaults import seed_defaults
            seed_defaults()
        except Exception as e:
            logger.warning(f"Default seeding check failed: {e}")
    else:
        logger.info("Default seeding skipped to avoid modifying database.")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/health/live")
def health_live():
    return {"status": "alive"}

@app.get("/health/ready")
def health_ready():
    from .db import engine
    # pyrefly: ignore [missing-import]
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Readiness check failed: Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database not ready")
        
    env = os.getenv("ENVIRONMENT", "development").lower()
    db_url = os.getenv("DATABASE_URL")
    if env == "production" and not db_url:
        raise HTTPException(status_code=503, detail="Configuration missing")

    return {"status": "ready", "database": "connected"}

# Ensure static/images directory exists
os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images"), exist_ok=True)

# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, RedirectResponse
from .db import SessionLocal
from .models.menu import MenuItem
import urllib.parse

@app.get("/static/images/{filename}")
async def serve_image(filename: str):
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    
    db = SessionLocal()
    try:
        item = db.query(MenuItem).filter(MenuItem.image_url.like(f"%{filename}%")).first()
        dish_name = item.name if item else "Delicious Food"
        encoded_name = urllib.parse.quote(dish_name)
        fallback_url = f"https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&q=80"
        return RedirectResponse(url=fallback_url)
    except Exception as e:
        logger.error(f"Fallback image error: {e}")
        return RedirectResponse(url="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&q=80")
    finally:
        db.close()

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")), name="static")

# CORS Middleware Configuration
# Explicit allowlist only (comma-separated CORS_ALLOWED_ORIGINS). A bare "*" is ignored because
# it cannot be combined with credentials safely. In non-production, local dev origins
# (localhost / 127.0.0.1 / private LAN IPs on any port) are additionally allowed so the admin
# web app and the mobile web app can both reach this one backend without extra setup.
import re as _re

cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
allowed_origins = [o.strip().rstrip("/") for o in cors_origins_env.split(",") if o.strip() and o.strip() != "*"]
if "*" in cors_origins_env:
    logger.warning("CORS_ALLOWED_ORIGINS contains '*' which is ignored; list explicit origins instead.")

_is_production = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower() == "production"
_DEV_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
allowed_origin_regex = None if _is_production else _DEV_ORIGIN_REGEX


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    origin = origin.rstrip("/")
    if origin in allowed_origins:
        return True
    return bool(allowed_origin_regex and _re.match(allowed_origin_regex, origin))


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

# HTTPException responses already pass through CORSMiddleware. Unhandled exceptions are
# produced outside it, so add CORS headers here -- but only for allowlisted origins.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin")
    headers = {}
    if _origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=headers
    )
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(table.router)
app.include_router(inventory.router)
app.include_router(restaurants.router)
app.include_router(reports.router)
app.include_router(mcp_router)
app.include_router(customer.router)
app.include_router(recipes.router)
app.include_router(customer_delivery.router)
app.include_router(delivery_assignments.router)
app.include_router(delivery_tracking.router)
app.include_router(payments.router)
app.include_router(rider.router)
app.include_router(catering.router)
app.include_router(admin_catering.router)
app.include_router(data_management.router)
app.include_router(waiter.router)
app.include_router(chat.router)
