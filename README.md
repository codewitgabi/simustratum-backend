# Simustratum Backend

FastAPI backend for Simustratum — an AI-powered mock interview platform. Handles real-time interview sessions over WebSocket, REST API, billing, document-grounded question generation, and audio transcript management.

---

## Architecture

![Simustratum system architecture](docs/simustratum.png)

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [Running the App](#running-the-app)
- [Database Migrations](#database-migrations)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [API Overview](#api-overview)
- [Deployment](#deployment)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Database | PostgreSQL (AWS Aurora in production) — SQLAlchemy async + asyncpg |
| Migrations | Alembic |
| Auth | JWT (PyJWT) + Google OAuth |
| Billing | Stripe |
| Vector store | Qdrant Cloud |
| LLM | Anthropic Claude + Google Gemini |
| Audio storage | Cloudinary |
| Email | SMTP via fastapi-mail |
| Package manager | uv |

---

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **PostgreSQL 16+** running locally (or a connection string to a remote instance)
- **Git**

---

## Local Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd simustratum-backend
```

### 2. Install dependencies

```bash
uv sync
```

This creates a virtual environment at `.venv/` and installs all dependencies from `uv.lock`.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values — see [Environment Variables](#environment-variables) below.

### 4. Create the local database

```bash
psql -U postgres -c "CREATE DATABASE simustratum;"
```

### 5. Apply migrations

```bash
uv run python scripts/migrate.py upgrade head
```

### 6. Start the server

```bash
uv run uvicorn main:app --reload
```

The API is now running at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Environment Variables

Copy `.env.example` and fill in the values. All variables are loaded via `api/v1/utils/config.py`.

### Core

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string — `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `JWT_SECRET_KEY` | Yes | Secret key for signing JWTs — generate with `openssl rand -hex 32` |
| `JWT_ALGORITHM` | No | Default: `HS256` |
| `JWT_ACCESS_EXPIRE_MINUTES` | No | Default: `15` |
| `JWT_REFRESH_EXPIRE_DAYS` | No | Default: `30` |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins — defaults to `*` in development |
| `FRONTEND_URL` | Yes | Base URL of the frontend app (e.g. `https://simustratum.com`) — used for Stripe redirect URLs |
| `PORT` | No | Uvicorn port — default: `8000` |

### AWS Aurora (production only)

Leave these unset locally — the app falls back to `DATABASE_URL`.

| Variable | Description |
|---|---|
| `DB_HOST` | Aurora writer endpoint (cluster endpoint — always routes to primary) |
| `DB_READER_HOST` | Aurora reader endpoint — when set, read-only queries are routed here, leaving the writer free for mutations |
| `DB_NAME` | Database name |
| `DB_USERNAME` | Database user |
| `DB_PORT` | Default: `5432` |
| `DB_POOL_TIMEOUT` | Connection acquisition timeout in seconds — default: `30` |
| `AWS_REGION` | e.g. `us-east-1` |

### Google OAuth

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID from Google Cloud Console |

### AI / LLM

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | API key from [console.anthropic.com](https://console.anthropic.com) |
| `GEMINI_API_KEY` | Yes | API key from Google AI Studio |

### Qdrant

| Variable | Required | Description |
|---|---|---|
| `QDRANT_URL` | Yes | Qdrant instance URL — default: `http://localhost:6333` |
| `QDRANT_API_KEY` | Cloud only | API key for Qdrant Cloud |
| `QDRANT_COLLECTION` | No | Collection name — default: `session_documents` |

### Cloudinary

| Variable | Required | Description |
|---|---|---|
| `CLOUDINARY_URL` | Yes | Full Cloudinary URL — format: `cloudinary://api_key:api_secret@cloud_name` |

### Stripe

| Variable | Required | Description |
|---|---|---|
| `STRIPE_SECRET_KEY` | Yes | From [Stripe Dashboard](https://dashboard.stripe.com/apikeys) — use `sk_test_` for development |
| `STRIPE_WEBHOOK_SECRET` | Yes | From Stripe Dashboard → Webhooks — use `whsec_` value for your endpoint |
| `STRIPE_PRICE_ID_NGN` | Yes | Stripe Price ID for the NGN recurring plan |
| `STRIPE_PRICE_ID_USD` | Yes | Stripe Price ID for the USD recurring plan |

### Email (SMTP)

| Variable | Description |
|---|---|
| `MAIL_USERNAME` | SMTP username |
| `MAIL_PASSWORD` | SMTP password |
| `MAIL_SERVER` | SMTP host (e.g. `smtp.gmail.com`) |
| `MAIL_FROM` | Sender address — default: `no-reply@simustratum.app` |
| `MAIL_PORT` | Default: `587` |

### Password reset

| Variable | Description |
|---|---|
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | Default: `30` |

---

## Running the App

```bash
# Quick run
uv run main.py

# Development (auto-reload)
uv run uvicorn main:app --reload

# Production-style (no reload, multiple workers)
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Database Migrations

Migrations are managed with Alembic via `scripts/migrate.py` — a thin wrapper that doesn't require the `alembic` CLI on PATH.

```bash
# Apply all pending migrations
uv run python scripts/migrate.py upgrade head

# Roll back one step
uv run python scripts/migrate.py downgrade -1

# Show current revision
uv run python scripts/migrate.py current

# Show migration history
uv run python scripts/migrate.py history
```

### Creating a new migration

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Review the generated file in `alembic/versions/` before applying.

---

## Running Tests

The test suite uses `pytest` with `pytest-asyncio`. Tests spin up an in-memory async client against a real PostgreSQL database (`simustratum_test`) and stub all external services (Stripe, Gemini, Anthropic, Cloudinary, Qdrant).

```bash
# Run all tests
uv run pytest tests -q

# Run a specific test file
uv run pytest tests/session_stream/ -q

# Run with verbose output
uv run pytest tests -v
```

> The test database (`simustratum_test`) is created and migrated automatically by `tests/conftest.py` on first run — no manual setup needed.

---

## Project Structure

```
.
├── api/
│   ├── database.py              # Async SQLAlchemy engine + session factory
│   ├── response.py              # success_response helper
│   └── v1/
│       ├── dependencies/
│       │   └── auth.py          # get_current_user / get_current_user_ws
│       ├── middlewares/
│       │   ├── errors.py        # Global exception handlers
│       │   └── logging.py       # Request/response logging middleware
│       ├── models/              # SQLAlchemy ORM models
│       ├── routes/              # FastAPI routers
│       │   ├── auth.py
│       │   ├── billing.py
│       │   ├── document.py
│       │   ├── health.py
│       │   ├── session.py
│       │   └── session_stream.py  # WebSocket live session loop
│       ├── schemas/             # Pydantic request/response schemas
│       ├── services/            # Business logic layer
│       │   ├── auth.py
│       │   ├── billing_service.py
│       │   ├── document_service.py
│       │   ├── llm_service.py
│       │   ├── scoring_service.py
│       │   ├── session.py
│       │   ├── session_orchestrator.py
│       │   └── session_stream_service.py
│       └── utils/
│           ├── config.py        # Pydantic Settings — all env vars
│           ├── jwt_tokens.py
│           └── logger.py
├── alembic/
│   └── versions/                # Migration files
├── scripts/
│   └── migrate.py               # Alembic wrapper (used by CI and locally)
├── tests/
├── main.py                      # FastAPI app entry point
├── pyproject.toml
└── uv.lock
```

---

## API Overview

All routes are prefixed with `/api/v1`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Email + password login |
| `POST` | `/auth/google` | Google OAuth login |
| `POST` | `/auth/refresh` | Refresh access token |
| `POST` | `/auth/logout` | Invalidate access token |
| `PATCH` | `/auth/me` | Update display name |
| `POST` | `/auth/forgot-password` | Request password reset email |
| `POST` | `/auth/reset-password` | Apply reset token |
| `GET` | `/billing/status` | Current plan + usage |
| `POST` | `/billing/plan` | Select free plan |
| `POST` | `/billing/checkout` | Create Stripe Checkout session (Pro) |
| `POST` | `/billing/portal` | Create Stripe Customer Portal session |
| `POST` | `/billing/webhook` | Stripe webhook receiver |
| `POST` | `/sessions` | Create session |
| `GET` | `/sessions` | List sessions (paginated) |
| `POST` | `/sessions/{id}/start` | Start session + enforce plan limits |
| `POST` | `/sessions/{id}/end` | End / abandon session |
| `DELETE` | `/sessions/{id}` | Delete session |
| `GET` | `/sessions/{id}/replay` | Full session replay with scores |
| `POST` | `/sessions/{id}/turns/audio-upload-url` | Generate signed audio upload URL |
| `WS` | `/sessions/{id}/stream` | Live session WebSocket |
| `POST` | `/documents` | Upload interview document (PDF/DOCX/TXT) |
| `GET` | `/health/db` | Database health check |
| `GET` | `/health/qdrant` | Qdrant health check |

---

## Deployment

Production runs on **AWS EC2** behind **nginx** with TLS via **Certbot**, managed by **systemd** (`fastapi.service`).

### CI/CD

Deployments are triggered automatically on every push to the `release` branch via GitHub Actions (`.github/workflows/ci.yml`):

1. Run the full test suite against an ephemeral PostgreSQL container
2. SCP the production `.env` to EC2
3. SSH in — pull the latest code, sync dependencies, **run `alembic upgrade head`**, restart the service, and smoke-test `/health/db`

### Required GitHub Secrets / Variables

| Name | Type | Value |
|---|---|---|
| `PRODUCTION_ENV_FILE` | Secret | Full contents of the production `.env` |
| `EC2_SSH_KEY` | Secret | Private SSH key for the EC2 instance |
| `EC2_HOST` | Variable | EC2 public IP or domain |
| `EC2_USER` | Variable | SSH username (e.g. `ubuntu`) |
| `EC2_DEPLOY_PATH` | Variable | Absolute path to the repo on EC2 |
| `EC2_SSH_PORT` | Variable | SSH port — defaults to `22` |

### Stripe Webhook

Register `https://<your-domain>/api/v1/billing/webhook` in the [Stripe Dashboard](https://dashboard.stripe.com/webhooks) and enable these events:

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`
