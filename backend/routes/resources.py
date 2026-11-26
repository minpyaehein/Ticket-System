"""Resources API endpoints."""
from __future__ import annotations
from ..common import *
from ..config import *
from ..models import *
from ..security import *
from ..email_service import *
from ..resource_service import *
from ..sla import *

router = APIRouter()

@router.get("/api/{resource}")
def list_resource(resource: str, request: Request, search: str = Query(default=""), action: str = Query(default=""), entity: str = Query(default=""), from_date: str = Query(default=""), to_date: str = Query(default=""), db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "read")
    model = RESOURCE_MODELS[resource]
    pk = RESOURCE_PK[resource]
    query = select(model)
    if resource == "audit-logs":
        query = query.order_by(AuditLog.created_at.desc())
    elif resource == "tickets":
        query = query.order_by(Ticket.updated_at.desc())
    elif resource == "projects":
        query = query.order_by(Project.project_id.desc())
    elif resource == "services":
        query = query.order_by(ServiceCatalog.request_order, ServiceCatalog.name)
    elif resource == "users":
        query = query.order_by(case(
            (func.lower(User.role) == "admin", 0),
            (func.lower(User.role) == "agent", 1),
            (func.lower(User.role) == "customer", 2),
            else_=3,
        ), func.lower(User.fullname), User.user_id)
    else:
        query = query.order_by(getattr(model, pk))
    rows = db.scalars(query).all()
    rows = scope_rows(db, resource, list(rows), actor)
    if search.strip():
        term = search.casefold()
        if resource == "audit-logs":
            rows = [r for r in rows if term in " ".join(str(v or "") for v in (r.user_name, r.actor_role, r.action, r.module, r.entity_id, r.entity_label, r.details, r.ip_address)).casefold()]
        else:
            rows = [r for r in rows if term in " ".join(str(v or "") for v in model_values(r).values()).casefold()]
    if resource == "audit-logs":
        if action and action.casefold() not in {"all actions", "all"}:
            rows = [r for r in rows if r.action.casefold() == action.casefold()]
        if entity and entity.casefold() not in {"all entities", "all"}:
            rows = [r for r in rows if entity.casefold() in " ".join([str(r.module or ""), str(r.entity_label or ""), str(r.entity_id or "")]).casefold()]
        if from_date:
            try: start = date.fromisoformat(from_date)
            except ValueError: raise HTTPException(status_code=422, detail="from_date must be YYYY-MM-DD.")
            rows = [r for r in rows if r.created_at.date() >= start]
        if to_date:
            try: end = date.fromisoformat(to_date)
            except ValueError: raise HTTPException(status_code=422, detail="to_date must be YYYY-MM-DD.")
            rows = [r for r in rows if r.created_at.date() <= end]
    return jsonable_encoder([serialize_row(db, resource, row) for row in rows])

@router.post("/api/{resource}")
def create_resource(resource: str, payload: dict[str, Any], request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "create")
    try:
        if resource == "plans":
            normalize_plan_type(payload)
        if resource == "users":
            # Normalize the email before any user lookup or insert. This keeps
            # duplicate detection consistent between PostgreSQL and the UI.
            if payload.get("email") not in (None, ""):
                payload["email"] = str(payload["email"]).strip().lower()
            _prepare_user_custom_selections(db, payload)
        data = clean_payload(resource, payload)
        validate_contact_fields(resource, data)
        validate_record_dates(resource, data)
        user_team_ids = _parse_user_team_ids(db, payload) if resource == "users" else None
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database pre-validation failed while creating %s", resource)
        raise HTTPException(status_code=400, detail=f"Could not prepare this {resource.rstrip('s')} record. Refresh the page and verify the selected values and related records.") from exc

    if resource == "customers":
        if not data.get("email"):
            raise HTTPException(status_code=422, detail="General Email is required because each Customer profile must have a linked Customer login account.")
        duplicate_customer = db.scalar(select(Customer).where(func.lower(Customer.email) == data["email"]))
        if duplicate_customer:
            raise HTTPException(status_code=409, detail="A Customer profile already exists with this email address. Open that customer record instead of creating a duplicate.")
        existing_user = db.scalar(select(User).where(func.lower(User.email) == data["email"]))
        if existing_user and existing_user.role != "customer":
            raise HTTPException(status_code=409, detail="This email address is already used by an Admin or Agent account. Use a different Customer email address.")
    if resource == "users":
        data["team_id"] = user_team_ids[0] if user_team_ids else None
        if str(data.get("role", "customer")).lower() == "agent":
            request_type_code = str(data.get("request_type_code") or "").strip()
            if not request_type_code or not db.get(ServiceCatalog, request_type_code):
                raise HTTPException(status_code=422, detail="Choose one valid Request Type for this Agent.")
        else:
            data["request_type_code"] = None
    if resource == "teams":
        service_codes = payload.get("service_codes")
        if service_codes is None:
            service_codes = [data.get("code_id")] if data.get("code_id") else []
        if isinstance(service_codes, str):
            service_codes = [service_codes] if service_codes else []
        selected_codes = [str(code) for code in service_codes if code]
        if len(selected_codes) != 1:
            raise HTTPException(status_code=422, detail="Choose exactly one Service Catalog item for this Support Team.")
        if not db.get(ServiceCatalog, selected_codes[0]):
            raise HTTPException(status_code=422, detail="Select an existing Service Catalog item for this Support Team.")
        data["code_id"] = selected_codes[0]
        data["member"] = str(data.get("member") or "").strip()
        # Validate selection count and that all names are active Agent accounts.
        names = [part.strip() for part in data["member"].split(",") if part.strip()]
        if not 1 <= len(set(names)) <= 4:
            raise HTTPException(status_code=422, detail="A Support Team must contain at least 1 and no more than 4 Agents.")
    if resource == "plans":
        data["plan_name"] = str(data.get("plan_name") or "").strip()
        data["plan_type"] = str(data.get("plan_type") or "Standard").strip()
        data["plan_code"] = str(data.get("plan_code") or "").strip().upper() or None
        validate_plan_unique_fields(db, data)
    asset_service_codes = payload.get("service_codes") if resource == "assets" else None
    if resource == "tickets" and actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        if not cust_id:
            raise HTTPException(status_code=400, detail="Your account is not linked to a customer record. Ask an administrator to link it.")
        customer_service = db.get(ServiceCatalog, data.get("service_code")) if data.get("service_code") else None
        if customer_service and not customer_service.customer_visible:
            raise HTTPException(status_code=422, detail="That Service Catalog item is not available to customers.")
        # Related records are optional; when supplied, they must belong to the signed-in customer.
        for key, model in (("project_id", Project), ("contact_id", Contact),
                           ("contract_id", Contract), ("asset_id", Asset)):
            related_id = data.get(key)
            if related_id:
                related = db.get(model, related_id)
                if not related or related.customer_id != cust_id:
                    raise HTTPException(status_code=422, detail=f"The selected {key.replace('_id','').replace('_',' ')} does not belong to your customer account.")
        mapped_team = _team_for_service(db, customer_service.code_id) if customer_service else None
        data["customer_id"] = cust_id
        data["created_by_id"] = actor["user_id"]
        data["team_id"] = mapped_team.team_id if mapped_team else None
        data["status"] = "Open"
        data["assigned"] = None
        data.setdefault("type", "Incident")
    if resource == "tickets":
        sync_ticket_contract_links(db, data)

        # Customers may have only one non-closed ticket for the same
        # project and request type. Resolved tickets still count as active.
        if actor["role"] == "customer":
            cust_id = actor_customer_id(db, actor)
            project_id = data.get("project_id")
            service_code = data.get("service_code")

            if project_id and service_code:
                existing_ticket = db.scalar(
                    select(Ticket).where(
                        Ticket.customer_id == cust_id,
                        Ticket.project_id == project_id,
                        Ticket.service_code == service_code,
                        func.lower(func.trim(Ticket.status)) != "closed"
                    ).limit(1)
                )

                if existing_ticket:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "You already have an active ticket for this Project "
                            "and Request Type. You can create another ticket only "
                            "after Admin closes the existing ticket."
                        )
                    )

        data.setdefault("created_by_id", actor["user_id"])
        if actor["role"] == "admin" and not data.get("team_id") and data.get("service_code"):
            mapped = _team_for_service(db, data.get("service_code"))
            if mapped:
                data["team_id"] = mapped.team_id
        if actor["role"] != "customer":
            validate_ticket_assignment(db, data)
    validate_customer_relationships(db, resource, data)
    if resource == "contacts":
        validate_primary_contact(db, data)
    if resource == "tickets":
        validate_ticket_prerequisites(db, data)
        if actor["role"] == "customer":
            validate_customer_ticket_support_hours(db, data)
    if resource == "users" and "active" not in data:
        data["active"] = True
    model = RESOURCE_MODELS[resource]
    consolidated_tickets: list[tuple[Ticket, str]] = []
    linked_customer_user_created = False
    linked_customer_user_id: int | None = None
    if resource == "services":
        data["code_id"] = assign_generated_service_code(db)
    # Asset.asset_tag is non-nullable in the existing schema. Give it a temporary
    # transaction-local value so the row can be flushed before the final sequence is assigned.
    if resource == "assets" and not data.get("asset_tag"):
        data["asset_tag"] = f"AUTO-TMP-{secrets.token_hex(12)}"
    row = model(**data)
    db.add(row)
    try:
        db.flush()
        if resource == "assets":
            for code in dict.fromkeys(str(code) for code in (asset_service_codes or []) if code):
                if db.get(ServiceCatalog, code):
                    db.add(AssetServiceLink(asset_id=row.asset_id, code_id=code))
        if resource == "users":
            for team_id in user_team_ids or []:
                db.add(UserTeamMembership(user_id=row.user_id, team_id=team_id))
            db.flush()
            for team_id in user_team_ids or []:
                refresh_team_member_label(db, team_id)
        if resource == "tickets" and actor["role"] == "customer" and row.service_code:
            # Use configured Auto Assign when enabled; otherwise leave the ticket for Admin dispatch.
            _route_ticket_to_support_team(db, row, force_assign=False)
            db.flush()
        if resource in AUTO_CODE_CONFIG:
            existing_code = getattr(row, AUTO_CODE_CONFIG[resource][1], None)
            if not existing_code or str(existing_code).startswith("AUTO-TMP-"):
                assign_generated_code(db, resource, row)
        if resource == "tickets" and actor["role"] == "admin" and row.project_id and row.service_code:
            # The Admin-created ticket becomes the retained consolidated record.
            # Keep historical duplicates for audit, but close every other active
            # ticket with the same Project + Service Catalog Request Type.
            duplicate_rows = db.scalars(select(Ticket).where(
                Ticket.project_id == row.project_id,
                Ticket.service_code == row.service_code,
                Ticket.ticket_id != row.ticket_id,
                Ticket.active.is_(True),
                func.lower(Ticket.status) != "closed",
            ).order_by(Ticket.ticket_id)).all()
            for duplicate in duplicate_rows:
                old_status = str(duplicate.status or "Open")
                duplicate.status = "Closed"
                duplicate.updated_at = datetime.utcnow()
                consolidated_tickets.append((duplicate, old_status))
                duplicate_code = duplicate.ticket_code or f"TKT-{duplicate.ticket_id}"
                retained_code = row.ticket_code or f"TKT-{row.ticket_id}"
                log_action(
                    db, actor, "CONSOLIDATE", "Tickets",
                    f"Closed duplicate ticket {duplicate_code} in favor of {retained_code} "
                    f"for Project ID {row.project_id} and Request Type {row.service_code}.",
                    request=request, entity_id=duplicate.ticket_id, entity_label=duplicate_code,
                    changes={"status": {"from": old_status, "to": "Closed"},
                             "consolidated_into": {"from": None, "to": retained_code}},
                )
        if resource == "teams":
            apply_team_members(db, row, data.get("member", ""))
            if row.code_id and db.get(ServiceCatalog, row.code_id):
                db.add(TeamServiceLink(team_id=row.team_id, code_id=row.code_id))
        if resource == "services" and row.mapped_team:
            _ensure_service_mapped_team(db, row)
        if resource == "users" and row.role == "customer":
            cust = db.scalar(select(Customer).where(func.lower(Customer.email) == row.email.lower()))
            if not cust:
                cust = Customer(
                    customer_name=row.fullname,
                    email=row.email.lower(),
                    contact_name=row.fullname,
                    active=bool(row.active),
                )
                db.add(cust)
            else:
                # The Customer organization remains the organization name;
                # the user account's full name is the linked primary contact.
                cust.contact_name = row.fullname
                cust.active = bool(row.active)
        if resource == "customers":
            linked_user, linked_customer_user_created = ensure_customer_login_account(db, row, actor)
            linked_customer_user_id = linked_user.user_id if linked_user else None
        row_id = getattr(row, RESOURCE_PK[resource])
        row_label = _entity_label(resource, row, db)
        create_snapshot = _snapshot(row)
        if resource == "users":
            create_snapshot["team_ids"] = user_team_ids or []
        create_changes = {k: {"from": None, "to": v} for k, v in create_snapshot.items() if k not in {"created_at", "updated_at"}}
        create_summary = _change_summary(create_changes, limit=4)
        details = f"Created {resource} record {row_label}" + (f"; initial values: {create_summary}" if create_summary else "")
        log_action(db, actor, "CREATE", resource, details, request=request, entity_id=row_id, entity_label=row_label, changes=create_changes)
        db.commit()
        db.refresh(row)
        if resource == "tickets":
            events = [("ticket_created", "")]
            if row.assigned:
                events.append(("ticket_assigned", ""))
            else:
                events.append(("unassigned_team_queue", ""))
            background_tasks.add_task(run_ticket_notifications, row.ticket_id, events, dict(actor))
            for duplicate, old_status in consolidated_tickets:
                retained_code = row.ticket_code or f"TKT-{row.ticket_id}"
                background_tasks.add_task(
                    run_ticket_notifications, duplicate.ticket_id,
                    [("ticket_closed", f"Closed as a duplicate and consolidated into {retained_code}. Previous status: {old_status}.")],
                    dict(actor),
                )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=integrity_error_message(exc, resource, "create")) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not create {resource} record. Check required fields and relationships.") from exc
    response_data = serialize_row(db, resource, row)
    if resource == "customers":
        response_data["linked_user_id"] = linked_customer_user_id
        response_data["linked_user_created"] = linked_customer_user_created
    if resource == "tickets":
        response_data["consolidated_ticket_count"] = len(consolidated_tickets)
    return jsonable_encoder(response_data)

@router.get("/api/{resource}/{item_id}")
def get_resource(resource: str, item_id: str, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "read")
    model = RESOURCE_MODELS[resource]
    pk = RESOURCE_PK[resource]
    lookup: Any = item_id
    if isinstance(inspect(model).columns[pk].type, Integer):
        try:
            lookup = int(item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Record ID must be an integer.")
    row = db.get(model, lookup)
    if not row or (actor["role"] != "admin" and not bool(getattr(row, "active", True))):
        raise HTTPException(status_code=404, detail="Record not found.")
    if actor["role"] == "agent" and resource == "tickets" and not _agent_can_access_ticket(db, row, actor):
        raise HTTPException(status_code=403, detail="This ticket is not assigned to your Agent account.")
    if actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        if resource == "tickets" and row.customer_id != cust_id:
            raise HTTPException(status_code=403, detail="You can only view your own tickets.")
        if resource == "assets" and row.customer_id != cust_id:
            raise HTTPException(status_code=403, detail="You can only view your own assets.")
        if resource == "services" and not row.customer_visible:
            raise HTTPException(status_code=404, detail="Service not found.")
    return jsonable_encoder(serialize_row(db, resource, row))

@router.put("/api/{resource}/{item_id}")
def update_resource(resource: str, item_id: str, payload: dict[str, Any], request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "update")
    model = RESOURCE_MODELS[resource]
    pk = RESOURCE_PK[resource]
    lookup: Any = item_id
    if isinstance(inspect(model).columns[pk].type, Integer):
        try:
            lookup = int(item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Record ID must be an integer.")
    row = db.get(model, lookup)
    if not row or (actor["role"] != "admin" and not bool(getattr(row, "active", True))):
        raise HTTPException(status_code=404, detail="Record not found.")
    if actor["role"] == "customer" and resource == "tickets" and row.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only access your own tickets.")
    if actor["role"] == "customer" and resource == "tickets":
        allowed_customer_fields = {"subject", "description", "priority", "attachment_reference"}
        payload = {key: value for key, value in payload.items() if key in allowed_customer_fields}
        if not payload:
            raise HTTPException(status_code=422, detail="You can edit only the Subject, Description, Priority and Attachment Reference.")
    if actor["role"] == "agent" and resource == "tickets":
        if not _agent_can_access_ticket(db, row, actor):
            raise HTTPException(status_code=403, detail="This ticket is not assigned to your Agent account or Support Team.")
        if not _agent_is_explicitly_assigned(db, row, actor):
            raise HTTPException(status_code=403, detail="Only the Agent explicitly assigned to this ticket can change its status.")
        unexpected_fields = set(payload) - {"status"}
        if unexpected_fields:
            raise HTTPException(status_code=403, detail="Agents may change only the ticket status. Priority, assignment, due date and ticket details are Admin-only.")
        if "status" not in payload:
            raise HTTPException(status_code=422, detail="Choose a ticket status.")
        status_aliases = {
            "open": "Open",
            "in progress": "In progress",
            "in-progress": "In progress",
            "pending": "Pending Customer",
            "pending customer": "Pending Customer",
            "pending_customer": "Pending Customer",
            "waiting for customer": "Pending Customer",
            "resolved": "Resolved",
            "closed": "Closed",
        }
        selected_status = str(payload.get("status") or "").strip().casefold()
        if selected_status not in status_aliases:
            raise HTTPException(status_code=422, detail="Status must be Open, In progress, Pending Customer, Resolved, or Closed.")
        payload = {"status": status_aliases[selected_status]}
    if resource == "plans":
        normalize_plan_type(payload, row)
    if resource == "users":
        _prepare_user_custom_selections(db, payload, row)
    user_team_ids = _parse_user_team_ids(db, payload, row) if resource == "users" else None
    previous_user_team_ids = _user_team_ids(db, row) if resource == "users" else []
    if resource == "plans":
        plan_data = clean_payload(resource, payload, row)
        if "plan_name" in plan_data:
            plan_data["plan_name"] = str(plan_data.get("plan_name") or "").strip()
        if "plan_code" in plan_data:
            plan_data["plan_code"] = str(plan_data.get("plan_code") or "").strip().upper() or None
        plan_data["plan_type"] = str(plan_data.get("plan_type") or row.plan_type or "Standard").strip()
        validate_plan_unique_fields(db, {**{
            "plan_name": plan_data.get("plan_name", row.plan_name),
            "plan_code": plan_data.get("plan_code", row.plan_code),
        }}, current_plan_id=row.plan_id)
        payload = plan_data
    before_snapshot = _snapshot(row)
    if resource == "users":
        before_snapshot["team_ids"] = _user_team_ids(db, row)
    before_label = _entity_label(resource, row, db)
    service_codes = payload.get("service_codes") if resource in {"teams", "assets"} else None
    if resource == "teams" and service_codes is not None:
        if isinstance(service_codes, str):
            service_codes = [service_codes] if service_codes else []
        selected_codes = [str(code) for code in service_codes if code]
        if len(selected_codes) != 1:
            raise HTTPException(status_code=422, detail="Choose exactly one Service Catalog item for this Support Team.")
        if not db.get(ServiceCatalog, selected_codes[0]):
            raise HTTPException(status_code=422, detail="Select an existing Service Catalog item for this Support Team.")
    old_customer_email = row.email if resource == "customers" else None
    previous_ticket_status = row.status if resource == "tickets" else None
    previous_ticket_assigned = row.assigned if resource == "tickets" else None
    previous_ticket_due_date = row.due_date if resource == "tickets" else None
    data = clean_payload(resource, payload, row)
    validate_contact_fields(resource, data)
    validate_record_dates(resource, data, row)
    if resource == "users":
        data["team_id"] = user_team_ids[0] if user_team_ids else None
        if str(data.get("role", row.role)).lower() != "agent":
            data["request_type_code"] = None
    if resource == "tickets":
        sync_ticket_contract_links(db, data, row)
    if resource == "tickets" and actor["role"] != "customer":
        validate_ticket_assignment(db, data, row)
    validate_customer_relationships(db, resource, data, row)
    if resource == "contacts":
        validate_primary_contact(db, data, row)
    changed_fields = [key for key, value in data.items() if getattr(row, key, None) != value]
    if resource == "users" and payload.get("password"):
        changed_fields.append("password (updated)")
    for key, value in data.items():
        setattr(row, key, value)
    if resource == "customers":
        linked_user = None
        if old_customer_email:
            linked_user = db.scalar(select(User).where(
                func.lower(User.email) == old_customer_email.lower(), User.role == "customer"))
        if linked_user:
            linked_user.fullname = str(row.contact_name or row.customer_name).strip() or row.customer_name
            linked_user.email = (row.email or old_customer_email).strip().lower()
            linked_user.active = bool(row.active)
        elif row.email:
            # Older Customer profiles may pre-date automatic login creation.
            # Link them on the next save rather than leaving the two modules apart.
            ensure_customer_login_account(db, row, actor, create_if_missing=True)
    if resource == "tickets":
        if actor["role"] == "customer" and str(previous_ticket_status or "").strip().lower() in {"resolved", "closed"}:
            row.status = "Open"
        now_utc = datetime.utcnow()
        if str(previous_ticket_status or "").strip().casefold() != str(row.status or "").strip().casefold():
            row.status_changed_at = now_utc
        row.updated_at = now_utc
    if resource == "users":
        db.query(UserTeamMembership).filter(UserTeamMembership.user_id == row.user_id).delete(synchronize_session=False)
        for team_id in user_team_ids or []:
            db.add(UserTeamMembership(user_id=row.user_id, team_id=team_id))
        db.flush()
        for team_id in set(previous_user_team_ids + (user_team_ids or [])):
            refresh_team_member_label(db, team_id)
    if resource == "teams":
        apply_team_members(db, row, data.get("member", row.member or ""))
    if resource == "teams" and service_codes is not None:
        db.query(TeamServiceLink).filter(TeamServiceLink.team_id == row.team_id).delete(synchronize_session=False)
        for code in dict.fromkeys(str(code) for code in service_codes if code):
            if db.get(ServiceCatalog, code):
                db.add(TeamServiceLink(team_id=row.team_id, code_id=code))
        row.code_id = str(next((code for code in service_codes if code), "")) or None
    if resource == "assets" and service_codes is not None:
        db.query(AssetServiceLink).filter(AssetServiceLink.asset_id == row.asset_id).delete(synchronize_session=False)
        for code in dict.fromkeys(str(code) for code in service_codes if code):
            if db.get(ServiceCatalog, code):
                db.add(AssetServiceLink(asset_id=row.asset_id, code_id=code))
    if resource == "services" and "mapped_team" in data:
        db.query(TeamServiceLink).filter(TeamServiceLink.code_id == row.code_id).delete(synchronize_session=False)
        if row.mapped_team:
            _ensure_service_mapped_team(db, row)
    if resource == "users" and row.role == "customer":
        cust = db.scalar(select(Customer).where(func.lower(Customer.email) == row.email.lower()))
        if not cust:
            db.add(Customer(customer_name=row.fullname, email=row.email, contact_name=row.fullname))
        else:
            cust.customer_name = row.fullname
            cust.contact_name = row.fullname
    try:
        after_snapshot = _snapshot(row)
        if resource == "users":
            after_snapshot["team_ids"] = user_team_ids or []
        change_map = _diff(before_snapshot, after_snapshot)
        change_map = {k: v for k, v in change_map.items() if k not in {"updated_at", "password_hash"}}
        detail = f"Updated {resource} record {before_label}" + (f"; {_change_summary(change_map)}" if change_map else "; no field values changed")
        log_action(db, actor, "UPDATE", resource, detail, request=request, entity_id=getattr(row, RESOURCE_PK[resource]), entity_label=_entity_label(resource, row, db), changes=change_map)
        db.commit()
        db.refresh(row)
        if resource == "tickets":
            assignment_changed = previous_ticket_assigned != row.assigned
            status_changed = previous_ticket_status != row.status
            notification_events: list[tuple[str, str]] = []
            if assignment_changed:
                notification_events.append(("ticket_assigned" if row.assigned else "unassigned_team_queue", ""))
            if status_changed:
                old_status = str(previous_ticket_status or "").strip().lower()
                new_status = str(row.status or "").strip().lower()
                if new_status in {"pending customer", "pending_customer", "waiting for customer"}:
                    status_event = "pending_customer"
                elif new_status in {"customer accepted resolution", "resolution accepted by customer"}:
                    status_event = "customer_accepted_resolution"
                elif new_status in {"resolved", "resolution accepted"}:
                    status_event = "resolved"
                elif new_status == "closed":
                    status_event = "ticket_closed"
                elif old_status in {"resolved", "closed"} and new_status in {"open", "in progress", "in-progress", "new"}:
                    status_event = "ticket_reopened"
                else:
                    status_event = "status_changed"
                notification_events.append((status_event, f"Previous status: {previous_ticket_status or '—'}"))
            if change_map and not assignment_changed and not status_changed:
                notification_events.append(("ticket_updated", _change_summary(change_map)))
            if notification_events:
                background_tasks.add_task(run_ticket_notifications, row.ticket_id, notification_events, dict(actor))
        elif resource == "customers" and actor.get("role") == "admin" and change_map:
            customer_user = db.scalar(select(User).where(
                User.role == "customer", User.active.is_(True), func.lower(User.email) == str(row.email or "").lower()))
            if customer_user:
                db.add(NotificationItem(user_id=customer_user.user_id, event_key="customer_profile_updated",
                    title="Your customer profile was updated",
                    message="An administrator updated your customer profile information.",
                    actor_name=actor.get("fullname"), actor_role=actor.get("role")))
                db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=integrity_error_message(exc, resource, "update")) from exc
    return jsonable_encoder(serialize_row(db, resource, row))

@router.post("/api/customers/{customer_id}/toggle-active")
def toggle_customer_active(customer_id: int, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    customer.active = not bool(customer.active)
    linked_user = None
    if customer.email:
        linked_user = db.scalar(select(User).where(User.role == "customer", func.lower(User.email) == customer.email.lower()))
    if linked_user:
        linked_user.active = customer.active
    status_label = "activated" if customer.active else "deactivated"
    log_action(db, actor, "ACTIVATE" if customer.active else "DEACTIVATE", "Customers",
               f"{status_label.title()} customer {customer.customer_name}", request=request,
               entity_id=customer.customer_id, entity_label=customer.customer_name,
               changes={"active": {"from": not customer.active, "to": customer.active}})
    db.commit()
    db.refresh(customer)
    return {"customer_id": customer.customer_id, "active": bool(customer.active), "message": f"Customer {status_label} successfully."}

@router.post("/api/users/{user_id}/toggle-active")
def toggle_user_active(user_id: int, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role not in {"agent", "admin"}:
        raise HTTPException(status_code=400, detail="This action is available for Agent and Admin accounts. Customer status is managed from Customers.")

    old_active = bool(user.active)
    role_label = "Admin" if user.role == "admin" else "Agent"
    if old_active and user.role == "admin":
        if int(actor.get("user_id") or 0) == user.user_id:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own Admin account.")
        # Lock the active Admin rows while checking the count. This prevents two
        # concurrent requests from deactivating the final Admin accounts together.
        active_admins = db.scalars(
            select(User).where(
                User.role == "admin",
                User.active.is_(True),
            ).order_by(User.user_id).with_for_update()
        ).all()
        if len(active_admins) <= 1:
            raise HTTPException(status_code=400, detail="You cannot deactivate the last active Admin account.")

    user.active = not old_active
    status_label = "activated" if user.active else "deactivated"
    log_action(db, actor, "ACTIVATE" if user.active else "DEACTIVATE", "User Management",
               f"{status_label.title()} {role_label} {user.fullname}", request=request,
               entity_id=user.user_id, entity_label=user.fullname,
               changes={"active": {"from": old_active, "to": bool(user.active)}})
    db.commit()
    return {
        "user_id": user.user_id,
        "role": user.role,
        "active": bool(user.active),
        "message": f"{role_label} {status_label} successfully.",
    }

@router.post("/api/{resource}/{item_id}/toggle-active")
def toggle_resource_active(
    resource: str,
    item_id: str,
    request: Request,
    db: Session = Depends(get_db),
    actor: dict[str, Any] = Depends(get_actor),
) -> dict[str, Any]:
    """Activate/deactivate a record without deleting its history or relationships."""
    admin_only(actor)
    supported = {"tickets", "contacts", "projects", "plans", "services", "teams", "contracts", "assets"}
    if resource not in supported:
        raise HTTPException(status_code=404, detail="This resource does not support activation controls.")
    model = RESOURCE_MODELS[resource]
    pk = RESOURCE_PK[resource]
    lookup: Any = item_id
    if isinstance(inspect(model).columns[pk].type, Integer):
        try:
            lookup = int(item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Record ID must be an integer.")
    row = db.get(model, lookup)
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if not hasattr(row, "active"):
        raise HTTPException(status_code=409, detail="Activation is not configured for this record.")

    old_active = bool(row.active)
    row.active = not old_active
    new_active = bool(row.active)
    status_label = "activated" if new_active else "deactivated"
    label = _entity_label(resource, row, db)
    log_action(
        db, actor,
        "ACTIVATE" if new_active else "DEACTIVATE",
        resource.replace("-", " ").title(),
        f"{status_label.title()} {resource.rstrip('s')} {label}",
        request=request,
        entity_id=str(getattr(row, pk)),
        entity_label=label,
        changes={"active": {"from": old_active, "to": new_active}},
    )
    db.commit()
    db.refresh(row)
    return {
        "resource": resource,
        "id": getattr(row, pk),
        "active": new_active,
        "message": f"{resource.rstrip('s').replace('-', ' ').title()} {status_label} successfully.",
    }

@router.delete("/api/{resource}/{item_id}")
def delete_resource(resource: str, item_id: str, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "delete")
    model = RESOURCE_MODELS[resource]
    pk = RESOURCE_PK[resource]
    lookup: Any = item_id
    if isinstance(inspect(model).columns[pk].type, Integer):
        try:
            lookup = int(item_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Record ID must be an integer.")
    row = db.get(model, lookup)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")
    deleted_snapshot = _snapshot(row)
    deleted_label = _entity_label(resource, row, db)
    related_ticket_count = 0
    deleted_team_ids: list[int] = []
    related_customer_counts: dict[str, int] = {}
    if resource == "customers":
        # Delete the complete customer-owned record tree explicitly. Existing
        # PostgreSQL databases may still have RESTRICT foreign keys from an
        # earlier schema, so relying only on ON DELETE CASCADE is not enough.
        customer_id = row.customer_id
        project_ids = db.scalars(
            select(Project.project_id).where(Project.customer_id == customer_id)
        ).all()
        contact_ids = db.scalars(
            select(Contact.contact_id).where(Contact.customer_id == customer_id)
        ).all()
        contract_ids = db.scalars(
            select(Contract.contract_id).where(
                or_(Contract.customer_id == customer_id, Contract.project_id.in_(project_ids))
            )
        ).all()
        asset_ids = db.scalars(
            select(Asset.asset_id).where(
                or_(Asset.customer_id == customer_id, Asset.project_id.in_(project_ids))
            )
        ).all()

        ticket_conditions = [Ticket.customer_id == customer_id]
        if project_ids:
            ticket_conditions.append(Ticket.project_id.in_(project_ids))
        if contact_ids:
            ticket_conditions.append(Ticket.contact_id.in_(contact_ids))
        if contract_ids:
            ticket_conditions.append(Ticket.contract_id.in_(contract_ids))
        if asset_ids:
            ticket_conditions.append(Ticket.asset_id.in_(asset_ids))
        ticket_ids = db.scalars(
            select(Ticket.ticket_id).where(or_(*ticket_conditions))
        ).all()

        # A customer portal account is linked to its organization by email.
        customer_users = []
        if row.email:
            customer_users = db.scalars(
                select(User).where(
                    func.lower(User.role) == "customer",
                    func.lower(User.email) == row.email.strip().lower(),
                )
            ).all()
        customer_user_ids = [user.user_id for user in customer_users]

        reply_conditions = []
        if ticket_ids:
            reply_conditions.append(TicketReply.ticket_id.in_(ticket_ids))
        if customer_user_ids:
            # Ticket replies RESTRICT user deletion; also remove replies this
            # customer account may have posted on another ticket.
            reply_conditions.append(TicketReply.user_id.in_(customer_user_ids))
        reply_count = 0
        if reply_conditions:
            reply_query = db.query(TicketReply).filter(or_(*reply_conditions))
            reply_count = reply_query.count()
            reply_query.delete(synchronize_session=False)

        # Keep notification and email-delivery history for other users while
        # clearing references to tickets that are being permanently removed.
        if ticket_ids:
            db.query(NotificationItem).filter(NotificationItem.ticket_id.in_(ticket_ids)).update(
                {"ticket_id": None}, synchronize_session=False
            )
            db.query(EmailDelivery).filter(EmailDelivery.ticket_id.in_(ticket_ids)).update(
                {"ticket_id": None}, synchronize_session=False
            )
            db.query(Ticket).filter(Ticket.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)

        if asset_ids:
            db.query(AssetServiceLink).filter(AssetServiceLink.asset_id.in_(asset_ids)).delete(
                synchronize_session=False
            )
            db.query(Asset).filter(Asset.asset_id.in_(asset_ids)).delete(synchronize_session=False)
        if contract_ids:
            db.query(Contract).filter(Contract.contract_id.in_(contract_ids)).delete(synchronize_session=False)
        if project_ids:
            db.query(Project).filter(Project.project_id.in_(project_ids)).delete(synchronize_session=False)
        if contact_ids:
            db.query(Contact).filter(Contact.contact_id.in_(contact_ids)).delete(synchronize_session=False)

        # Remove the matching customer login account(s), if one exists.
        for customer_user in customer_users:
            db.query(UserTeamMembership).filter(
                UserTeamMembership.user_id == customer_user.user_id
            ).delete(synchronize_session=False)
            db.query(UserNotificationPreference).filter(
                UserNotificationPreference.user_id == customer_user.user_id
            ).delete(synchronize_session=False)
            db.query(NotificationItem).filter(
                NotificationItem.user_id == customer_user.user_id
            ).delete(synchronize_session=False)
            db.delete(customer_user)

        related_customer_counts = {
            "contacts": len(contact_ids),
            "projects": len(project_ids),
            "contracts": len(contract_ids),
            "assets": len(asset_ids),
            "tickets": len(ticket_ids),
            "ticket replies": reply_count,
            "customer login accounts": len(customer_user_ids),
        }
    if resource == "users":
        deleted_team_ids = _user_team_ids(db, row)
        deleted_snapshot["team_ids"] = deleted_team_ids
        ticket_conditions = [Ticket.created_by_id == row.user_id]
        if row.role == "agent":
            ticket_conditions.append(func.lower(Ticket.assigned) == row.fullname.strip().lower())
        elif row.role == "customer" and row.email:
            linked_customer = db.scalar(select(Customer).where(func.lower(Customer.email) == row.email.lower()))
            if linked_customer:
                ticket_conditions.append(Ticket.customer_id == linked_customer.customer_id)
        related_tickets = db.scalars(select(Ticket).where(or_(*ticket_conditions))).all()
        related_ticket_ids = [ticket.ticket_id for ticket in related_tickets]
        related_ticket_count = len(related_ticket_ids)
        # Ticket replies reference users with RESTRICT, so remove affected replies first.
        db.query(TicketReply).filter(TicketReply.user_id == row.user_id).delete(synchronize_session=False)
        if related_ticket_ids:
            db.query(TicketReply).filter(TicketReply.ticket_id.in_(related_ticket_ids)).delete(synchronize_session=False)
            db.query(NotificationItem).filter(NotificationItem.ticket_id.in_(related_ticket_ids)).update(
                {"ticket_id": None}, synchronize_session=False)
            for ticket in related_tickets:
                db.delete(ticket)
        db.query(UserTeamMembership).filter(UserTeamMembership.user_id == row.user_id).delete(synchronize_session=False)
        db.query(UserNotificationPreference).filter(UserNotificationPreference.user_id == row.user_id).delete(synchronize_session=False)
        db.query(NotificationItem).filter(NotificationItem.user_id == row.user_id).delete(synchronize_session=False)
    db.delete(row)
    if resource == "users":
        db.flush()
        for team_id in deleted_team_ids:
            refresh_team_member_label(db, team_id)
    delete_changes = {k: {"from": v, "to": None} for k, v in deleted_snapshot.items() if k not in {"created_at", "updated_at"}}
    detail = f"Deleted {resource} record {deleted_label}"
    if resource == "users":
        detail += f"; also deleted {related_ticket_count} related ticket(s) and their replies"
    elif resource == "customers":
        detail += "; also deleted " + ", ".join(
            f"{count} {label}" for label, count in related_customer_counts.items()
        )
    log_action(db, actor, "DELETE", resource, detail, request=request, entity_id=item_id, entity_label=deleted_label, changes=delete_changes)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This record is still referenced by other records and cannot be deleted.") from exc
    if resource == "users":
        return {"message": f"User deleted successfully. {related_ticket_count} related ticket(s) and their replies were also deleted."}
    if resource == "customers":
        summary = ", ".join(
            f"{count} {label}" for label, count in related_customer_counts.items()
        )
        return {"message": f"Customer deleted successfully. Also deleted: {summary}."}
    return {"message": "Record deleted."}

__all__ = ["router"]
