"""Golden Pride Ticket Service System API.

Serves the existing HTML/CSS interface and its JSON API from one origin. PostgreSQL
is the intended production database; configure DATABASE_URL in .env before running.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
from datetime import date, datetime, time
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, func, inspect, or_, select)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent


def normalize_database_url(url: str) -> str:
    # psycopg v3 is used by this project. Support common PostgreSQL URL formats.
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalize_database_url(os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/golden_pride_ticket",
))
engine_options: dict[str, Any] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SESSION_SECRET = os.getenv("SESSION_SECRET", "replace-this-secret-before-deployment-" + secrets.token_hex(16))


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Contact(Base):
    __tablename__ = "contacts"
    contact_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contact_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True)
    fullname: Mapped[str] = mapped_column(String(160), nullable=False)
    department: Mapped[str | None] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)


class Project(Base):
    __tablename__ = "projects"
    project_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    project_manager: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(50), default="Planning", nullable=False)
    date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)


class Plan(Base):
    __tablename__ = "plans"
    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    response_sla: Mapped[str | None] = mapped_column(String(80))
    resolution_sla: Mapped[str | None] = mapped_column(String(80))
    response_warning: Mapped[int | None] = mapped_column(Integer)
    response_critical: Mapped[int | None] = mapped_column(Integer)
    resolution_warning: Mapped[int | None] = mapped_column(Integer)
    resolution_critical: Mapped[int | None] = mapped_column(Integer)
    sla_mode: Mapped[str | None] = mapped_column(String(80))
    time_zone: Mapped[str | None] = mapped_column(String(80), default="Asia/Yangon")
    business_start_hour: Mapped[str | None] = mapped_column(String(10))
    business_end_hour: Mapped[str | None] = mapped_column(String(10))
    working_days: Mapped[str | None] = mapped_column(Text)
    escalation_level: Mapped[str | None] = mapped_column(String(50))
    remote_support: Mapped[str | None] = mapped_column(String(40))
    onsite_support: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)


class ServiceCatalog(Base):
    __tablename__ = "service_catalog"
    code_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    request_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    asset_requirement: Mapped[str | None] = mapped_column(String(80))
    mapped_team: Mapped[str | None] = mapped_column(String(160))
    auto_assign: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assignment_method: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)


class Team(Base):
    __tablename__ = "teams"
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    member: Mapped[str | None] = mapped_column(Text)
    code_id: Mapped[str | None] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)


class TeamServiceLink(Base):
    __tablename__ = "team_service_catalog"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True)
    code_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="CASCADE"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fullname: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="customer", nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Contract(Base):
    __tablename__ = "contracts"
    contract_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contract_code: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    contract_name: Mapped[str] = mapped_column(String(180), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.project_id", ondelete="SET NULL"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.plan_id", ondelete="SET NULL"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="Active", nullable=False)


class Asset(Base):
    __tablename__ = "assets"
    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_tag: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    asset_name: Mapped[str] = mapped_column(String(180), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.customer_id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.project_id", ondelete="SET NULL"), index=True)
    type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(60), default="In service", nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(160))
    serial_no: Mapped[str | None] = mapped_column(String(160))
    ip_address: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)


class Ticket(Base):
    __tablename__ = "tickets"
    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_code: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.project_id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.contact_id", ondelete="SET NULL"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.plan_id", ondelete="SET NULL"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.asset_id", ondelete="SET NULL"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.contract_id", ondelete="SET NULL"), index=True)
    type: Mapped[str] = mapped_column(String(120), nullable=False, default="Incident")
    service_code: Mapped[str | None] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="SET NULL"), index=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="Open", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(30), default="Medium", nullable=False)
    assigned: Mapped[str | None] = mapped_column(String(160))
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    attachment_reference: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TicketReply(Base):
    __tablename__ = "ticket_replies"
    reply_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    user_name: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    module: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EmailSetting(Base):
    __tablename__ = "email_settings"
    setting_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LoginBody(BaseModel):
    username: str
    password: str
    role: str


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class RoleBody(BaseModel):
    role_key: str
    description: str = ""
    permissions: dict[str, Any] = Field(default_factory=dict)


class EmailSettingsBody(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    encryption: str = "STARTTLS"
    authentication: str = "Username and password"
    smtp_username: str = ""
    smtp_password: str = ""
    from_name: str = "Golden Pride Support"
    from_email: str = ""
    reply_to_email: str = ""
    timeout: int = 15
    event_rules: dict[str, bool] = Field(default_factory=dict)


app = FastAPI(title="Golden Pride Ticket Service API", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="gp_session", same_site="lax", https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true")


# ---------- Authentication, sessions, serialization ----------
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


def get_actor(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    user = db.get(User, int(user_id))
    if not user or not user.active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your session is no longer valid. Please sign in again.")
    return {"user_id": user.user_id, "fullname": user.fullname, "email": user.email, "role": user.role, "team_id": user.team_id}


def admin_only(actor: dict[str, Any]) -> None:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="This action is available to administrators only.")


def actor_customer_id(db: Session, actor: dict[str, Any]) -> int | None:
    customer = db.scalar(select(Customer).where(func.lower(Customer.email) == actor["email"].lower()))
    return customer.customer_id if customer else None


def log_action(db: Session, actor: dict[str, Any] | None, action: str, module: str, details: str = "") -> None:
    db.add(AuditLog(user_id=actor.get("user_id") if actor else None,
                    user_name=actor.get("fullname") if actor else "System",
                    action=action, module=module, details=details[:2000]))


def model_values(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in inspect(row).mapper.column_attrs:
        key = column.key
        if key == "password_hash":
            continue
        value = getattr(row, key)
        result[key] = value
    return result


def serialize_row(db: Session, resource: str, row: Any) -> dict[str, Any]:
    item = model_values(row)
    if resource == "customers":
        cid = item.get("customer_id")
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
        item.update(customer_name=customer.customer_name if customer else "—",
                    project_name=project.project_name if project else "—",
                    service_name=service.name if service else "—",
                    contract_name=contract.contract_name if contract else (contract.contract_code if contract else "—"),
                    contract_code=contract.contract_code if contract else "",
                    plan_name=plan.plan_name if plan else "—", plan_code=plan.plan_code if plan else "",
                    asset_name=asset.asset_name if asset else "—", asset_tag=asset.asset_tag if asset else "—",
                    contact_name=contact.fullname if contact else "—")
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
        item.update(customer_name=customer.customer_name if customer else "—",
                    project_name=project.project_name if project else "—")
    elif resource == "users":
        team = db.get(Team, item.get("team_id")) if item.get("team_id") else None
        item["team_name"] = team.team_name if team else "—"
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
    elif resource == "role-permissions":
        try:
            item["permissions"] = json.loads(item.pop("permissions_json", "{}"))
        except json.JSONDecodeError:
            item["permissions"] = {}
    return item


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/login.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.post("/api/auth/login")
def login(payload: LoginBody, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    email = payload.username.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not user.active or not verify_password(payload.password, user.password_hash) or user.role != payload.role.lower():
        log_action(db, None, "LOGIN_FAILED", "Authentication", f"Failed login for {email}")
        db.commit()
        raise HTTPException(status_code=401, detail="The email, password, or selected role is incorrect.")
    request.session.clear()
    request.session["user_id"] = user.user_id
    log_action(db, {"user_id": user.user_id, "fullname": user.fullname}, "LOGIN", "Authentication", f"Signed in as {user.role}")
    db.commit()
    return {"user_id": user.user_id, "fullname": user.fullname, "email": user.email, "role": user.role,
            "home": {"admin": "admin-dashboard.html", "agent": "agent-dashboard.html", "customer": "user-dashboard.html"}[user.role]}


@app.get("/api/auth/me")
def me(actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    return actor


@app.post("/api/auth/logout")
def logout(request: Request, actor: dict[str, Any] = Depends(get_actor), db: Session = Depends(get_db)) -> dict[str, str]:
    log_action(db, actor, "LOGOUT", "Authentication", "Signed out")
    db.commit()
    request.session.clear()
    return {"message": "Signed out successfully."}


@app.get("/api/lookups")
def lookups(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    customers = db.scalars(select(Customer).order_by(Customer.customer_name)).all()
    if actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        customers = [c for c in customers if c.customer_id == cust_id]
        projects = db.scalars(select(Project).where(Project.customer_id == cust_id).order_by(Project.project_name)).all() if cust_id else []
        assets = db.scalars(select(Asset).where(Asset.customer_id == cust_id).order_by(Asset.asset_name)).all() if cust_id else []
        contracts = db.scalars(select(Contract).where(Contract.customer_id == cust_id).order_by(Contract.contract_name)).all() if cust_id else []
        services = db.scalars(select(ServiceCatalog).where(ServiceCatalog.customer_visible.is_(True)).order_by(ServiceCatalog.request_order)).all()
        users = []
        teams = []
    else:
        projects = db.scalars(select(Project).order_by(Project.project_name)).all()
        assets = db.scalars(select(Asset).order_by(Asset.asset_name)).all()
        contracts = db.scalars(select(Contract).order_by(Contract.contract_name)).all()
        services = db.scalars(select(ServiceCatalog).order_by(ServiceCatalog.request_order)).all()
        users = db.scalars(select(User).where(User.active.is_(True)).order_by(User.fullname)).all()
        teams = db.scalars(select(Team).order_by(Team.team_name)).all() if actor["role"] == "admin" else []
    plans = db.scalars(select(Plan).order_by(Plan.plan_name)).all()
    contacts_query = select(Contact).order_by(Contact.fullname)
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


@app.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    query = select(Ticket)
    if actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        query = query.where(Ticket.customer_id == cust_id) if cust_id else query.where(Ticket.ticket_id == -1)
    tickets = db.scalars(query.order_by(Ticket.updated_at.desc())).all()
    return {"tickets_total": len(tickets),
            "open_tickets": sum(1 for t in tickets if t.status.lower() in ("open", "new")),
            "in_progress": sum(1 for t in tickets if t.status.lower() in ("in progress", "in-progress")),
            "waiting": sum(1 for t in tickets if "pending" in t.status.lower() or "waiting" in t.status.lower()),
            "resolved": sum(1 for t in tickets if t.status.lower() in ("resolved", "closed")),
            "customers": db.scalar(select(func.count(Customer.customer_id))) or 0,
            "projects": db.scalar(select(func.count(Project.project_id))) or 0,
            "assets": db.scalar(select(func.count(Asset.asset_id))) or 0,
            "contracts": db.scalar(select(func.count(Contract.contract_id))) or 0,
            "recent_tickets": [serialize_row(db, "tickets", t) for t in tickets[:8]]}


@app.get("/api/email-settings")
def get_email_settings(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    row = db.get(EmailSetting, 1)
    settings = json.loads(row.settings_json) if row else {}
    settings["smtp_password_set"] = bool(settings.get("smtp_password"))
    settings.pop("smtp_password", None)
    return settings


@app.put("/api/email-settings")
def put_email_settings(payload: EmailSettingsBody, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    admin_only(actor)
    current = db.get(EmailSetting, 1)
    settings = json.loads(current.settings_json) if current else {}
    data = payload.model_dump()
    if not data.get("smtp_password"):
        data["smtp_password"] = settings.get("smtp_password", "")
    row = current or EmailSetting(setting_id=1, settings_json="{}")
    row.settings_json = json.dumps(data)
    db.add(row)
    log_action(db, actor, "UPDATE", "Email settings", f"Updated SMTP settings for host {data.get('smtp_host','')}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not save mail settings.")
    return {"message": "Email settings saved.", "smtp_password_set": bool(data.get("smtp_password"))}


@app.post("/api/email-settings/test")
def test_email(payload: dict[str, str], db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    admin_only(actor)
    recipient = (payload.get("recipient") or "").strip()
    if not recipient or "@" not in recipient:
        raise HTTPException(status_code=422, detail="Enter a valid recipient email address.")
    row = db.get(EmailSetting, 1)
    if not row:
        raise HTTPException(status_code=400, detail="Save the SMTP settings first.")
    cfg = json.loads(row.settings_json)
    host = cfg.get("smtp_host", "").strip()
    if not host or not cfg.get("from_email"):
        raise HTTPException(status_code=400, detail="SMTP host and From email are required.")
    message = EmailMessage()
    message["Subject"] = "Golden Pride - test notification"
    message["From"] = f"{cfg.get('from_name', 'Golden Pride Support')} <{cfg['from_email']}>"
    message["To"] = recipient
    if cfg.get("reply_to_email"):
        message["Reply-To"] = cfg["reply_to_email"]
    message.set_content("This is a test email from your Golden Pride Ticket Service System. The email connection is working.")
    timeout = max(3, min(int(cfg.get("timeout") or 15), 60))
    try:
        port = int(cfg.get("smtp_port") or 587)
        if cfg.get("encryption") == "SSL / TLS":
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as server:
                _smtp_auth(server, cfg)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                if cfg.get("encryption", "STARTTLS") == "STARTTLS":
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                _smtp_auth(server, cfg)
                server.send_message(message)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Email delivery failed: {str(exc)[:300]}") from exc
    log_action(db, actor, "SEND_TEST", "Email settings", f"Sent a test notification to {recipient}")
    db.commit()
    return {"message": f"Test email sent to {recipient}."}


def _smtp_auth(server: smtplib.SMTP, cfg: dict[str, Any]) -> None:
    if cfg.get("authentication") == "No authentication":
        return
    if cfg.get("authentication") == "OAuth 2.0":
        raise RuntimeError("OAuth 2.0 is not implemented here. Use username/password or no authentication.")
    if cfg.get("smtp_username"):
        server.login(cfg["smtp_username"], cfg.get("smtp_password", ""))


@app.get("/api/role-permissions")
def list_role_permissions(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    admin_only(actor)
    rows = db.scalars(select(RolePermission).order_by(RolePermission.role_key)).all()
    return [serialize_row(db, "role-permissions", r) for r in rows]


@app.post("/api/role-permissions")
def create_role_permission(payload: RoleBody, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
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


@app.get("/api/tickets/{ticket_id}/replies")
def list_ticket_replies(ticket_id: int, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if actor["role"] == "customer" and ticket.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only view replies on your own tickets.")
    rows = db.scalars(select(TicketReply).where(TicketReply.ticket_id == ticket_id).order_by(TicketReply.created_at)).all()
    results = []
    for r in rows:
        user = db.get(User, r.user_id)
        results.append({"reply_id": r.reply_id, "ticket_id": r.ticket_id, "user_id": r.user_id,
                        "user_name": user.fullname if user else "System", "body": r.body, "created_at": r.created_at})
    return jsonable_encoder(results)


@app.post("/api/tickets/{ticket_id}/replies")
def create_ticket_reply(ticket_id: int, payload: ReplyBody, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if actor["role"] == "customer" and ticket.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only reply to your own tickets.")
    reply = TicketReply(ticket_id=ticket_id, user_id=actor["user_id"], body=payload.body.strip())
    db.add(reply)
    ticket.updated_at = datetime.utcnow()
    log_action(db, actor, "REPLY", "Tickets", f"Added reply to ticket {ticket.ticket_code or ticket.ticket_id}")
    db.commit()
    db.refresh(reply)
    return {"reply_id": reply.reply_id, "ticket_id": reply.ticket_id, "user_id": reply.user_id,
            "user_name": actor["fullname"], "body": reply.body, "created_at": reply.created_at}


# ---------- Database-backed CRUD for every ERD module ----------
RESOURCE_MODELS: dict[str, type[Base]] = {
    "tickets": Ticket, "customers": Customer, "contacts": Contact, "projects": Project,
    "users": User, "teams": Team, "services": ServiceCatalog, "plans": Plan,
    "contracts": Contract, "assets": Asset, "audit-logs": AuditLog,
    "role-permissions": RolePermission,
}
RESOURCE_PK = {
    "tickets": "ticket_id", "customers": "customer_id", "contacts": "contact_id", "projects": "project_id",
    "users": "user_id", "teams": "team_id", "services": "code_id", "plans": "plan_id",
    "contracts": "contract_id", "assets": "asset_id", "audit-logs": "audit_id", "role-permissions": "role_permission_id",
}


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
        if resource in {"tickets", "customers", "contacts", "projects", "contracts", "plans", "services", "assets"}:
            if operation in {"read", "create", "update"} and (resource == "tickets" or operation == "read"):
                return
        if operation == "read" and resource == "teams":
            return
        raise HTTPException(status_code=403, detail="Your agent role does not have permission for this module/action.")
    if role == "customer":
        if resource == "tickets" and operation in {"read", "create"}:
            return
        if resource == "tickets" and operation == "update":
            raise HTTPException(status_code=403, detail="Use the reply feature to respond to a ticket.")
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
        if key in {"password_hash", "created_at", "updated_at", "permissions_json"}:
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
        password = payload.get("password")
        if password:
            accepted["password_hash"] = hash_password(str(password))
        elif row is None:
            raise HTTPException(status_code=422, detail="A password is required for a new user.")
        if "email" in accepted:
            accepted["email"] = str(accepted["email"]).lower()
    if resource == "services":
        # HTML selects may send yes/no or enabled/disabled values; normalize to booleans.
        for bool_key in ("customer_visible", "auto_assign"):
            if bool_key in payload:
                accepted[bool_key] = str(payload[bool_key]).lower() in {"true", "yes", "enabled", "1", "on"} if not isinstance(payload[bool_key], bool) else payload[bool_key]
    if resource == "tickets" and "date" not in accepted and row is None:
        accepted["date"] = date.today()
    return accepted


def scope_rows(db: Session, resource: str, rows: list[Any], actor: dict[str, Any]) -> list[Any]:
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


@app.get("/api/{resource}")
def list_resource(resource: str, request: Request, search: str = Query(default=""), db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
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
    else:
        query = query.order_by(getattr(model, pk))
    rows = db.scalars(query).all()
    rows = scope_rows(db, resource, list(rows), actor)
    if search.strip():
        term = search.casefold()
        rows = [r for r in rows if term in " ".join(str(v or "") for v in model_values(r).values()).casefold()]
    return jsonable_encoder([serialize_row(db, resource, row) for row in rows])


@app.post("/api/{resource}")
def create_resource(resource: str, payload: dict[str, Any], db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    if resource not in RESOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown API resource.")
    check_resource_access(resource, actor, "create")
    data = clean_payload(resource, payload)
    if resource == "tickets" and actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        if not cust_id:
            raise HTTPException(status_code=400, detail="Your account is not linked to a customer record. Ask an administrator to link it.")
        data["customer_id"] = cust_id
        data["created_by_id"] = actor["user_id"]
        data["status"] = "Open"
        data["assigned"] = None
    if resource == "tickets":
        data.setdefault("created_by_id", actor["user_id"])
    if resource == "users" and "active" not in data:
        data["active"] = True
    model = RESOURCE_MODELS[resource]
    row = model(**data)
    db.add(row)
    try:
        db.flush()
        if resource == "tickets" and not row.ticket_code:
            ticket_year = (row.date or date.today()).year
            existing_codes = db.scalars(select(Ticket.ticket_code).where(Ticket.ticket_code.like(f"TKT-{ticket_year}-%"))).all()
            used_numbers = []
            for code in existing_codes:
                try: used_numbers.append(int(str(code).rsplit("-", 1)[1]))
                except (ValueError, IndexError): pass
            row.ticket_code = f"TKT-{ticket_year}-{max(used_numbers, default=0)+1:03d}"
        if resource == "teams":
            codes = payload.get("service_codes") or ([row.code_id] if row.code_id else [])
            for code in dict.fromkeys(str(code) for code in codes if code):
                if db.get(ServiceCatalog, code):
                    db.add(TeamServiceLink(team_id=row.team_id, code_id=code))
        if resource == "users" and row.role == "customer":
            cust = db.scalar(select(Customer).where(func.lower(Customer.email) == row.email.lower()))
            if not cust:
                db.add(Customer(customer_name=row.fullname, email=row.email, contact_name=row.fullname))
            else:
                cust.customer_name = row.fullname
                cust.contact_name = row.fullname
        log_action(db, actor, "CREATE", resource, f"Created {resource} record {getattr(row, RESOURCE_PK[resource])}")
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This record conflicts with existing data or a required relationship is missing. Check unique codes, email, and foreign keys.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not create {resource} record. Check required fields and relationships.") from exc
    return jsonable_encoder(serialize_row(db, resource, row))


@app.get("/api/{resource}/{item_id}")
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
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")
    if actor["role"] == "customer":
        cust_id = actor_customer_id(db, actor)
        if resource == "tickets" and row.customer_id != cust_id:
            raise HTTPException(status_code=403, detail="You can only view your own tickets.")
        if resource == "assets" and row.customer_id != cust_id:
            raise HTTPException(status_code=403, detail="You can only view your own assets.")
        if resource == "services" and not row.customer_visible:
            raise HTTPException(status_code=404, detail="Service not found.")
    return jsonable_encoder(serialize_row(db, resource, row))


@app.put("/api/{resource}/{item_id}")
def update_resource(resource: str, item_id: str, payload: dict[str, Any], db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
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
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")
    if actor["role"] == "customer" and resource == "tickets" and row.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only access your own tickets.")
    if actor["role"] == "agent" and resource == "tickets" and actor["role"] != "admin":
        # Agent can update operational fields but cannot change ownership/relationship fields.
        payload = {k: v for k, v in payload.items() if k in {"status", "priority", "assigned", "due_date"}}
    service_codes = payload.get("service_codes") if resource == "teams" else None
    old_customer_email = row.email if resource == "customers" else None
    data = clean_payload(resource, payload, row)
    for key, value in data.items():
        setattr(row, key, value)
    if resource == "customers" and old_customer_email:
        linked_user = db.scalar(select(User).where(func.lower(User.email) == old_customer_email.lower(), User.role == "customer"))
        if linked_user:
            linked_user.fullname = row.customer_name
            linked_user.email = (row.email or old_customer_email).lower()
    if resource == "tickets":
        row.updated_at = datetime.utcnow()
    if resource == "teams" and service_codes is not None:
        db.query(TeamServiceLink).filter(TeamServiceLink.team_id == row.team_id).delete(synchronize_session=False)
        for code in dict.fromkeys(str(code) for code in service_codes if code):
            if db.get(ServiceCatalog, code):
                db.add(TeamServiceLink(team_id=row.team_id, code_id=code))
        if service_codes:
            row.code_id = str(service_codes[0])
    if resource == "users" and row.role == "customer":
        cust = db.scalar(select(Customer).where(func.lower(Customer.email) == row.email.lower()))
        if not cust:
            db.add(Customer(customer_name=row.fullname, email=row.email, contact_name=row.fullname))
        else:
            cust.customer_name = row.fullname
            cust.contact_name = row.fullname
    try:
        log_action(db, actor, "UPDATE", resource, f"Updated {resource} record {item_id}")
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Update conflicts with existing data or a foreign-key relationship.") from exc
    return jsonable_encoder(serialize_row(db, resource, row))


@app.delete("/api/{resource}/{item_id}")
def delete_resource(resource: str, item_id: str, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
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
    db.delete(row)
    log_action(db, actor, "DELETE", resource, f"Deleted {resource} record {item_id}")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This record is still referenced by other records and cannot be deleted.") from exc
    return {"message": "Record deleted."}


# ---------- Demo seed data: created once, in the database, not in browser JavaScript ----------
def seed_database() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(User.user_id))) == 0:
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
                Plan(plan_code="SLA-STD-01", plan_name="Standard", response_sla="4 hours", resolution_sla="1 business day", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="Business hours", time_zone="Asia/Yangon", business_start_hour="09:00", business_end_hour="17:00", working_days="Monday-Friday", escalation_level="Level 1", remote_support="Included", onsite_support="Excluded", description="Standard business-hours support"),
                Plan(plan_code="SLA-PRM-01", plan_name="Premium", response_sla="1 hour", resolution_sla="8 hours", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="24×7 calendar", time_zone="Asia/Yangon", business_start_hour="00:00", business_end_hour="23:59", working_days="Monday-Sunday", escalation_level="Level 2", remote_support="Included", onsite_support="Included", description="Priority 24×7 support"),
                Plan(plan_code="SLA-ENT-01", plan_name="Enterprise", response_sla="30 minutes", resolution_sla="4 hours", response_warning=70, response_critical=90, resolution_warning=70, resolution_critical=90, sla_mode="24×7 calendar", time_zone="Asia/Yangon", business_start_hour="00:00", business_end_hour="23:59", working_days="Monday-Sunday", escalation_level="Level 3", remote_support="Included", onsite_support="Included", description="Business critical enterprise support"),
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
                User(fullname="System Administrator", email="admin@goldenpride.local", password_hash=hash_password(os.getenv("SEED_ADMIN_PASSWORD", "Admin@123")), role="admin"),
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
                RolePermission(role_key="agent", description="Manage support tickets and linked service records", permissions_json=json.dumps({"tickets": ["view", "create", "edit"], "customers": ["view"], "projects": ["view"], "assets": ["view"]})),
                RolePermission(role_key="customer", description="View own tickets, reply and submit service requests", permissions_json=json.dumps({"tickets": ["own-view", "create", "reply"], "services": ["customer-visible-view"]})),
            ])
            db.add(EmailSetting(setting_id=1, settings_json=json.dumps({"smtp_host":"", "smtp_port":587, "encryption":"STARTTLS", "authentication":"Username and password", "smtp_username":"", "smtp_password":"", "from_name":"Golden Pride Support", "from_email":"", "reply_to_email":"", "timeout":15, "event_rules":{"ticket_created":True,"ticket_assigned":True,"status_changed":True,"new_reply":True,"sla_approaching":True,"ticket_resolved":True,"daily_summary":False}})))
            log_action(db, None, "SEED", "System", "Created starter data and demo users")
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed_database()


# Keep the original standalone HTML pages and CSS, now served on the API's origin.
app.mount("/", StaticFiles(directory=str(BASE_DIR), html=True), name="frontend")
