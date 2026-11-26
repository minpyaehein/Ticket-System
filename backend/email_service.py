"""Email Service logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .models import *
from .security import *

def _attempt_queued_delivery(db: Session, delivery: EmailDelivery, cfg: dict[str, Any], force: bool = False) -> None:
    delivery.status = "queued"
    delivery.error = None
    db.flush()
    if not bool(cfg.get("enabled", False)) or not cfg.get("smtp_host") or not cfg.get("from_email"):
        delivery.status = "queued"
        delivery.error = "Email service is disabled or SMTP settings are incomplete."
        return
    max_attempts = int(cfg.get("max_retry", 3)) + 1
    if delivery.attempts >= max_attempts:
        if force:
            delivery.attempts = 0  # A manual retry starts a fresh retry cycle.
        else:
            delivery.status = "failed"
            delivery.error = f"Maximum attempts ({max_attempts}) reached."
            delivery.next_attempt_at = None
            return
    if not force and delivery.next_attempt_at and delivery.next_attempt_at > datetime.utcnow():
        delivery.status = "failed"
        return
    delivery.attempts += 1
    try:
        _send_notification_email(cfg, [delivery.recipient_email], delivery.subject, delivery.body)
        delivery.status = "sent"
        delivery.sent_at = datetime.utcnow()
        delivery.error = None
        delivery.next_attempt_at = None
    except Exception as exc:
        delivery.status = "failed"
        delivery.error = str(exc)[:2000]
        delivery.next_attempt_at = (datetime.utcnow() + timedelta(minutes=max(1, int(cfg.get("retry_delay", 5))))) if delivery.attempts < max_attempts else None

async def _attempt_queued_delivery_async(
    db: Session,
    delivery: EmailDelivery,
    cfg: dict[str, Any],
) -> None:
    """Dispatch one queued message without blocking FastAPI's event loop."""
    delivery.status = "queued"
    delivery.error = None
    db.flush()
    if not bool(cfg.get("enabled", False)) or not cfg.get("smtp_host") or not cfg.get("from_email"):
        delivery.status = "queued"
        delivery.error = "Email service is disabled or SMTP settings are incomplete."
        return
    max_attempts = int(cfg.get("max_retry", 3)) + 1
    if delivery.attempts >= max_attempts:
        delivery.status = "failed"
        delivery.error = f"Maximum attempts ({max_attempts}) reached."
        delivery.next_attempt_at = None
        return
    if delivery.next_attempt_at and delivery.next_attempt_at > datetime.utcnow():
        delivery.status = "failed"
        return
    delivery.attempts += 1
    try:
        await send_email_async(
            cfg,
            [delivery.recipient_email],
            delivery.subject,
            delivery.body,
        )
        delivery.status = "sent"
        delivery.sent_at = datetime.utcnow()
        delivery.error = None
        delivery.next_attempt_at = None
    except Exception as exc:
        delivery.status = "failed"
        delivery.error = str(exc)[:2000]
        delivery.next_attempt_at = (
            datetime.utcnow() + timedelta(minutes=max(1, int(cfg.get("retry_delay", 5))))
            if delivery.attempts < max_attempts else None
        )

async def email_retry_loop() -> None:
    """Retry failed SMTP deliveries after the configured delay while the API is running."""
    while True:
        db = SessionLocal()
        try:
            setting = db.get(EmailSetting, 1)
            cfg = json.loads(setting.settings_json or "{}") if setting else {}
            if bool(cfg.get("enabled", False)) and cfg.get("smtp_host") and cfg.get("from_email"):
                now = datetime.utcnow()
                due = db.scalars(select(EmailDelivery).where(
                    or_(EmailDelivery.status == "queued",
                        (EmailDelivery.status == "failed") &
                        (EmailDelivery.attempts <= int(cfg.get("max_retry", 3))) &
                        (or_(EmailDelivery.next_attempt_at.is_(None), EmailDelivery.next_attempt_at <= now)))
                ).order_by(EmailDelivery.created_at).limit(50).with_for_update(skip_locked=True)).all()
                for row in due:
                    await _attempt_queued_delivery_async(db, row, cfg)
                if due:
                    db.commit()
        except Exception:
            db.rollback()
            logger.exception("Email retry loop failed while processing queued deliveries")
        finally:
            db.close()
        await asyncio.sleep(5)

def _send_notification_email(cfg: dict[str, Any], recipients: list[str], subject: str, body: str) -> None:
    """Send one SMTP message to a deduplicated recipient list."""
    recipients = sorted({str(x).strip() for x in recipients if x and "@" in str(x)})
    host = str(cfg.get("smtp_host", "")).strip()
    from_email = str(cfg.get("from_email", "")).strip()
    if not recipients or not host or not from_email:
        return
    encryption = cfg.get("encryption", "STARTTLS")
    if encryption not in {"STARTTLS", "SSL / TLS", "None"}:
        raise RuntimeError("Unsupported SMTP encryption mode. Choose STARTTLS, SSL / TLS, or None.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{cfg.get('from_name', 'Golden Pride Support')} <{from_email}>"
    message["To"] = ", ".join(recipients)
    if cfg.get("reply_to_email"):
        message["Reply-To"] = cfg["reply_to_email"]
    message.set_content(body)
    timeout = max(3, min(int(cfg.get("timeout") or 15), 60))
    port = int(cfg.get("smtp_port") or 587)
    try:
        tls_context = ssl.create_default_context()
        if bool(cfg.get("allow_self_signed_certificate", False)):
            # This is intentionally opt-in for private SMTP servers only.
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE
        if cfg.get("encryption") == "SSL / TLS":
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=tls_context) as server:
                _smtp_auth(server, cfg)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                if cfg.get("encryption", "STARTTLS") == "STARTTLS":
                    server.starttls(context=tls_context)
                    server.ehlo()
                _smtp_auth(server, cfg)
                server.send_message(message)
    except socket.gaierror as exc:
        raise RuntimeError(f"SMTP host '{host}' could not be resolved. Check Email Notifications > SMTP host and internet/DNS connectivity. For Gmail choose the Gmail provider preset (smtp.gmail.com). Do not enter an email address or URL in the host field.") from exc

async def send_email_async(
    cfg: dict[str, Any],
    recipients: list[str],
    subject: str,
    body: str,
) -> None:
    """Send via smtplib in a worker thread so SMTP I/O never blocks the event loop."""
    await asyncio.to_thread(
        _send_notification_email,
        cfg,
        recipients,
        subject,
        body,
    )

def _user_allows_event(db: Session, email: str, event: str, legacy_event: str | None = None) -> bool:
    if legacy_event is None:
        legacy_event = {
            "ticket_created_support": "ticket_created",
            "ticket_created_customer": "ticket_created",
            "ticket_updated_customer": "status_changed",
            "customer_reply": "new_reply",
            "engineer_public_reply": "new_reply",
            "response_sla_warning": "sla_approaching",
            "response_sla_critical": "sla_approaching",
            "response_sla_breach": "sla_approaching",
            "resolution_sla_warning": "sla_approaching",
            "resolution_sla_critical": "sla_approaching",
            "resolution_sla_breach": "sla_approaching",
            "pending_customer_reminder": "status_changed",
            "resolution_confirmation_reminder": "ticket_resolved",
            "auto_closed": "ticket_resolved",
        }.get(event)
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower(), User.active.is_(True)))
    if not user:
        return True  # Customer contact addresses may not have portal logins.
    row = db.get(UserNotificationPreference, user.user_id)
    if not row:
        return True
    try:
        prefs = json.loads(row.settings_json or "{}")
        if event in prefs:
            return bool(prefs[event])
        if legacy_event and legacy_event in prefs:
            return bool(prefs[legacy_event])
        return True
    except (json.JSONDecodeError, AttributeError):
        return True

EMAIL_EVENT_LABELS: dict[str, str] = {
    "ticket_created_support": "New Ticket - Support Notification",
    "ticket_created_customer": "New Ticket - Customer Confirmation",
    "ticket_assigned": "Assigned / Reassigned",
    "status_changed": "Ticket Status Changed",
    "ticket_updated_customer": "Ticket Details Updated",
    "customer_reply": "Customer Reply",
    "engineer_public_reply": "Engineer Public Reply",
    "internal_note": "Internal Note",
    "pending_customer": "Pending Customer",
    "resolved": "Resolved",
    "customer_accepted_resolution": "Customer Accepted Resolution",
    "ticket_reopened": "Ticket Reopened",
    "ticket_closed": "Ticket Closed",
    "response_sla_warning": "Response SLA Warning",
    "response_sla_critical": "Response SLA Critical",
    "response_sla_breach": "Response SLA Breach",
    "resolution_sla_warning": "Resolution SLA Warning",
    "resolution_sla_critical": "Resolution SLA Critical",
    "resolution_sla_breach": "Resolution SLA Breach",
    "unassigned_team_queue": "Unassigned Admin Dispatch Queue",
    "pending_customer_reminder": "Pending Customer Reminder",
    "resolution_confirmation_reminder": "Resolution Confirmation Reminder",
    "auto_closed": "Auto Closed",
    "daily_summary": "Daily Ticket Summary",
}

def _email_event_display_label(event_key: str, audience_role: str | None = None) -> str:
    """Build the delivery-log label from the canonical event key."""
    label = EMAIL_EVENT_LABELS.get(event_key, str(event_key or "").replace("_", " ").title())
    if audience_role:
        label = f"{label} · {audience_role.title()}"
    return label

EMAIL_TEMPLATE_AUDIENCES: dict[str, tuple[str, ...]] = {
    "ticket_created_support": ("admin", "agent"),
    "ticket_created_customer": ("customer",),
    "ticket_assigned": ("admin", "agent"),
    "customer_reply": ("admin", "agent"),
    "engineer_public_reply": ("customer",),
    "internal_note": ("admin", "agent"),
    "pending_customer": ("customer",),
    "resolved": ("customer",),
    "customer_accepted_resolution": ("admin", "agent", "customer"),
    "ticket_reopened": ("admin", "agent"),
    "ticket_closed": ("admin", "customer"),
    "status_changed": ("admin", "customer"),
    "ticket_updated_customer": ("admin", "customer"),
    "response_sla_warning": ("admin", "agent"),
    "response_sla_critical": ("admin", "agent"),
    "response_sla_breach": ("admin", "agent"),
    "resolution_sla_warning": ("admin", "agent"),
    "resolution_sla_critical": ("admin", "agent"),
    "resolution_sla_breach": ("admin", "agent"),
    "unassigned_team_queue": ("admin",),
    "pending_customer_reminder": ("customer",),
    "resolution_confirmation_reminder": ("customer",),
    "auto_closed": ("customer",),
    "daily_summary": ("admin", "agent"),
}

_EVENT_ROLE_COPY: dict[str, dict[str, str]] = {
    "ticket_created_support": {
        "admin": "A new customer ticket has entered the support queue. Review the ticket details and confirm that the correct team and engineer are assigned.",
        "agent": "A new ticket has been submitted to your support team. Review the request and follow your team's assignment process.",
    },
    "ticket_created_customer": {
        "customer": "We have received your support request. Keep this email for your records. Our support team will review the ticket and contact you through the ticket thread.",
    },
    "ticket_assigned": {
        "admin": "A ticket assignment has changed. This is an internal dispatch update for administrators.",
        "agent": "This ticket is assigned to you. You can send a public reply to the customer and add a staff-only internal note for Admin and yourself.",
    },
    "customer_reply": {
        "admin": "A customer has replied to a ticket. Review the conversation if escalation or coordination is required.",
        "agent": "The customer has replied to a ticket assigned to you. Review the message and continue the conversation with a public reply or an internal note for Admin.",
    },
    "engineer_public_reply": {
        "customer": "The support team has posted a public reply to your ticket. Sign in to Golden Pride to read the full conversation and provide any requested information.",
    },
    "internal_note": {
        "admin": "A staff-only internal note was added. This message is restricted to authorized support staff and must not be forwarded to the customer.",
        "agent": "A staff-only internal note was added to this ticket. Read it as internal support context. Do not copy internal-note content into customer-facing replies.",
    },
    "pending_customer": {
        "customer": "Your ticket is waiting for information or confirmation from you. Please review the request below and reply through the customer portal so the support team can continue.",
    },
    "resolved": {
        "customer": "Your ticket has been marked as resolved. Please review the resolution details and use the customer portal link below to accept the resolution or reopen the ticket if the issue is not fixed. Ticket details: {{ticket_url}}",
    },
    "customer_accepted_resolution": {
        "admin": "The customer accepted the proposed resolution. This is an internal record of the resolution acceptance.",
        "agent": "The customer accepted your ticket's proposed resolution. Review the ticket and complete any remaining internal follow-up.",
        "customer": "Thank you for confirming. Your ticket is now closed. If the issue returns, please contact support and reference this ticket. Ticket details: {{ticket_url}}",
    },
    "ticket_reopened": {
        "admin": "A previously resolved or closed ticket has been reopened and requires staff attention.",
        "agent": "This ticket has been reopened and returned to the support workload. Review the latest conversation and coordinate any required action with the Admin.",
    },
    "ticket_closed": {
        "admin": "A ticket has been closed. This is a global status event for the administrator activity record.",
        "customer": "Your ticket has been closed. You can contact the support team and reference this ticket if you need further assistance.",
    },
    "status_changed": {
        "admin": "A ticket status changed. Review the status and ticket history if administrative action is needed.",
        "customer": "The status of your support ticket has changed. Review the latest status below and sign in to see the ticket history.",
    },
    "ticket_updated_customer": {
        "admin": "Ticket details were updated. This is an administrative record of the customer-facing change.",
        "customer": "The support team updated details on your ticket. Review the information below and contact support if anything looks incorrect.",
    },
    "response_sla_warning": {
        "admin": "A ticket is approaching the first-public-response target configured in its linked Support Plan.",
        "agent": "The first-public-response target in this ticket's Support Plan is approaching. Send a public reply to the customer.",
    },
    "response_sla_critical": {
        "admin": "A ticket has reached the critical percentage of its first-public-response Support Plan target.",
        "agent": "The first-public-response target is at its critical threshold. Send a public reply immediately.",
    },
    "response_sla_breach": {
        "admin": "A ticket has breached its first-public-response SLA target from its linked Support Plan. Review the breach and escalation.",
        "agent": "The first-public-response SLA target from this ticket's Support Plan has been exceeded. Send the required public response and follow the escalation procedure.",
    },
    "resolution_sla_warning": {
        "admin": "A ticket is approaching the resolution target configured in its linked Support Plan.",
        "agent": "The Support Plan resolution target is approaching. Continue working the ticket and update its status as appropriate.",
    },
    "resolution_sla_critical": {
        "admin": "A ticket has reached the critical percentage of its Support Plan resolution target.",
        "agent": "The Support Plan resolution target is at its critical threshold. Prioritize the remaining work.",
    },
    "resolution_sla_breach": {
        "admin": "A ticket has exceeded its Support Plan resolution target. Review the SLA breach and escalation requirements.",
        "agent": "The Support Plan resolution target has been exceeded. Escalate and continue working toward resolution.",
    },
    "unassigned_team_queue": {
        "admin": "A new ticket is not assigned to an engineer. Review the support queue and assign an eligible agent.",
    },
    "pending_customer_reminder": {
        "customer": "This is a reminder that the support team is waiting for your response. Please reply to the ticket so work can continue.",
    },
    "resolution_confirmation_reminder": {
        "customer": "The support team is waiting for your confirmation of the proposed resolution. Open your ticket below to accept the resolution or reopen it if the issue is not fixed. Ticket details: {{ticket_url}}",
    },
    "auto_closed": {
        "customer": "Your ticket was automatically closed under the support team's ticket policy. You can contact support and reference this ticket if you still need help.",
    },
    "daily_summary": {
        "admin": "This is the daily overview of open support tickets for administrative monitoring.",
        "agent": "This is your daily overview of open support tickets for work planning.",
    },
}

_TEMPLATE_VARIABLES_HELP = (
    "Ticket No: {{ticket_no}}\nSubject: {{ticket_subject}}\nCustomer: {{customer_name}}\n"
    "Ticket Portal: {{ticket_url}}\n"
    "Priority: {{priority}}\nStatus: {{status}}\nSupport Team: {{team_name}}\n"
    "Assigned To: {{assigned_to}}\nDue Date: {{due_date}}\n"
    "Project: {{project_name}}\nContract: {{contract_no}}\nService: {{service_name}}\n"
    "Created By: {{created_by_name}}\nCreated At: {{created_timestamp}}\n"
    "Latest Update: {{event_message}}\nResolution: {{resolution}}\n\nGolden Pride Support"
)

def _build_default_email_templates() -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}
    for event_key, roles in EMAIL_TEMPLATE_AUDIENCES.items():
        event_label = EMAIL_EVENT_LABELS[event_key]
        for role in roles:
            copy_text = _EVENT_ROLE_COPY.get(event_key, {}).get(role, "A ticket event requires your attention.")
            key = f"{event_key}__{role}"
            if event_key == "daily_summary":
                templates[key] = {
                    "subject": "[Golden Pride] Daily Ticket Summary - {{summary_date}}",
                    "body": (
                        "Dear {{recipient_name}},\n\n"
                        f"{copy_text}\n\n"
                        "Summary date: {{summary_date}}\n"
                        "Open tickets listed: {{open_ticket_count}}\n\n"
                        "{{ticket_lines}}\n\n"
                        "Golden Pride Support"
                    ),
                }
            else:
                templates[key] = {
                    "subject": f"[Golden Pride] {event_label} - {{{{ticket_no}}}} - {{{{ticket_subject}}}}",
                    "body": (
                        "Dear {{recipient_name}},\n\n"
                        f"{copy_text}\n\n"
                        "{{event_message}}\n\n"
                        f"{_TEMPLATE_VARIABLES_HELP}"
                    ),
                }
    return templates

DEFAULT_EMAIL_TEMPLATES: dict[str, dict[str, str]] = _build_default_email_templates()

LEGACY_GENERIC_EMAIL_TEMPLATE = {
    "subject": "[CTS] {{event_label}} - {{ticket_no}} - {{ticket_subject}}",
    "body": "Dear {{recipient_name}},\n\n{{event_label}} for ticket {{ticket_no}}.\n\n{{event_message}}\n\nTicket No: {{ticket_no}}\nSubject: {{ticket_subject}}\nCustomer: {{customer_name}}\nProject: {{project_name}}\nContract: {{contract_no}}\nService: {{service_name}}\nStatus: {{status}}\nSupport Team: {{team_name}}\nAssigned To: {{assigned_to}}\nCreated By: {{created_by_name}}\nCreated At: {{created_timestamp}}\nResolution: {{resolution}}\n\nGolden Pride Service Desk",
}

def _effective_email_templates(saved_templates: dict[str, dict[str, str]] | None) -> dict[str, dict[str, str]]:
    """Merge defaults and migrate customized single-event templates into role variants."""
    saved = saved_templates or {}
    result = dict(DEFAULT_EMAIL_TEMPLATES)
    result.update(saved)
    for event_key, roles in EMAIL_TEMPLATE_AUDIENCES.items():
        legacy_template = saved.get(event_key)
        if not legacy_template or legacy_template == LEGACY_GENERIC_EMAIL_TEMPLATE:
            continue
        for role in roles:
            role_key = f"{event_key}__{role}"
            if role_key not in saved:
                result[role_key] = legacy_template
    return result

def _email_template_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for event_key, roles in EMAIL_TEMPLATE_AUDIENCES.items():
        for role in roles:
            options.append({
                "key": f"{event_key}__{role}",
                "event_key": event_key,
                "role": role,
                "label": f"{role.title()} - {EMAIL_EVENT_LABELS[event_key]}",
            })
    return options

def _default_event_rules() -> dict[str, bool]:
    rules = {key: True for key in EMAIL_EVENT_LABELS}
    rules["daily_summary"] = False
    return rules

def _template_context(db: Session, ticket: Ticket, recipient: User | None, event_key: str,
                      actor: dict[str, Any] | None, message: str) -> dict[str, str]:
    customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
    project = db.get(Project, ticket.project_id) if ticket.project_id else None
    contract = db.get(Contract, ticket.contract_id) if ticket.contract_id else None
    service = db.get(ServiceCatalog, ticket.service_code) if ticket.service_code else None
    plan = db.get(Plan, ticket.plan_id) if ticket.plan_id else None
    team = db.get(Team, ticket.team_id) if ticket.team_id else None
    team_name = team.team_name if team else "—"
    if team_name == "—" and ticket.assigned:
        assigned_user = db.scalar(select(User).where(func.lower(User.fullname) == str(ticket.assigned).strip().lower()))
        assigned_team = db.get(Team, assigned_user.team_id) if assigned_user and assigned_user.team_id else None
        if assigned_team:
            team_name = assigned_team.team_name
    return {
        "recipient_name": recipient.fullname if recipient else (customer.customer_name if customer else "Customer"),
        "recipient_email": recipient.email if recipient else (customer.email if customer else ""),
        "event_label": EMAIL_EVENT_LABELS.get(event_key, event_key.replace("_", " ").title()),
        "event_message": message,
        "ticket_no": ticket.ticket_code or f"TKT-{ticket.ticket_id}",
        "ticket_subject": ticket.subject or "—",
        "ticket_description": ticket.description or "—",
        "customer_name": customer.customer_name if customer else "—",
        "project_name": project.project_name if project else "—",
        "contract_no": (contract.contract_code or contract.contract_name) if contract else "—",
        "service_name": service.name if service else (ticket.type or "—"),
        "status": ticket.status or "—",
        "team_name": team_name,
        "assigned_to": ticket.assigned or "Unassigned",
        "created_by_name": (actor or {}).get("fullname") or "System",
        "created_by_email": (actor or {}).get("email") or "",
        "created_timestamp": format_yangon_datetime(ticket.created_at or ticket.updated_at),
        "resolution": getattr(ticket, "resolution", None) or "—",
        "requester_name": customer.contact_name if customer and customer.contact_name else (customer.customer_name if customer else "—"),
        "requester_email": customer.email if customer else "",
        "priority": ticket.priority or "—",
        "due_date": ticket.due_date.isoformat() if ticket.due_date else "Not set",
        "ticket_url": f"{APP_BASE_URL}/user-ticket-detail.html?id={ticket.ticket_id}" if APP_BASE_URL else "Configure APP_BASE_URL in the server .env to enable the customer ticket link.",
        "event_details": message or "—",
        "reply_message": message or "—",
    }

def _render_email_template(template: dict[str, str], context: dict[str, str]) -> tuple[str, str]:
    def render(value: str) -> str:
        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", lambda m: str(context.get(m.group(1), "") or ""), value or "")
    return render(template.get("subject", "")), render(template.get("body", ""))

def parse_email_template(
    settings: dict[str, Any],
    event_key: str,
    audience_role: str,
    variables: dict[str, str],
) -> tuple[str, str]:
    """Render the PostgreSQL-persisted role-specific template for an event.

    This project stores editable templates in email_settings.settings_json so the
    existing Admin Email Notifications UI and deployed database remain compatible.
    """
    templates = _effective_email_templates(settings.get("templates") or {})
    template = templates.get(f"{event_key}__{audience_role}", {})
    if not template:
        raise ValueError(f"No email template configured for {event_key} / {audience_role}")
    return _render_email_template(template, variables)

def _active_admin_users(db: Session) -> list[User]:
    return db.scalars(select(User).where(User.role == "admin", User.active.is_(True))).all()

def _ticket_customer_user(db: Session, ticket: Ticket) -> User | None:
    customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
    if not customer or not customer.email:
        return None
    return db.scalar(select(User).where(func.lower(User.email) == customer.email.lower(), User.role == "customer", User.active.is_(True)))

def _agent_is_explicitly_assigned(db: Session, ticket: Ticket, actor: dict[str, Any]) -> bool:
    """Team membership grants viewing only; status changes and staff replies require the assigned Agent."""
    assigned_agent = _ticket_assigned_agent(db, ticket)
    try:
        actor_user_id = int(actor.get("user_id") or 0)
    except (TypeError, ValueError):
        return False
    return bool(assigned_agent and assigned_agent.user_id == actor_user_id)

def _ticket_notification_recipients(db: Session, ticket: Ticket, event: str, actor: dict[str, Any] | None) -> list[User]:
    """In-app audience. Admins receive every ticket event; staff/customer audiences are explicit."""
    admins = _active_admin_users(db)
    agent = _ticket_assigned_agent(db, ticket)
    customer = _ticket_customer_user(db, ticket)
    recipients: dict[int, User] = {u.user_id: u for u in admins}
    if event == "ticket_created":
        if customer:
            recipients[customer.user_id] = customer
    elif event == "ticket_assigned":
        if agent:
            recipients[agent.user_id] = agent
        if customer:
            recipients[customer.user_id] = customer
    elif event == "status_changed":
        # General status changes are customer-facing updates. The assigned Agent
        # is notified only for work specifically routed to the Agent (assignment,
        # customer reply, internal note, or SLA alert).
        if customer:
            recipients[customer.user_id] = customer
    elif event == "new_reply":
        if actor and actor.get("role") == "customer":
            if agent:
                recipients[agent.user_id] = agent
        elif customer:
            recipients[customer.user_id] = customer
    elif event == "internal_note":
        # Internal notes are shared only between Admin and the ticket's assigned Agent.
        if agent:
            recipients[agent.user_id] = agent
    elif event == "unassigned_team_queue":
        # Unassigned work stays in the Admin dispatch queue, never in Agent lists.
        pass
    elif event == "customer_accepted_resolution":
        if agent:
            recipients[agent.user_id] = agent
    elif event == "ticket_updated":
        # Any ticket mutation is visible to Admin. Only an Admin's customer-related
        # edit is additionally surfaced to the linked customer and assigned agent.
        if actor and actor.get("role") == "admin":
            if customer:
                recipients[customer.user_id] = customer
    elif event in {"ticket_resolved", "ticket_closed", "ticket_reopened", "pending_customer", "resolved",
                   "pending_customer_reminder", "resolution_confirmation_reminder", "auto_closed"}:
        if customer:
            recipients[customer.user_id] = customer
    elif event == "sla_approaching" or event.startswith("response_sla_") or event.startswith("resolution_sla_"):
        if agent:
            recipients[agent.user_id] = agent
    # Never show agents/customers a notification they themselves just generated.
    # Admin notifications are intentionally retained, including the acting admin.
    if actor and actor.get("role") != "admin" and event != "ticket_created":
        recipients.pop(int(actor.get("user_id") or 0), None)
    return list(recipients.values())

def _create_ticket_in_app_notifications(db: Session, event: str, ticket: Ticket,
                                         actor: dict[str, Any] | None, message: str) -> None:
    recipients = _ticket_notification_recipients(db, ticket, event, actor)
    title_prefix = {
        "ticket_created": "New ticket",
        "ticket_assigned": "Ticket assigned to you",
        "status_changed": "Ticket status updated",
        "new_reply": "New ticket reply",
        "internal_note": "New internal note",
        "unassigned_team_queue": "Ticket needs assignment",
        "customer_accepted_resolution": "Customer accepted resolution",
        "ticket_updated": "Ticket updated for you",
        "resolved": "Ticket resolved",
        "ticket_resolved": "Ticket resolved",
        "ticket_closed": "Ticket closed",
        "ticket_reopened": "Ticket reopened",
        "pending_customer": "Your response is needed",
        "sla_approaching": "SLA deadline approaching",
        "resolution_sla_warning": "Resolution SLA warning",
        "resolution_sla_critical": "Resolution SLA critical",
        "resolution_sla_breach": "Resolution SLA breached",
        "response_sla_warning": "Response SLA warning",
        "response_sla_critical": "Response SLA critical",
        "response_sla_breach": "Response SLA breached",
        "pending_customer_reminder": "Pending customer reminder",
        "resolution_confirmation_reminder": "Resolution confirmation reminder",
        "auto_closed": "Ticket automatically closed",
    }.get(event, "Ticket update")
    code = ticket.ticket_code or f"TKT-{ticket.ticket_id}"
    actor_name = (actor or {}).get("fullname") or "System"
    for user in recipients:
        # Admin receives every ticket event, including actions by another admin.
        db.add(NotificationItem(user_id=user.user_id, event_key=event,
            title=f"{title_prefix}: {code}", message=message[:1000], ticket_id=ticket.ticket_id,
            ticket_code=code, actor_name=actor_name, actor_role=(actor or {}).get("role")))

def _event_email_targets(
    db: Session,
    event: str,
    ticket: Ticket,
    actor: dict[str, Any] | None = None,
) -> list[tuple[str, str, list[User], list[str]]]:
    """Return (event key, audience role, portal users, direct email addresses).

    Role groups are deliberately separate so Admin, Agent and Customer messages
    can use different templates for the same business event.
    """
    admins = _active_admin_users(db)
    assigned_agent = _ticket_assigned_agent(db, ticket)
    team_agents = _team_agents(db, ticket.team_id)
    customer_user = _ticket_customer_user(db, ticket)
    customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
    customer_emails = [customer.email] if customer and customer.email else []

    def staff_targets(event_key: str, include_agent: bool = True, include_team: bool = False):
        rows: list[tuple[str, str, list[User], list[str]]] = [(event_key, "admin", admins, [])]
        agents: dict[int, User] = {}
        if include_agent and assigned_agent:
            agents[assigned_agent.user_id] = assigned_agent
        if include_team:
            agents.update({u.user_id: u for u in team_agents})
        if agents:
            rows.append((event_key, "agent", list(agents.values()), []))
        return rows

    def customer_targets(event_key: str):
        return [(event_key, "customer", [customer_user] if customer_user else [],
                 customer_emails if not customer_user else [])]

    if event == "ticket_created":
        # New Ticket support notice goes to Admins and the relevant support team.
        support_agents: dict[int, User] = {u.user_id: u for u in team_agents}
        if assigned_agent:
            support_agents[assigned_agent.user_id] = assigned_agent
        return (
            [("ticket_created_support", "admin", admins, [])]
            + ([ ("ticket_created_support", "agent", list(support_agents.values()), []) ] if support_agents else [])
            + customer_targets("ticket_created_customer")
        )

    if event == "ticket_assigned":
        # Assignment is an internal event: never notify the customer.
        return staff_targets("ticket_assigned", include_agent=True)

    if event == "new_reply":
        if actor and actor.get("role") == "customer":
            # Customer replies alert Admin and the assigned Agent, not the sender.
            return staff_targets("customer_reply", include_agent=True)
        # Public staff replies are customer-facing only.
        return customer_targets("engineer_public_reply")

    if event == "internal_note":
        # Internal note is shared only with Admin and the explicitly assigned Agent.
        return staff_targets("internal_note", include_agent=True, include_team=False)

    if event == "unassigned_team_queue":
        return [("unassigned_team_queue", "admin", admins, [])]

    if event == "customer_accepted_resolution":
        return staff_targets("customer_accepted_resolution", include_agent=True) + customer_targets("customer_accepted_resolution")

    if event == "ticket_updated" and actor and actor.get("role") == "admin":
        return staff_targets("ticket_updated_customer", include_agent=False) + customer_targets("ticket_updated_customer")

    if event == "pending_customer":
        return customer_targets("pending_customer")

    if event in {"resolved", "ticket_resolved"}:
        return customer_targets("resolved")

    if event == "ticket_reopened":
        return staff_targets("ticket_reopened", include_agent=True)

    if event == "ticket_closed":
        # Global close event: Admin + Customer, but not the Agent.
        return [("ticket_closed", "admin", admins, [])] + customer_targets("ticket_closed")

    if event == "status_changed":
        status = str(ticket.status or "").strip().lower()
        if status in {"pending customer", "pending_customer", "waiting for customer"}:
            return customer_targets("pending_customer")
        if status in {"resolved", "resolution accepted"}:
            return customer_targets("resolved")
        if status == "closed":
            return [("ticket_closed", "admin", admins, [])] + customer_targets("ticket_closed")
        # A general status change is a Global event: Admin + Customer.
        return [("status_changed", "admin", admins, [])] + customer_targets("status_changed")

    if event == "sla_approaching":
        return staff_targets("response_sla_warning", include_agent=True)

    if event.startswith("response_sla_") or event.startswith("resolution_sla_"):
        return staff_targets(event, include_agent=True)

    if event in {"pending_customer_reminder", "resolution_confirmation_reminder", "auto_closed"}:
        return customer_targets(event)

    return []

def _record_email_delivery(db: Session, cfg: dict[str, Any], ticket: Ticket | None, event_key: str,
                           recipient: User | None, email: str, subject: str, body: str,
                           audience_role: str | None = None) -> EmailDelivery:
    event_label = _email_event_display_label(event_key, audience_role)
    delivery = EmailDelivery(ticket_id=ticket.ticket_id if ticket else None,
        ticket_code=(ticket.ticket_code or f"TKT-{ticket.ticket_id}") if ticket else None,
        event_key=event_key, event_label=event_label,
        recipient_user_id=recipient.user_id if recipient else None,
        recipient_name=recipient.fullname if recipient else email, recipient_email=email,
        subject=subject[:300], body=body, status="queued", attempts=0)
    # Persist an outbound job only; SMTP network latency must not block ticket actions.
    delivery.status = "queued"
    delivery.attempts = 0
    db.add(delivery)
    db.flush()
    if not bool(cfg.get("enabled", False)) or not cfg.get("smtp_host") or not cfg.get("from_email"):
        delivery.error = "Email service is disabled or SMTP settings are incomplete."
    return delivery

def _configured_event_enabled(cfg: dict[str, Any], event_key: str, legacy_key: str | None = None) -> bool:
    rules = cfg.get("event_rules") or {}
    defaults = _default_event_rules()
    if event_key in rules:
        return bool(rules[event_key])
    if legacy_key and legacy_key in rules:
        return bool(rules[legacy_key])
    return defaults.get(event_key, True)

def run_ticket_notifications(ticket_id: int, events: list[tuple[str, str]], actor: dict[str, Any] | None = None) -> None:
    """Persist notification fan-out after the ticket CRUD response has been sent."""
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return
        for event_name, extra in events:
            notify_ticket_event(db, event_name, ticket, actor, extra, request=None)
    except Exception:
        db.rollback()
        logger.exception("Background ticket notification failed for ticket %s", ticket_id)
    finally:
        db.close()

def notify_ticket_event(db: Session, event: str, ticket: Ticket, actor: dict[str, Any] | None = None,
                        extra: str = "", request: Request | None = None) -> None:
    """Create role-targeted in-app notices and queue/send configured per-recipient emails."""
    try:
        message = {
            "ticket_created": f"{(actor or {}).get('fullname') or 'A user'} created this ticket.",
            "ticket_assigned": f"Ticket {ticket.ticket_code or ticket.ticket_id} is assigned to {ticket.assigned or 'an unassigned queue'}.",
            "status_changed": f"Ticket status is now {ticket.status}." + (f" {extra}" if extra else ""),
            "new_reply": f"A new public reply was added by {(actor or {}).get('fullname') or 'a user'}.\n\nReply: {extra}".strip(),
            "internal_note": f"A staff-only internal note was added by {(actor or {}).get('fullname') or 'a staff member'}.\n\nInternal note: {extra}".strip(),
            "ticket_resolved": f"The ticket was marked {ticket.status}.",
            "resolved": f"The ticket was marked {ticket.status}.",
            "pending_customer": "The support team is waiting for a response from the customer.",
            "ticket_closed": "The ticket has been closed.",
            "ticket_reopened": "The ticket has been reopened and needs attention.",
            "customer_accepted_resolution": "The customer accepted the proposed resolution.",
            "ticket_updated": f"The support team updated ticket details. {extra}".strip(),
            "unassigned_team_queue": "This ticket is not assigned. Please review the support queue.",
            "sla_approaching": f"Ticket due date is approaching ({ticket.due_date.isoformat() if ticket.due_date else 'not set'}).",
            "response_sla_warning": f"First public response is approaching its Support Plan SLA target. {extra}".strip(),
            "response_sla_critical": f"First public response has reached its critical Support Plan SLA threshold. {extra}".strip(),
            "response_sla_breach": f"The first public response Support Plan SLA target has been exceeded. {extra}".strip(),
            "resolution_sla_warning": f"The Support Plan resolution target is approaching. {extra}".strip(),
            "resolution_sla_critical": f"The Support Plan resolution target has reached its critical threshold. {extra}".strip(),
            "resolution_sla_breach": f"The Support Plan resolution target has been exceeded. {extra}".strip(),
            "pending_customer_reminder": "We are still waiting for the information requested on your ticket. Please reply so support can continue.",
            "resolution_confirmation_reminder": "Your ticket is marked Resolved. Please confirm whether the issue is fixed or reopen it if you still need help.",
            "auto_closed": "Your ticket was automatically closed after remaining in Resolved status for the configured confirmation period.",
        }.get(event, f"Ticket update: {event.replace('_', ' ')}.")
        _create_ticket_in_app_notifications(db, event, ticket, actor, message)
        setting = db.get(EmailSetting, 1)
        cfg = json.loads(setting.settings_json or "{}") if setting else {}
        targets = _event_email_targets(db, event, ticket, actor)
        legacy = {"ticket_created_support": "ticket_created", "ticket_created_customer": "ticket_created",
                  "resolved": "ticket_resolved", "response_sla_warning": "sla_approaching",
                  "customer_reply": "new_reply", "engineer_public_reply": "new_reply",
                  "internal_note": "internal_note", "status_changed": "status_changed",
                  "ticket_closed": "status_changed", "pending_customer": "status_changed"}
        saved_templates = cfg.get("templates") or {}
        templates = _effective_email_templates(saved_templates)
        for event_key, audience_role, users, extra_emails in targets:
            if not _configured_event_enabled(cfg, event_key, legacy.get(event_key)):
                continue
            # Internal-note content is confidential. Only staff-role deliveries are
            # accepted here; customer user objects and direct customer addresses are
            # rejected even if a future routing change accidentally adds them.
            if event == "internal_note" and audience_role not in {"admin", "agent"}:
                logger.error("Blocked non-staff internal-note email target for ticket %s", ticket.ticket_id)
                continue
            unique: dict[str, User | None] = {}
            for user in users:
                if user and user.active and user.email and user.role == audience_role:
                    unique[user.email.lower()] = user
            # Direct customer contact addresses are only returned by customer_targets().
            if audience_role == "customer" and event != "internal_note":
                for email in extra_emails:
                    if email and "@" in email:
                        unique.setdefault(email.lower(), None)
            for email, recipient in unique.items():
                if recipient is not None and recipient.role != audience_role:
                    continue
                if not _user_allows_event(db, email, event_key, legacy.get(event_key)):
                    continue
                context = _template_context(db, ticket, recipient, event_key, actor, message)
                subject, body = parse_email_template(
                    {"templates": templates}, event_key, audience_role, context
                )
                # Existing database-saved templates may predate the ticket link.
                # Always append the portal URL to customer resolution emails unless
                # that exact URL is already present in the customized template.
                if (audience_role == "customer"
                        and event_key in {"resolved", "resolution_confirmation_reminder", "customer_accepted_resolution"}
                        and APP_BASE_URL and context.get("ticket_url")
                        and context["ticket_url"] not in body):
                    body = (body.rstrip() + "\n\nOpen your ticket in Golden Pride: " + context["ticket_url"])
                _record_email_delivery(
                    db, cfg, ticket, event_key, recipient, email, subject, body,
                    audience_role=audience_role,
                )
        log_action(db, actor, "NOTIFICATION_CREATED", "Notifications", f"Created in-app notifications for {event} on {ticket.ticket_code or ticket.ticket_id}", request=request, entity_id=ticket.ticket_id, entity_label=ticket.ticket_code or f"TKT-{ticket.ticket_id}")
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
            log_action(db, actor, "NOTIFICATION_FAILED", "Notifications", f"Ticket event {event} failed: {str(exc)[:350]}", request=request, entity_id=ticket.ticket_id, entity_label=ticket.ticket_code or f"TKT-{ticket.ticket_id}")
            db.commit()
        except Exception:
            db.rollback()

def _smtp_auth(server: smtplib.SMTP, cfg: dict[str, Any]) -> None:
    authentication = cfg.get("authentication", "Username and password")
    if authentication == "No authentication":
        return
    if authentication != "Username and password":
        raise RuntimeError("Unsupported SMTP authentication method. Choose Username and password or No authentication.")
    username = str(cfg.get("smtp_username") or "").strip()
    password = str(cfg.get("smtp_password") or "")
    if not username or not password:
        raise RuntimeError("SMTP username and password are required. Enter the SMTP password or App Password, then save the settings.")
    server.login(username, password)

__all__ = [name for name in globals() if not name.startswith("__")]
