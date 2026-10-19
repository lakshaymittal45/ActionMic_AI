"""
Live Recording and Streaming router for ActionMic_AI.
Handles recording lifecycle (start/pause/resume/stop),
chunk-persisting WebSocket streaming, and live interim transcription.
"""
import json
import logging
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from app.services import audio_storage
from app.services import meeting_service
from app.services import transcription_service
from app.services import job_service
from app.db.mysql_connection import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings/{meeting_id}/recording", tags=["Live Recording"])


@router.post("/start")
def start_recording(meeting_id: int):
    """Mark meeting as actively recording."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_service.update_meeting(meeting_id, {
        "recording_status": "recording",
        "started_at": datetime.now()
    })
    return {"status": "recording", "meeting_id": meeting_id}


@router.post("/pause")
def pause_recording(meeting_id: int):
    """Pause live recording session."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_service.update_meeting(meeting_id, {
        "recording_status": "paused"
    })
    return {"status": "paused", "meeting_id": meeting_id}


@router.post("/resume")
def resume_recording(meeting_id: int):
    """Resume paused live recording session."""
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_service.update_meeting(meeting_id, {
        "recording_status": "recording"
    })
    return {"status": "recording", "meeting_id": meeting_id}


@router.post("/stop")
def stop_recording(meeting_id: int, background_tasks: BackgroundTasks):
    """
    Stop live recording, assemble all recorded chunks into a master audio file,
    and trigger the background meeting pipeline.
    """
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Assemble chunks
    assembled = audio_storage.assemble_recording_from_chunks(meeting_id)
    updates = {
        "recording_status": "stopped",
        "ended_at": datetime.now()
    }

    if assembled:
        updates["audio_storage_key"] = assembled["file_path"]
        updates["audio_mime_type"] = assembled["mime_type"]
        updates["audio_size_bytes"] = assembled["size_bytes"]
        updates["duration_seconds"] = assembled["duration_seconds"]
        updates["processing_status"] = "pending"

        # Record assembled asset
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO audio_assets (
                    meeting_id, asset_type, storage_backend, storage_key,
                    original_filename, mime_type, size_bytes, duration_seconds, checksum
                ) VALUES (%s, 'original', 'local', %s, 'master_recording.wav', 'audio/wav', %s, %s, %s)
            """
            cursor.execute(query, (
                meeting_id,
                assembled["file_path"],
                assembled["size_bytes"],
                assembled["duration_seconds"],
                assembled["checksum"]
            ))
            conn.commit()
            cursor.close()

        # Enqueue full pipeline (diarization, alignment, translation, intelligence)
        background_tasks.add_task(job_service.run_meeting_pipeline, meeting_id, assembled["file_path"])

    meeting_service.update_meeting(meeting_id, updates)

    return {
        "status": "stopped",
        "meeting_id": meeting_id,
        "assembled": assembled is not None,
        "details": assembled
    }


@router.websocket("/stream")
async def websocket_recording_stream(websocket: WebSocket, meeting_id: int):
    """
    Real-time audio streaming WebSocket for meeting recording.
    Persists audio chunks immediately to disk for crash-resilience.
    Emits live transcript tokens and status back to the client.
    """
    meeting = meeting_service.get_meeting(meeting_id)
    if not meeting:
        await websocket.close(code=4004, reason="Meeting not found")
        return

    await websocket.accept()
    logger.info(f"🎙️ WebSocket connected for meeting recording #{meeting_id}")

    chunk_index = 0
    buffer = bytearray()
    sample_rate = 16000
    chunk_bytes_threshold = sample_rate * 2 * 3  # ~3 seconds of 16-bit 16kHz mono audio

    try:
        meeting_service.update_meeting(meeting_id, {
            "recording_status": "recording",
            "started_at": datetime.now() if not meeting.get("started_at") else meeting.get("started_at")
        })

        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "meeting_id": meeting_id
        })

        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                chunk = message["bytes"]
                buffer.extend(chunk)

                # When buffer exceeds threshold, write chunk to disk
                if len(buffer) >= chunk_bytes_threshold:
                    chunk_data = bytes(buffer[:chunk_bytes_threshold])
                    buffer = buffer[chunk_bytes_threshold:]

                    # Persist chunk to disk
                    saved_chunk = audio_storage.save_audio_chunk(
                        meeting_id=meeting_id,
                        chunk_index=chunk_index,
                        pcm16_data=chunk_data,
                        sample_rate=sample_rate
                    )

                    # Track in audio_assets
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO audio_assets (
                                meeting_id, asset_type, storage_backend, storage_key,
                                chunk_index, size_bytes, duration_seconds
                            ) VALUES (%s, 'chunk', 'local', %s, %s, %s, %s)
                        """, (
                            meeting_id,
                            saved_chunk["chunk_path"],
                            chunk_index,
                            saved_chunk["size_bytes"],
                            saved_chunk["duration_seconds"]
                        ))
                        conn.commit()
                        cursor.close()

                    chunk_index += 1

                    # Send chunk acknowledgment
                    await websocket.send_json({
                        "type": "chunk_saved",
                        "chunk_index": chunk_index - 1,
                        "duration": saved_chunk["duration_seconds"]
                    })

            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    cmd = payload.get("command")
                    if cmd == "pause":
                        meeting_service.update_meeting(meeting_id, {"recording_status": "paused"})
                        await websocket.send_json({"type": "status", "status": "paused"})
                    elif cmd == "resume":
                        meeting_service.update_meeting(meeting_id, {"recording_status": "recording"})
                        await websocket.send_json({"type": "status", "status": "recording"})
                    elif cmd == "stop":
                        break
                except Exception:
                    pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for meeting #{meeting_id}")
    except Exception as e:
        logger.error(f"WebSocket error for meeting #{meeting_id}: {e}")
    finally:
        # Flush remaining buffer if any
        if buffer:
            saved_chunk = audio_storage.save_audio_chunk(
                meeting_id=meeting_id,
                chunk_index=chunk_index,
                pcm16_data=bytes(buffer),
                sample_rate=sample_rate
            )
            chunk_index += 1

        logger.info(f"WebSocket recording stream closed for meeting #{meeting_id}. Chunks saved: {chunk_index}")
