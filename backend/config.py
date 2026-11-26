"""Config logic for Golden Pride."""
from __future__ import annotations
from .common import *

BASE_DIR = Path(__file__).resolve().parent.parent

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

APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")

engine_options: dict[str, Any] = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

SESSION_SECRET = os.getenv("SESSION_SECRET", "replace-this-secret-before-deployment-" + secrets.token_hex(16))

APP_BOOT_ID = secrets.token_urlsafe(24)

LOGIN_ATTEMPT_WINDOW_SECONDS = 60.0

LOGIN_MAX_FAILED_ATTEMPTS = 5

LOGIN_LOCKOUT_SECONDS = 60.0

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

logger = logging.getLogger("golden_pride.database")

__all__ = [name for name in globals() if not name.startswith("__")]
