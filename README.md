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

- Email settings, event rules and templates are saved in PostgreSQL. Each outgoing email has a separate `email_deliveries` record with queued/sent/failed status, retry attempts and error detail. Real delivery requires valid SMTP settings and provider access. OAuth 2.0 SMTP authentication is not implemented; choose username/password or no authentication.
- In-app notifications are stored separately in `notifications` and displayed by the 🔔 notification bell. They work independently of SMTP and are scoped so each user can read only their own notifications. Admins receive recorded ticket/system activity; Customers receive customer-facing ticket updates; Agents receive assigned work, customer replies, internal notes and resolution-SLA alerts.
- Resolution due-date alerts use `tickets.due_date` and run daily at 09:00 Asia/Yangon. Response-SLA threshold triggers and reminder/auto-close schedules are not configured in the existing schema; their event rule/template entries are saved but do not automatically fire yet. See `README_NOTIFICATION_AND_EMAIL_FLOW.md` for setup and role-routing tests.
- The attachment field is retained as a reference/text field; file upload storage is not implemented. Ticket edit forms reload the saved record before changes are submitted.
- Audit Log stores successful login/logout, failed logins, create/update/delete changes, ticket replies, email delivery attempts, and daily summary activity. Audit records are read-only through the API.
- The customer account is linked to the customer record by email, matching the supplied ERD without adding a `customer_id` foreign key to `users`.
- Backend authorization applies to API calls, not just menu visibility. Demo data is for development only.


## Important: use the backend URL

Do not double-click HTML pages or open them using a `file:///` address. This bypasses authentication, the Python API, database writes, email notifications, and audit logging. Start with `uvicorn main:app --reload --host 127.0.0.1 --port 8000`, then open `http://127.0.0.1:8000`.

## Email notifications and audit log

Configure SMTP from the administrator Email Notifications page, save settings while the service is disabled, then send a test email. Once the test arrives, enable the service and save again. Ticket events can create in-app notifications and per-recipient email deliveries. Audit activity is tracked separately. See `README_NOTIFICATION_AND_EMAIL_FLOW.md` for the step-by-step flow and recipient rules.


## Agent access scope
- Agents cannot create tickets. Agents can view tickets assigned to them or routed to their Support Team. Only the explicitly assigned Agent can post public replies and staff-only internal notes; internal notes are visible to Admin and that assigned Agent only.
- Agents may change only the status of tickets explicitly assigned to them (Open, In progress, Pending Customer, Resolved, Closed). Priority, assignment, due date and ticket details remain Admin-only.
- Customers, Projects, Contracts, Support Plans, Service Catalog, Contacts and Assets are read-only for Agents. Their Add/Edit/Delete actions are hidden in the Agent interface and rejected by the API.
- User Management, SMTP configuration, role permissions and audit logs are Admin-only.

## SMTP authentication support
- Supported authentication modes: `Username and password` and `No authentication`.
- Supported encryption modes: `STARTTLS`, `SSL / TLS`, and `None`.
- OAuth 2.0 is not implemented in this version and is intentionally not offered in the settings UI.
- Use a provider-approved sender address. For Gmail, use `smtp.gmail.com`, port `587`, `STARTTLS`, and a Google App Password.
- SMTP delivery cannot be confirmed until an Admin saves real provider credentials and sends a test email.


## Support team routing and asset/service relationships

Customer-created tickets use the selected Service Catalog item's `Mapped Team` as the default ticket team. Assignment follows a hybrid service-desk workflow: when that service has `Auto Assign` enabled, the backend chooses the least-loaded active Agent from the mapped Team; if that Team has no active members, it falls back to the least-loaded active Agent across the workspace. When Auto Assign is disabled or no active Agent exists, the ticket remains unassigned in the Admin dispatch queue. Admins can assign or reassign it to any active Agent, regardless of the Agent profile's Support Team or Request Type. Agents can read, update, and reply to a ticket only after it is explicitly assigned to their account; Team and Request Type do not grant ticket access.

Admin manages Customer-visible Service Catalog items in Service Catalog. Customers request those services from their separate Customer Portal Service Catalog page. Customer forms do not contain Support Team or Assigned Agent fields.

Assets can be linked to one or more Service Catalog items in Add/Edit Asset. A ticket's Related Asset dropdown then shows only assets linked to the selected Service. The Add Asset Project dropdown filters to projects belonging to the selected Customer. Customer, Contact, Project, Contract, Asset and Ticket relationships are also validated by the API.

The application creates the `asset_service_catalog` link table and adds the `customers.active` field when starting against an existing database. Back up PostgreSQL before updating. Customer deactivation also disables the linked Customer login account.


## November 2, 2026 — Agent teams, ticket deletion and form fixes
- Agent User Management now supports multiple Support Team selections. The new `user_team_memberships` table stores the many-to-many links; the old `users.team_id` remains as a primary/legacy team field.
- Startup creates the membership table and backfills existing Agent `team_id` values. Existing PostgreSQL data is retained; no database recreation is needed. Back up the database before the first updated start.
- Startup also adds common IT support teams when they are not already present: Application Support, Network Operations, Systems Administration, Hardware & Desktop Support, Cybersecurity, Cloud & DevOps, ERP Support, IT Operations, Data & Analytics, Backup & Recovery, Field Support, Telecommunications and IT Helpdesk.
- After login, an Agent sees their assigned Team name(s) under the Golden Pride brand in the sidebar.
- User deletion now removes tickets created by that user and, for Agents, tickets assigned to that Agent; for Customer accounts it also removes tickets associated with the linked Customer. Related replies are removed and the confirmation uses a centered dialog.
- Support Plan SLA fields reject negative values. Add Project and Add Request Type pages have a single correctly structured sidebar navigation region so it can scroll like the other pages.
- Support Plans are a global reusable catalog. The Support Plan form offers Standard, Premium, Enterprise, VVIP, and Other (custom type); saved plans appear in Contract and Ticket dropdowns, and Ticket plan selection is independent of the selected Contract. Existing databases automatically receive the `plans.plan_type` column.
- Ticket list filters include Ticket View, Customer, Project and Contract, alongside Status, Priority, Request Type and Support Team. `SLA at Risk` currently uses the ticket's `due_date` as its deadline indicator.

## November 5, 2026 assignment update

Agent Support Team and Request Type are independent single-select profile fields. Admin ticket Support Team and Request Type choices are independent too; Admin-selected teams are not forced to match the Service Catalog `mapped_team`. Neither field restricts manual assignment. Agents in the mapped Support Team can view the ticket and public conversation; only the explicitly assigned Agent can post replies or internal notes and can see those internal notes. Customer-created tickets use the Service Catalog `mapped_team` as a default and support configurable Auto Assign with an Admin dispatch fallback. See `ASSIGNMENT_DISPATCH_WORKFLOW_2026-11-05.md` for details.
