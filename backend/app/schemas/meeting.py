"""
Pydantic schemas for ActionMic_AI meeting intelligence platform.
Defines request and response models for meetings, transcripts,
speakers, intelligence entities, and processing jobs.
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field


# =====================================================================
# USER SCHEMAS
# =====================================================================

class UserBase(BaseModel):
    name: str = "Host"
    email: Optional[str] = None

class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =====================================================================
# SPEAKER SCHEMAS
# =====================================================================

class SpeakerBase(BaseModel):
    speaker_label: str
    display_name: Optional[str] = None
    first_seen_ms: Optional[int] = None
    last_seen_ms: Optional[int] = None

class SpeakerUpdate(BaseModel):
    display_name: str

class SpeakerResponse(SpeakerBase):
    id: int
    meeting_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =====================================================================
# TRANSCRIPT SEGMENT & VARIANT SCHEMAS
# =====================================================================

class TranscriptVariantResponse(BaseModel):
    id: Optional[int] = None
    transcript_segment_id: int
    variant_type: str  # translation, transliteration, normalized
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    text: str
    model_name: Optional[str] = None
    confidence_score: Optional[float] = None

    class Config:
        from_attributes = True
        protected_namespaces = ()


class TranscriptSegmentCreate(BaseModel):
    speaker_id: Optional[int] = None
    speaker_label: Optional[str] = "SPEAKER_00"
    start_time_ms: int
    end_time_ms: int
    original_text: str
    normalized_text: Optional[str] = None
    language_code: Optional[str] = "auto"
    confidence_score: Optional[float] = 1.0
    is_final: bool = True
    segment_index: Optional[int] = 0


class TranscriptSegmentUpdate(BaseModel):
    original_text: Optional[str] = None
    speaker_label: Optional[str] = None


class TranscriptSegmentResponse(BaseModel):
    id: int
    meeting_id: int
    speaker_id: Optional[int] = None
    speaker_label: Optional[str] = "SPEAKER_00"
    start_time_ms: int
    end_time_ms: int
    original_text: str
    normalized_text: Optional[str] = None
    language_code: Optional[str] = None
    confidence_score: Optional[float] = None
    is_final: bool = True
    segment_index: Optional[int] = None
    created_at: Optional[datetime] = None
    variants: List[TranscriptVariantResponse] = []

    class Config:
        from_attributes = True


# =====================================================================
# INTELLIGENCE SCHEMAS
# =====================================================================

class MeetingSummaryResponse(BaseModel):
    id: int
    meeting_id: int
    summary_type: str = "final"
    content: Optional[str] = None
    structured_content_json: Optional[Dict[str, Any]] = None
    model_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        protected_namespaces = ()


class KeyPointResponse(BaseModel):
    id: int
    meeting_id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    importance: str = "medium"
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DecisionResponse(BaseModel):
    id: int
    meeting_id: int
    description: str
    rationale: Optional[str] = None
    decision_status: str = "agreed"
    confirmation_status: str = "unconfirmed"
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ActionItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str = "medium"
    status: str = "pending"


class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    confirmation_status: Optional[str] = None


class ActionItemResponse(BaseModel):
    id: int
    meeting_id: int
    title: str
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    due_at: Optional[datetime] = None
    timezone: str = "Asia/Kolkata"
    priority: str = "medium"
    status: str = "pending"
    confirmation_status: str = "ai_generated"
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScheduledEventResponse(BaseModel):
    id: int
    meeting_id: int
    title: str
    description: Optional[str] = None
    original_date_expression: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    timezone: str = "Asia/Kolkata"
    resolution_status: str = "unresolved"
    confirmation_status: str = "ai_generated"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FollowUpResponse(BaseModel):
    id: int
    meeting_id: int
    title: str
    description: Optional[str] = None
    responsible_person: Optional[str] = None
    status: str = "open"
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MeetingIntelligenceResponse(BaseModel):
    summary: Optional[MeetingSummaryResponse] = None
    key_points: List[KeyPointResponse] = []
    decisions: List[DecisionResponse] = []
    action_items: List[ActionItemResponse] = []
    scheduled_events: List[ScheduledEventResponse] = []
    follow_ups: List[FollowUpResponse] = []


# =====================================================================
# MEETING SCHEMAS
# =====================================================================

class MeetingCreate(BaseModel):
    title: str = "Untitled Meeting"
    description: Optional[str] = None
    source_type: str = "live"  # live, upload, imported
    platform: Optional[str] = "google_meet"  # google_meet, zoom, whatsapp, teams, in_person, custom
    source_language: str = "auto"
    target_language: str = "en"
    meeting_date: Optional[datetime] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    platform: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    status: Optional[str] = None
    recording_status: Optional[str] = None
    processing_status: Optional[str] = None


class MeetingResponse(BaseModel):
    id: int
    user_id: Optional[int] = 1
    title: str
    description: Optional[str] = None
    meeting_date: Optional[datetime] = None
    timezone: str = "Asia/Kolkata"
    duration_seconds: Optional[float] = None
    status: str = "draft"
    source_type: str = "live"
    platform: Optional[str] = "google_meet"
    source_language: str = "auto"
    target_language: str = "en"
    recording_status: str = "idle"
    processing_status: str = "pending"
    audio_storage_key: Optional[str] = None
    audio_mime_type: Optional[str] = None
    audio_size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    speaker_count: Optional[int] = 0
    segment_count: Optional[int] = 0

    class Config:
        from_attributes = True


class MeetingDetailResponse(MeetingResponse):
    speakers: List[SpeakerResponse] = []
    intelligence: Optional[MeetingIntelligenceResponse] = None


class MeetingListResponse(BaseModel):
    total: int
    items: List[MeetingResponse]
    page: int = 1
    page_size: int = 50


# =====================================================================
# PROCESSING JOB SCHEMAS
# =====================================================================

class ProcessingJobResponse(BaseModel):
    id: int
    meeting_id: int
    job_type: str
    status: str
    attempt_count: int = 0
    max_attempts: int = 3
    progress: float = 0.0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
