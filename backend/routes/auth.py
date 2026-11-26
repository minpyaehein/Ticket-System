"""Auth API endpoints."""
from __future__ import annotations
from ..common import *
from ..config import *
from ..models import *
from ..security import *
from ..email_service import *

router = APIRouter()

@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/login.html")

@router.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}

@router.post("/api/auth/login")
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

@router.get("/api/auth/me")
def me(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user_id = _require_current_server_session(request)
    user = db.get(User, int(user_id))
    if not user or not user.active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your session is no longer valid. Please sign in again.")
    return {**_user_team_context(db, user), "must_change_password": bool(user.must_change_password)}

@router.post("/api/auth/logout")
def logout(request: Request, actor: dict[str, Any] = Depends(get_actor), db: Session = Depends(get_db)) -> dict[str, str]:
    log_action(db, actor, "LOGOUT", "Authentication", "Signed out", request=request, entity_id=actor.get("user_id"), entity_label=actor.get("email"))
    db.commit()
    request.session.clear()
    return {"message": "Signed out successfully."}

@router.post("/api/auth/change-password")
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

@router.post("/api/users/{user_id}/reset-password")
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

__all__ = ["router"]
