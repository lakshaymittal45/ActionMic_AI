"""
Meeting Service for ActionMic_AI.
Handles database operations, meeting lifecycle, speaker registry,
and audit logging using the connection pool.
"""
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from app.db.mysql_connection import get_db_connection

logger = logging.getLogger(__name__)


# =====================================================================
# AUDIT LOGGING
# =====================================================================

def log_audit(
    meeting_id: Optional[int],
    entity_type: str,
    entity_id: Optional[int],
    action: str,
    changes: Optional[Dict[str, Any]] = None,
    user_id: int = 1
):
    """Write an audit entry into meeting_audit_logs."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO meeting_audit_logs
                (meeting_id, user_id, entity_type, entity_id, action, changes_json)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                meeting_id,
                user_id,
                entity_type,
                entity_id,
                action,
                json.dumps(changes or {}, default=str)
            ))
            conn.commit()
            cursor.close()
    except Exception as e:
        logger.warning(f"Failed to record audit log: {e}")


# =====================================================================
# MEETING CRUD
# =====================================================================

def create_meeting(
    title: str = "Untitled Meeting",
    description: Optional[str] = None,
    source_type: str = "live",
    platform: Optional[str] = "google_meet",
    source_language: str = "auto",
    target_language: str = "en",
    meeting_date: Optional[datetime] = None,
    user_id: int = 1
) -> Dict[str, Any]:
    """Create a new meeting record in the database."""
    if meeting_date is None:
        meeting_date = datetime.now()

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            INSERT INTO meetings (
                user_id, title, description, meeting_date,
                source_type, platform, source_language, target_language,
                status, recording_status, processing_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', 'idle', 'pending')
        """
        cursor.execute(query, (
            user_id, title, description, meeting_date,
            source_type, platform or "google_meet", source_language, target_language
        ))
        conn.commit()
        meeting_id = cursor.lastrowid
        cursor.close()

    log_audit(meeting_id, "meeting", meeting_id, "created", {
        "title": title,
        "source_type": source_type,
        "source_language": source_language
    })

    return get_meeting(meeting_id)


def get_meeting(meeting_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve meeting by ID, including speaker and segment counts."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT m.*,
                   (SELECT COUNT(*) FROM speakers WHERE meeting_id = m.id) AS speaker_count,
                   (SELECT COUNT(*) FROM transcript_segments WHERE meeting_id = m.id) AS segment_count
            FROM meetings m
            WHERE m.id = %s
        """
        cursor.execute(query, (meeting_id,))
        meeting = cursor.fetchone()
        cursor.close()

    return meeting


def list_meetings(
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None
) -> Tuple[int, List[Dict[str, Any]]]:
    """List meetings with pagination and search filter."""
    offset = (page - 1) * page_size
    conditions = ["status != 'deleted'"]
    params: List[Any] = []

    if search:
        conditions.append("(title LIKE %s OR description LIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])

    if status and status != "all":
        conditions.append("status = %s")
        params.append(status)

    if source_type and source_type != "all":
        conditions.append("source_type = %s")
        params.append(source_type)

    where_clause = " AND ".join(conditions)

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        # Count total
        count_query = f"SELECT COUNT(*) AS total FROM meetings WHERE {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()["total"]

        # Fetch page items
        query = f"""
            SELECT m.*,
                   (SELECT COUNT(*) FROM speakers WHERE meeting_id = m.id) AS speaker_count,
                   (SELECT COUNT(*) FROM transcript_segments WHERE meeting_id = m.id) AS segment_count
            FROM meetings m
            WHERE {where_clause}
            ORDER BY m.meeting_date DESC, m.id DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, params + [page_size, offset])
        items = cursor.fetchall()
        cursor.close()

    return total, items


def update_meeting(meeting_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update editable meeting fields."""
    allowed_fields = [
        "title", "description", "platform", "status", "recording_status",
        "processing_status", "source_language", "target_language",
        "duration_seconds", "audio_storage_key", "audio_mime_type",
        "audio_size_bytes", "started_at", "ended_at"
    ]
    fields_to_update = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}

    if not fields_to_update:
        return get_meeting(meeting_id)

    set_clauses = [f"{k} = %s" for k in fields_to_update.keys()]
    values = list(fields_to_update.values()) + [meeting_id]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = f"UPDATE meetings SET {', '.join(set_clauses)} WHERE id = %s"
        cursor.execute(query, values)
        conn.commit()
        cursor.close()

    log_audit(meeting_id, "meeting", meeting_id, "updated", fields_to_update)
    return get_meeting(meeting_id)


def delete_meeting(meeting_id: int) -> bool:
    """Soft-delete a meeting."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE meetings SET status = 'deleted' WHERE id = %s", (meeting_id,))
        conn.commit()
        cursor.close()

    log_audit(meeting_id, "meeting", meeting_id, "deleted")
    return True


# =====================================================================
# SPEAKER REGISTRY
# =====================================================================

def get_or_create_speaker(
    meeting_id: int,
    speaker_label: str,
    display_name: Optional[str] = None
) -> Dict[str, Any]:
    """Get existing speaker by label or register a new one."""
    clean_label = speaker_label.strip() or "SPEAKER_00"
    if display_name is None:
        display_name = clean_label.replace("_", " ").title()

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM speakers WHERE meeting_id = %s AND speaker_label = %s",
            (meeting_id, clean_label)
        )
        speaker = cursor.fetchone()

        if not speaker:
            insert_query = """
                INSERT INTO speakers (meeting_id, speaker_label, display_name)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (meeting_id, clean_label, display_name))
            conn.commit()
            speaker_id = cursor.lastrowid
            cursor.execute("SELECT * FROM speakers WHERE id = %s", (speaker_id,))
            speaker = cursor.fetchone()

        cursor.close()

    return speaker


def list_speakers(meeting_id: int) -> List[Dict[str, Any]]:
    """List all registered speakers for a meeting."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM speakers WHERE meeting_id = %s ORDER BY id ASC",
            (meeting_id,)
        )
        speakers = cursor.fetchall()
        cursor.close()
    return speakers


def update_speaker_display_name(
    speaker_id: int,
    display_name: str
) -> Optional[Dict[str, Any]]:
    """Update speaker display name and update transcript segments."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "UPDATE speakers SET display_name = %s WHERE id = %s",
            (display_name, speaker_id)
        )
        conn.commit()
        cursor.execute("SELECT * FROM speakers WHERE id = %s", (speaker_id,))
        speaker = cursor.fetchone()
        cursor.close()

    return speaker
