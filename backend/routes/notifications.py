"""Notifications API endpoints."""
from __future__ import annotations
from ..common import *
from ..models import *
from ..security import *

router = APIRouter()

@router.get("/api/notification-preferences")
def get_notification_preferences(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, Any]:
    row = db.get(UserNotificationPreference, actor["user_id"])
    values = _default_user_notification_preferences(actor["role"])
    if row:
        try: values.update({k: bool(v) for k, v in json.loads(row.settings_json or "{}").items() if k in values})
        except (json.JSONDecodeError, AttributeError): pass
    return {"preferences": values}

@router.put("/api/notification-preferences")
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

@router.get("/api/notifications")
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

@router.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    row = db.get(NotificationItem, notification_id)
    if not row or row.user_id != actor["user_id"]:
        raise HTTPException(status_code=404, detail="Notification not found.")
    row.is_read = True
    db.commit()
    return {"message": "Notification marked as read."}

@router.post("/api/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), actor: dict[str, Any] = Depends(get_actor)) -> dict[str, str]:
    db.query(NotificationItem).filter(NotificationItem.user_id == actor["user_id"], NotificationItem.is_read.is_(False)).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read."}

__all__ = ["router"]
