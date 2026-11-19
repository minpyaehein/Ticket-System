"""Golden Pride Ticket Service System API.

Serves the existing HTML/CSS interface and its JSON API from one origin. PostgreSQL
is the intended production database; configure DATABASE_URL in .env before running.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import socket
import ssl
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Generator
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, case, create_engine, func, inspect, or_, select, text)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent
# Load the project-local .env even when Uvicorn is launched from another folder.
load_dotenv(BASE_DIR / ".env")


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
# Public URL used in customer email links. Set this to the VM/domain address in production.
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
engine_options: dict[str, Any] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SESSION_SECRET = os.getenv("SESSION_SECRET", "replace-this-secret-before-deployment-" + secrets.token_hex(16))
# A fresh identifier per application process forces every browser to sign in again
# after the server is stopped/restarted (for example, Ctrl+C then Uvicorn restart).
APP_BOOT_ID = secrets.token_urlsafe(24)

# Login policy is enforced by the FastAPI endpoint and persisted in the existing
# system_settings table, so the limit is shared across app workers and restarts.
LOGIN_ATTEMPT_WINDOW_SECONDS = 60.0
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60.0

# The one-time Admin bootstrap credential is written outside BASE_DIR because
# BASE_DIR is served by StaticFiles. The file is removed after the Admin changes
# the temporary password.
INITIAL_ADMIN_PASSWORD_SETTING = "initial_admin_password_bootstrap_completed"
INITIAL_ADMIN_CREDENTIALS_DIR = BASE_DIR.parent / ".golden_pride_private"
INITIAL_ADMIN_CREDENTIALS_FILE = INITIAL_ADMIN_CREDENTIALS_DIR / "initial_admin_credentials.txt"

MYANMAR_TIME_ZONE = "Asia/Yangon"

def yangon_today() -> date:
    """Return the business date in Myanmar time."""
    return datetime.now(ZoneInfo(MYANMAR_TIME_ZONE)).date()

def _as_yangon_datetime(value: datetime | None) -> datetime | None:
    """Interpret stored naive datetimes as UTC and convert them to Myanmar time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(MYANMAR_TIME_ZONE))

def format_yangon_datetime(value: datetime | None) -> str:
    """Format a stored timestamp explicitly as Myanmar Standard Time (MMT)."""
    local_value = _as_yangon_datetime(value)
    return local_value.strftime("%Y-%m-%d %H:%M:%S MMT (Asia/Yangon)") if local_value else "—"

def yangon_datetime_iso(value: datetime | None) -> str | None:
    """Return a timezone-aware ISO timestamp for browser-safe Myanmar display."""
    local_value = _as_yangon_datetime(value)
    return local_value.isoformat(timespec="seconds") if local_value else None


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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Plan(Base):
    __tablename__ = "plans"
    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    plan_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Standard")
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Team(Base):
    __tablename__ = "teams"
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    member: Mapped[str | None] = mapped_column(Text)
    code_id: Mapped[str | None] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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
    request_type_code: Mapped[str | None] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserTeamMembership(Base):
    __tablename__ = "user_team_memberships"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True)


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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AssetServiceLink(Base):
    __tablename__ = "asset_service_catalog"
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True)
    code_id: Mapped[str] = mapped_column(ForeignKey("service_catalog.code_id", ondelete="CASCADE"), primary_key=True)


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
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id", ondelete="SET NULL"), index=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="Open", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(30), default="Medium", nullable=False)
    assigned: Mapped[str | None] = mapped_column(String(160))
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    attachment_reference: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TicketReply(Base):
    __tablename__ = "ticket_replies"
    reply_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    module: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    entity_label: Mapped[str | None] = mapped_column(String(240))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text)
    change_data: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EmailSetting(Base):
    __tablename__ = "email_settings"
    setting_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    setting_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class NotificationItem(Base):
    __tablename__ = "notifications"
    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="SET NULL"), index=True)
    ticket_code: Mapped[str | None] = mapped_column(String(60))
    actor_name: Mapped[str | None] = mapped_column(String(160))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    delivery_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.ticket_id", ondelete="SET NULL"), index=True)
    ticket_code: Mapped[str | None] = mapped_column(String(60))
    event_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_label: Mapped[str] = mapped_column(String(160), nullable=False)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(160))
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class LoginBody(BaseModel):
    username: str
    password: str


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    is_internal: bool = False


class RoleBody(BaseModel):
    role_key: str
    description: str = ""
    permissions: dict[str, Any] = Field(default_factory=dict)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=300)
    new_password: str = Field(min_length=10, max_length=300)


class EmailSettingsBody(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    encryption: str = "STARTTLS"
    authentication: str = "Username and password"
    allow_self_signed_certificate: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    from_name: str = "Golden Pride Support"
    from_email: str = ""
    reply_to_email: str = ""
    timeout: int = 15
    enabled: bool = False
    max_retry: int = 3
    retry_delay: int = 5
    event_rules: dict[str, bool] = Field(default_factory=dict)
    templates: dict[str, dict[str, str]] = Field(default_factory=dict)
    pending_customer_reminder_minutes: int | None = None
    resolution_confirmation_reminder_minutes: int | None = None
    auto_close_resolved_minutes: int | None = None
    # Backward-compatible inputs for older browser tabs / API clients.
    pending_customer_reminder_hours: int | None = None
    resolution_confirmation_reminder_days: int | None = None
    auto_close_resolved_days: int | None = None


app = FastAPI(title="Golden Pride Ticket Service API", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="gp_session", same_site="lax", https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true")


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected API errors and return a stable JSON detail to the frontend."""
    logger.exception("Unhandled request error: %s %s", request.method, request.url.path, exc_info=exc)
    if request.url.path.startswith("/api/"):
        detail = "An unexpected server error occurred while saving this record. Check the Uvicorn terminal for the full error details."
    else:
        detail = "An unexpected server error occurred. Check the Uvicorn terminal for the full error details."
    return JSONResponse(status_code=500, content={"detail": detail})


@app.middleware("http")
async def prevent_stale_page_and_api_cache(request: Request, call_next):
    """A refresh must read the committed database state, not a cached page/API response."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/login.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.post("/api/auth/login")
def login(payload: LoginBody, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    throttle_key, throttle_state, retry_after = _load_login_throttle_state(db, request)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    email = payload.username.strip().lower()
    # The first Admin can sign in with the stable username "admin". This avoids
    # depending on the demo email address, which may not be a real mailbox.
    if email == "admin":
        user = db.scalar(
            select(User).where(User.role == "admin", User.active.is_(True)).order_by(User.user_id.asc())
        )
    else:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        _record_failed_login(db, throttle_key, throttle_state)
        log_action(db, None, "LOGIN_FAILED", "Authentication", f"Failed login for {email}", request=request, entity_label=email)
        db.commit()
        raise HTTPException(status_code=401, detail="The email or password is incorrect.")
    _clear_login_failures(db, throttle_key)
    request.session.clear()
    request.session["user_id"] = user.user_id
    request.session["boot_id"] = APP_BOOT_ID
    log_action(db, {"user_id": user.user_id, "fullname": user.fullname, "role": user.role}, "LOGIN", "Authentication", f"Signed in as {user.role}", request=request, entity_id=user.user_id, entity_label=user.email)
    db.commit()
    return {**_user_team_context(db, user), "must_change_password": bool(user.must_change_password),
            "home": {"admin": "admin-dashboard.html", "agent": "agent-dashboard.html", "customer": "user-dashboard.html"}[user.role]}


@app.get("/api/auth/me")
def me(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user_id = _require_current_server_session(request)
    user = db.get(User, int(user_id))
    if not user or not user.active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your session is no longer valid. Please sign in again.")
    return {**_user_team_context(db, user), "must_change_password": bool(user.must_change_password)}


@app.post("/api/auth/logout")
def logout(request: Request, actor: dict[str, Any] = Depends(get_actor), db: Session = Depends(get_db)) -> dict[str, str]:
    log_action(db, actor, "LOGOUT", "Authentication", "Signed out", request=request, entity_id=actor.get("user_id"), entity_label=actor.get("email"))
    db.commit()
    request.session.clear()
    return {"message": "Signed out successfully."}


@app.get("/api/lookups")
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


@app.get("/api/dashboard/stats")
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


def _default_user_notification_preferences(role: str) -> dict[str, bool]:
    base = {"ticket_created": True, "ticket_assigned": True, "status_changed": True,
            "new_reply": True, "internal_note": role in {"admin", "agent"},
            "sla_approaching": True, "ticket_resolved": True,
            "daily_summary": role in {"admin", "agent"}}
    return base


@app.get("/api/notification-preferences")
def get_notification_preferences(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    row = db.get(UserNotificationPreference, actor["user_id"])
    values = _default_user_notification_preferences(actor["role"])
    if row:
        try: values.update({k: bool(v) for k, v in json.loads(row.settings_json or "{}").items() if k in values})
        except (json.JSONDecodeError, AttributeError): pass
    return {"preferences": values}


@app.put("/api/notification-preferences")
def put_notification_preferences(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    submitted = payload.get("preferences", payload)
    if not isinstance(submitted, dict):
        raise HTTPException(status_code=422, detail="Preferences must be an object.")
    current = db.get(UserNotificationPreference, actor["user_id"])
    values = _default_user_notification_preferences(actor["role"])
    if current:
        try: values.update({k: bool(v) for k, v in json.loads(current.settings_json or "{}").items() if k in values})
        except (json.JSONDecodeError, AttributeError): pass
    for key in values:
        if key in submitted: values[key] = bool(submitted[key])
    row = current or UserNotificationPreference(user_id=actor["user_id"], settings_json="{}")
    row.settings_json = json.dumps(values)
    db.add(row)
    log_action(db, actor, "UPDATE_PREFERENCES", "Email notifications", "Updated personal email notification preferences", request=request, entity_id=actor["user_id"], entity_label=actor.get("email"), changes={k:{"from":"previous setting","to":v} for k,v in values.items() if k in submitted})
    db.commit()
    return {"message": "Your email notification preferences were saved.", "preferences": values}


@app.get("/api/notifications")
def list_notifications(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    query = select(NotificationItem).where(NotificationItem.user_id == actor["user_id"]).order_by(NotificationItem.created_at.desc())
    rows = db.scalars(query.limit(limit)).all()
    unread = db.scalar(select(func.count(NotificationItem.notification_id)).where(
        NotificationItem.user_id == actor["user_id"], NotificationItem.is_read.is_(False))) or 0
    return {"unread_count": unread, "items": [{
        "notification_id": row.notification_id, "event_key": row.event_key,
        "title": row.title, "message": row.message, "ticket_id": row.ticket_id,
        "ticket_code": row.ticket_code, "actor_name": row.actor_name,
        "actor_role": row.actor_role, "is_read": bool(row.is_read), "created_at": row.created_at,
    } for row in rows]}


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    row = db.get(NotificationItem, notification_id)
    if not row or row.user_id != actor["user_id"]:
        raise HTTPException(status_code=404, detail="Notification not found.")
    row.is_read = True
    db.commit()
    return {"message": "Notification marked as read."}


@app.post("/api/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    db.query(NotificationItem).filter(NotificationItem.user_id == actor["user_id"], NotificationItem.is_read.is_(False)).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read."}


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordBody, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    user = db.get(User, actor["user_id"])
    if not user or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="The current or temporary password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="Choose a new password different from the temporary password.")
    before = {"must_change_password": bool(user.must_change_password)}
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    log_action(db, actor, "PASSWORD_CHANGED", "Authentication", "User changed their password", request=request, entity_id=user.user_id, entity_label=user.email, changes={"must_change_password":{"from":before["must_change_password"],"to":False}})
    db.commit()
    # Once the initial Admin has chosen a private password, remove the only
    # plaintext copy of the generated temporary credential.
    if user.role == "admin" and before["must_change_password"]:
        try:
            INITIAL_ADMIN_CREDENTIALS_FILE.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove the one-time Admin credentials file")
    return {"message": "Password changed successfully. You can now continue to your dashboard."}


@app.post("/api/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, request: Request, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    admin_only(actor)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role not in {"customer", "agent"}:
        raise HTTPException(status_code=400, detail="Password reset is available for Customer and Agent accounts.")
    setting = db.get(EmailSetting, 1)
    cfg = json.loads(setting.settings_json or "{}") if setting else {}
    if not cfg.get("smtp_host") or not cfg.get("from_email"):
        raise HTTPException(status_code=400, detail="Configure and save SMTP settings before resetting an Agent or Customer password.")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    temp_password = "".join(secrets.choice(alphabet) for _ in range(16))
    subject = "Golden Pride — temporary password for your account"
    body = (f"Hello {user.fullname},\n\nAn administrator reset the password for your Golden Pride account.\n\n"
            f"Temporary password: {temp_password}\n\nSign in with this temporary password. You will be required to change it before continuing."
            " If you did not request this, contact your support administrator.\n\nGolden Pride Support")
    old_hash, old_flag = user.password_hash, bool(user.must_change_password)
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    try:
        db.commit()
        _send_notification_email(cfg, [user.email], subject, body)
    except Exception as exc:
        db.rollback()
        # If delivery failed after the first commit, restore the old credential so
        # we never strand the customer with a password they did not receive.
        refreshed = db.get(User, user_id)
        if refreshed:
            refreshed.password_hash, refreshed.must_change_password = old_hash, old_flag
            log_action(db, actor, "PASSWORD_RESET_EMAIL_FAILED", "User Management", f"Temporary password email failed for customer {user.email}: {str(exc)[:250]}", request=request, entity_id=user.user_id, entity_label=user.email)
            db.commit()
        raise HTTPException(status_code=400, detail=f"Temporary password was not issued because email delivery failed: {str(exc)[:250]}") from exc
    log_action(db, actor, "PASSWORD_RESET", "User Management", f"Admin issued a temporary password and emailed customer {user.email}; password change required at next sign in", request=request, entity_id=user.user_id, entity_label=user.email, changes={"must_change_password":{"from":old_flag,"to":True}})
    db.commit()
    return {"message": f"Temporary password sent to {user.email}. The user must change it at next sign in."}


@app.get("/api/email-settings")
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


@app.put("/api/email-settings")
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


@app.get("/api/email-deliveries")
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


@app.post("/api/email-deliveries/process-queue")
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


@app.post("/api/email-deliveries/retry-failed")
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


@app.post("/api/email-settings/test")
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


# Each event has a separate template for each recipient role. Event rules remain
# event-level toggles, so one checkbox can enable/disable all audience variants.
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

# Used only to detect the single generic template stored by older project versions.
# A user-customized legacy event template is copied forward for that event/role unless
# a role-specific template has already been saved.
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


def _ticket_assigned_agent(db: Session, ticket: Ticket) -> User | None:
    """Resolve the explicitly assigned active Agent, independent of profile tags."""
    if not ticket.assigned:
        return None
    return db.scalar(select(User).where(
        func.lower(func.trim(User.fullname)) == str(ticket.assigned).strip().lower(),
        User.role == "agent", User.active.is_(True)
    ).order_by(User.user_id))


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


@app.get("/api/role-permissions")
def list_role_permissions(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    admin_only(actor)
    rows = db.scalars(select(RolePermission).order_by(RolePermission.role_key)).all()
    return [serialize_row(db, "role-permissions", r) for r in rows]


@app.post("/api/role-permissions")
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


@app.get("/api/tickets/{ticket_id}/replies")
def list_ticket_replies(ticket_id: int, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> list[dict[str, Any]]:
    ticket = db.get(Ticket, ticket_id)
    if not ticket or (actor["role"] != "admin" and not ticket.active):
        raise HTTPException(status_code=404, detail="Ticket not found.")
    # Agents can read conversations for tickets assigned to them or routed to
    # their Support Team. Only the explicitly assigned Agent sees internal notes.
    if actor["role"] == "customer" and ticket.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only view replies on your own tickets.")
    if actor["role"] == "agent" and not _agent_can_access_ticket(db, ticket, actor):
        raise HTTPException(status_code=403, detail="This ticket has not been assigned to your account.")
    query = select(TicketReply).where(TicketReply.ticket_id == ticket_id)
    # Public replies are part of the shared customer-facing conversation, so
    # every authorized Agent (assigned or in the ticket's Support Team) can see
    # replies from the Customer, Admin, and support staff. Internal notes remain
    # private to Admins and the Agent explicitly assigned to this ticket.
    is_assigned_agent = actor["role"] == "agent" and _agent_is_explicitly_assigned(db, ticket, actor)
    if actor["role"] == "customer" or (actor["role"] == "agent" and not is_assigned_agent):
        query = query.where(TicketReply.is_internal.is_(False))
    rows = db.scalars(query.order_by(TicketReply.created_at)).all()
    results = []
    for r in rows:
        user = db.get(User, r.user_id)
        results.append({"reply_id": r.reply_id, "ticket_id": r.ticket_id, "user_id": r.user_id,
                        "user_name": user.fullname if user else "System", "body": r.body,
                        "is_internal": bool(r.is_internal), "created_at": r.created_at})
    return jsonable_encoder(results)


@app.post("/api/tickets/{ticket_id}/accept-resolution")
def customer_accept_ticket_resolution(
    ticket_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: dict[str, Any] = Depends(get_actor),
) -> dict[str, Any]:
    """Allow only the owning customer to accept a currently Resolved ticket."""
    if actor.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Only the ticket's customer can accept its resolution.")
    ticket = db.get(Ticket, ticket_id)
    customer_id = actor_customer_id(db, actor)
    if not ticket or not customer_id or ticket.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if str(ticket.status or "").strip().casefold() != "resolved":
        raise HTTPException(status_code=409, detail="Only a Resolved ticket can be accepted.")

    old_status = ticket.status
    ticket.status = "Closed"
    ticket.status_changed_at = datetime.utcnow()
    ticket.updated_at = datetime.utcnow()
    log_action(
        db, actor, "ACCEPT_RESOLUTION", "Tickets",
        f"Customer accepted the resolution for {ticket.ticket_code or ticket.ticket_id}",
        request=request, entity_id=ticket.ticket_id,
        entity_label=ticket.ticket_code or str(ticket.ticket_id),
        changes={"status": {"from": old_status, "to": ticket.status}},
    )
    db.commit()
    background_tasks.add_task(
        run_ticket_notifications, ticket.ticket_id,
        [("customer_accepted_resolution", "Customer accepted the proposed resolution and closed the ticket.")],
        dict(actor),
    )
    return {"ticket_id": ticket.ticket_id, "status": ticket.status,
            "message": "Thank you. You accepted the resolution and the ticket is now closed."}


@app.post("/api/tickets/{ticket_id}/reopen")
def customer_reopen_ticket(
    ticket_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: dict[str, Any] = Depends(get_actor),
) -> dict[str, Any]:
    """Allow only the owning customer to reject a resolution and reopen the ticket."""
    if actor.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Only the ticket's customer can reopen it through this action.")
    ticket = db.get(Ticket, ticket_id)
    customer_id = actor_customer_id(db, actor)
    if not ticket or not customer_id or ticket.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if str(ticket.status or "").strip().casefold() not in {"resolved", "closed"}:
        raise HTTPException(status_code=409, detail="Only a Resolved or Closed ticket can be reopened using this action.")

    old_status = ticket.status
    ticket.status = "Open"
    ticket.status_changed_at = datetime.utcnow()
    ticket.updated_at = datetime.utcnow()
    log_action(
        db, actor, "REOPEN", "Tickets",
        f"Customer reopened {ticket.ticket_code or ticket.ticket_id} because the issue is not resolved",
        request=request, entity_id=ticket.ticket_id,
        entity_label=ticket.ticket_code or str(ticket.ticket_id),
        changes={"status": {"from": old_status, "to": ticket.status}},
    )
    db.commit()
    background_tasks.add_task(
        run_ticket_notifications, ticket.ticket_id,
        [("ticket_reopened", "Customer reported that the issue is not fully resolved.")],
        dict(actor),
    )
    return {"ticket_id": ticket.ticket_id, "status": ticket.status,
            "message": "Your ticket has been reopened. The support team will continue working on it."}


@app.post("/api/tickets/{ticket_id}/replies")
def create_ticket_reply(ticket_id: int, payload: ReplyBody, request: Request,
                        background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                        actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    ticket = db.get(Ticket, ticket_id)
    if not ticket or (actor["role"] != "admin" and not ticket.active):
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if actor["role"] == "customer" and ticket.customer_id != actor_customer_id(db, actor):
        raise HTTPException(status_code=403, detail="You can only reply to your own tickets.")
    if actor["role"] == "agent":
        if not _agent_can_access_ticket(db, ticket, actor):
            raise HTTPException(status_code=403, detail="This ticket has not been assigned to your account or Support Team.")
        if not _agent_is_explicitly_assigned(db, ticket, actor):
            raise HTTPException(status_code=403, detail="Only the Agent explicitly assigned to this ticket can send replies or internal notes.")
    if payload.is_internal and actor["role"] not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Only Admin and the assigned Agent can create internal notes.")
    reply = TicketReply(ticket_id=ticket_id, user_id=actor["user_id"], body=payload.body.strip(), is_internal=payload.is_internal)
    db.add(reply)
    ticket.updated_at = datetime.utcnow()
    action = "INTERNAL_NOTE" if reply.is_internal else "REPLY"
    summary = f"Added internal note to ticket {ticket.ticket_code or ticket.ticket_id}" if reply.is_internal else f"Added reply to ticket {ticket.ticket_code or ticket.ticket_id}"
    log_action(db, actor, action, "Tickets", summary, request=request, entity_id=ticket.ticket_id, entity_label=ticket.ticket_code or f"TKT-{ticket.ticket_id}", changes={"internal":{"from":None,"to":True}} if reply.is_internal else {"reply":{"from":None,"to":payload.body.strip()[:500]}})
    db.commit()
    db.refresh(reply)
    # Queue notification fan-out after the reply transaction is committed.
    # Internal-note routing is staff-only in _event_email_targets(); customers
    # are never included in its recipient groups.
    event_name = "internal_note" if reply.is_internal else "new_reply"
    background_tasks.add_task(
        run_ticket_notifications,
        ticket.ticket_id,
        [(event_name, payload.body.strip()[:500])],
        dict(actor),
    )
    return {"reply_id": reply.reply_id, "ticket_id": reply.ticket_id, "user_id": reply.user_id,
            "user_name": actor["fullname"], "body": reply.body, "is_internal": bool(reply.is_internal), "created_at": reply.created_at}


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


@app.get("/api/{resource}")
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


logger = logging.getLogger("golden_pride.database")

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


@app.post("/api/{resource}")
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


@app.put("/api/{resource}/{item_id}")
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


@app.post("/api/customers/{customer_id}/toggle-active")
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


@app.post("/api/users/{user_id}/toggle-active")
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


@app.post("/api/{resource}/{item_id}/toggle-active")
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


@app.delete("/api/{resource}/{item_id}")
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


# ---------- Demo seed data: created once, in the database, not in browser JavaScript ----------
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


_daily_summary_task: asyncio.Task | None = None
_email_retry_task: asyncio.Task | None = None
_scheduled_ticket_event_task: asyncio.Task | None = None


def migrate_legacy_schema() -> None:
    """Add fields introduced after existing installations were created."""
    inspector = inspect(engine)
    if "audit_logs" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("audit_logs")}
        additions = {
            "actor_role": "VARCHAR(40)",
            "entity_id": "VARCHAR(120)",
            "entity_label": "VARCHAR(240)",
            "ip_address": "VARCHAR(64)",
            "change_data": "TEXT",
        }
        missing = [(name, ddl) for name, ddl in additions.items() if name not in existing]
        if missing:
            with engine.begin() as conn:
                for name, ddl in missing:
                    conn.execute(text(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}"))
    if "customers" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("customers")}
        if "active" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE customers ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE"))
    if "users" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("users")}
        if "must_change_password" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE"))
        if "request_type_code" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN request_type_code VARCHAR(50) REFERENCES service_catalog(code_id) ON DELETE SET NULL"))
    if "ticket_replies" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("ticket_replies")}
        if "is_internal" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE ticket_replies ADD COLUMN is_internal BOOLEAN NOT NULL DEFAULT FALSE"))
    if "tickets" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("tickets")}
        with engine.begin() as conn:
            if "team_id" not in existing:
                conn.execute(text("ALTER TABLE tickets ADD COLUMN team_id INTEGER REFERENCES teams(team_id) ON DELETE SET NULL"))
            if "active" not in existing:
                conn.execute(text("ALTER TABLE tickets ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE"))
            for timestamp_column in ("created_at", "status_changed_at"):
                if timestamp_column not in existing:
                    conn.execute(text(f"ALTER TABLE tickets ADD COLUMN {timestamp_column} TIMESTAMP WITHOUT TIME ZONE"))
                    conn.execute(text(f"UPDATE tickets SET {timestamp_column} = COALESCE(updated_at, CURRENT_TIMESTAMP) WHERE {timestamp_column} IS NULL"))
                    if engine.dialect.name == "postgresql":
                        conn.execute(text(f"ALTER TABLE tickets ALTER COLUMN {timestamp_column} SET DEFAULT CURRENT_TIMESTAMP"))
                        conn.execute(text(f"ALTER TABLE tickets ALTER COLUMN {timestamp_column} SET NOT NULL"))
    # Existing rows remain active by default; records are never physically removed by the UI.
    active_columns = {
        "contacts": "contact_id",
        "projects": "project_id",
        "plans": "plan_id",
        "service_catalog": "code_id",
        "teams": "team_id",
        "contracts": "contract_id",
        "assets": "asset_id",
    }
    for table_name in active_columns:
        if table_name in inspect(engine).get_table_names():
            existing = {col["name"] for col in inspect(engine).get_columns(table_name)}
            if "active" not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE"))
    if "plans" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("plans")}
        if "plan_type" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE plans ADD COLUMN plan_type VARCHAR(100) NOT NULL DEFAULT 'Standard'"))
                conn.execute(text("UPDATE plans SET plan_type = CASE LOWER(plan_name) WHEN 'standard' THEN 'Standard' WHEN 'premium' THEN 'Premium' WHEN 'enterprise' THEN 'Enterprise' WHEN 'vvip' THEN 'VVIP' ELSE 'Standard' END"))
    # Preserve each Agent's primary team and collapse any older multi-team links to one.
    if "user_team_memberships" in inspect(engine).get_table_names():
        db = SessionLocal()
        try:
            legacy_agents = db.scalars(select(User).where(User.role == "agent")).all()
            for agent in legacy_agents:
                primary_team_id = agent.team_id
                if primary_team_id is None:
                    primary_team_id = db.scalar(select(UserTeamMembership.team_id).where(
                        UserTeamMembership.user_id == agent.user_id).order_by(UserTeamMembership.team_id).limit(1))
                db.query(UserTeamMembership).filter(
                    UserTeamMembership.user_id == agent.user_id,
                    UserTeamMembership.team_id != primary_team_id if primary_team_id is not None else True
                ).delete(synchronize_session=False)
                if primary_team_id is not None:
                    agent.team_id = primary_team_id
                    exists = db.get(UserTeamMembership, (agent.user_id, primary_team_id))
                    if not exists:
                        db.add(UserTeamMembership(user_id=agent.user_id, team_id=primary_team_id))
                else:
                    agent.team_id = None
            db.commit()
        finally:
            db.close()


@app.on_event("startup")
async def startup() -> None:
    global _daily_summary_task, _email_retry_task, _scheduled_ticket_event_task
    Base.metadata.create_all(bind=engine)
    migrate_legacy_schema()
    seed_database()
    # Generate a one-time Admin password on fresh and already-seeded databases.
    ensure_initial_admin_password()
    # Keep the Support Team catalog available on both fresh and existing databases.
    # This function is idempotent: it adds missing defaults without replacing custom teams.
    ensure_default_support_teams()
    _daily_summary_task = asyncio.create_task(daily_summary_loop())
    _email_retry_task = asyncio.create_task(email_retry_loop())
    _scheduled_ticket_event_task = asyncio.create_task(scheduled_ticket_event_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _daily_summary_task, _email_retry_task, _scheduled_ticket_event_task
    for task in (_daily_summary_task, _email_retry_task, _scheduled_ticket_event_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _daily_summary_task = None
    _email_retry_task = None
    _scheduled_ticket_event_task = None


# Keep the original standalone HTML pages and CSS, now served on the API's origin.
app.mount("/", StaticFiles(directory=str(BASE_DIR), html=True), name="frontend")
