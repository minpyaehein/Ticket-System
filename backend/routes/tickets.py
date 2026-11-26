"""Tickets API endpoints."""
from __future__ import annotations
from ..common import *
from ..models import *
from ..security import *
from ..email_service import *
from ..resource_service import *

router = APIRouter()

@router.get("/api/tickets/{ticket_id}/replies")
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

@router.post("/api/tickets/{ticket_id}/accept-resolution")
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

@router.post("/api/tickets/{ticket_id}/reopen")
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

@router.post("/api/tickets/{ticket_id}/replies")
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

__all__ = ["router"]
