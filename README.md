<<<<<<< HEAD
# Golden Pride Ticket Service System — Frontend + Python API + PostgreSQL

This version connects the supplied HTML/CSS pages to a FastAPI backend and PostgreSQL. Existing page layouts and modules are kept; the inline prototype-only session checks have been replaced by a shared `js/app.js` client that talks to the backend. The application starts on its own, creates missing database tables and inserts starter/demo data on the first run. **You do not have to open `/docs` and manually POST a login or database record before you can sign in.** `/docs` is available only as optional API documentation/testing.

## Modules connected

- Login and server-side session cookies; Admin, Agent, and Customer page/API permissions
- Tickets: create, view, update status/priority/assignee/due date, customer request submission, ticket number generation, customer-owned ticket filtering, replies and CSV export
- Customers, contacts, projects, contracts, support plans, service catalog, teams, assets, and user accounts: database-backed lists, create/edit and delete actions where the role permits
- Role permissions, audit logs, dashboard counts, lookups for dropdowns, and email settings/test email
- All the original separate `.html` pages and the shared `css/style.css`

The original ERD tables are represented by `customers`, `contacts`, `projects`, `plans`, `contracts`, `assets`, `service_catalog`, `teams`, `users`, and `tickets`. `schema.sql` contains the PostgreSQL DDL. Additional support tables (`ticket_replies`, `team_service_catalog`, `role_permissions`, `audit_logs`, `email_settings`) support features already shown in the frontend. A few extra columns (for example ticket number, priority and due date) support details in the supplied UI while preserving the relationships from the diagram.

## 1. Create the PostgreSQL database

Install/start PostgreSQL, then create an empty database named `golden_pride_ticket` using pgAdmin Query Tool or `psql`:

```sql
CREATE DATABASE golden_pride_ticket;
```

The FastAPI app will create the tables inside this database automatically when it starts. You do not need to execute `schema.sql` manually; it is included for reference/manual setup.

## 2. Install and configure on Windows / VS Code

Open a terminal inside the extracted `golden_pride_ticket_system` folder.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set `DATABASE_URL` to your actual PostgreSQL username/password. For example:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_REAL_PASSWORD@127.0.0.1:5432/golden_pride_ticket
SESSION_SECRET=put-a-long-random-secret-here
COOKIE_HTTPS_ONLY=false
```

URL-encode special characters in the PostgreSQL password (for example `@` as `%40`) or use a password without URL-reserved characters. Ensure PostgreSQL is running and the database exists before starting the app.

## 3. Start the whole application

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The root URL redirects to `login.html`. Do not double-click the HTML file or run the HTML pages through a separate static server; the frontend must be served by FastAPI so its `/api/...` requests use the same origin and session cookie.

### Demo logins

These accounts are created once when the database is first initialized. Choose the matching role in the login form.

| Role | Email | Default password |
|---|---|---|
| Admin | `admin@goldenpride.local` | `Admin@123` |
| Agent | `agent@goldenpride.local` | `Agent@123` |
| Customer | `customer@goldenpride.local` | `customer@123` |

The app stores password hashes, not plaintext passwords. `SEED_ADMIN_PASSWORD`, `SEED_AGENT_PASSWORD`, and `SEED_CUSTOMER_PASSWORD` in `.env` can set the initial passwords **before the first database seed**. If the database was already seeded, changing these values will not change existing user passwords. Change demo credentials and `SESSION_SECRET` before deployment.

## 4. Useful URLs

- Frontend: `http://127.0.0.1:8000/`
- Health/database check: `http://127.0.0.1:8000/api/health`
- Optional Swagger API docs: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Login/session and all form actions are handled by the website automatically. Use `/docs` only if you want to inspect or manually test an API endpoint.

## 5. PostgreSQL configuration tips

- If you see `connection refused`, start the PostgreSQL service and verify host/port `127.0.0.1:5432`.
- If you see `password authentication failed`, correct the username/password in `.env`.
- If you see `database ... does not exist`, create `golden_pride_ticket` first.
- If you change `.env`, restart Uvicorn.
- If you want to reset the demo data, back up anything important, drop/recreate the database, and restart the app. Startup seeding only occurs when the `users` table is empty.

## 6. Running behind Gunicorn

For local Windows development, use Uvicorn as shown above. Gunicorn is normally run on Linux/Unix (not natively on Windows). On a Linux deployment install `gunicorn` and `uvicorn-worker`, then run:

```bash
gunicorn -w 2 -k uvicorn_worker.UvicornWorker main:app --bind 0.0.0.0:8000
```

Use HTTPS in deployment and set `COOKIE_HTTPS_ONLY=true`. Configure a real random `SESSION_SECRET`, restrict database access, and change demo passwords.

## Notes / limitations

- Email settings are saved in PostgreSQL and the test-email button sends through the configured SMTP server. Real delivery will fail until valid SMTP settings and provider access are configured. OAuth 2.0 SMTP authentication is not implemented; choose username/password or no authentication.
- The attachment field is retained as a reference/text field; file upload storage is not implemented.
- The customer account is linked to the customer record by email, matching the supplied ERD without adding a `customer_id` foreign key to `users`.
- Backend authorization applies to API calls, not just menu visibility. Demo data is for development only.
=======
# Ticket-System
>>>>>>> origin/main
