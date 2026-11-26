"""Application startup and shutdown tasks."""
from __future__ import annotations
from .common import *
from .config import *
from .database import *
from .models import *
from .security import *
from .email_service import *
from .seed import *
from .sla import *
from .migration import *

_daily_summary_task: asyncio.Task | None = None
_email_retry_task: asyncio.Task | None = None
_scheduled_ticket_event_task: asyncio.Task | None = None

def register_lifecycle(app: FastAPI) -> None:
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
