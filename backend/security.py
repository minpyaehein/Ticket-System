"""Security logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .models import *

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _require_current_server_session(request: Request) -> int:
    """Reject browser cookies issued by a previous server process."""
    user_id = request.session.get("user_id")
    boot_id = request.session.get("boot_id")
    if not user_id or boot_id != APP_BOOT_ID:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your server session has expired. Please sign in again.")
    return int(user_id)

def get_actor(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user_id = _require_current_server_session(request)
    user = db.get(User, int(user_id))
    if not user or not user.active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your session is no longer valid. Please sign in again.")
    if user.must_change_password and request.url.path not in {"/api/auth/change-password", "/api/auth/logout"}:
        raise HTTPException(status_code=403, detail="Change your temporary password before using the system.")
    return {**_user_team_context(db, user), "must_change_password": bool(user.must_change_password)}

def admin_only(actor: dict[str, Any]) -> None:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="This action is available to administrators only.")

def actor_customer_id(db: Session, actor: dict[str, Any]) -> int | None:
    customer = db.scalar(select(Customer).where(func.lower(Customer.email) == actor["email"].lower()))
    return customer.customer_id if customer else None

def _json_safe(value: Any) -> Any:
    return jsonable_encoder(value)

def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    # Do not trust arbitrary X-Forwarded-For headers; use the actual connected peer.
    return str(request.client.host or "")[:64] or None

def _login_throttle_storage_key(request: Request) -> str:
    """Return a non-reversible per-client key for persistent login throttling."""
    client_ip = _client_ip(request) or "unknown"
    digest = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    return f"login_attempts:{digest}"

def _load_login_throttle_state(db: Session, request: Request) -> tuple[str, dict[str, Any], int]:
    """Lock and load a client's recent failures; return a Retry-After value when blocked."""
    key = _login_throttle_storage_key(request)
    if engine.dialect.name == "postgresql":
        # Serialize login attempts for the same client across all FastAPI workers.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": key})

    setting = db.get(SystemSetting, key)
    try:
        state = json.loads(setting.setting_value or "{}") if setting else {}
        if not isinstance(state, dict):
            state = {}
    except (json.JSONDecodeError, TypeError):
        state = {}

    now = _time.time()
    try:
        locked_until = float(state.get("locked_until") or 0)
    except (TypeError, ValueError):
        locked_until = 0.0
    if locked_until > now:
        return key, state, max(1, int(locked_until - now + 0.999))

    # Expired lockouts start with a clean one-minute failure window.
    if locked_until:
        state = {}
    recent: list[float] = []
    for stamp in state.get("failed_at", []) if isinstance(state.get("failed_at", []), list) else []:
        try:
            value = float(stamp)
        except (TypeError, ValueError):
            continue
        if 0 <= now - value < LOGIN_ATTEMPT_WINDOW_SECONDS:
            recent.append(value)
    state = {"failed_at": recent}
    return key, state, 0

def _save_login_throttle_state(db: Session, key: str, state: dict[str, Any]) -> None:
    setting = db.get(SystemSetting, key)
    serialized = json.dumps(state, separators=(",", ":"))
    if setting is None:
        db.add(SystemSetting(setting_key=key, setting_value=serialized))
    else:
        setting.setting_value = serialized

def _record_failed_login(db: Session, key: str, state: dict[str, Any]) -> None:
    now = _time.time()
    recent = [float(stamp) for stamp in state.get("failed_at", []) if 0 <= now - float(stamp) < LOGIN_ATTEMPT_WINDOW_SECONDS]
    recent.append(now)
    if len(recent) >= LOGIN_MAX_FAILED_ATTEMPTS:
        _save_login_throttle_state(db, key, {"failed_at": [], "locked_until": now + LOGIN_LOCKOUT_SECONDS})
    else:
        _save_login_throttle_state(db, key, {"failed_at": recent})

def _clear_login_failures(db: Session, key: str) -> None:
    setting = db.get(SystemSetting, key)
    if setting is not None:
        db.delete(setting)

def log_action(db: Session, actor: dict[str, Any] | None, action: str, module: str, details: str = "",
               request: Request | None = None, entity_id: Any = None, entity_label: str | None = None,
               changes: dict[str, Any] | None = None) -> None:
    change_json = json.dumps(_json_safe(changes), ensure_ascii=False) if changes else None
    db.add(AuditLog(
        user_id=actor.get("user_id") if actor else None,
        user_name=actor.get("fullname") if actor else "System",
        actor_role=actor.get("role") if actor else "system",
        action=action, module=module,
        entity_id=str(entity_id)[:120] if entity_id is not None else None,
        entity_label=str(entity_label)[:240] if entity_label else None,
        ip_address=_client_ip(request), details=details[:2000], change_data=change_json,
    ))
    # Admins receive an in-app audit notification for non-ticket system activity too.
    # Ticket events have their own audience-aware notification path to avoid duplicates.
    if (module not in {"Notifications", "Email notifications"} and (module != "Tickets" or action == "DELETE")
            and action not in {"NOTIFICATION_CREATED", "EMAIL_SENT", "EMAIL_FAILED", "EMAIL_SKIPPED"}):
        admins = db.scalars(select(User).where(User.role == "admin", User.active.is_(True))).all()
        actor_name = (actor or {}).get("fullname") or "System"
        label = f" · {entity_label}" if entity_label else ""
        for admin_user in admins:
            db.add(NotificationItem(user_id=admin_user.user_id, event_key="system_activity",
                title=f"{module}: {action.replace('_', ' ').title()}{label}"[:220],
                message=f"{actor_name} ({(actor or {}).get('role') or 'system'}) — {details}"[:1000],
                ticket_id=None, ticket_code=None, actor_name=actor_name,
                actor_role=(actor or {}).get("role")))

def _entity_label(resource: str, row: Any, db: Session) -> str:
    if resource == "tickets": return row.ticket_code or f"TKT-{row.ticket_id}"
    if resource == "customers": return row.customer_name
    if resource == "users": return f"{row.fullname} ({row.email})"
    if resource == "projects": return row.project_name
    if resource == "plans": return row.plan_name
    if resource == "services": return row.name
    if resource == "teams": return row.team_name
    if resource == "contacts": return row.fullname
    if resource == "contracts": return row.contract_code or row.contract_name
    if resource == "assets": return row.asset_tag
    return f"{resource} {getattr(row, RESOURCE_PK.get(resource, ''), '')}".strip()

def _snapshot(row: Any) -> dict[str, Any]:
    values = model_values(row)
    # No password or secret material ever belongs in a change diff.
    values.pop("password_hash", None)
    values.pop("smtp_password", None)
    return _json_safe(values)

def _diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    before, after = before or {}, after or {}
    changes = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"from": before.get(key), "to": after.get(key)}
    return changes

def _change_summary(changes: dict[str, Any], limit: int = 6) -> str:
    def short(value: Any) -> str:
        if value is None: return "—"
        if isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=False)
        value = str(value).replace("\n", " ").strip()
        return value if len(value) <= 100 else value[:97] + "…"
    parts = []
    for key, change in list(changes.items())[:limit]:
        parts.append(f"{key.replace('_', ' ')}: {short(change.get('from'))} → {short(change.get('to'))}")
    if len(changes) > limit: parts.append(f"+{len(changes)-limit} more field(s); open View Changes")
    return "; ".join(parts)

def model_values(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in inspect(row).mapper.column_attrs:
        key = column.key
        if key == "password_hash":
            continue
        value = getattr(row, key)
        result[key] = value
    return result

def _teams_for_service(db: Session, service_code: str | None) -> list[Team]:
    """Return only teams explicitly mapped to the selected Service Catalog item."""
    if not service_code:
        return []
    service = db.get(ServiceCatalog, service_code)
    if not service:
        return []
    found: dict[int, Team] = {}
    mapped = str(service.mapped_team or "").strip()
    if mapped:
        for team in db.scalars(select(Team).where(
            or_(func.lower(Team.team_name) == mapped.lower(),
                func.lower(Team.team_code) == mapped.lower())
        )).all():
            found[team.team_id] = team
    for team in db.scalars(select(Team).join(
        TeamServiceLink, TeamServiceLink.team_id == Team.team_id
    ).where(TeamServiceLink.code_id == service_code)).all():
        found[team.team_id] = team
    for team in db.scalars(select(Team).where(Team.code_id == service_code)).all():
        found[team.team_id] = team
    return sorted(found.values(), key=lambda team: (team.team_name.casefold(), team.team_id))

def _ensure_service_mapped_team(db: Session, service: ServiceCatalog) -> Team | None:
    # Ensure a Service Catalog mapped-team name resolves to a real reusable Team.
    name = str(service.mapped_team or "").strip()
    if not name:
        return None
    team = db.scalar(select(Team).where(func.lower(Team.team_name) == name.lower()))
    if not team:
        team = Team(
            team_name=name,
            code_id=service.code_id,
            description=f"Created from Service Catalog mapping for {service.name}.",
        )
        db.add(team)
        db.flush()
        assign_generated_code(db, "teams", team)
    exists = db.scalar(select(TeamServiceLink).where(
        TeamServiceLink.team_id == team.team_id,
        TeamServiceLink.code_id == service.code_id,
    ))
    if not exists:
        db.add(TeamServiceLink(team_id=team.team_id, code_id=service.code_id))
    if not team.code_id:
        team.code_id = service.code_id
    return team

def _team_for_service(db: Session, service_code: str | None) -> Team | None:
    """Resolve the first configured support team for a service (legacy auto-route)."""
    teams = _teams_for_service(db, service_code)
    return teams[0] if teams else None

def _user_team_ids(db: Session, user: User) -> list[int]:
    """Return every assigned team, including the legacy single team_id."""
    ids: list[int] = []
    if user.team_id is not None:
        ids.append(int(user.team_id))
    linked = db.scalars(select(UserTeamMembership.team_id).where(
        UserTeamMembership.user_id == user.user_id).order_by(UserTeamMembership.team_id)).all()
    for value in linked:
        value = int(value)
        if value not in ids:
            ids.append(value)
    return ids

def _user_team_context(db: Session, user: User) -> dict[str, Any]:
    ids = _user_team_ids(db, user)
    teams = [db.get(Team, team_id) for team_id in ids]
    names = [team.team_name for team in teams if team]
    return {"user_id": user.user_id, "fullname": user.fullname, "email": user.email,
            "role": user.role, "team_id": ids[0] if ids else None,
            "team_ids": ids, "team_names": names, "team_name": ", ".join(names) if names else "—"}

def _parse_user_team_ids(db: Session, payload: dict[str, Any], row: User | None = None) -> list[int]:
    role = str(payload.get("role", getattr(row, "role", "customer"))).lower()
    role = {"administrator": "admin"}.get(role, role)
    if role != "agent":
        return []
    if "team_ids" in payload:
        raw = payload.get("team_ids") or []
    elif payload.get("team_id") not in (None, ""):
        raw = [payload.get("team_id")]
    elif row is not None:
        raw = _user_team_ids(db, row)
    else:
        raw = []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    ids: list[int] = []
    for value in raw:
        try:
            team_id = int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Choose valid Support Teams for this Agent.")
        if team_id not in ids:
            ids.append(team_id)
    if len(ids) != 1:
        raise HTTPException(status_code=422, detail="Choose exactly one Support Team for this Agent.")
    existing = set(db.scalars(select(Team.team_id).where(Team.team_id.in_(ids))).all())
    missing = [team_id for team_id in ids if team_id not in existing]
    if missing:
        raise HTTPException(status_code=422, detail="One or more selected Support Teams no longer exist. Refresh and select again.")
    return ids

def _prepare_user_custom_selections(db: Session, payload: dict[str, Any], row: User | None = None) -> None:
    """Resolve User Management's Other selections to real reusable catalog records.

    Custom teams become normal Team records so Agent access checks work. Custom
    request types become Service Catalog records so the existing request_type_code
    foreign key remains valid and the new type is available in later forms.
    """
    role = str(payload.get("role", getattr(row, "role", "customer"))).strip().lower()
    role = {"administrator": "admin"}.get(role, role)
    if role != "agent":
        payload.pop("other_team_name", None)
        payload.pop("other_request_type_name", None)
        return

    custom_team_name = str(payload.pop("other_team_name", "") or "").strip()
    if custom_team_name:
        if len(custom_team_name) > 160:
            raise HTTPException(status_code=422, detail="Support Team name must be 160 characters or fewer.")
        team = db.scalar(select(Team).where(func.lower(Team.team_name) == custom_team_name.casefold()))
        if not team:
            team = Team(
                team_name=custom_team_name,
                member="",
                description="Created from User Management custom Support Team selection.",
            )
            db.add(team)
            db.flush()
            assign_generated_code(db, "teams", team)
        raw_ids = payload.get("team_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [part.strip() for part in raw_ids.split(",") if part.strip()]
        elif not isinstance(raw_ids, (list, tuple, set)):
            raw_ids = [raw_ids] if raw_ids else []
        payload["team_ids"] = list(dict.fromkeys([*raw_ids, team.team_id]))

    custom_request_type = str(payload.pop("other_request_type_name", "") or "").strip()
    if custom_request_type:
        if len(custom_request_type) > 180:
            raise HTTPException(status_code=422, detail="Request Type name must be 180 characters or fewer.")
        service = db.scalar(select(ServiceCatalog).where(func.lower(ServiceCatalog.name) == custom_request_type.casefold()))
        if not service:
            next_order = int(db.scalar(select(func.max(ServiceCatalog.request_order))) or 0) + 1
            service = ServiceCatalog(
                code_id=assign_generated_service_code(db),
                name=custom_request_type,
                category="Other",
                request_order=next_order,
                customer_visible=False,
                auto_assign=False,
                description="Created from User Management custom Request Type selection.",
            )
            db.add(service)
            db.flush()
        payload["request_type_code"] = service.code_id

    request_type_code = str(payload.get("request_type_code") or (getattr(row, "request_type_code", None) if row else "") or "").strip()
    if not request_type_code or not db.get(ServiceCatalog, request_type_code):
        raise HTTPException(status_code=422, detail="Choose exactly one Request Type for this Agent.")
    payload["request_type_code"] = request_type_code

def _lock_active_agent_for_assignment(db: Session, agent: User) -> User | None:
    """Serialize concurrent assignments to one Agent using a database row lock."""
    return db.scalar(
        select(User).where(
            User.user_id == agent.user_id,
            User.role == "agent",
            User.active.is_(True),
        ).with_for_update().execution_options(populate_existing=True)
    )

def _agent_has_unresolved_assignment(
    db: Session, agent: User, exclude_ticket_id: int | None = None
) -> bool:
    """An Agent is unavailable while they own any active, unresolved ticket."""
    query = select(Ticket.ticket_id).where(
        Ticket.active.is_(True),
        func.lower(func.trim(Ticket.assigned)) == str(agent.fullname or "").strip().lower(),
        func.lower(func.trim(Ticket.status)).not_in(["resolved", "closed"]),
    )
    if exclude_ticket_id is not None:
        query = query.where(Ticket.ticket_id != exclude_ticket_id)
    return db.scalar(query.limit(1)) is not None

def _route_ticket_to_support_team(db: Session, ticket: Ticket, force_assign: bool = False) -> Team | None:
    """Route a customer ticket to its catalog Team and optionally auto-assign.

    Auto assignment is limited to active Agents who belong to the mapped Team.
    When Auto Assign is disabled, or the mapped Team has no active Agents, the
    ticket stays unassigned in that Team's queue for manual assignment by its
    members. It is never sent to an unrelated Agent in another Team.
    """
    team = _team_for_service(db, ticket.service_code)
    if team:
        ticket.team_id = team.team_id
    service = db.get(ServiceCatalog, ticket.service_code) if ticket.service_code else None
    if not force_assign and (not service or not service.auto_assign):
        return team

    team_agents = _team_agents(db, team.team_id) if team else []
    # Lock candidates in a stable order. If two customers submit at once, the
    # second transaction re-checks availability after the first assignment commits.
    selected = None
    for candidate in sorted(team_agents, key=lambda item: item.user_id):
        locked_agent = _lock_active_agent_for_assignment(db, candidate)
        if locked_agent and not _agent_has_unresolved_assignment(db, locked_agent):
            selected = locked_agent
            break
    # When every Agent already owns an unresolved ticket, keep this ticket
    # unassigned in the Admin dispatch queue.
    ticket.assigned = selected.fullname if selected else None
    return team

def _team_agents(db: Session, team_id: int | None) -> list[User]:
    if not team_id:
        return []
    linked_ids = select(UserTeamMembership.user_id).where(UserTeamMembership.team_id == team_id)
    return db.scalars(select(User).where(
        User.role == "agent", User.active.is_(True),
        or_(User.team_id == team_id, User.user_id.in_(linked_ids))
    ).order_by(User.user_id)).all()

def _ticket_access_agents(db: Session, ticket: Ticket) -> list[User]:
    """Return only the active Agent explicitly assigned to this ticket.

    Team and Request Type remain useful routing/reporting metadata, but neither
    one grants an Agent visibility. Unassigned tickets stay in the Admin queue.
    """
    assigned_agent = _ticket_assigned_agent(db, ticket)
    return [assigned_agent] if assigned_agent else []

def serialize_row(db: Session, resource: str, row: Any) -> dict[str, Any]:
    item = model_values(row)
    if resource == "customers":
        cid = item.get("customer_id")
        item["active"] = bool(item.get("active", True))
        item["projects_count"] = db.scalar(select(func.count(Project.project_id)).where(Project.customer_id == cid)) or 0
        item["contracts_count"] = db.scalar(select(func.count(Contract.contract_id)).where(Contract.customer_id == cid)) or 0
        item["tickets_count"] = db.scalar(select(func.count(Ticket.ticket_id)).where(Ticket.customer_id == cid)) or 0
    elif resource == "tickets":
        item["ticket_code"] = item.get("ticket_code") or f"TKT-{(item.get('date') or date.today()).year}-{item['ticket_id']:03d}"
        customer = db.get(Customer, item.get("customer_id")) if item.get("customer_id") else None
        project = db.get(Project, item.get("project_id")) if item.get("project_id") else None
        contract = db.get(Contract, item.get("contract_id")) if item.get("contract_id") else None
        plan = db.get(Plan, item.get("plan_id")) if item.get("plan_id") else None
        asset = db.get(Asset, item.get("asset_id")) if item.get("asset_id") else None
        contact = db.get(Contact, item.get("contact_id")) if item.get("contact_id") else None
        service = db.get(ServiceCatalog, item.get("service_code")) if item.get("service_code") else None
        support_team = db.get(Team, item.get("team_id")) if item.get("team_id") else None
        assigned_agent = _ticket_assigned_agent(db, row)
        item.update(customer_name=customer.customer_name if customer else "—",
                    project_name=project.project_name if project else "—",
                    team_name=support_team.team_name if support_team else "—",
                    service_name=service.name if service else "—",
                    contract_name=contract.contract_name if contract else (contract.contract_code if contract else "—"),
                    contract_code=contract.contract_code if contract else "",
                    plan_name=plan.plan_name if plan else "—", plan_code=plan.plan_code if plan else "",
                    asset_name=asset.asset_name if asset else "—", asset_tag=asset.asset_tag if asset else "—",
                    contact_name=contact.fullname if contact else "—",
                    assigned_agent_id=assigned_agent.user_id if assigned_agent else None)
    elif resource == "projects":
        customer = db.get(Customer, item.get("customer_id")) if item.get("customer_id") else None
        item["customer_name"] = customer.customer_name if customer else "—"
    elif resource == "contacts":
        customer = db.get(Customer, item.get("customer_id")) if item.get("customer_id") else None
        item["customer_name"] = customer.customer_name if customer else "—"
    elif resource == "contracts":
        customer = db.get(Customer, item.get("customer_id")) if item.get("customer_id") else None
        project = db.get(Project, item.get("project_id")) if item.get("project_id") else None
        plan = db.get(Plan, item.get("plan_id")) if item.get("plan_id") else None
        item.update(customer_name=customer.customer_name if customer else "—",
                    project_name=project.project_name if project else "—",
                    plan_name=plan.plan_name if plan else "—")
    elif resource == "assets":
        customer = db.get(Customer, item.get("customer_id")) if item.get("customer_id") else None
        project = db.get(Project, item.get("project_id")) if item.get("project_id") else None
        links = db.scalars(select(AssetServiceLink).where(AssetServiceLink.asset_id == item["asset_id"])).all()
        service_codes = [link.code_id for link in links]
        service_names = [db.get(ServiceCatalog, code).name for code in service_codes if db.get(ServiceCatalog, code)]
        item.update(customer_name=customer.customer_name if customer else "—",
                    project_name=project.project_name if project else "—",
                    service_code_ids=service_codes, service_names=", ".join(service_names) if service_names else "—")
    elif resource == "users":
        team_ids = _user_team_ids(db, row) if row.role == "agent" else []
        team_rows = [db.get(Team, team_id) for team_id in team_ids]
        team_names = [team.team_name for team in team_rows if team]
        item["team_ids"] = team_ids
        item["team_names"] = team_names
        item["team_name"] = ", ".join(team_names) if team_names else "—"
        if row.role == "agent":
            item["available_for_assignment"] = not _agent_has_unresolved_assignment(db, row)
        request_type = db.get(ServiceCatalog, item.get("request_type_code")) if item.get("request_type_code") else None
        item["request_type_name"] = request_type.name if request_type else "—"
        if item.get("role") == "customer" and item.get("email"):
            customer = db.scalar(select(Customer).where(func.lower(Customer.email) == str(item["email"]).lower()))
            item["customer_id"] = customer.customer_id if customer else None
            item["customer_active"] = bool(customer.active) if customer else bool(item.get("active", True))
    elif resource == "teams":
        service = db.get(ServiceCatalog, item.get("code_id")) if item.get("code_id") else None
        links = db.scalars(select(TeamServiceLink).where(TeamServiceLink.team_id == item["team_id"])).all()
        all_codes = [link.code_id for link in links]
        if item.get("code_id") and item["code_id"] not in all_codes:
            all_codes.insert(0, item["code_id"])
        names = [db.get(ServiceCatalog, code).name for code in all_codes if db.get(ServiceCatalog, code)]
        item["service_name"] = service.name if service else "—"
        item["service_names"] = ", ".join(names) if names else (service.name if service else "—")
        item["service_code_ids"] = all_codes
    elif resource == "audit-logs":
        item["timestamp"] = item.get("created_at")
        if not item.get("actor_role") and item.get("user_id"):
            logged_user = db.get(User, item.get("user_id"))
            if logged_user:
                item["actor_role"] = logged_user.role
        try:
            item["changes"] = json.loads(item.get("change_data") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["changes"] = {}
    elif resource == "role-permissions":
        try:
            item["permissions"] = json.loads(item.pop("permissions_json", "{}"))
        except json.JSONDecodeError:
            item["permissions"] = {}
    return item

def _default_user_notification_preferences(role: str) -> dict[str, bool]:
    base = {"ticket_created": True, "ticket_assigned": True, "status_changed": True,
            "new_reply": True, "internal_note": role in {"admin", "agent"},
            "sla_approaching": True, "ticket_resolved": True,
            "daily_summary": role in {"admin", "agent"}}
    return base

def _ticket_assigned_agent(db: Session, ticket: Ticket) -> User | None:
    """Resolve the explicitly assigned active Agent, independent of profile tags."""
    if not ticket.assigned:
        return None
    return db.scalar(select(User).where(
        func.lower(func.trim(User.fullname)) == str(ticket.assigned).strip().lower(),
        User.role == "agent", User.active.is_(True)
    ).order_by(User.user_id))

RESOURCE_PK = {
    "tickets": "ticket_id", "customers": "customer_id", "contacts": "contact_id", "projects": "project_id",
    "users": "user_id", "teams": "team_id", "services": "code_id", "plans": "plan_id",
    "contracts": "contract_id", "assets": "asset_id", "audit-logs": "audit_id", "role-permissions": "role_permission_id",
}

AUTO_CODE_CONFIG = {
    "tickets": (Ticket, "ticket_code", "ticket_id", "TKT"),
    "contacts": (Contact, "contact_code", "contact_id", "CTC"),
    "projects": (Project, "project_code", "project_id", "PRJ"),
    "contracts": (Contract, "contract_code", "contract_id", "CTR"),
    "plans": (Plan, "plan_code", "plan_id", "SPL"),
    "teams": (Team, "team_code", "team_id", "TEAM"),
    "assets": (Asset, "asset_tag", "asset_id", "AST"),
}

def assign_generated_service_code(db: Session) -> str:
    """Allocate the next SRV-### identifier inside the current transaction."""
    lock_key = f"golden-pride-code:services:{yangon_today().year}"
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": lock_key})
    used = []
    for value in db.scalars(select(ServiceCatalog.code_id).where(ServiceCatalog.code_id.like("SRV-%"))).all():
        match = re.fullmatch(r"SRV-(\d+)", str(value or ""), re.I)
        if match:
            used.append(int(match.group(1)))
    sequence = max(used, default=0) + 1
    code = f"SRV-{sequence:03d}"
    while db.get(ServiceCatalog, code) is not None:
        sequence += 1
        code = f"SRV-{sequence:03d}"
    return code

def assign_generated_code(db: Session, resource: str, row: Any) -> str | None:
    """Generate stable YYYY-sequence codes after the row has its database ID."""
    config = AUTO_CODE_CONFIG.get(resource)
    if not config:
        return None
    model, field_name, pk_name, prefix = config
    current = getattr(row, field_name, None)
    if current and not str(current).startswith("AUTO-TMP-"):
        return str(current)
    year = yangon_today().year
    lock_key = f"golden-pride-code:{resource}:{year}"
    if engine.dialect.name == "postgresql":
        # Serialize generators for the same module/year across all application workers.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": lock_key})
    column = getattr(model, field_name)
    pattern = re.compile(rf"^{re.escape(prefix)}-{year}-(\d+)$")
    used = []
    for value in db.scalars(select(column).where(column.like(f"{prefix}-{year}-%"))).all():
        match = pattern.match(str(value or ""))
        if match:
            used.append(int(match.group(1)))
    row_number = int(getattr(row, pk_name))
    sequence = max(row_number, max(used, default=0) + 1)
    code = f"{prefix}-{year}-{sequence:03d}"
    while db.scalar(select(column).where(column == code)) is not None:
        sequence += 1
        code = f"{prefix}-{year}-{sequence:03d}"
    setattr(row, field_name, code)
    db.flush()
    return code

__all__ = [name for name in globals() if not name.startswith("__")]
