"""Migration logic for Golden Pride."""
from __future__ import annotations
from .common import *
from .config import *
from .models import *

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

__all__ = [name for name in globals() if not name.startswith("__")]
