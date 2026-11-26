"""Resource Service logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .database import *
from .models import *
from .security import *

RESOURCE_MODELS: dict[str, type[Base]] = {
    "tickets": Ticket, "customers": Customer, "contacts": Contact, "projects": Project,
    "users": User, "teams": Team, "services": ServiceCatalog, "plans": Plan,
    "contracts": Contract, "assets": Asset, "audit-logs": AuditLog,
    "role-permissions": RolePermission,
}

def refresh_team_member_label(db: Session, team_id: int | None) -> None:
    if not team_id:
        return
    team = db.get(Team, team_id)
    if team:
        team.member = ", ".join(agent.fullname for agent in _team_agents(db, team_id))

def apply_team_members(db: Session, team: Team, member_value: Any) -> None:
    """Keep each team to 1–4 active Agent members and synchronize membership links."""
    if isinstance(member_value, (list, tuple)):
        names = [str(value).strip() for value in member_value if str(value).strip()]
    else:
        names = [part.strip() for part in str(member_value or "").split(",") if part.strip()]
    # Preserve order while removing repeated selections.
    names = list(dict.fromkeys(names))
    if not 1 <= len(names) <= 4:
        raise HTTPException(status_code=422, detail="A Support Team must contain at least 1 and no more than 4 Agents.")
    agents = db.scalars(select(User).where(User.role == "agent", User.active.is_(True))).all()
    by_name = {agent.fullname.casefold(): agent for agent in agents}
    missing = [name for name in names if name.casefold() not in by_name]
    if missing:
        raise HTTPException(status_code=422, detail="Select active Agent accounts only. Unknown Agent: " + ", ".join(missing))
    selected = [by_name[name.casefold()] for name in names]
    selected_ids = {agent.user_id for agent in selected}
    old_team_ids: set[int] = set()
    existing_agents = db.scalars(select(User).where(User.role == "agent")).all()
    for agent in existing_agents:
        memberships = _user_team_ids(db, agent)
        if team.team_id in memberships:
            old_team_ids.update(memberships)
            if agent.user_id not in selected_ids:
                db.query(UserTeamMembership).filter(
                    UserTeamMembership.user_id == agent.user_id,
                    UserTeamMembership.team_id == team.team_id
                ).delete(synchronize_session=False)
                if agent.team_id == team.team_id:
                    agent.team_id = None
    for agent in selected:
        old_team_ids.update(_user_team_ids(db, agent))
        db.query(UserTeamMembership).filter(UserTeamMembership.user_id == agent.user_id).delete(synchronize_session=False)
        agent.team_id = team.team_id
        db.add(UserTeamMembership(user_id=agent.user_id, team_id=team.team_id))
    team.member = ", ".join(agent.fullname for agent in selected)
    db.flush()
    for old_team_id in old_team_ids:
        if old_team_id != team.team_id:
            refresh_team_member_label(db, old_team_id)

def check_resource_access(resource: str, actor: dict[str, Any], operation: str) -> None:
    role = actor["role"]
    if resource == "audit-logs" or resource == "role-permissions":
        admin_only(actor)
        if operation != "read" and resource == "audit-logs":
            raise HTTPException(status_code=405, detail="Audit logs are read-only.")
        return
    if resource == "users":
        admin_only(actor)
        return
    if role == "admin":
        return
    if role == "agent":
        if resource == "tickets":
            if operation in {"read", "update"}:
                # The update endpoint applies a stricter assigned-Agent-only,
                # status-only allow-list before accepting any ticket change.
                return
            raise HTTPException(status_code=403, detail="Agents cannot create or delete tickets. The assigned Agent may change ticket status and use the permitted conversation tools.")
        if resource in {"customers", "contacts", "projects", "contracts", "plans", "services", "assets"}:
            if operation == "read":
                return
        if operation == "read" and resource == "teams":
            return
        raise HTTPException(status_code=403, detail="Your agent role does not have permission for this module/action.")
    if role == "customer":
        if resource == "tickets" and operation in {"read", "create"}:
            return
        if resource == "tickets" and operation == "update":
            return
        if resource == "services" and operation == "read":
            return
        if resource == "assets" and operation == "read":
            return
        raise HTTPException(status_code=403, detail="Your customer role does not have permission for this module/action.")
    raise HTTPException(status_code=403, detail="Access denied.")

def coerce_value(column_type: Any, value: Any, key: str) -> Any:
    if value == "":
        return None
    if value is None:
        return None
    if isinstance(column_type, Boolean):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "yes", "enabled", "on"}
    if isinstance(column_type, Integer):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{key} must be a whole number.")
    if isinstance(column_type, Float):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{key} must be a number.")
    if isinstance(column_type, Date):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{key} must be a date in YYYY-MM-DD format.")
    if isinstance(column_type, DateTime):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{key} must be a valid date and time.")
    return str(value).strip()

def clean_payload(resource: str, payload: dict[str, Any], row: Any | None = None) -> dict[str, Any]:
    model = RESOURCE_MODELS[resource]
    columns = {c.key: c for c in inspect(model).columns}
    pk = RESOURCE_PK[resource]
    accepted: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"password_hash", "created_at", "updated_at", "permissions_json", "must_change_password"}:
            continue
        if key in {
            "contact_code", "project_code", "contract_code", "plan_code", "team_code", "asset_tag", "ticket_code"
        } or (resource == "services" and key == "code_id"):
            # These identifiers are server-managed and cannot be supplied or edited by clients.
            continue
        # Service catalog codes are user-supplied string primary keys (e.g. SRV-001),
        # unlike the auto-incrementing integer IDs on the other entities.
        if key == pk and not (resource == "services" and row is None):
            continue
        if key not in columns:
            continue
        if resource == "users" and key == "password_hash":
            continue
        if resource == "users" and key == "password":
            continue
        accepted[key] = coerce_value(columns[key].type, value, key)
    if resource == "users":
        role = str(payload.get("role", getattr(row, "role", "customer"))).lower()
        role = {"administrator": "admin", "admin": "admin", "agent": "agent", "customer": "customer"}.get(role, role)
        if role not in {"admin", "agent", "customer"}:
            raise HTTPException(status_code=422, detail="Role must be admin, agent, or customer.")
        accepted["role"] = role
        if role == "agent" and not (payload.get("team_ids") or payload.get("other_team_name") or accepted.get("team_id") or (row and row.team_id)):
            raise HTTPException(status_code=422, detail="Select one Support Team for this Agent.")
        password = payload.get("password")
        if password:
            accepted["password_hash"] = hash_password(str(password))
        elif row is None:
            raise HTTPException(status_code=422, detail="A password is required for a new user.")
        if "email" in accepted:
            accepted["email"] = str(accepted["email"]).lower()
    if resource == "plans":
        for key in ("response_warning", "response_critical", "resolution_warning", "resolution_critical"):
            value = accepted.get(key)
            if value is not None and not 0 <= value <= 99:
                raise HTTPException(status_code=422, detail=f"{key.replace('_', ' ').title()} must be a whole number from 0 to 99.")
        for key in ("response_sla", "resolution_sla"):
            value = accepted.get(key)
            if value is not None and re.match(r"^\s*-\s*\d", str(value)):
                raise HTTPException(status_code=422, detail=f"{key.replace('_', ' ').title()} cannot be negative.")
    if resource == "services":
        if not str(accepted.get("name") or "").strip():
            raise HTTPException(status_code=422, detail="Service Catalog Name is required.")
        accepted["name"] = str(accepted["name"]).strip()
        if "request_order" in payload and payload.get("request_order") not in (None, ""):
            try:
                numeric_order = float(payload["request_order"])
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Sort Order must be a whole number zero or greater.")
            if numeric_order < 0 or not numeric_order.is_integer():
                raise HTTPException(status_code=422, detail="Sort Order must be a whole number zero or greater.")
        # HTML selects may send yes/no or enabled/disabled values; normalize to booleans.
        for bool_key in ("customer_visible", "auto_assign"):
            if bool_key in payload:
                accepted[bool_key] = str(payload[bool_key]).lower() in {"true", "yes", "enabled", "1", "on"} if not isinstance(payload[bool_key], bool) else payload[bool_key]
        if "request_order" in accepted and (accepted["request_order"] is None or accepted["request_order"] < 0):
            raise HTTPException(status_code=422, detail="Sort Order must be zero or a positive whole number.")
    if resource == "tickets" and row is None:
        # Ticket Created date is system-controlled and cannot be backdated from the UI/API.
        accepted["date"] = yangon_today()
    return accepted

def _agent_can_access_ticket(db: Session, ticket: Ticket, actor: dict[str, Any]) -> bool:
    """Allow an Agent to view tickets assigned to them or routed to their Team.

    Team access lets the mapped Team review an unassigned ticket for dispatch
    without exposing other Teams' work. Posting replies or internal notes is
    separately restricted to the explicitly assigned Agent.
    """
    current_agent = db.get(User, actor.get("user_id"))
    if not current_agent or current_agent.role != "agent" or not current_agent.active or not ticket.active:
        return False
    assigned_to_current_agent = bool(
        ticket.assigned and
        str(ticket.assigned).strip().casefold() == str(current_agent.fullname or "").strip().casefold()
    )
    belongs_to_ticket_team = bool(ticket.team_id and ticket.team_id in _user_team_ids(db, current_agent))
    return assigned_to_current_agent or belongs_to_ticket_team

def scope_rows(db: Session, resource: str, rows: list[Any], actor: dict[str, Any]) -> list[Any]:
    # Admins retain visibility of inactive records so they can reactivate them.
    # All other roles receive active records only.
    if actor["role"] != "admin":
        rows = [row for row in rows if bool(getattr(row, "active", True))]
    if actor["role"] == "agent" and resource == "tickets":
        current_agent = db.get(User, actor.get("user_id"))
        if not current_agent or not current_agent.active:
            return []
        # Team members share visibility of their Team queue so they can manually
        # assign unassigned tickets and reassign work within the same Team.
        agent_name = str(current_agent.fullname or "").strip().casefold()
        agent_team_ids = set(_user_team_ids(db, current_agent))
        return [ticket for ticket in rows if (
            (ticket.assigned and str(ticket.assigned).strip().casefold() == agent_name)
            or (ticket.team_id is not None and ticket.team_id in agent_team_ids)
        )]
    if actor["role"] != "customer":
        return rows
    cust_id = actor_customer_id(db, actor)
    if resource == "tickets":
        return [r for r in rows if cust_id is not None and r.customer_id == cust_id]
    if resource == "assets":
        return [r for r in rows if cust_id is not None and r.customer_id == cust_id]
    if resource == "services":
        return [r for r in rows if r.customer_visible]
    return []

def validate_primary_contact(db: Session, data: dict[str, Any], existing: Contact | None = None) -> None:
    """Allow at most one Contact whose Type is Primary Contact for each Customer."""
    selected_type = data.get("type", existing.type if existing is not None else None)
    if str(selected_type or "").strip().casefold() != "primary contact":
        return

    customer_id = data.get("customer_id", existing.customer_id if existing is not None else None)
    if customer_id in (None, ""):
        raise HTTPException(status_code=422, detail="Select a customer before marking this contact as Primary Contact.")
    customer_id = int(customer_id)

    # PostgreSQL advisory locking serializes concurrent Primary Contact changes
    # for one customer, so two simultaneous requests cannot both pass the check.
    if engine.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"golden-pride-primary-contact:{customer_id}"},
        )

    # Editing an existing Primary Contact without changing its customer/type is
    # not a new assignment, and should remain possible even with legacy duplicates.
    if existing is not None and existing.customer_id == customer_id and str(existing.type or "").strip().casefold() == "primary contact":
        return

    duplicate_query = select(Contact.contact_id).where(
        Contact.customer_id == customer_id,
        func.lower(func.trim(Contact.type)) == "primary contact",
    )
    if existing is not None:
        duplicate_query = duplicate_query.where(Contact.contact_id != existing.contact_id)
    duplicate_id = db.scalar(duplicate_query.limit(1))
    if duplicate_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This customer already has a Primary Contact. Choose another contact type.",
        )

def validate_customer_relationships(db: Session, resource: str, data: dict[str, Any], existing: Any | None = None) -> None:
    """Validate that linked records belong to the selected customer/project scope."""
    def value(key: str) -> Any:
        if key in data:
            return data[key]
        return getattr(existing, key, None) if existing is not None else None

    if resource not in {"contacts", "contracts", "assets", "tickets"}:
        return
    customer_id = value("customer_id")
    project_id = value("project_id")
    if resource in {"contacts", "contracts", "assets", "tickets"} and customer_id:
        if not db.get(Customer, customer_id):
            raise HTTPException(status_code=422, detail="Select an existing customer.")
    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=422, detail="Select an existing project.")
        if customer_id and project.customer_id != customer_id:
            raise HTTPException(status_code=422, detail="The selected project does not belong to the selected customer.")
    if resource == "tickets":
        for key, model in (("contact_id", Contact), ("contract_id", Contract), ("asset_id", Asset)):
            related_id = value(key)
            if related_id:
                related = db.get(model, related_id)
                if not related:
                    raise HTTPException(status_code=422, detail=f"Select an existing {key.replace('_id','').replace('_',' ')}.")
                if customer_id and related.customer_id != customer_id:
                    raise HTTPException(status_code=422, detail=f"The selected {key.replace('_id','').replace('_',' ')} does not belong to the selected customer.")
        # A Ticket may use only the Support Plan linked to its selected Contract.
        plan_id = value("plan_id")
        if plan_id and not db.get(Plan, plan_id):
            raise HTTPException(status_code=422, detail="Select an existing support plan.")
        contract_id = value("contract_id")
        contract = db.get(Contract, contract_id) if contract_id else None
        legacy_pair_unchanged = bool(
            existing is not None
            and str(contract_id or "") == str(existing.contract_id or "")
            and str(plan_id or "") == str(existing.plan_id or "")
        )
        if contract and contract.plan_id != plan_id and not legacy_pair_unchanged:
            raise HTTPException(status_code=422, detail="The Support Plan must be the plan linked to the selected Contract.")
        if not contract and plan_id and existing is None:
            raise HTTPException(status_code=422, detail="Select a Contract before selecting its Support Plan.")
        if contract and project_id and contract.project_id and contract.project_id != project_id:
            raise HTTPException(status_code=422, detail="The selected contract is linked to a different project.")
        service_code = value("service_code")
        team_id = value("team_id")
        # Ticket Support Team and Request Type are independent descriptive/routing
        # fields. Neither has to match an Agent profile during assignment.
        if service_code and not db.get(ServiceCatalog, service_code):
            raise HTTPException(status_code=422, detail="Select an existing Service Catalog request type.")
        if team_id and not db.get(Team, team_id):
            raise HTTPException(status_code=422, detail="Select an existing Support Team.")
    if resource == "contracts" and value("plan_id") and not db.get(Plan, value("plan_id")):
        raise HTTPException(status_code=422, detail="Select an existing support plan.")

def sync_ticket_contract_links(db: Session, data: dict[str, Any], existing: Ticket | None = None) -> None:
    """Keep a ticket's Support Plan synchronized with its selected Contract."""
    contract_was_submitted = "contract_id" in data
    contract_id = data.get("contract_id") if contract_was_submitted else (existing.contract_id if existing else None)
    contract = db.get(Contract, contract_id) if contract_id else None
    if contract_id and not contract:
        raise HTTPException(status_code=422, detail="Select an existing Contract.")

    if contract:
        submitted_plan_id = data.get("plan_id") if "plan_id" in data else (existing.plan_id if existing else None)
        legacy_pair_unchanged = bool(
            existing is not None
            and str(contract_id or "") == str(existing.contract_id or "")
            and str(submitted_plan_id or "") == str(existing.plan_id or "")
        )
        if submitted_plan_id not in (None, "", contract.plan_id) and not legacy_pair_unchanged:
            raise HTTPException(status_code=422, detail="The selected Support Plan does not belong to this Contract.")
        # A new or changed Contract always determines the Ticket's Plan. Preserve
        # an unchanged historical mismatch so unrelated edits still remain possible.
        if existing is None or (contract_was_submitted or "plan_id" in data) and not legacy_pair_unchanged:
            data["plan_id"] = contract.plan_id
        if not data.get("project_id") and contract.project_id:
            data["project_id"] = contract.project_id
    elif contract_was_submitted:
        if data.get("plan_id") not in (None, ""):
            raise HTTPException(status_code=422, detail="Select a Contract before selecting its Support Plan.")
        data["plan_id"] = None
    elif existing is None and data.get("plan_id") not in (None, ""):
        raise HTTPException(status_code=422, detail="Select a Contract before selecting its Support Plan.")
    return None

def validate_ticket_prerequisites(db: Session, data: dict[str, Any]) -> None:
    """Validate only the essential ticket fields; related setup records are optional."""
    customer_id = data.get("customer_id")
    if not customer_id or not db.get(Customer, customer_id):
        raise HTTPException(status_code=422, detail="Select an existing customer.")
    if not str(data.get("subject") or "").strip():
        raise HTTPException(status_code=422, detail="Enter a ticket subject.")
    data.setdefault("type", "Incident")

def validate_record_dates(resource: str, data: dict[str, Any], existing: Any | None = None) -> None:
    """Enforce Yangon-local dates: no past dates and no same-day project/contract ranges."""
    today = yangon_today()
    if resource == "tickets":
        due = data.get("due_date") if "due_date" in data else None
        previous_due = getattr(existing, "due_date", None) if existing is not None else None
        # An overdue value already on a ticket must not block unrelated edits.
        # A newly selected due date still cannot be earlier than today.
        if due is not None and due < today and due != previous_due:
            raise HTTPException(status_code=422, detail=f"Due Date cannot be earlier than today ({today.isoformat()}).")
        if existing is not None:
            # Creation date is immutable after creation.
            data.pop("date", None)
        else:
            # Never trust a submitted value for a newly created ticket's creation date.
            data["date"] = today
    if resource in {"contracts", "projects"}:
        start = data.get("start_date") if "start_date" in data else getattr(existing, "start_date", None)
        end = data.get("end_date") if "end_date" in data else getattr(existing, "end_date", None)
        if existing is None and start is None:
            label = "Contract" if resource == "contracts" else "Project"
            raise HTTPException(status_code=422, detail=f"{label} Start Date is required.")
        if existing is None and end is None:
            label = "Contract" if resource == "contracts" else "Project"
            raise HTTPException(status_code=422, detail=f"{label} End Date is required.")
        if start is not None and start < today:
            raise HTTPException(status_code=422, detail=f"Start Date cannot be earlier than today ({today.isoformat()}).")
        if end is not None and end < today:
            raise HTTPException(status_code=422, detail=f"End Date cannot be earlier than today ({today.isoformat()}).")
        if start is not None and end is not None and end <= start:
            label = "Contract" if resource == "contracts" else "Project"
            raise HTTPException(status_code=422, detail=f"{label} End Date must be later than Start Date. Same-day dates are not allowed.")

def validate_contact_fields(resource: str, data: dict[str, Any]) -> None:
    """Validate phone numbers and email addresses before writing them to the database."""
    if "phone" in data and data.get("phone") not in (None, ""):
        phone = str(data["phone"]).strip()
        digits = phone[1:] if phone.startswith("+") else phone
        if not re.fullmatch(r"[0-9]{1,15}", digits):
            raise HTTPException(status_code=422, detail="Phone number must contain 1 to 15 digits, with an optional leading +. Hyphens and spaces are not allowed.")
        data["phone"] = phone
    if "email" in data and data.get("email") not in (None, ""):
        email = str(data["email"]).strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", email, re.I):
            raise HTTPException(status_code=422, detail="Enter a valid email address, for example name@gmail.com.")
        if email.endswith("@gmail.com"):
            local = email.split("@", 1)[0]
            if not re.fullmatch(r"[a-z0-9]+(?:\.[a-z0-9]+)*(?:\+[a-z0-9-]+)?", local):
                raise HTTPException(status_code=422, detail="Enter a valid Gmail address before @gmail.com.")
        data["email"] = email

def validate_ticket_assignment(db: Session, data: dict[str, Any], existing: Ticket | None = None) -> None:
    """Require a newly selected assignee to belong to the ticket's Support Team."""
    team_id = data.get("team_id") if "team_id" in data else (existing.team_id if existing else None)
    service_code = data.get("service_code") if "service_code" in data else (existing.service_code if existing else None)
    assigned = data.get("assigned") if "assigned" in data else (existing.assigned if existing else None)

    if team_id not in (None, "") and not db.get(Team, team_id):
        raise HTTPException(status_code=422, detail="Select an existing Support Team.")
    if service_code and not db.get(ServiceCatalog, service_code):
        raise HTTPException(status_code=422, detail="Select an existing Request Type.")
    # For older records without team_id, use the Service Catalog mapping as the
    # effective assignment team without changing any unrelated ticket fields.
    effective_team = db.get(Team, team_id) if team_id not in (None, "") else _team_for_service(db, service_code)
    assignment_unchanged = existing is not None and str(assigned or "").strip().casefold() == str(existing.assigned or "").strip().casefold()
    if assigned and not assignment_unchanged:
        agent = db.scalar(select(User).where(
            func.lower(User.fullname) == str(assigned).strip().lower(),
            User.role == "agent", User.active.is_(True)))
        if not agent:
            raise HTTPException(status_code=422, detail="Assigned user must be an active Agent.")
        agent = _lock_active_agent_for_assignment(db, agent)
        if not agent:
            raise HTTPException(status_code=422, detail="Assigned user must be an active Agent.")
        if effective_team and effective_team.team_id not in _user_team_ids(db, agent):
            raise HTTPException(status_code=422, detail="Assigned Agent must belong to the ticket's selected Support Team.")
        if _agent_has_unresolved_assignment(
            db, agent, exclude_ticket_id=getattr(existing, "ticket_id", None)
        ):
            busy_ticket = db.scalar(select(Ticket).where(
                Ticket.active.is_(True),
                func.lower(func.trim(Ticket.assigned)) == str(agent.fullname or "").strip().lower(),
                func.lower(func.trim(Ticket.status)).not_in(["resolved", "closed"]),
                Ticket.ticket_id != getattr(existing, "ticket_id", -1),
            ).order_by(Ticket.ticket_id).limit(1))
            busy_code = (busy_ticket.ticket_code or f"TKT-{busy_ticket.ticket_id}") if busy_ticket else "another ticket"
            raise HTTPException(
                status_code=409,
                detail=f"{agent.fullname} is unavailable because {busy_code} is still unresolved. Resolve or close that ticket before assigning another one.",
            )

def validate_plan_unique_fields(db: Session, data: dict[str, Any], current_plan_id: int | None = None) -> None:
    """Give clear validation errors before the database unique constraint fires."""
    code = str(data.get("plan_code") or "").strip()
    name = str(data.get("plan_name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Plan Name is required.")
    if code:
        stmt = select(Plan).where(func.lower(Plan.plan_code) == code.lower())
        if current_plan_id is not None:
            stmt = stmt.where(Plan.plan_id != current_plan_id)
        if db.scalar(stmt):
            raise HTTPException(status_code=409, detail=f"Support Plan Code '{code}' already exists. Enter a different Plan Code.")
    stmt = select(Plan).where(func.lower(Plan.plan_name) == name.lower())
    if current_plan_id is not None:
        stmt = stmt.where(Plan.plan_id != current_plan_id)
    if db.scalar(stmt):
        raise HTTPException(status_code=409, detail=f"Support Plan Name '{name}' already exists. Enter a different Plan Name.")

def normalize_plan_type(payload: dict[str, Any], existing: Plan | None = None) -> None:
    """Resolve the built-in Plan Type selector or its custom Other value."""
    selected = str(payload.get("plan_type") or (existing.plan_type if existing else "Standard") or "Standard").strip()
    if selected.casefold() == "other":
        selected = str(payload.get("custom_plan_type") or "").strip()
        if not selected:
            raise HTTPException(status_code=422, detail="Enter a name for the custom Support Plan Type.")
    if not selected:
        raise HTTPException(status_code=422, detail="Select a Support Plan Type.")
    if len(selected) > 100:
        raise HTTPException(status_code=422, detail="Support Plan Type must be 100 characters or fewer.")
    payload["plan_type"] = selected
    payload.pop("custom_plan_type", None)

def integrity_error_message(exc: IntegrityError, resource: str, operation: str) -> str:
    """Return a useful, safe explanation for common database integrity failures.

    Keep the original database exception in the server log for diagnosis, but do not
    expose SQL statements, credentials, or raw values to the browser.
    """
    original = str(getattr(exc, "orig", exc) or "")
    lowered = original.lower()
    field_labels = {
        "email": "Email address", "customer_name": "Customer name",
        "contact_code": "Contact Code", "project_code": "Project Code",
        "plan_code": "Plan Code", "plan_name": "Plan Name", "plan_type": "Plan Type",
        "team_code": "Team Code", "team_name": "Team Name",
        "code_id": "Service Code", "contract_code": "Contract Code",
        "asset_tag": "Asset Tag", "ticket_code": "Ticket Code",
        "role_key": "Role Key",
    }
    unique_column = None
    # SQLite: UNIQUE constraint failed: table.column
    match = re.search(r"unique constraint failed:\s*(?:[\w\"]+\.)?([\w\"]+)", original, re.I)
    if match:
        unique_column = match.group(1).strip('"')
    # PostgreSQL: Key (column)=(value) already exists.
    if not unique_column:
        match = re.search(r"key\s*\(\s*([\w, ]+)\s*\)\s*=", original, re.I)
        if match:
            unique_column = match.group(1).strip().split(",")[0].strip()
    if unique_column or "unique constraint" in lowered or "duplicate key" in lowered:
        label = field_labels.get(unique_column or "", (unique_column or "unique field").replace("_", " ").title())
        logger.warning("Database %s conflict for %s: %s", operation, resource, original)
        return f"{label} already exists. Please use a different {label.lower()}."
    if "foreign key constraint failed" in lowered or "violates foreign key constraint" in lowered:
        logger.warning("Database %s relationship conflict for %s: %s", operation, resource, original)
        return "A selected related record no longer exists or is not linked correctly. Refresh the page and reselect the Customer, Project, Contact, Contract, Support Plan, Team, Service, or Asset."
    if "not null constraint failed" in lowered or "violates not-null constraint" in lowered:
        match = re.search(r"(?:not null constraint failed:\s*(?:[\w\"]+\.)?|column \"?)([\w\"]+)", original, re.I)
        column = match.group(1).strip('"') if match else None
        label = (column or "A required field").replace("_", " ").title()
        logger.warning("Database %s required-field conflict for %s: %s", operation, resource, original)
        return f"{label} is required. Please complete this field and try again."
    logger.exception("Database %s integrity failure for %s", operation, resource, exc_info=exc)
    return f"Could not {operation} this {resource.rstrip('s')} record because one of its values or relationships conflicts with the database. Check required fields and linked records."

def ensure_customer_login_account(
    db: Session,
    customer: Customer,
    actor: dict[str, Any] | None = None,
    *,
    create_if_missing: bool = True,
) -> tuple[User | None, bool]:
    """Keep a Customer profile linked to exactly one Customer login by email.

    The email is the existing relationship key used by the portal and serializer.
    New accounts receive an undisclosed random credential and must use Admin's
    password-reset flow before their first sign-in.
    """
    email = str(customer.email or "").strip().lower()
    if not email:
        if create_if_missing:
            raise HTTPException(
                status_code=422,
                detail="General Email is required because each Customer profile must have a linked Customer login account.",
            )
        return None, False

    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing:
        if existing.role != "customer":
            raise HTTPException(
                status_code=409,
                detail="This email address is already used by an Admin or Agent account. Use a different Customer email address.",
            )
        existing.email = email
        existing.fullname = str(customer.contact_name or customer.customer_name).strip() or customer.customer_name
        existing.active = bool(customer.active)
        db.flush()
        return existing, False

    if not create_if_missing:
        return None, False

    linked_user = User(
        fullname=str(customer.contact_name or customer.customer_name).strip() or customer.customer_name,
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="customer",
        team_id=None,
        request_type_code=None,
        notes="Customer login created automatically from the Customers module.",
        active=bool(customer.active),
        must_change_password=True,
    )
    db.add(linked_user)
    db.flush()
    log_action(
        db,
        actor,
        "CREATE",
        "users",
        f"Created Customer login account linked to customer {customer.customer_name} ({email}). A temporary password must be issued by Admin.",
        entity_id=linked_user.user_id,
        entity_label=f"{linked_user.fullname} ({linked_user.email})",
        changes={"role": {"from": None, "to": "customer"}, "customer_email": {"from": None, "to": email}},
    )
    return linked_user, True

__all__ = [name for name in globals() if not name.startswith("__")]
