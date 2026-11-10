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
cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip() and origin.strip() != "*"]

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"^https?://.*$" if "*" in cors_origins_env else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)

# Global handlers so CORS headers are ALWAYS present even on unhandled or HTTP errors.
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin")
    headers = dict(getattr(exc, "headers", None) or {})
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin")
    headers = {}
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
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
