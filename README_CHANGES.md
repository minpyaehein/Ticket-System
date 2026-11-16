# Audit Log, Email Notifications and Customer Password Reset

## What's added

- The Audit Log page reads rows from PostgreSQL through `/api/audit-logs`, supports searching, action/entity filters and inclusive date filters, and exports the filtered view to CSV.
- Create, update and delete events store a field-level `from` / `to` diff. The details dialog shows the actor, role, entity, summary, IP address and changed field values. Password hashes and temporary passwords are never stored in audit diffs.
- New audit columns and the `users.must_change_password` flag are added automatically at application startup for existing databases.
- Admins can use **Reset password** on a customer user row. This generates a temporary password and emails it using the saved SMTP settings. On the next sign in, the customer is redirected to the Change Password page; the backend blocks other API access until the password has changed.
- Admins continue to manage SMTP and global event rules. Agent and Customer roles also have an **Email Notifications** page for their own notification preferences. Recipient routing respects these preferences for ticket-created, assigned, status-changed, reply, SLA-approaching, resolved, and daily-summary events.
- Email send/skip/failure and password-reset activity is recorded in the Audit Log.

## Existing installation

1. Back up the PostgreSQL database before updating application code.
2. Extract this project and copy the existing `.env` into `golden_pride_ticket_system/`.
3. Activate the virtual environment and install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Configure and save SMTP credentials in **Email Notifications** as Admin. Use **Send test email** to verify the real mail server before using customer password reset.
5. Start from the folder containing `main.py`:

   ```powershell
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

The application automatically adds the new columns when it starts against the existing schema. Take a database backup first; the app does not delete existing rows.

## Test limits

Code/API tests were run against an isolated SQLite test database. SMTP calls were mocked for the password-reset workflow, so real PostgreSQL connectivity and real email delivery still must be verified on your machine with your `.env` and SMTP provider.
