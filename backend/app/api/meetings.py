"""
Meetings API router for ActionMic_AI.
Endpoints for meeting CRUD, status updates, and pipeline triggering.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from app.schemas.meeting import (
    MeetingCreate,
    MeetingUpdate,
    MeetingResponse,
    MeetingDetailResponse,
    MeetingListResponse,
    ProcessingJobResponse
)
from app.services import meeting_service
from app.services import intelligence_service
from app.services import job_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


@router.post("", response_model=MeetingResponse, status_code=201)
def create_meeting(payload: MeetingCreate):
    """Create a new meeting session."""
    meeting = meeting_service.create_meeting(
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        platform=payload.platform,
        source_language=payload.source_language,
        target_language=payload.target_language,
        meeting_date=payload.meeting_date
    )
    return meeting


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None
):
    """List meetings with pagination and search."""
    total, items = meeting_service.list_meetings(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        source_type=source_type
    )
    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size
    }


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
def get_meeting_detail(meeting_id: int):
    """Get complete meeting details including speakers and intelligence."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    speakers = meeting_service.list_speakers(meeting_id)
    intelligence = intelligence_service.get_meeting_intelligence(meeting_id)

    meeting_dict = dict(meeting)
    meeting_dict["speakers"] = speakers
    meeting_dict["intelligence"] = intelligence
    return meeting_dict


@router.patch("/{meeting_id}", response_model=MeetingResponse)
def update_meeting(meeting_id: int, payload: MeetingUpdate):
    """Update meeting title, description, languages, or status."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    updated = meeting_service.update_meeting(
        meeting_id,
        payload.model_dump(exclude_unset=True)
    )
    return updated


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: int):
    """Soft delete a meeting."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_service.delete_meeting(meeting_id)
    return {"status": "success", "message": f"Meeting {meeting_id} deleted"}


@router.post("/{meeting_id}/process")
def trigger_processing(meeting_id: int, background_tasks: BackgroundTasks):
    """Trigger or re-run the full transcription and intelligence pipeline."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_service.update_meeting(meeting_id, {
        "processing_status": "pending"
    })
    background_tasks.add_task(job_service.run_meeting_pipeline, meeting_id)
    return {
        "status": "queued",
        "message": f"Pipeline queued for meeting {meeting_id}"
    }


@router.get("/{meeting_id}/jobs")
def get_jobs(meeting_id: int):
    """Get all background processing jobs for a meeting."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    jobs = job_service.get_meeting_jobs(meeting_id)
    return {"meeting_id": meeting_id, "jobs": jobs}
