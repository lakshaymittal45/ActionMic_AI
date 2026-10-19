"""
Audio API router for ActionMic_AI.
Endpoints for audio file uploads, HTTP 206 range-based audio streaming,
and audio downloads.
"""
import os
import re
import mimetypes
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Header, Response, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from app.services import audio_storage
from app.services import meeting_service
from app.services import job_service
from app.db.mysql_connection import get_db_connection

router = APIRouter(prefix="/meetings/{meeting_id}/audio", tags=["Audio Management"])
MAX_MEDIA_BYTES = 2 * 1024 * 1024 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".webm", ".ogg", ".mp4", ".mov", ".avi", ".mkv", ".m4v"}


@router.post("/upload")
async def upload_meeting_audio(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload an existing audio or video recording for a meeting. Video uploads
    are converted to a normalized WAV track before processing.
    Saves audio to local storage, tracks in audio_assets table,
    and automatically starts the background pipeline.
    """
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty media file")
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported media format")
    if len(content) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="Media file exceeds the 2 GB upload limit")

    # Save to dedicated meeting directory
    try:
        meta = audio_storage.save_uploaded_media(
            meeting_id=meeting_id,
            filename=file.filename or "recording.wav",
            content=content,
            mime_type=file.content_type
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Record in audio_assets table
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO audio_assets (
                meeting_id, asset_type, storage_backend, storage_key,
                original_filename, mime_type, size_bytes, duration_seconds, checksum
            ) VALUES (%s, 'original', 'local', %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            meeting_id,
            meta["file_path"],
            meta["original_filename"],
            meta["mime_type"],
            meta["size_bytes"],
            meta["duration_seconds"],
            meta["checksum"]
        ))
        conn.commit()
        cursor.close()

    # Update meeting metadata
    meeting_service.update_meeting(meeting_id, {
        "audio_storage_key": meta["file_path"],
        "audio_mime_type": meta["mime_type"],
        "audio_size_bytes": meta["size_bytes"],
        "duration_seconds": meta["duration_seconds"],
        "source_type": "upload",
        "processing_status": "pending"
    })

    # Automatically queue background transcription & intelligence
    background_tasks.add_task(job_service.run_meeting_pipeline, meeting_id, meta["file_path"])

    return {
        "status": "success",
        "message": "Video converted to audio and queued for processing" if meta.get("source_media_type") == "video" else "Audio uploaded successfully and queued for processing",
        "audio": meta
    }


def send_bytes_range_requests(
    file_path: str,
    range_header: str,
    content_type: str = "audio/wav"
) -> Response:
    """Helper to serve partial content (HTTP 206) for seeking in HTML5 audio players."""
    file_size = os.path.getsize(file_path)
    
    # Parse range header: e.g. "bytes=0-1000"
    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return Response(status_code=416, content="Requested Range Not Satisfiable")

    start_str, end_str = range_match.groups()
    start = int(start_str)
    end = int(end_str) if end_str else file_size - 1

    if start >= file_size or end >= file_size:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    chunk_size = (end - start) + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = chunk_size
            while bytes_left > 0:
                read_size = min(bytes_left, 65536)
                data = f.read(read_size)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": content_type,
    }
    return StreamingResponse(iter_file(), status_code=206, headers=headers)


@router.get("/stream")
def stream_audio(meeting_id: int, request: Request):
    """
    Stream meeting audio with full byte-range support for HTML5 playback and scrubbing.
    """
    audio_path = audio_storage.get_meeting_audio_path(meeting_id)
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio recording not found for this meeting")

    mime_type, _ = mimetypes.guess_type(audio_path)
    mime_type = mime_type or "audio/wav"

    range_header = request.headers.get("Range")
    if range_header:
        return send_bytes_range_requests(audio_path, range_header, mime_type)

    return FileResponse(
        audio_path,
        media_type=mime_type,
        headers={"Accept-Ranges": "bytes"}
    )


@router.get("/download")
def download_audio(meeting_id: int):
    """Download meeting audio file as an attachment."""
    audio_path = audio_storage.get_meeting_audio_path(meeting_id)
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio recording not found")

    filename = os.path.basename(audio_path)
    return FileResponse(
        audio_path,
        filename=filename,
        media_type="application/octet-stream"
    )
