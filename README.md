# SRH Platform — Backend API

FastAPI backend for the AI-Powered SRH Education Platform.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111 |
| Database | PostgreSQL (via SQLAlchemy 2) |
| Auth | JWT (access + refresh tokens), bcrypt passwords |
| Migrations | Alembic |
| Deployment | Render (free tier) |

---

## Project Structure

```
srh-backend/
├── main.py                        # App entry point
├── requirements.txt
├── .env.example                   # Copy to .env and fill in
├── alembic/                       # Database migrations
│   └── env.py
└── app/
    ├── api/v1/
    │   ├── router.py              # Aggregates all routers
    │   └── endpoints/
    │       ├── auth.py            # User auth routes
    │       └── admin_auth.py      # Admin-only routes
    ├── core/
    │   ├── config.py              # Settings (from .env)
    │   ├── security.py            # JWT + bcrypt helpers
    │   └── dependencies.py        # Route protection deps
    ├── db/
    │   ├── session.py             # SQLAlchemy engine + get_db
    │   └── init_db.py             # Table creation + admin seed
    ├── models/
    │   └── user.py                # User ORM model
    ├── schemas/
    │   └── auth.py                # Pydantic request/response schemas
    └── services/
        └── auth_service.py        # Business logic
```

---

## Auth Endpoints

### User Auth
| Method | Path | Description | Auth required |
|---|---|---|---|
| POST | `/api/v1/auth/signup` | Register new user | ❌ |
| POST | `/api/v1/auth/login` | Login (users + admins) | ❌ |
| POST | `/api/v1/auth/refresh` | Refresh tokens | ❌ |
| POST | `/api/v1/auth/logout` | Invalidate refresh token | ✅ User |
| GET | `/api/v1/auth/me` | Get own profile | ✅ User |

### Admin Auth
| Method | Path | Description | Auth required |
|---|---|---|---|
| POST | `/api/v1/admin/signup` | Create admin account | ✅ Admin |
| GET | `/api/v1/admin/users` | List all users | ✅ Admin |
| PATCH | `/api/v1/admin/users/{id}/deactivate` | Deactivate user | ✅ Admin |
| PATCH | `/api/v1/admin/users/{id}/activate` | Reactivate user | ✅ Admin |

---

## Local Setup

```bash
# 1. Clone and enter directory
cd srh-backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials and a new SECRET_KEY:
#   openssl rand -hex 32

# 5. Run (tables + first admin created automatically on startup)
uvicorn main:app --reload --port 8000
```

Interactive docs → http://localhost:8000/docs

---

## Database Migrations (Alembic)

```bash
# Initialise (first time only)
alembic init alembic

# Generate migration from model changes
alembic revision --autogenerate -m "describe_change"

# Apply migrations
alembic upgrade head
```

---

## Deploying to Render

1. Push this folder to GitHub (can be a separate repo from the frontend)
2. On Render → **New Web Service** → connect the repo
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add all `.env` variables as **Environment Variables** in Render dashboard
6. Deploy — tables are created automatically on first startup

---

## Security Notes

- Passwords hashed with **bcrypt** (cost factor 12)
- Access tokens expire in **30 minutes** (configurable)
- Refresh tokens are **rotated on every use** (prevents replay)
- Refresh token stored in DB; logout invalidates it immediately
- Admin accounts can only be created by an existing admin
- First admin is seeded from `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` env vars
