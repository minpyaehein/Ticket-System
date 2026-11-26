"""Sla logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .models import *
from .security import *
from .email_service import *

def _parse_sla_minutes(value: str | None, plan: Plan) -> float | None:
    """Parse the existing Support Plan SLA value into minutes."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(business\s+days?|days?|d|hours?|hrs?|h|minutes?|mins?|m)\b", raw)
    if not match:
        return None
    amount = float(match.group(1))
    unit = re.sub(r"\s+", " ", match.group(2))
    if unit.startswith("business"):
        start = _parse_clock(plan.business_start_hour, time(9, 0))
        end = _parse_clock(plan.business_end_hour, time(17, 0))
        minutes_per_day = max(1, int((datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).total_seconds() // 60))
        return amount * minutes_per_day
    if unit.startswith("day") or unit == "d":
        return amount * 24 * 60
    if unit.startswith("hour") or unit.startswith("hr") or unit == "h":
        return amount * 60
    return amount

def _parse_clock(value: str | None, fallback: time) -> time:
    try:
        return time.fromisoformat(str(value or "").strip())
    except (TypeError, ValueError):
        return fallback

def _working_weekdays(value: str | None) -> set[int]:
    raw = str(value or "Monday-Friday").strip().lower()
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if "-" in raw:
        left, right = [part.strip() for part in raw.split("-", 1)]
        left_name = next((n for n in names if left.startswith(n[:3])), None)
        right_name = next((n for n in names if right.startswith(n[:3])), None)
        if left_name and right_name:
            start_idx, end_idx = names.index(left_name), names.index(right_name)
            days = set()
            idx = start_idx
            while True:
                days.add(idx)
                if idx == end_idx:
                    break
                idx = (idx + 1) % 7
            return days
    selected = {idx for idx, name in enumerate(names) if name in raw or name[:3] in raw}
    return selected or {0, 1, 2, 3, 4}

def _customer_ticket_support_hours_error(
    plan: Plan, now_local: datetime | None = None
) -> dict[str, str] | None:
    """Return a structured customer alert when a Business-hours Plan is closed."""
    mode = str(plan.sla_mode or "Business hours").strip().lower().replace("×", "x")
    if "24x7" in mode or "24/7" in mode or "calendar" in mode:
        return None

    try:
        tz = ZoneInfo(plan.time_zone or MYANMAR_TIME_ZONE)
    except Exception:
        tz = ZoneInfo(MYANMAR_TIME_ZONE)
    now_value = now_local or datetime.now(tz)
    if now_value.tzinfo is None:
        now_value = now_value.replace(tzinfo=tz)
    else:
        now_value = now_value.astimezone(tz)

    start = _parse_clock(plan.business_start_hour, time(9, 0))
    end = _parse_clock(plan.business_end_hour, time(17, 0))
    # An invalid/overnight range is not treated as a closed window. The SLA clock
    # calculator already handles these configurations separately.
    if end <= start:
        return None

    working_days = _working_weekdays(plan.working_days)
    current_clock = now_value.timetz().replace(tzinfo=None)
    if now_value.weekday() in working_days and start <= current_clock < end:
        return None

    next_opening = None
    for offset in range(0, 8):
        candidate_day = now_value.date() + timedelta(days=offset)
        if candidate_day.weekday() not in working_days:
            continue
        candidate = datetime.combine(candidate_day, start).replace(tzinfo=tz)
        if candidate > now_value:
            next_opening = candidate
            break
    plan_name = str(plan.plan_name or plan.plan_type or "selected").strip()
    plan_type = str(plan.plan_type or "Support").strip()
    hours_label = f"{start.strftime('%I:%M %p').lstrip('0')}–{end.strftime('%I:%M %p').lstrip('0')}"
    days_label = str(plan.working_days or "Monday-Friday").strip()
    zone_label = str(plan.time_zone or MYANMAR_TIME_ZONE).strip()
    zone_suffix = "MMT (Asia/Yangon)" if zone_label in {"Asia/Yangon", "Asia/Rangoon"} else f"({zone_label})"
    next_label = (
        next_opening.strftime("%A, %d %B %Y at %I:%M %p") + f" {zone_suffix}"
        if next_opening else "the next configured working day"
    )
    return {
        "code": "SUPPORT_HOURS_BLOCKED",
        "message": (
            f"Your {plan_name} ({plan_type}) support plan accepts new tickets only "
            f"during {hours_label} on {days_label}. The next available submission time "
            f"is {next_label}. Please create your ticket then."
        ),
    }

def validate_customer_ticket_support_hours(db: Session, data: dict[str, Any]) -> None:
    """Block customer ticket creation outside the Contract's linked Plan hours."""
    plan_id = data.get("plan_id")
    if not plan_id:
        return
    plan = db.get(Plan, plan_id)
    if not plan or not plan.active:
        return
    error = _customer_ticket_support_hours_error(plan)
    if error:
        raise HTTPException(status_code=422, detail=error)

def _elapsed_response_sla_minutes(start_utc: datetime, now_utc: datetime, plan: Plan) -> float:
    """Calculate elapsed SLA minutes using Calendar or configured Business hours."""
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    mode = str(plan.sla_mode or "Business hours").lower().replace("×", "x")
    if "24x7" in mode or "calendar" in mode:
        return max(0.0, (now_utc - start_utc).total_seconds() / 60.0)
    try:
        tz = ZoneInfo(plan.time_zone or "Asia/Yangon")
    except Exception:
        tz = ZoneInfo("Asia/Yangon")
    start_local = start_utc.astimezone(tz)
    now_local = now_utc.astimezone(tz)
    day_start = _parse_clock(plan.business_start_hour, time(9, 0))
    day_end = _parse_clock(plan.business_end_hour, time(17, 0))
    if day_end <= day_start:
        return max(0.0, (now_utc - start_utc).total_seconds() / 60.0)
    weekdays = _working_weekdays(plan.working_days)
    total = 0.0
    cursor = start_local.date()
    while cursor <= now_local.date():
        if cursor.weekday() in weekdays:
            window_start = datetime.combine(cursor, day_start, tzinfo=tz)
            window_end = datetime.combine(cursor, day_end, tzinfo=tz)
            overlap_start = max(window_start, start_local)
            overlap_end = min(window_end, now_local)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds() / 60.0
        cursor += timedelta(days=1)
    return max(0.0, total)

def _ticket_has_event_notification(db: Session, ticket_id: int, event_key: str) -> bool:
    return db.scalar(select(NotificationItem.notification_id).where(
        NotificationItem.ticket_id == ticket_id,
        NotificationItem.event_key == event_key,
    ).limit(1)) is not None

def _normalize_ticket_status(value: Any) -> str:
    return re.sub(r"[\s_-]+", " ", str(value or "").strip().casefold())

def _elapsed_resolution_sla_minutes(
    db: Session, ticket: Ticket, now_utc: datetime, plan: Plan
) -> float:
    """Count Support-Plan minutes while work is active; Pending Customer pauses the clock.

    Status transitions are read from the existing ticket audit history, so this
    behaviour does not require a database schema migration. Resolved/Closed stop
    the clock; reopening resumes the remaining elapsed-time calculation.
    """
    start = ticket.created_at or ticket.updated_at
    if start is None:
        return 0.0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    if now_utc <= start:
        return 0.0

    logs = db.scalars(select(AuditLog).where(
        AuditLog.module == "Tickets",
        AuditLog.entity_id == str(ticket.ticket_id),
        AuditLog.action == "UPDATE",
        AuditLog.created_at >= start.replace(tzinfo=None),
    ).order_by(AuditLog.created_at.asc(), AuditLog.audit_id.asc())).all()

    transitions: list[tuple[datetime, str, str]] = []
    for log in logs:
        try:
            changes = json.loads(log.change_data or "{}")
        except (TypeError, ValueError):
            continue
        status_change = changes.get("status") if isinstance(changes, dict) else None
        if not isinstance(status_change, dict) or "to" not in status_change:
            continue
        at = log.created_at
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        else:
            at = at.astimezone(timezone.utc)
        transitions.append((at, str(status_change.get("from") or "Open"), str(status_change.get("to") or "Open")))

    if transitions:
        current_status = transitions[0][1]
    else:
        current_status = str(ticket.status or "Open")

    def is_clock_running(status: str) -> bool:
        normalized = _normalize_ticket_status(status)
        return normalized not in {"pending customer", "waiting for customer", "resolved", "closed"}

    cursor = start
    total_minutes = 0.0
    for changed_at, _old_status, new_status in transitions:
        if changed_at < cursor:
            continue
        if is_clock_running(current_status) and changed_at > cursor:
            total_minutes += _elapsed_response_sla_minutes(cursor, changed_at, plan)
        current_status = new_status
        cursor = changed_at
    if is_clock_running(current_status) and now_utc > cursor:
        total_minutes += _elapsed_response_sla_minutes(cursor, now_utc, plan)
    return max(0.0, total_minutes)

def _sla_milestone_message(kind: str, plan: Plan, target_minutes: float, elapsed_minutes: float, percentage: float) -> str:
    target_value = plan.response_sla if kind == "response" else plan.resolution_sla
    target = str(target_value or "configured target")
    elapsed = f"{elapsed_minutes:.1f} active minutes"
    return (
        f"Support Plan: {plan.plan_name} ({plan.plan_type}). Target: {target} "
        f"({target_minutes:g} active minutes). Elapsed: {elapsed}; {percentage:.0f}% of target."
    )

def _send_sla_milestones(
    db: Session, ticket: Ticket, plan: Plan, kind: str, elapsed_minutes: float,
    target_minutes: float, warning_percent: int, critical_percent: int,
    completed: bool = False,
) -> int:
    """Send every crossed SLA milestone once; completed tickets only get late breaches."""
    progress = (elapsed_minutes / target_minutes) * 100.0 if target_minutes > 0 else 0.0
    prefix = "response" if kind == "response" else "resolution"
    if completed:
        if progress < 100.0:
            return 0
        # A completed ticket should not receive fresh warning/critical emails.
        milestones = [(100, f"{prefix}_sla_breach")]
    else:
        milestones = [
            (warning_percent, f"{prefix}_sla_warning"),
            (critical_percent, f"{prefix}_sla_critical"),
            (100, f"{prefix}_sla_breach"),
        ]
    sent = 0
    for threshold, event_key in milestones:
        if progress < threshold or _ticket_has_event_notification(db, ticket.ticket_id, event_key):
            continue
        message = _sla_milestone_message(kind, plan, target_minutes, elapsed_minutes, progress)
        if event_key.endswith("_breach"):
            message = "SLA target has been exceeded. " + message
        elif event_key.endswith("_critical"):
            message = "SLA target is at its critical threshold. " + message
        else:
            message = "SLA target is approaching. " + message
        notify_ticket_event(db, event_key, ticket, None, message)
        sent += 1
    return sent

def run_response_sla_scan(db: Session, now_utc: datetime | None = None) -> int:
    """Raise first-public-response SLA milestones from each ticket's linked Plan."""
    now_utc = now_utc or datetime.now(timezone.utc)
    tickets = db.scalars(select(Ticket).where(
        Ticket.active.is_(True),
        Ticket.plan_id.is_not(None),
    )).all()
    triggered = 0
    for ticket in tickets:
        first_public_staff_reply = db.scalar(
            select(TicketReply.reply_id)
            .join(User, User.user_id == TicketReply.user_id)
            .where(
                TicketReply.ticket_id == ticket.ticket_id,
                TicketReply.is_internal.is_(False),
                User.role.in_(["admin", "agent"]),
            )
            .order_by(TicketReply.created_at.asc(), TicketReply.reply_id.asc())
            .limit(1)
        )
        # A public staff reply satisfies Response SLA. Internal notes and status
        # changes alone do not count as a response to the customer.
        if first_public_staff_reply:
            continue
        plan = db.get(Plan, ticket.plan_id)
        if not plan:
            continue
        target_minutes = _parse_sla_minutes(plan.response_sla, plan)
        if not target_minutes or target_minutes <= 0:
            continue
        start = ticket.created_at or ticket.updated_at
        status = _normalize_ticket_status(ticket.status)
        completed = status in {"resolved", "closed"}
        stop_at = ticket.status_changed_at if completed and ticket.status_changed_at else now_utc
        elapsed = _elapsed_response_sla_minutes(start, stop_at, plan)
        warning = max(1, min(99, int(plan.response_warning or 70)))
        critical = max(warning + 1, min(99, int(plan.response_critical or 90)))
        triggered += _send_sla_milestones(
            db, ticket, plan, "response", elapsed, target_minutes, warning, critical,
            completed=completed,
        )
    return triggered

def run_customer_ticket_schedule_scan(db: Session, cfg: dict[str, Any], now_utc: datetime | None = None) -> dict[str, int]:
    """Run one-shot customer reminders and optional automatic closure policies."""
    now_utc = now_utc or datetime.utcnow()
    pending_minutes = int(cfg.get("pending_customer_reminder_minutes") if cfg.get("pending_customer_reminder_minutes") is not None
                          else int(cfg["pending_customer_reminder_hours"]) * 60 if cfg.get("pending_customer_reminder_hours") is not None else 5)
    resolution_minutes = int(cfg.get("resolution_confirmation_reminder_minutes") if cfg.get("resolution_confirmation_reminder_minutes") is not None
                              else int(cfg["resolution_confirmation_reminder_days"]) * 1440 if cfg.get("resolution_confirmation_reminder_days") is not None else 5)
    auto_close_minutes = int(cfg.get("auto_close_resolved_minutes") if cfg.get("auto_close_resolved_minutes") is not None
                             else int(cfg["auto_close_resolved_days"]) * 1440 if cfg.get("auto_close_resolved_days") is not None else 10)
    pending_minutes = max(1, min(43200, pending_minutes))
    resolution_minutes = max(1, min(43200, resolution_minutes))
    auto_close_minutes = max(0, min(129600, auto_close_minutes))
    counts = {"pending_customer_reminder": 0, "resolution_confirmation_reminder": 0, "auto_closed": 0}
    rows = db.scalars(select(Ticket).where(
        Ticket.active.is_(True),
        func.lower(Ticket.status).in_(["pending customer", "pending_customer", "waiting for customer", "resolved"]),
    )).all()
    for ticket in rows:
        status = str(ticket.status or "").strip().lower()
        changed_at = ticket.status_changed_at or ticket.updated_at
        if changed_at and status in {"pending customer", "pending_customer", "waiting for customer"}:
            if now_utc - changed_at >= timedelta(minutes=pending_minutes) and not _ticket_has_event_notification(db, ticket.ticket_id, "pending_customer_reminder"):
                notify_ticket_event(db, "pending_customer_reminder", ticket, None)
                counts["pending_customer_reminder"] += 1
        if changed_at and status == "resolved":
            age = now_utc - changed_at
            if age >= timedelta(minutes=resolution_minutes) and not _ticket_has_event_notification(db, ticket.ticket_id, "resolution_confirmation_reminder"):
                notify_ticket_event(db, "resolution_confirmation_reminder", ticket, None)
                counts["resolution_confirmation_reminder"] += 1
            if auto_close_minutes > 0 and age >= timedelta(minutes=auto_close_minutes):
                ticket.status = "Closed"
                ticket.status_changed_at = now_utc
                ticket.updated_at = now_utc
                log_action(db, None, "AUTO_CLOSE", "Tickets",
                           f"Automatically closed ticket {ticket.ticket_code or ticket.ticket_id} after {auto_close_minutes} minutes in Resolved status.",
                           entity_id=ticket.ticket_id, entity_label=ticket.ticket_code or f"TKT-{ticket.ticket_id}")
                db.commit()
                notify_ticket_event(db, "auto_closed", ticket, None,
                                    f"Ticket was automatically closed after {auto_close_minutes} minutes without a resolution response.")
                counts["auto_closed"] += 1
    return counts

def run_resolution_sla_scan(db: Session, now_utc: datetime | None = None) -> int:
    """Check resolution milestones against the selected Support Plan, not due_date."""
    now_utc = now_utc or datetime.now(timezone.utc)
    tickets = db.scalars(select(Ticket).where(
        Ticket.active.is_(True),
        Ticket.plan_id.is_not(None),
    )).all()
    sent = 0
    for ticket in tickets:
        plan = db.get(Plan, ticket.plan_id)
        if not plan:
            continue
        target_minutes = _parse_sla_minutes(plan.resolution_sla, plan)
        if not target_minutes or target_minutes <= 0:
            continue
        elapsed = _elapsed_resolution_sla_minutes(db, ticket, now_utc, plan)
        status = _normalize_ticket_status(ticket.status)
        completed = status in {"resolved", "closed"}
        warning = max(1, min(99, int(plan.resolution_warning or 70)))
        critical = max(warning + 1, min(99, int(plan.resolution_critical or 90)))
        sent += _send_sla_milestones(
            db, ticket, plan, "resolution", elapsed, target_minutes,
            warning, critical, completed=completed,
        )
    return sent

async def scheduled_ticket_event_loop() -> None:
    """Check response SLA, resolution SLA, and customer follow-up schedules once per minute."""
    while True:
        db = SessionLocal()
        try:
            setting = db.get(EmailSetting, 1)
            cfg = json.loads(setting.settings_json or "{}") if setting else {}
            run_response_sla_scan(db)
            run_resolution_sla_scan(db)
            run_customer_ticket_schedule_scan(db, cfg)
        except Exception:
            db.rollback()
            logger.exception("Scheduled ticket email event scan failed")
        finally:
            db.close()
        await asyncio.sleep(60)

async def daily_summary_loop() -> None:
    """Run optional daily digests after 09:00 Asia/Yangon."""
    while True:
        now = datetime.now(ZoneInfo("Asia/Yangon"))
        if now.hour >= 9:
            run_date = now.date().isoformat()
            db = SessionLocal()
            try:
                marker = db.get(SystemSetting, "daily_email_scan_last_run")
                if not marker or marker.setting_value != run_date:
                    setting = db.get(EmailSetting, 1)
                    cfg = json.loads(setting.settings_json or "{}") if setting else {}
                    if (cfg.get("event_rules") or {}).get("daily_summary", False):
                        if not cfg.get("enabled") or not cfg.get("smtp_host") or not cfg.get("from_email"):
                            log_action(db, None, "EMAIL_SKIPPED", "Email notifications",
                                       f"Daily summary {run_date}; Email Service or SMTP settings are disabled/incomplete")
                        else:
                            open_tickets = db.scalars(select(Ticket).where(
                                func.lower(Ticket.status).not_in(["resolved", "closed"])
                            ).order_by(Ticket.due_date, Ticket.updated_at.desc()).limit(40)).all()
                            lines = [
                                f"{t.ticket_code or ('TKT-' + str(t.ticket_id))} | {t.status} | {t.priority} | due {t.due_date or 'not set'} | {t.subject}"
                                for t in open_tickets
                            ]
                            template_map = _effective_email_templates(cfg.get("templates") or {})
                            recipients = db.scalars(select(User).where(
                                User.active.is_(True), User.role.in_(["admin", "agent"])
                            ).order_by(User.role, User.fullname)).all()
                            queued = 0
                            for recipient in recipients:
                                if not recipient.email or not _user_allows_event(db, recipient.email, "daily_summary"):
                                    continue
                                role = recipient.role
                                context = {
                                    "recipient_name": recipient.fullname,
                                    "recipient_email": recipient.email,
                                    "event_label": "Daily Ticket Summary",
                                    "event_message": _EVENT_ROLE_COPY["daily_summary"][role],
                                    "summary_date": run_date,
                                    "open_ticket_count": str(len(open_tickets)),
                                    "ticket_lines": "\n".join(lines) if lines else "There are no open tickets.",
                                }
                                subject, body = parse_email_template(
                                    {"templates": template_map}, "daily_summary", role, context
                                )
                                _record_email_delivery(
                                    db, cfg, None, "daily_summary", recipient,
                                    recipient.email, subject, body, audience_role=role,
                                )
                                queued += 1
                            log_action(db, None, "DAILY_SUMMARY", "Email notifications",
                                       f"Daily summary queued for {run_date}; open tickets listed: {len(open_tickets)}; deliveries queued: {queued}")
                    db.merge(SystemSetting(setting_key="daily_email_scan_last_run", setting_value=run_date))
                    db.commit()
            except Exception as exc:
                db.rollback()
                logger.exception("Daily email scheduler failed")
                try:
                    log_action(db, None, "EMAIL_FAILED", "Email notifications",
                               f"Daily summary scheduler error: {str(exc)[:300]}")
                    db.commit()
                except Exception:
                    db.rollback()
            finally:
                db.close()
        await asyncio.sleep(30)

__all__ = [name for name in globals() if not name.startswith("__")]
