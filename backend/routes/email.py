"""Email API endpoints."""
from __future__ import annotations
from ..common import *
from ..config import *
from ..models import *
from ..security import *
from ..email_service import *

router = APIRouter()

@router.get("/api/email-settings")
def get_email_settings(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    row = db.get(EmailSetting, 1)
    settings = json.loads(row.settings_json) if row else {}
    settings.setdefault("event_rules", _default_event_rules())
    settings["event_rules"] = {**_default_event_rules(), **(settings.get("event_rules") or {})}
    settings["templates"] = _effective_email_templates(settings.get("templates") or {})
    settings["default_templates"] = DEFAULT_EMAIL_TEMPLATES
    settings["template_options"] = _email_template_options()
    settings.setdefault("enabled", False)
    settings.setdefault("allow_self_signed_certificate", False)
    settings.setdefault("max_retry", 3)
    settings.setdefault("retry_delay", 5)
    # New installations start with short test-friendly minute values. Existing
    # installations keep their former schedule by converting saved hours/days.
    if settings.get("pending_customer_reminder_minutes") is None:
        settings["pending_customer_reminder_minutes"] = (
            int(settings["pending_customer_reminder_hours"]) * 60
            if settings.get("pending_customer_reminder_hours") is not None else 5
        )
    if settings.get("resolution_confirmation_reminder_minutes") is None:
        settings["resolution_confirmation_reminder_minutes"] = (
            int(settings["resolution_confirmation_reminder_days"]) * 1440
            if settings.get("resolution_confirmation_reminder_days") is not None else 5
        )
    if settings.get("auto_close_resolved_minutes") is None:
        settings["auto_close_resolved_minutes"] = (
            int(settings["auto_close_resolved_days"]) * 1440
            if settings.get("auto_close_resolved_days") is not None else 10
        )
    for legacy_key in ("pending_customer_reminder_hours", "resolution_confirmation_reminder_days", "auto_close_resolved_days"):
        settings.pop(legacy_key, None)
    settings["smtp_password_set"] = bool(settings.get("smtp_password"))
    settings.pop("smtp_password", None)
    return settings

@router.put("/api/email-settings")
def put_email_settings(payload: EmailSettingsBody, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    current = db.get(EmailSetting, 1)
    settings = json.loads(current.settings_json) if current else {}
    data = payload.model_dump()
    if data["encryption"] not in {"STARTTLS", "SSL / TLS", "None"}:
        raise HTTPException(status_code=422, detail="Encryption must be STARTTLS, SSL / TLS, or None.")
    if data["authentication"] not in {"Username and password", "No authentication"}:
        raise HTTPException(status_code=422, detail="This SMTP authentication method is not supported. Choose Username and password or No authentication.")
    if data["smtp_host"].strip() and not 1 <= data["smtp_port"] <= 65535:
        raise HTTPException(status_code=422, detail="SMTP port must be between 1 and 65535.")
    if not 3 <= data["timeout"] <= 60:
        raise HTTPException(status_code=422, detail="Connection timeout must be between 3 and 60 seconds.")
    if not 0 <= data["max_retry"] <= 10:
        raise HTTPException(status_code=422, detail="Maximum retry must be between 0 and 10.")
    if not 1 <= data["retry_delay"] <= 1440:
        raise HTTPException(status_code=422, detail="Retry delay must be between 1 and 1440 minutes.")
    legacy_to_minutes = {
        "pending_customer_reminder_minutes": ("pending_customer_reminder_hours", 60, 5, 1, 43200),
        "resolution_confirmation_reminder_minutes": ("resolution_confirmation_reminder_days", 1440, 5, 1, 43200),
        "auto_close_resolved_minutes": ("auto_close_resolved_days", 1440, 10, 0, 129600),
    }
    for key, (legacy_key, multiplier, default, minimum, maximum) in legacy_to_minutes.items():
        submitted = data.get(key)
        if submitted is None and data.get(legacy_key) is not None:
            submitted = int(data[legacy_key]) * multiplier
        if submitted is None and settings.get(key) is not None:
            submitted = settings[key]
        if submitted is None and settings.get(legacy_key) is not None:
            submitted = int(settings[legacy_key]) * multiplier
        value = default if submitted is None else int(submitted)
        if not minimum <= value <= maximum:
            raise HTTPException(status_code=422, detail=f"{key.replace('_', ' ').title()} must be between {minimum} and {maximum} minutes.")
        data[key] = value
    # Store only minute-based values so there is one unambiguous source of truth.
    for legacy_key in ("pending_customer_reminder_hours", "resolution_confirmation_reminder_days", "auto_close_resolved_days"):
        data.pop(legacy_key, None)
    if data["from_email"] and ("@" not in data["from_email"] or any(ch.isspace() for ch in data["from_email"])):
        raise HTTPException(status_code=422, detail="Enter a valid From email address.")
    if data["reply_to_email"] and ("@" not in data["reply_to_email"] or any(ch.isspace() for ch in data["reply_to_email"])):
        raise HTTPException(status_code=422, detail="Enter a valid Reply-to email address.")
    if data["enabled"] and (not data["smtp_host"].strip() or not data["from_email"].strip()):
        raise HTTPException(status_code=422, detail="Configure SMTP host and From email before enabling the email service.")
    if data["enabled"] and data["authentication"] == "Username and password":
        if not data["smtp_username"].strip() or not (data.get("smtp_password") or settings.get("smtp_password")):
            raise HTTPException(status_code=422, detail="Enter SMTP username and password / App Password before enabling the email service.")
    if data["authentication"] == "No authentication":
        data["smtp_password"] = ""
        data["smtp_username"] = ""
    elif not data.get("smtp_password"):
        data["smtp_password"] = settings.get("smtp_password", "")
    data["event_rules"] = {**_default_event_rules(), **(settings.get("event_rules") or {}), **(data.get("event_rules") or {})}
    data["templates"] = _effective_email_templates({**(settings.get("templates") or {}), **(data.get("templates") or {})})
    row = current or EmailSetting(setting_id=1, settings_json="{}")
    row.settings_json = json.dumps(data)
    db.add(row)
    safe_keys = (set(settings) | set(data)) - {"smtp_password"}
    changes = {key: {"from": settings.get(key), "to": data.get(key)} for key in sorted(safe_keys) if settings.get(key) != data.get(key)}
    log_action(db, actor, "UPDATE", "Email settings", f"Updated SMTP settings for host {data.get('smtp_host','') or '(not configured)'}", request=request, entity_id=1, entity_label="SMTP configuration", changes=changes)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not save mail settings.")
    return {"message": "Email settings saved.", "smtp_password_set": bool(data.get("smtp_password")), "enabled": bool(data.get("enabled"))}

@router.get("/api/email-deliveries")
def list_email_deliveries(limit: int = Query(300, ge=1, le=500), offset: int = Query(0, ge=0), status: str = "all",
                          db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    query = select(EmailDelivery).order_by(EmailDelivery.created_at.desc(), EmailDelivery.delivery_id.desc())
    count_query = select(func.count(EmailDelivery.delivery_id))
    if status != "all":
        query = query.where(EmailDelivery.status == status)
        count_query = count_query.where(EmailDelivery.status == status)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.offset(offset).limit(limit)).all()
    since = datetime.utcnow() - timedelta(hours=24)
    counts = {
        "queued": db.scalar(select(func.count(EmailDelivery.delivery_id)).where(EmailDelivery.status == "queued")) or 0,
        "retry": db.scalar(select(func.count(EmailDelivery.delivery_id)).where(EmailDelivery.status == "failed")) or 0,
        "sent_24h": db.scalar(select(func.count(EmailDelivery.delivery_id)).where(EmailDelivery.status == "sent", EmailDelivery.sent_at >= since)) or 0,
        "failed_24h": db.scalar(select(func.count(EmailDelivery.delivery_id)).where(EmailDelivery.status == "failed", EmailDelivery.created_at >= since)) or 0,
    }
    return {"stats": counts, "total": total, "limit": limit, "offset": offset, "items": [{
        "delivery_id": r.delivery_id, "created_at": yangon_datetime_iso(r.created_at), "ticket_id": r.ticket_id,
        "ticket_code": r.ticket_code, "event_key": r.event_key,
        # event_key is the canonical source of truth. Rebuild the label here so
        # an old/stale stored label cannot show a Response SLA delivery as Resolution SLA.
        "event_label": _email_event_display_label(
            r.event_key,
            (r.event_label.rsplit(" · ", 1)[1].lower()
             if r.event_label and " · " in r.event_label
             and r.event_label.rsplit(" · ", 1)[1].lower() in {"admin", "agent", "customer"}
             else None),
        ),
        "recipient_name": r.recipient_name, "recipient_email": r.recipient_email,
        "status": r.status, "attempts": r.attempts, "sent_at": yangon_datetime_iso(r.sent_at), "error": r.error,
    } for r in rows]}

@router.post("/api/email-deliveries/process-queue")
def process_email_queue(request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    setting = db.get(EmailSetting, 1)
    cfg = json.loads(setting.settings_json or "{}") if setting else {}
    rows = db.scalars(select(EmailDelivery).where(EmailDelivery.status == "queued").order_by(EmailDelivery.created_at).limit(100).with_for_update(skip_locked=True)).all()
    for row in rows:
        _attempt_queued_delivery(db, row, cfg)
    log_action(db, actor, "PROCESS_EMAIL_QUEUE", "Email notifications", f"Processed {len(rows)} queued email(s)", request=request)
    db.commit()
    return {"message": f"Processed {len(rows)} queued email(s).", "processed": len(rows)}

@router.post("/api/email-deliveries/retry-failed")
def retry_failed_email(request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    setting = db.get(EmailSetting, 1)
    cfg = json.loads(setting.settings_json or "{}") if setting else {}
    rows = db.scalars(select(EmailDelivery).where(EmailDelivery.status == "failed").order_by(EmailDelivery.created_at).limit(100)).all()
    for row in rows:
        _attempt_queued_delivery(db, row, cfg, force=True)
    log_action(db, actor, "RETRY_FAILED_EMAIL", "Email notifications", f"Retried {len(rows)} failed email(s)", request=request)
    db.commit()
    return {"message": f"Retried {len(rows)} failed email(s).", "retried": len(rows)}

@router.post("/api/email-settings/test")
def test_email(payload: dict[str, str], request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    admin_only(actor)
    recipient = (payload.get("recipient") or "").strip()
    if not recipient or "@" not in recipient or any(ch.isspace() for ch in recipient):
        raise HTTPException(status_code=422, detail="Enter a valid recipient email address.")
    row = db.get(EmailSetting, 1)
    if not row:
        raise HTTPException(status_code=400, detail="Save the SMTP settings first.")
    cfg = json.loads(row.settings_json or "{}")
    if not str(cfg.get("smtp_host") or "").strip() or not str(cfg.get("from_email") or "").strip():
        raise HTTPException(status_code=400, detail="SMTP host and From email are required.")
    delivery = EmailDelivery(event_key="test_email", event_label="Test Email", recipient_name=recipient,
        recipient_email=recipient, subject="Golden Pride - test notification",
        body="This is a test email from your Golden Pride Ticket Service System. The email connection is working.",
        status="queued", attempts=0)
    db.add(delivery)
    db.flush()
    try:
        delivery.attempts = 1
        _send_notification_email(cfg, [recipient], delivery.subject, delivery.body)
        delivery.status = "sent"
        delivery.sent_at = datetime.utcnow()
        log_action(db, actor, "SEND_TEST", "Email settings", f"Sent a test notification to {recipient}", request=request, entity_label=recipient)
        db.commit()
    except Exception as exc:
        delivery.status = "failed"
        delivery.error = str(exc)[:2000]
        log_action(db, actor, "EMAIL_FAILED", "Email settings", f"Test email to {recipient} failed: {str(exc)[:300]}", request=request, entity_label=recipient)
        db.commit()
        raise HTTPException(status_code=400, detail=f"Email delivery failed: {str(exc)[:300]}") from exc
    return {"message": f"Test email sent to {recipient}."}

__all__ = ["router"]
