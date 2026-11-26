"""Dashboard API endpoints."""
from __future__ import annotations
from ..common import *
from ..config import *
from ..database import *
from ..models import *
from ..security import *
from ..resource_service import *

router = APIRouter()

@router.get("/api/lookups")
def lookups(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    customers = db.scalars(select(Customer).where(Customer.active.is_(True)).order_by(Customer.customer_name)).all()
    if actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        customers = [c for c in customers if c.customer_id == cust_id]
        projects = db.scalars(select(Project).where(Project.customer_id == cust_id, Project.active.is_(True)).order_by(Project.project_name)).all() if cust_id else []
        assets = db.scalars(select(Asset).where(Asset.customer_id == cust_id, Asset.active.is_(True)).order_by(Asset.asset_name)).all() if cust_id else []
        contracts = db.scalars(select(Contract).where(Contract.customer_id == cust_id, Contract.active.is_(True)).order_by(Contract.contract_name)).all() if cust_id else []
        services = db.scalars(select(ServiceCatalog).where(ServiceCatalog.customer_visible.is_(True), ServiceCatalog.active.is_(True)).order_by(ServiceCatalog.request_order)).all()
        users = []
        teams = []
    else:
        projects = db.scalars(select(Project).where(Project.active.is_(True)).order_by(Project.project_name)).all()
        assets = db.scalars(select(Asset).where(Asset.active.is_(True)).order_by(Asset.asset_name)).all()
        contracts = db.scalars(select(Contract).where(Contract.active.is_(True)).order_by(Contract.contract_name)).all()
        services = db.scalars(select(ServiceCatalog).where(ServiceCatalog.active.is_(True)).order_by(ServiceCatalog.request_order)).all()
        users = db.scalars(select(User).where(User.active.is_(True)).order_by(User.fullname)).all()
        teams = db.scalars(select(Team).where(Team.active.is_(True)).order_by(Team.team_name)).all() if actor["role"] == "admin" else []
    # Support Plans are reusable catalog records, not owned by one customer or contract.
    plans = db.scalars(select(Plan).where(Plan.active.is_(True)).order_by(Plan.plan_name)).all()
    contacts_query = select(Contact).where(Contact.active.is_(True)).order_by(Contact.fullname)
    if actor["role"] == "customer":
        contacts_query = contacts_query.where(Contact.customer_id == actor_customer_id(db, actor))
    contacts = db.scalars(contacts_query).all()
    return {"customers": [serialize_row(db, "customers", x) for x in customers],
            "projects": [serialize_row(db, "projects", x) for x in projects],
            "contracts": [serialize_row(db, "contracts", x) for x in contracts],
            "plans": [serialize_row(db, "plans", x) for x in plans],
            "assets": [serialize_row(db, "assets", x) for x in assets],
            "services": [serialize_row(db, "services", x) for x in services],
            "contacts": [serialize_row(db, "contacts", x) for x in contacts],
            "users": [serialize_row(db, "users", x) for x in users],
            "teams": [serialize_row(db, "teams", x) for x in teams]}

@router.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    """Live dashboard data scoped to Admin, the Agent's team, or the Customer."""
    base_query = select(Ticket).order_by(Ticket.updated_at.desc())
    # Dashboard activity totals represent active records only. Admin list pages
    # still receive inactive records so they can be reactivated when needed.
    all_rows = db.scalars(base_query).all()
    active_ticket_rows = [row for row in all_rows if bool(row.active)]
    tickets = scope_rows(db, "tickets", active_ticket_rows, actor)
    today = yangon_today()
    active_statuses = {"open", "new", "in progress", "in-progress", "pending customer", "pending_customer", "waiting for customer"}
    open_count = sum(1 for t in tickets if str(t.status or "").strip().lower() in {"open", "new"})
    in_progress_count = sum(1 for t in tickets if str(t.status or "").strip().lower() in {"in progress", "in-progress"})
    waiting_count = sum(1 for t in tickets if "pending" in str(t.status or "").lower() or "waiting" in str(t.status or "").lower())
    resolved_count = sum(1 for t in tickets if str(t.status or "").strip().lower() in {"resolved", "closed"})
    at_risk = sum(1 for t in tickets if t.due_date and t.due_date <= today + timedelta(days=2)
                  and str(t.status or "").strip().lower() not in {"resolved", "closed"})
    assigned_to_me = 0
    if actor["role"] == "agent":
        assigned_to_me = sum(1 for t in tickets if t.assigned and t.assigned.casefold() == str(actor["fullname"]).casefold())
    customer_id = actor_customer_id(db, actor) if actor["role"] == "customer" else None
    def active_record_count(model: type[Base], primary_key: str) -> int:
        """Count active records for dashboard KPIs, excluding deactivated rows."""
        pk_column = getattr(model, primary_key)
        return int(db.scalar(
            select(func.count(pk_column)).where(model.active.is_(True))
        ) or 0)

    if actor["role"] == "customer":
        available_services = db.scalar(select(func.count(ServiceCatalog.code_id)).where(ServiceCatalog.customer_visible.is_(True), ServiceCatalog.active.is_(True))) or 0
        customers_total = projects_total = assets_total = contracts_total = users_total = 0
    else:
        available_services = 0
        customers_total = active_record_count(Customer, "customer_id")
        projects_total = active_record_count(Project, "project_id")
        assets_total = active_record_count(Asset, "asset_id")
        contracts_total = active_record_count(Contract, "contract_id")
        users_total = active_record_count(User, "user_id")

    # The Admin dashboard compares active and deactivated rows across all
    # requested modules. Deactivation moves a record from Active to Inactive;
    # it does not erase its database history.
    module_overview: list[dict[str, Any]] = []
    if actor["role"] == "admin":
        module_definitions = [
            ("Tickets", "tickets", Ticket, "ticket_id"),
            ("Customers", "customers", Customer, "customer_id"),
            ("Projects", "projects", Project, "project_id"),
            ("Contracts", "contracts", Contract, "contract_id"),
            ("Support Plans", "plans", Plan, "plan_id"),
            ("Service Catalog", "services", ServiceCatalog, "code_id"),
            ("Contacts", "contacts", Contact, "contact_id"),
            ("Assets", "assets", Asset, "asset_id"),
        ]
        for label, resource, model, primary_key in module_definitions:
            pk_column = getattr(model, primary_key)
            total = int(db.scalar(select(func.count(pk_column))) or 0)
            active = active_record_count(model, primary_key)
            module_overview.append({
                "label": label,
                "resource": resource,
                "active": active,
                "inactive": max(total - active, 0),
                "total": total,
            })

    # This breakdown is calculated from the same role-scoped ticket rows as the
    # dashboard cards, so the chart never displays sample or unrelated data.
    status_labels = ["Open", "In Progress", "Pending Customer", "Resolved", "Closed", "Other"]
    status_counts = {label: 0 for label in status_labels}
    trend_dates = [today - timedelta(days=offset) for offset in reversed(range(7))]
    daily_counts = {day: {label: 0 for label in status_labels} for day in trend_dates}

    def dashboard_status_label(value: str | None) -> str:
        status_value = str(value or "").strip().casefold().replace("_", " ").replace("-", " ")
        if status_value in {"open", "new"}:
            return "Open"
        if status_value == "in progress":
            return "In Progress"
        if "pending" in status_value or "waiting" in status_value:
            return "Pending Customer"
        if status_value == "resolved":
            return "Resolved"
        if status_value == "closed":
            return "Closed"
        return "Other"

    for ticket in tickets:
        status_label = dashboard_status_label(ticket.status)
        status_counts[status_label] += 1
        created_local = _as_yangon_datetime(ticket.created_at)
        if created_local and created_local.date() in daily_counts:
            daily_counts[created_local.date()][status_label] += 1

    daily_breakdown = []
    for day in trend_dates:
        day_row = {"date": day.isoformat(), "label": day.strftime("%a"), **daily_counts[day]}
        day_row["total"] = sum(daily_counts[day].values())
        daily_breakdown.append(day_row)

    # Rolling 12-month activity, using the same role-scoped ticket rows.
    def dashboard_month_start(offset: int) -> date:
        month_index = today.year * 12 + (today.month - 1) + offset
        year, zero_based_month = divmod(month_index, 12)
        return date(year, zero_based_month + 1, 1)

    trend_months = [dashboard_month_start(offset) for offset in range(-11, 1)]
    monthly_counts = {
        month: {label: 0 for label in status_labels}
        for month in trend_months
    }

    for ticket in tickets:
        created_local = _as_yangon_datetime(ticket.created_at)
        if not created_local:
            continue
        created_month = created_local.date().replace(day=1)
        if created_month in monthly_counts:
            status_label = dashboard_status_label(ticket.status)
            monthly_counts[created_month][status_label] += 1

    monthly_breakdown = []
    for month in trend_months:
        month_row = {
            "date": month.isoformat(),
            "label": month.strftime("%b %y"),
            **monthly_counts[month],
        }
        month_row["total"] = sum(monthly_counts[month].values())
        monthly_breakdown.append(month_row)

    agents_overview: list[dict[str, Any]] = []
    customers_overview: list[dict[str, Any]] = []
    if actor["role"] == "admin":
        agent_counts: dict[str, dict[str, int]] = {}
        for ticket in active_ticket_rows:
            agent_key = str(ticket.assigned or "").strip().casefold()
            if not agent_key:
                continue
            counts = agent_counts.setdefault(agent_key, {"total": 0, "active": 0, "resolved": 0})
            counts["total"] += 1
            normalized_status = str(ticket.status or "").strip().casefold().replace("_", " ").replace("-", " ")
            if normalized_status in {"resolved", "closed"}:
                counts["resolved"] += 1
            else:
                counts["active"] += 1

        agent_users = db.scalars(
            select(User).where(User.role == "agent", User.active.is_(True)).order_by(User.fullname)
        ).all()
        for agent_user in agent_users:
            agent_key = str(agent_user.fullname or "").strip().casefold()
            counts = agent_counts.get(agent_key, {"total": 0, "active": 0, "resolved": 0})
            team_ids = _user_team_ids(db, agent_user)
            team_names = [team.team_name for team_id in team_ids if (team := db.get(Team, team_id))]
            agents_overview.append({
                "name": agent_user.fullname,
                "team": ", ".join(team_names) if team_names else "No support team",
                "total_tickets": counts["total"],
                "active_tickets": counts["active"],
                "resolved_tickets": counts["resolved"],
            })
        agents_overview.sort(key=lambda row: (-row["total_tickets"], row["name"].casefold()))

        customer_counts: dict[int, dict[str, int]] = {}
        for ticket in active_ticket_rows:
            counts = customer_counts.setdefault(ticket.customer_id, {"total": 0, "open": 0})
            counts["total"] += 1
            normalized_status = str(ticket.status or "").strip().casefold().replace("_", " ").replace("-", " ")
            if normalized_status not in {"resolved", "closed"}:
                counts["open"] += 1

        customer_users = db.scalars(
            select(Customer).where(Customer.active.is_(True)).order_by(Customer.customer_name)
        ).all()
        for customer in customer_users:
            counts = customer_counts.get(customer.customer_id, {"total": 0, "open": 0})
            customers_overview.append({
                "name": customer.customer_name,
                "total_tickets": counts["total"],
                "open_tickets": counts["open"],
            })
        customers_overview.sort(key=lambda row: (-row["total_tickets"], row["name"].casefold()))

    return {
        "role": actor["role"], "tickets_total": len(tickets), "open_tickets": open_count,
        "in_progress": in_progress_count, "waiting": waiting_count, "resolved": resolved_count,
        "assigned_to_me": assigned_to_me, "sla_at_risk": at_risk,
        "customers": customers_total, "projects": projects_total, "assets": assets_total,
        "contracts": contracts_total, "users": users_total,
        "available_services": available_services,
        "status_breakdown": [{"label": label, "count": status_counts[label]} for label in status_labels],
        "daily_breakdown": daily_breakdown,
        "monthly_breakdown": monthly_breakdown,
        "agents_overview": agents_overview,
        "customers_overview": customers_overview,
        "module_overview": module_overview,
        "refreshed_at": datetime.now(ZoneInfo("Asia/Yangon")).isoformat(),
    }

@router.get("/api/role-permissions")
def list_role_permissions(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    admin_only(actor)
    rows = db.scalars(select(RolePermission).order_by(RolePermission.role_key)).all()
    return [serialize_row(db, "role-permissions", r) for r in rows]

@router.post("/api/role-permissions")
def create_role_permission(payload: RoleBody, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    key = payload.role_key.strip()
    row = db.scalar(select(RolePermission).where(func.lower(RolePermission.role_key) == key.lower()))
    if row:
        row.description = payload.description
        row.permissions_json = json.dumps(payload.permissions)
        action = "UPDATE"
    else:
        row = RolePermission(role_key=key, description=payload.description, permissions_json=json.dumps(payload.permissions))
        db.add(row)
        action = "CREATE"
    log_action(db, actor, action, "Role permissions", f"Saved role {key}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not save role permissions.")
    db.refresh(row)
    return serialize_row(db, "role-permissions", row)

__all__ = ["router"]
