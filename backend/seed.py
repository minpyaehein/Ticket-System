"""Seed logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .models import *
from .security import *
from .email_service import *

def seed_database() -> None:
    db = SessionLocal()
    try:
        if db.get(SystemSetting, "initial_demo_seed_completed") is not None:
            return
        pristine_database = all(
            (db.scalar(select(func.count(model))) or 0) == 0
            for model in (User.user_id, Customer.customer_id, ServiceCatalog.code_id, Ticket.ticket_id)
        )
        if pristine_database:
            svc_rows = [
                ServiceCatalog(code_id="SRV-001", name="Database Support", category="Incident", request_order=1, customer_visible=True, asset_requirement="Optional asset", mapped_team="Database Team", auto_assign=True, assignment_method="Round robin", description="Database connection, performance and availability support"),
                ServiceCatalog(code_id="SRV-002", name="Application Support", category="Service Request", request_order=2, customer_visible=True, asset_requirement="Optional asset", mapped_team="Service Desk", auto_assign=True, assignment_method="Least assigned", description="Application troubleshooting and access"),
                ServiceCatalog(code_id="SRV-003", name="Hardware", category="Hardware", request_order=3, customer_visible=True, asset_requirement="Asset required", mapped_team="Infrastructure", auto_assign=False, assignment_method="Manual assignment", description="Workstation, server and equipment support"),
                ServiceCatalog(code_id="SRV-004", name="Network", category="Network", request_order=4, customer_visible=True, asset_requirement="Optional asset", mapped_team="Infrastructure", auto_assign=True, assignment_method="Team default", description="Network, VPN and connectivity issues"),
            ]
            db.add_all(svc_rows)
            db.flush()
            customers = [
                Customer(customer_name="Nova Manufacturing", email="nova@example.com", phone="+95 9 450 000 001", address="Yangon, Myanmar", contact_name="Aung Aung"),
                Customer(customer_name="Summit Trading", email="summit@example.com", phone="+95 9 450 000 002", address="Yangon, Myanmar", contact_name="May Thu"),
                Customer(customer_name="Orchid Healthcare", email="orchid@example.com", phone="+95 9 450 000 003", address="Mandalay, Myanmar", contact_name="Su Su"),
            ]
            db.add_all(customers)
            plans = [
                Plan(plan_code="SLA-STD-01", plan_name="Standard", plan_type="Standard", response_sla="4 hours", resolution_sla="1 business day", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="Business hours", time_zone="Asia/Yangon", business_start_hour="09:00", business_end_hour="17:00", working_days="Monday-Friday", escalation_level="Level 1", remote_support="Included", onsite_support="Excluded", description="Standard business-hours support"),
                Plan(plan_code="SLA-PRM-01", plan_name="Premium", plan_type="Premium", response_sla="1 hour", resolution_sla="8 hours", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="24×7 calendar", time_zone="Asia/Yangon", business_start_hour="00:00", business_end_hour="23:59", working_days="Monday-Sunday", escalation_level="Level 2", remote_support="Included", onsite_support="Included", description="Priority 24×7 support"),
                Plan(plan_code="SLA-ENT-01", plan_name="Enterprise", plan_type="Enterprise", response_sla="30 minutes", resolution_sla="4 hours", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="24×7 calendar", time_zone="Asia/Yangon", business_start_hour="00:00", business_end_hour="23:59", working_days="Monday-Sunday", escalation_level="Level 3", remote_support="Included", onsite_support="Included", description="Business critical enterprise support"),
            ]
            db.add_all(plans)
            db.flush()
            projects = [
                Project(project_code="PRJ-2026-001", customer_id=customers[0].customer_id, project_name="General Support Project", project_manager="Aye Aye", status="Active", start_date=date(2026, 1, 12), description="General service desk support"),
                Project(project_code="PRJ-2026-002", customer_id=customers[1].customer_id, project_name="ERP Modernization", project_manager="Ko Min", status="Active", start_date=date(2026, 2, 5), description="ERP rollout and support"),
                Project(project_code="PRJ-2026-003", customer_id=customers[2].customer_id, project_name="Infrastructure", project_manager="Support Engineer", status="Planning", start_date=date(2026, 3, 1), description="Infrastructure improvements"),
            ]
            db.add_all(projects)
            db.flush()
            teams = [Team(team_code="TEAM-SD", team_name="Service Desk", member="Support Engineer, Aye Aye", code_id="SRV-002", description="First-line customer support"),
                     Team(team_code="TEAM-INFRA", team_name="Infrastructure", member="Ko Min, May Thu", code_id="SRV-004", description="Servers and network"),
                     Team(team_code="TEAM-DB", team_name="Database Team", member="Aye Aye, Ko Min", code_id="SRV-001", description="Database systems")]
            db.add_all(teams)
            db.flush()
            users = [
                User(fullname="System Administrator", email="admin@goldenpride.local", password_hash=hash_password(secrets.token_urlsafe(32)), role="admin", must_change_password=True),
                User(fullname="Support Agent", email="agent@goldenpride.local", password_hash=hash_password(os.getenv("SEED_AGENT_PASSWORD", "Agent@123")), role="agent", team_id=teams[0].team_id),
                User(fullname="Customer customer", email="customer@goldenpride.local", password_hash=hash_password(os.getenv("SEED_CUSTOMER_PASSWORD", "customer@123")), role="customer"),
            ]
            db.add_all(users)
            db.flush()
            # Keep the demo portal account linked by email to a real customer record.
            customer_user = users[2]
            portal_customer = Customer(customer_name=customer_user.fullname, email=customer_user.email, phone="", address="", contact_name=customer_user.fullname)
            db.add(portal_customer)
            db.flush()
            customers.append(portal_customer)
            contacts = [
                Contact(contact_code="CON-NOVA-01", customer_id=customers[0].customer_id, fullname="Aung Aung", department="IT", job_title="IT Manager", email="aung@nova.example", phone="+95 9 450 000 111", type="Primary contact", note="Primary technical contact"),
                Contact(contact_code="CON-SUM-01", customer_id=customers[1].customer_id, fullname="May Thu", department="Operations", job_title="Operations Lead", email="may@summit.example", phone="+95 9 450 000 222", type="Technical contact", note="ERP support contact"),
            ]
            db.add_all(contacts)
            db.flush()
            contracts = [
                Contract(contract_code="AUTO-2-SUPPORT", contract_name="Auto Manufacturing Support", customer_id=customers[0].customer_id, project_id=projects[0].project_id, plan_id=plans[0].plan_id, start_date=date(2026,1,1), end_date=date(2027,12,31), scope="Standard service desk and database support"),
                Contract(contract_code="ERP-CARE", contract_name="ERP Care", customer_id=customers[1].customer_id, project_id=projects[1].project_id, plan_id=plans[1].plan_id, start_date=date(2026,1,1), end_date=date(2027,12,31), scope="ERP and application support"),
                Contract(contract_code="INFRA-STD", contract_name="Infrastructure Standard", customer_id=customers[2].customer_id, project_id=projects[2].project_id, plan_id=plans[0].plan_id, start_date=date(2026,1,1), end_date=date(2027,12,31), scope="Infrastructure support"),
            ]
            db.add_all(contracts)
            db.flush()
            assets = [
                Asset(asset_tag="DB-SRV-014", asset_name="Production Database Server", customer_id=customers[0].customer_id, project_id=projects[0].project_id, type="Server", status="In service", vendor="Dell", model="PowerEdge R750", serial_no="SN-DB-14882", ip_address="192.168.1.14", note="Server Room A"),
                Asset(asset_tag="LAP-0042", asset_name="Finance Laptop", customer_id=customers[1].customer_id, project_id=projects[1].project_id, type="Laptop", status="Assigned", vendor="Lenovo", model="ThinkPad T14", serial_no="SN-LAP-0042", note="Assigned to finance"),
                Asset(asset_tag="PC-0091", asset_name="Reception Workstation", customer_id=customers[2].customer_id, project_id=projects[2].project_id, type="Desktop", status="In service", vendor="HP", model="EliteDesk", serial_no="SN-PC-0091"),
                Asset(asset_tag="MY-LAPTOP-01", asset_name="Customer Portal Laptop", customer_id=customers[3].customer_id, type="Laptop", status="Assigned", vendor="Lenovo", model="ThinkPad", serial_no="DEMO-CUSTOMER-01"),
            ]
            db.add_all(assets)
            db.flush()
            ticket_rows = [
                Ticket(ticket_code="TKT-2026-007", customer_id=customers[0].customer_id, project_id=projects[0].project_id, contact_id=contacts[0].contact_id, plan_id=plans[0].plan_id, contract_id=contracts[0].contract_id, asset_id=assets[0].asset_id, type="Database Support", subject="Database connection timeout", description="Connections time out during peak traffic.", status="Closed", priority="High", assigned="Support Agent", date=date(2026,10,19), created_by_id=users[1].user_id),
                Ticket(ticket_code="TKT-2026-006", customer_id=customers[1].customer_id, project_id=projects[1].project_id, contact_id=contacts[1].contact_id, plan_id=plans[1].plan_id, contract_id=contracts[1].contract_id, asset_id=assets[1].asset_id, type="Application Support", subject="Customer access request", description="New employee needs ERP access.", status="In progress", priority="Medium", assigned="Aye Aye", date=date(2026,10,22), created_by_id=users[1].user_id),
                Ticket(ticket_code="TKT-2026-005", customer_id=customers[2].customer_id, project_id=projects[2].project_id, plan_id=plans[0].plan_id, contract_id=contracts[2].contract_id, asset_id=assets[2].asset_id, type="Hardware", subject="Workstation setup", description="Prepare a workstation for a new employee.", status="Open", priority="Low", assigned="", date=date(2026,10,22), created_by_id=users[1].user_id),
                Ticket(ticket_code="TKT-2026-004", customer_id=customers[0].customer_id, project_id=projects[0].project_id, plan_id=plans[0].plan_id, contract_id=contracts[0].contract_id, asset_id=assets[0].asset_id, type="Network", subject="VPN connectivity issue", description="VPN drops intermittently.", status="In progress", priority="High", assigned="Support Agent", date=date(2026,10,21), created_by_id=users[1].user_id),
                Ticket(ticket_code="TKT-2026-003", customer_id=customers[3].customer_id, plan_id=plans[0].plan_id, service_code="SRV-002", asset_id=assets[3].asset_id, type="Service request", subject="Customer portal access assistance", description="Demo customer ticket for the requester portal.", status="Open", priority="Medium", assigned="Support Agent", date=date(2026,10,23), created_by_id=users[2].user_id),
            ]
            db.add_all(ticket_rows)
            db.add_all([
                RolePermission(role_key="admin", description="Full system access", permissions_json=json.dumps({"all": True})),
                RolePermission(role_key="agent", description="View tickets assigned to the support team and linked service records", permissions_json=json.dumps({"tickets": ["view"], "customers": ["view"], "projects": ["view"], "assets": ["view"]})),
                RolePermission(role_key="customer", description="View own tickets, reply and submit service requests", permissions_json=json.dumps({"tickets": ["own-view", "create", "reply"], "services": ["customer-visible-view"]})),
            ])
            db.add(EmailSetting(setting_id=1, settings_json=json.dumps({"smtp_host":"", "smtp_port":587, "encryption":"STARTTLS", "authentication":"Username and password", "allow_self_signed_certificate":False, "smtp_username":"", "smtp_password":"", "from_name":"Golden Pride Support", "from_email":"", "reply_to_email":"", "timeout":15, "enabled":False, "max_retry":3, "retry_delay":5, "event_rules":{**_default_event_rules(), "daily_summary":False}, "templates":DEFAULT_EMAIL_TEMPLATES})))
            log_action(db, None, "SEED", "System", "Created starter data and demo users")
        # Persist this marker even when the database was not pristine. Deleting the
        # last sample/customer row later must never trigger demo-data recreation.
        db.add(SystemSetting(setting_key="initial_demo_seed_completed", setting_value="true"))
        db.commit()
    finally:
        db.close()

def ensure_initial_admin_password() -> None:
    """Create a one-time random Admin password and save it outside the web root.

    Existing installations are handled too: on the first startup after this
    feature is introduced, the earliest active Admin is assigned a fresh
    temporary password and forced through the existing change-password flow.
    Only the password hash is stored in PostgreSQL.
    """
    db = SessionLocal()
    credential_file_written = False
    temp_file: Path | None = None
    try:
        # Serialize initial setup across FastAPI workers on PostgreSQL.
        if engine.dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
                {"lock_name": INITIAL_ADMIN_PASSWORD_SETTING},
            )

        if db.get(SystemSetting, INITIAL_ADMIN_PASSWORD_SETTING) is not None:
            return

        admin = db.scalar(
            select(User).where(User.role == "admin", User.active.is_(True)).order_by(User.user_id.asc())
        )
        if not admin:
            # Do not mark setup complete until an active Admin exists.
            return

        temporary_password = secrets.token_urlsafe(24)
        admin.password_hash = hash_password(temporary_password)
        admin.must_change_password = True

        INITIAL_ADMIN_CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = INITIAL_ADMIN_CREDENTIALS_DIR / f".initial_admin_credentials.{secrets.token_hex(8)}.tmp"
        fd = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                "Golden Pride — Initial Admin Login\n"
                "=====================================\n"
                "Username: admin\n"
                f"Temporary password: {temporary_password}\n\n"
                "Sign in at the Golden Pride login page. You will be required to\n"
                "change this password immediately. This file is deleted after\n"
                "the new Admin password is saved. Keep this file private.\n"
            )
        try:
            os.chmod(temp_file, 0o600)
        except OSError:
            pass
        os.replace(temp_file, INITIAL_ADMIN_CREDENTIALS_FILE)
        temp_file = None
        credential_file_written = True

        db.add(SystemSetting(setting_key=INITIAL_ADMIN_PASSWORD_SETTING, setting_value="true"))
        db.commit()
        logger.warning(
            "Initial Admin password generated. Read the one-time credentials file at: %s",
            INITIAL_ADMIN_CREDENTIALS_FILE,
        )
    except Exception:
        db.rollback()
        if credential_file_written:
            try:
                INITIAL_ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not clean up an uncommitted Admin credentials file")
        raise
    finally:
        if temp_file:
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass
        db.close()

def ensure_default_support_teams() -> None:
    """Add a practical IT support-team list without replacing custom teams."""
    defaults = [
        ("TEAM-APP", "Application Support", "Business applications and software support"),
        ("TEAM-NETOPS", "Network Operations", "LAN, WAN, Wi-Fi, VPN and network connectivity"),
        ("TEAM-SYS", "Systems Administration", "Servers, operating systems and directory services"),
        ("TEAM-HWDSK", "Hardware & Desktop Support", "Laptops, desktops, printers and end-user devices"),
        ("TEAM-SEC", "Cybersecurity", "Security incidents, access reviews and endpoint protection"),
        ("TEAM-CLOUD", "Cloud & DevOps", "Cloud infrastructure, deployment pipelines and automation"),
        ("TEAM-ERP", "ERP Support", "ERP platform and business-process application support"),
        ("TEAM-OPS", "IT Operations", "Daily IT operations, monitoring and operational support"),
        ("TEAM-DATA", "Data & Analytics", "Data platforms, reporting and analytics support"),
        ("TEAM-BACKUP", "Backup & Recovery", "Backup jobs, restoration and disaster recovery"),
        ("TEAM-FIELD", "Field Support", "On-site IT support and branch visits"),
        ("TEAM-TELECOM", "Telecommunications", "IP telephony, mobile and communication systems"),
        ("TEAM-HELP", "IT Helpdesk", "First-contact IT support and service requests"),
    ]
    db = SessionLocal()
    try:
        existing_names = {name.casefold() for name in db.scalars(select(Team.team_name)).all()}
        used_codes = {code.casefold() for code in db.scalars(select(Team.team_code).where(Team.team_code.is_not(None))).all()}
        added = False
        for code, name, description in defaults:
            if name.casefold() in existing_names:
                continue
            candidate = code
            suffix = 2
            while candidate.casefold() in used_codes:
                candidate = f"{code}-{suffix}"
                suffix += 1
            db.add(Team(team_code=candidate, team_name=name, description=description))
            existing_names.add(name.casefold())
            used_codes.add(candidate.casefold())
            added = True
        if added:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not ensure the default IT support teams")
    finally:
        db.close()

__all__ = [name for name in globals() if not name.startswith("__")]
