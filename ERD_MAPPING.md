# ERD and API mapping

## Tables from the provided diagram

| ERD entity | PostgreSQL table | Primary key | Main foreign keys |
|---|---|---|---|
| Ticket | `tickets` | `ticket_id` | `project_id`, `customer_id`, `contact_id`, `plan_id`, `asset_id`; `contract_id` and `service_code` are added for the matching ticket form fields |
| User | `users` | `user_id` | `team_id` |
| Team | `teams` | `team_id` | `code_id` → `service_catalog.code_id` |
| Service Catalog | `service_catalog` | `code_id` | `mapped_team` remains the supplied mapped-team text field |
| Project | `projects` | `project_id` | `customer_id` |
| Customer | `customers` | `customer_id` | — |
| Contact | `contacts` | `contact_id` | `customer_id` |
| Plan | `plans` | `plan_id` | — |
| Contract | `contracts` | `contract_id` | `customer_id`, `project_id`, `plan_id` |
| Asset | `assets` | `asset_id` | `customer_id`, `project_id` |

## Supporting tables

- `ticket_replies`: stores customer/agent replies for the ticket detail page.
- `team_service_catalog`: preserves the multi-select service catalog UI for teams; `teams.code_id` remains the primary service foreign key shown in the ERD.
- `role_permissions`: stores the permission matrix submitted from the Add Role form.
- `audit_logs`: records login, CRUD and ticket reply activity for the Audit Log page.
- `email_settings`: stores SMTP settings and event-rule options for Email Notifications.

## API path patterns

- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `GET /api/{resource}`; `POST /api/{resource}`
- `GET /api/{resource}/{id}`; `PUT /api/{resource}/{id}`; `DELETE /api/{resource}/{id}`
- Resources: `tickets`, `customers`, `contacts`, `projects`, `users`, `teams`, `services`, `plans`, `contracts`, `assets`, `audit-logs`, `role-permissions`
- `GET/POST /api/tickets/{id}/replies`
- `GET /api/lookups`, `GET /api/dashboard/stats`, `GET/PUT /api/email-settings`, `POST /api/email-settings/test`

`main.py` defines the SQLAlchemy models and automatically creates missing tables during startup. `schema.sql` is generated from those models for reference.
