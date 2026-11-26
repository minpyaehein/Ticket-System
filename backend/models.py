"""Models logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .database import *

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

__all__ = [name for name in globals() if not name.startswith("__")]
