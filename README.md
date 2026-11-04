# MaitreD Ordering Backend (`maitreD_ordering_backend`)

FastAPI backend service powering the **MaitreD Restaurant Management & Customer Mobile Ordering App**.

## Features
- **Public & Customer APIs**: Menus, categories, items, dishes, dine-in tables, order placement, payments, and tracking.
- **Admin & Manager APIs**: Category and menu item CRUD, sales reports, inventory consumption, tables, and KOT generation.
- **Delivery & Rider Integration**: Order status, rider assignments, live tracking endpoints.
- **Voice Agent / AI Integration**: Gemini and Vapi AI assistant integration endpoints.
- **Database**: SQLite with auto-migrated tables and SQLite multithreading support (pluggable to PostgreSQL).

## Quick Start

### 1. Setup Virtual Environment & Dependencies
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` (or configure your variables):
```env
ENVIRONMENT=development
DATABASE_URL=sqlite:///./restaurant.db
SECRET_KEY=maitred_super_secret_jwt_key_2026_dev_testing
CORS_ALLOWED_ORIGINS=*
```

### 3. Start Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
or on Windows:
```cmd
start.bat
```

Interactive API docs will be available at:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
