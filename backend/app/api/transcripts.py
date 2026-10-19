"""
Transcripts API router for ActionMic_AI.
Endpoints for fetching segments, updating speaker labels, and multi-format exports.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from app.schemas.meeting import (
    TranscriptSegmentResponse,
    TranscriptSegmentCreate,
    SpeakerUpdate,
    SpeakerResponse
)
from app.services import transcription_service
from app.services import meeting_service

router = APIRouter(prefix="/meetings/{meeting_id}", tags=["Transcripts"])


@router.get("/transcript", response_model=List[TranscriptSegmentResponse])
def get_transcript(meeting_id: int):
    """Retrieve full chronological transcript segments with translations & transliterations."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    segments = transcription_service.get_meeting_segments(meeting_id, include_variants=True)
    return segments


@router.post("/transcript/segments", response_model=TranscriptSegmentResponse, status_code=201)
def add_segment(meeting_id: int, payload: TranscriptSegmentCreate):
    """Manually add or append a transcript segment."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    segment = transcription_service.add_transcript_segment(
        meeting_id=meeting_id,
        start_time_ms=payload.start_time_ms,
        end_time_ms=payload.end_time_ms,
        original_text=payload.original_text,
        speaker_label=payload.speaker_label,
        normalized_text=payload.normalized_text,
        language_code=payload.language_code,
        confidence_score=payload.confidence_score,
        is_final=payload.is_final,
        segment_index=payload.segment_index
    )
    return segment


@router.patch("/speakers/{speaker_id}", response_model=SpeakerResponse)
def update_speaker_name(meeting_id: int, speaker_id: int, payload: SpeakerUpdate):
    """Rename a speaker's display name across the meeting."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    speaker = meeting_service.update_speaker_display_name(speaker_id, payload.display_name)
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return speaker


@router.get("/export")
def export_meeting_transcript(
    meeting_id: int,
    format: str = Query("markdown", regex="^(markdown|txt|srt|vtt|json)$")
):
    """
    Export meeting transcript in various formats:
    - markdown: Formatted notes with headers and quotes
    - txt: Simple speaker + timestamp dialogue
    - srt: Standard subtitle format with millisecond timing
    - vtt: WebVTT for web video/audio players
    - json: Structured array of segments
    """
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    segments = transcription_service.get_meeting_segments(meeting_id, include_variants=True)
    clean_title = "".join(c for c in meeting.get("title", "meeting") if c.isalnum() or c in ("-", "_")).rstrip()

    if format == "json":
        return {
            "meeting": meeting,
            "segments": segments
        }
    elif format == "markdown":
        md_content = transcription_service.export_transcript_markdown(meeting, segments)
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{clean_title}.md"'}
        )
    elif format == "txt":
        txt_content = transcription_service.export_transcript_txt(meeting, segments)
        return Response(
            content=txt_content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{clean_title}.txt"'}
        )
    elif format == "srt":
        srt_content = transcription_service.export_transcript_srt(segments)
        return Response(
            content=srt_content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{clean_title}.srt"'}
        )
    elif format == "vtt":
        vtt_content = transcription_service.export_transcript_vtt(segments)
        return Response(
            content=vtt_content,
            media_type="text/vtt",
            headers={"Content-Disposition": f'attachment; filename="{clean_title}.vtt"'}
        )
