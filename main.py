"""FastAPI application entry point for the Golden Pride Ticket Service System."""
from __future__ import annotations
from backend.common import *
from backend.config import BASE_DIR, SESSION_SECRET, logger
from backend.lifecycle import register_lifecycle
from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.notifications import router as notifications_router
from backend.routes.email import router as email_router
from backend.routes.tickets import router as tickets_router
from backend.routes.resources import router as resources_router

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

# Keep route registration order stable: specific endpoints are registered before
# the generic /api/{resource} routes.
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(notifications_router)
app.include_router(email_router)
app.include_router(tickets_router)
app.include_router(resources_router)
register_lifecycle(app)

# Keep the existing standalone HTML pages and CSS served from the same origin.
app.mount("/", StaticFiles(directory=str(BASE_DIR), html=True), name="frontend")
