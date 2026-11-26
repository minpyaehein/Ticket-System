# Modular Backend and Frontend Structure

The existing Golden Pride API and HTML pages are kept. `uvicorn main:app` remains
the application entry point and all existing `/api/...` URL paths are preserved.

## Backend modules

- `main.py` – creates the FastAPI app, installs middleware, includes routers, and serves the existing HTML/CSS.
- `backend/config.py` – environment settings, database connection, session settings, and Myanmar-time helpers.
- `backend/database.py` and `backend/models.py` – SQLAlchemy base, database models, and request schemas.
- `backend/security.py` – login/password handling, authorization, team access, audit logging, and serialization helpers.
- `backend/email_service.py` – SMTP delivery, templates, notification recipients, and email queue processing.
- `backend/resource_service.py` – shared validation, resource mapping, permissions, and CRUD support logic.
- `backend/seed.py`, `backend/sla.py`, and `backend/migration.py` – initial data, SLA/scheduled jobs, and legacy-schema migration.
- `backend/routes/` – HTTP endpoints grouped by authentication, dashboard, notifications, email, tickets, and resources.
- `backend/common.py` – shared imports used by the modules.
- `backend/lifecycle.py` – startup/shutdown background tasks.

The original API paths, SQLAlchemy tables, validation routines, and business rules have
been carried over. The Python package keeps shared service logic in domain modules so
route handlers stay focused on HTTP input/output.

## Frontend modules

The original 3,000-line `js/app.js` has been separated into ordered source files in
`js/modules/` (app shell, form controls, records/dashboard, ticket workflows,
settings/admin, and page initialization). The existing HTML pages still load
`js/app.js`, which is the generated compatibility bundle. After editing a source
module, rebuild the bundle from the project root:

```powershell
python tools/build_frontend.py
```

## Run locally

Install the packages in `requirements.txt`, configure `.env`, then run:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Environment and deployment safety

The archive intentionally does not include the real `.env` file, Git internals,
virtual-environment files, Python bytecode, or the one-time administrator credential
file. Keep the existing server `.env` in place when updating the source. When setting
up a new environment, copy `.env.example` to `.env` and fill in the database, session,
and SMTP values before starting the application.
