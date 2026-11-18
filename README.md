# Golden Pride Ticket Service System

A web-based IT service desk and ticket management application built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, and a multi-page **HTML/CSS/JavaScript** frontend.

The frontend is served by FastAPI. Authentication, role checks, business rules, ticket workflows, dashboard data, notifications, and database operations are handled by the Python backend.

---

## Contents

- [Main capabilities](#main-capabilities)
- [User roles](#user-roles)
- [Ticket assignment workflow](#ticket-assignment-workflow)
- [SLA and notifications](#sla-and-notifications)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Installation on Windows](#installation-on-windows)
- [Environment configuration](#environment-configuration)
- [Run the application](#run-the-application)
- [Database behavior and backups](#database-behavior-and-backups)
- [Useful URLs](#useful-urls)
- [Troubleshooting](#troubleshooting)
- [Important operational notes](#important-operational-notes)

---

## Main capabilities

### Dashboard
- Role-aware dashboard information for Admin, Agent, and Customer accounts.
- Live dashboard statistics are loaded from PostgreSQL through the API.
- Ticket status breakdown and recent daily ticket activity.
- Admin overview of customers, agents, tickets, and selected module records.
- Active and inactive record counts for the supported dashboard modules.
- Deactivated records remain in the database; they are not counted as active.

### Ticket management
- Create, view, update, assign, and manage support tickets according to role permissions.
- Customer ticket submission through the Customer Portal.
- Ticket details include customer, contact, project, support plan, contract, service/request type, asset, status, priority, due date, and assignment information where applicable.
- Ticket replies and staff-only internal notes.
- Customer actions to accept a resolution or reopen a ticket, where permitted.
- Ticket list filters, search, and CSV export.
- Ticket access is checked by the backend; hiding a button in the frontend is not the only permission control.

### Customer and service administration
The application includes separate pages for:
- Customers and customer details
- Contacts
- Projects
- Contracts
- Support Plans
- Service Catalog / Request Types
- Support Teams
- Assets
- Users
- Roles and Role Access
- Audit Log
- Email Notifications

### Support Plans and SLA
- Support Plans can define response and resolution targets.
- SLA configuration includes warning and critical thresholds, calendar mode, time zone, business hours, working days, escalation level, and remote/onsite support details.
- Response and resolution SLA milestones are evaluated by the backend scheduler.
- Ticket due dates are used for the dashboard's general “SLA at Risk” indicator.

### Notifications and email
- In-app notifications are stored in PostgreSQL and shown through the notification interface.
- Users can manage their own notification preferences.
- Admins can configure SMTP settings, event rules, and email templates.
- Test email, email delivery records, failed-delivery retry, and delivery status tracking are supported.
- Email delivery requires valid SMTP provider settings; saving settings alone does not guarantee delivery.

### User and access administration
- Role-aware Admin, Agent, and Customer experiences.
- Backend authorization for protected API operations.
- Admin-managed user accounts, role permissions, and account activation/deactivation.
- Customer password reset by an Admin using the configured email service.
- Users flagged to change their password must complete that step before accessing other protected API features.


### Admin temporary password reset and first login

The Admin temporary-password recovery flow is separate from the Admin reset action in User Management. The application's `/api/users/{user_id}/reset-password` endpoint is intentionally limited to **Customer and Agent** accounts; it does not reset Admin passwords.

#### First-time Admin setup: what happens on a fresh download?

**Important distinction:** generating a temporary password for an existing Admin account is not the same as creating an Admin account in a brand-new database.

In the **Admin First Login Fix** build, the backend runs `ensure_initial_admin_password()` during startup:

1. It checks a one-time initialization marker in `system_settings`.
2. If setup has not already run, it selects the earliest active Admin account that already exists.
3. It generates a random temporary password and stores only its password hash in PostgreSQL.
4. It sets `must_change_password = true`.
5. It writes the one-time plaintext credential to a private file outside the application/web folder:
   - Folder: `.golden_pride_private`
   - File: `initial_admin_credentials.txt`
6. The Admin signs in using the login name shown in the credentials file, then must choose a new password before using the rest of the system.
7. After the Admin successfully changes the password, the one-time credential file is deleted in that build.

**This helper does not, by itself, create an Admin account when a brand-new database contains no Admin users.** A fresh-install setup routine must first create or seed the initial Admin account, and then generate its temporary password. The later `Golden_Pride_PostgreSQL_Live_Dashboard_Fix (3)` ZIP inspected for this README does not include the Admin First Login Fix helper. Therefore, do not promise that a person downloading that ZIP will automatically receive a temporary Admin password. The fresh-install flow must be added to that exact project build and tested with a new, empty database before distributing it.

The path is based on the parent of the application folder:

```text
<project-parent>/.golden_pride_private/initial_admin_credentials.txt
```

For example, if the application folder is:

```text
C:\Users\GP-admin\Downloads\Golden_Pride_PostgreSQL_Live_Dashboard_Fix\golden_pride_ticket_system
```

the credential file is:

```text
C:\Users\GP-admin\Downloads\Golden_Pride_PostgreSQL_Live_Dashboard_Fix\.golden_pride_private\initial_admin_credentials.txt
```

#### Expected behavior for another person downloading the project

For a distributable release, the intended fresh-install behavior should be:

1. The installer creates/configures a PostgreSQL database and sets the local `.env` values.
2. On the first application startup, the backend checks whether an Admin account exists.
3. If no Admin exists, the setup routine creates one initial Admin account using a configured Admin email/login value.
4. The backend generates a cryptographically random temporary password, stores only its hash in PostgreSQL, and marks the account `must_change_password = true`.
5. The plaintext temporary password is written once to that installer's local private credentials file:
   `.golden_pride_private/initial_admin_credentials.txt`
6. The installer reads that file, signs in, and changes the password immediately.
7. The application must not reset existing Admin passwords on every restart. The one-time setup state must be recorded safely in the database.

The private credentials file belongs to each installation. It must never be shared in the project ZIP, committed to GitHub, or copied from one installation to another. A person who downloads the source should generate their own credentials from their own database.

**Release checklist:** before publishing a new ZIP or GitHub repository, test the setup from a clean checkout and a brand-new empty database. Confirm that an Admin is created, the private credentials file appears outside the web folder, the generated password works, first-login password change is enforced, and restarting the server does not generate or reset credentials again. Also test that an existing database and its Admin accounts are not unexpectedly reset.

#### Manually reset both existing Admin accounts

For the existing local database where the two active Admin accounts have IDs **1** and **47**, the following PowerShell command resets both passwords, creates new random temporary passwords, and requires both accounts to change their passwords at next login.

Run it from the project folder after activating `.venv`. Stop Uvicorn first so that no application process is using the database while the recovery is performed.

```powershell
@'
import os
import secrets
import main
from sqlalchemy import select

db = main.SessionLocal()
temp_file = None
credentials_written = False

try:
    admins = db.scalars(
        select(main.User)
        .where(
            main.User.role == "admin",
            main.User.active.is_(True)
        )
        .order_by(main.User.user_id.asc())
    ).all()

    expected_ids = {1, 47}
    actual_ids = {admin.user_id for admin in admins}

    if actual_ids != expected_ids:
        raise RuntimeError(
            f"Admin ID verification failed. Found: {actual_ids}. "
            "No passwords were changed."
        )

    credentials = []

    for admin in admins:
        temporary_password = secrets.token_urlsafe(24)
        admin.password_hash = main.hash_password(temporary_password)
        admin.must_change_password = True

        login_name = "admin" if admin.user_id == 1 else admin.email

        credentials.append(
            f"Admin ID: {admin.user_id}\n"
            f"Login: {login_name}\n"
            f"Email: {admin.email}\n"
            f"Temporary password: {temporary_password}\n"
        )

    credentials_dir = main.INITIAL_ADMIN_CREDENTIALS_DIR
    credentials_file = main.INITIAL_ADMIN_CREDENTIALS_FILE
    credentials_dir.mkdir(parents=True, exist_ok=True)

    temp_file = credentials_dir / (
        ".recovery_" + secrets.token_hex(8) + ".tmp"
    )

    fd = os.open(
        temp_file,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600
    )

    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(
            "GOLDEN PRIDE - ADMIN PASSWORD RECOVERY\n"
            "======================================\n\n"
            + "\n".join(credentials)
            + "\nChange both passwords immediately.\n"
        )

    os.replace(temp_file, credentials_file)
    temp_file = None
    credentials_written = True

    db.commit()

    print("\nSUCCESS: Both Admin passwords were reset.")
    print("Both accounts must change their passwords.")
    print("\nCredentials saved at:")
    print(credentials_file)
    print("\nOpen this file to view both temporary passwords.")

except Exception:
    db.rollback()

    if credentials_written:
        main.INITIAL_ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)

    raise

finally:
    if temp_file:
        temp_file.unlink(missing_ok=True)

    db.close()
'@ | python
```

If the command succeeds, open the private credentials file:

```powershell
notepad "C:\Users\GP-admin\Downloads\Golden_Pride_PostgreSQL_Live_Dashboard_Fix\.golden_pride_private\initial_admin_credentials.txt"
```

The login names for this database are:

| Admin ID | Login name |
|---:|---|
| 1 | `admin` |
| 47 | The account's email address |

**Important:** Save both temporary passwords in a secure password manager before either Admin changes their password. In this build, the shared credential file is deleted after the first Admin with `must_change_password` changes their password. Then sign in as the second Admin using the saved temporary password and change that password too. Delete any remaining recovery copy after both accounts have changed their passwords.

#### Compatibility check before using the recovery command

The manual command above requires a `main.py` version that defines both `INITIAL_ADMIN_CREDENTIALS_DIR` and `INITIAL_ADMIN_CREDENTIALS_FILE` (the **Admin First Login Fix** build). The later `Golden_Pride_PostgreSQL_Live_Dashboard_Fix (3)` ZIP inspected for this README does **not** contain those two definitions or the `ensure_initial_admin_password()` startup helper. Therefore, do not run the command against that ZIP unchanged; first merge/apply the Admin First Login Fix code to the local project, or the command will fail because those attributes are missing.

#### Security notes

- The temporary passwords are plaintext only in the private recovery file; PostgreSQL stores password hashes.
- Keep the `.golden_pride_private` folder outside the web/application folder and do not upload it, email it, or commit it to source control.
- Add `.golden_pride_private/`, `.env`, `.venv/`, Python cache folders, and local credential files to `.gitignore` before the first Git commit.
- `.gitignore` prevents future accidental additions; it does not remove a secret that was already committed. If a password or secret was pushed to a remote repository, rotate it and remove the exposed secret from repository history as appropriate.
- Do not paste temporary passwords into chat, screenshots, or support tickets.
- A forced password change blocks access to protected application features until the new password is saved.
- Back up the database before manual credential recovery.

### Audit Log
- Records important authentication and application activity.
- Tracks create, update, and delete operations and relevant ticket/email events.
- Supports searching and filtering the recorded activity.
- Audit records are read-only through the application API.

---

## User roles

| Role | Main access |
|---|---|
| **Admin** | Full administration of tickets, customers, contacts, projects, contracts, support plans, service catalog, teams, assets, users, roles, audit log, and email settings. |
| **Agent** | Access to assigned work and permitted team ticket information; can update allowed ticket statuses and participate in ticket conversations according to assignment rules. |
| **Customer** | Customer Portal access to available services, own tickets, ticket conversations, and permitted ticket actions. |

The exact operations available to an account are enforced by backend role checks and the configured role permissions.

### Agent access rules
- Agents can access tickets assigned to them or made visible through the ticket's Support Team routing rules.
- Only the explicitly assigned Agent can post ticket replies and staff-only internal notes.
- Internal notes are restricted to Admin and the explicitly assigned Agent.
- Agents cannot manage Admin-only configuration such as users, SMTP settings, role permissions, and audit records.
- Customer and business administration pages are read-only for Agents where the current interface exposes them.

---

## Ticket assignment workflow

The current backend supports a hybrid dispatch workflow:

1. A Customer submits a ticket using a Customer-visible Service Catalog item.
2. The Service Catalog item's mapped Support Team is used as the default ticket team.
3. If **Auto Assign** is enabled, the backend attempts to select an active Agent from the mapped team using the configured assignment behavior and workload checks.
4. If automatic assignment is disabled or no eligible Agent is available, the ticket can remain unassigned for Admin dispatch.
5. Admin can assign or reassign a ticket to any active Agent. The Agent's profile Support Team or Request Type does not block an Admin's manual assignment.
6. Agent visibility and reply permissions are then evaluated by the ticket access rules. Team visibility does not give every team member permission to post as the assigned Agent.

Agent Support Team membership and Request Type are separate profile settings. They are not a cascading dropdown dependency.

---

## SLA and notifications

The backend runs scheduled tasks while the application process is running. These include:
- Response SLA milestone scans.
- Resolution SLA milestone scans.
- Customer ticket schedule checks.
- Daily summary processing.
- Queued email retry processing.

SLA calculations use the Support Plan associated with the ticket and its configured calendar/time-zone rules. Scheduled tasks stop when the application process stops, so keep the application process running for continuous background processing.

Email notifications depend on working SMTP settings and user/event preferences. In-app notifications are stored separately and do not require SMTP.

---

## Project structure

```text
golden_pride_ticket_system/
├── main.py                    # FastAPI backend, database models, API, business logic
├── requirements.txt           # Python dependencies
├── .env.example               # Environment configuration template
├── .env                       # Local secrets; create locally and do not commit
├── schema.sql                 # PostgreSQL schema reference
├── ERD_MAPPING.md             # Entity/relationship mapping notes
├── login.html
├── admin-dashboard.html
├── agent-dashboard.html
├── user-dashboard.html        # Customer Portal dashboard
├── tickets.html
├── ticket-detail.html
├── customers.html
├── contacts.html
├── projects.html
├── contracts.html
├── support-plans.html
├── service-catalog.html
├── teams.html
├── assets.html
├── users.html
├── roles-access.html
├── audit-log.html
├── email-notifications.html
├── css/
│   ├── style.css
│   └── role-access.css
└── js/
    ├── app.js                 # Shared frontend/API behavior
    └── role-access.js         # Role-access page behavior
```

There are also separate HTML pages for add/edit forms and Customer Portal functions.

---

## Requirements

- Windows, Linux, or macOS
- Python 3.10 or newer (Python 3.13 is supported by the supplied project environment)
- PostgreSQL
- A browser
- SMTP account/settings if outgoing email is required

Python dependencies are listed in `requirements.txt`:

- FastAPI
- Uvicorn
- SQLAlchemy
- psycopg
- python-dotenv
- itsdangerous
- tzdata

---

## Installation on Windows

### 1. Open the project folder

Open the folder containing `main.py` in VS Code.

Open a PowerShell terminal in that same folder.

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use the appropriate execution-policy setting permitted by your Windows environment, or activate the environment from Command Prompt instead.

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create the PostgreSQL database

Create an empty database in pgAdmin or with `psql`:

```sql
CREATE DATABASE golden_pride_ticket;
```

If you already have a project database containing real or test records, **do not create a replacement database or drop the existing one**. Configure the application to use the intended existing database.

### 5. Create the local environment file

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and enter the connection details for your PostgreSQL installation.

---

## GitHub and private local files

Do not commit passwords, database connection strings, generated Admin credentials, or local virtual-environment files.

Create a `.gitignore` file in the project root before your first Git commit. A suitable starting point is:

```gitignore
# Local secrets and configuration
.env
.golden_pride_private/
initial_admin_credentials.txt
*.pem
*.key

# Python virtual environment and cache
.venv/
venv/
__pycache__/
*.py[cod]

# Local editor and operating-system files
.vscode/
.idea/
.DS_Store
Thumbs.db
```

Keep `.env.example` in the repository as a template with placeholder values only. Never put real passwords, API keys, SMTP credentials, or generated Admin passwords in `.env.example`.

If a secret has already been committed or pushed, adding it to `.gitignore` is not enough: revoke or rotate that secret and clean the repository history before sharing the repository further.

---

## Environment configuration

Example `.env` values:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@127.0.0.1:5432/golden_pride_ticket
SESSION_SECRET=replace-with-a-long-random-secret
COOKIE_HTTPS_ONLY=false
```

Use the actual PostgreSQL username, password, host, port, and database name for your machine.

**Important:**
- Keep `.env` private. Do not upload it to a public repository or share it with other people.
- Do not overwrite your existing `.env` when updating the application.
- If the PostgreSQL password contains URL-reserved characters, URL-encode those characters in `DATABASE_URL`.
- Use a strong, unique `SESSION_SECRET`.
- For an HTTPS deployment, configure HTTPS and set `COOKIE_HTTPS_ONLY=true`.

---

## Run the application

From the folder containing `main.py`, with the virtual environment active:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open the application in your browser:

```text
http://127.0.0.1:8000
```

The root address redirects to the login page.

**Do not open the HTML files by double-clicking them.** The pages must be served by FastAPI so that login sessions, API calls, database updates, permissions, and notifications work correctly.

For local development, keep the terminal window running while using the application. Stop the server with `Ctrl + C`.

---

## Database behavior and backups

- On startup, the application creates missing SQLAlchemy tables, runs its built-in legacy-schema adjustments, seeds starter data when applicable, and ensures default Support Teams are present.
- Existing database records are intended to be retained by the startup adjustments; the application does not require deleting the database for normal code updates.
- New columns and supporting tables may be added by the startup migration logic as the project evolves.
- `schema.sql` is provided as a schema reference; normal startup handles table creation for this application.

### Before updating the project

1. Stop the running application.
2. Back up the PostgreSQL database.
3. Back up the current project folder.
4. Preserve your existing `.env`.
5. Copy only the intended updated application files into the project.
6. Start the application and verify the health endpoint and key workflows.

Do not drop tables or recreate the database just to install a frontend/backend code update.

### Active and deactivated records

Deactivation is different from deletion:
- Deactivated records remain in PostgreSQL.
- Dashboard active counts exclude deactivated records.
- Admin list pages can continue to show inactive records so they can be reviewed or reactivated.
- Deleting a record is a separate operation and may remove related data according to the database relationships and backend rules.

---

## Useful URLs

| URL | Purpose |
|---|---|
| `http://127.0.0.1:8000/` | Application entry point |
| `http://127.0.0.1:8000/api/health` | API and database health check |
| `http://127.0.0.1:8000/docs` | Optional interactive API documentation |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI specification |

A healthy database connection should return a response similar to:

```json
{
  "status": "ok",
  "database": "connected"
}
```

---

## Troubleshooting

### `connection refused`
- Confirm that the PostgreSQL service is running.
- Check the host and port in `.env` (commonly `127.0.0.1:5432`).

### `password authentication failed`
- Check the PostgreSQL username and password in `DATABASE_URL`.
- Check URL encoding if the password contains special characters.

### `database does not exist`
- Create the database or correct the database name in `.env`.

### `ModuleNotFoundError`
- Activate the project's `.venv`.
- Run `pip install -r requirements.txt` again.

### Port 8000 is already in use
Run the application on another port:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

Then open `http://127.0.0.1:8001`.

### Frontend opens but data or login does not work
- Make sure the page was opened through `http://127.0.0.1:8000/`, not as a local `file:///` path.
- Confirm that Uvicorn is still running.
- Check `/api/health`.
- Check the terminal for backend errors.
- Confirm that `.env` points to the intended PostgreSQL database.

### Email does not arrive
- Verify SMTP host, port, encryption, sender address, and authentication settings in the Admin Email Notifications page.
- Send a test email.
- Check the email delivery records for failed status and error details.
- Confirm the recipient's notification preferences and the relevant event rule.

---

## Important operational notes

- This project is an application codebase, not a hosted service. It needs a running Python process and a reachable PostgreSQL server.
- Starter/demo accounts and passwords, when created, apply only when the database is first seeded. Existing account passwords are not changed simply by editing `.env`.
- Change any demo credentials before using the application with real data.
- Back up the database before schema/code updates and before deleting records.
- Real SMTP delivery requires valid provider credentials and network access.
- The attachment reference field in the ticket data model does not, by itself, mean that a complete file-upload storage service is configured.
- Use HTTPS, strong secrets, database access controls, and secure backups before exposing the application outside a trusted local network.
