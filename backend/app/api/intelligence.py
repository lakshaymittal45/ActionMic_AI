"""
Intelligence API router for ActionMic_AI.
Endpoints for viewing and updating meeting summaries, key points,
decisions, action items, scheduled events, and follow-ups.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.schemas.meeting import (
    MeetingIntelligenceResponse,
    ActionItemCreate,
    ActionItemUpdate,
    ActionItemResponse
)
from app.services import intelligence_service
from app.services import meeting_service
from app.db.mysql_connection import get_db_connection

router = APIRouter(prefix="/meetings/{meeting_id}/intelligence", tags=["Meeting Intelligence"])


@router.get("", response_model=MeetingIntelligenceResponse)
def get_intelligence(meeting_id: int):
    """Get all structured intelligence for a meeting."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    intelligence = intelligence_service.get_meeting_intelligence(meeting_id)
    return intelligence


@router.post("/regenerate")
def regenerate_intelligence(meeting_id: int, background_tasks: BackgroundTasks):
    """Trigger re-extraction of meeting intelligence via LLM."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    background_tasks.add_task(intelligence_service.extract_and_save_meeting_intelligence, meeting_id)
    return {
        "status": "queued",
        "message": f"Intelligence extraction re-queued for meeting {meeting_id}"
    }


@router.post("/action-items", response_model=ActionItemResponse, status_code=201)
def create_action_item(meeting_id: int, payload: ActionItemCreate):
    """Manually add an action item to a meeting."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            INSERT INTO action_items (
                meeting_id, title, description, assignee_name, due_at,
                priority, status, confirmation_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'user_confirmed')
        """
        cursor.execute(query, (
            meeting_id, payload.title, payload.description,
            payload.assignee_name, payload.due_at,
            payload.priority, payload.status
        ))
        conn.commit()
        item_id = cursor.lastrowid
        cursor.execute("SELECT * FROM action_items WHERE id = %s", (item_id,))
        item = cursor.fetchone()
        cursor.close()

    return item


@router.patch("/action-items/{item_id}", response_model=ActionItemResponse)
def update_action_item(meeting_id: int, item_id: int, payload: ActionItemUpdate):
    """Update action item status (e.g. mark completed), assignee, priority, or deadline."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM action_items WHERE id = %s AND meeting_id = %s", (item_id, meeting_id))
        item = cursor.fetchone()
        if not item:
            cursor.close()
            raise HTTPException(status_code=404, detail="Action item not found")

        # Handle completion timestamp
        if updates.get("status") == "completed" and item.get("status") != "completed":
            updates["completed_at"] = datetime.now()
        elif updates.get("status") and updates.get("status") != "completed":
            updates["completed_at"] = None

        set_clauses = [f"{k} = %s" for k in updates.keys()]
        values = list(updates.values()) + [item_id]

        cursor.execute(f"UPDATE action_items SET {', '.join(set_clauses)} WHERE id = %s", values)
        conn.commit()
        cursor.execute("SELECT * FROM action_items WHERE id = %s", (item_id,))
        updated_item = cursor.fetchone()
        cursor.close()

    return updated_item


@router.delete("/action-items/{item_id}")
def delete_action_item(meeting_id: int, item_id: int):
    """Delete an action item."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_items WHERE id = %s AND meeting_id = %s", (item_id, meeting_id))
        conn.commit()
        cursor.close()
    return {"status": "success", "message": f"Action item {item_id} deleted"}
