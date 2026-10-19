"""
Processing Job Service for ActionMic_AI.
Coordinates asynchronous end-to-end meeting processing:
audio enhancement, diarization, transcription, alignment,
multilingual variants (translation/transliteration), and meeting intelligence.
"""
import os
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.db.mysql_connection import get_db_connection
from app.services.meeting_service import update_meeting, get_meeting
from app.services.transcription_service import (
    add_transcript_segment,
    add_transcript_variant,
    transliterate_text,
    
)
from app.services.intelligence_service import extract_and_save_meeting_intelligence
from app.services.audio_storage import get_meeting_audio_path, get_audio_duration_seconds

logger = logging.getLogger(__name__)


def create_processing_job(
    meeting_id: int,
    job_type: str = "full_pipeline"
) -> int:
    """Register a new processing job in MySQL."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO processing_jobs (meeting_id, job_type, status, progress, started_at)
            VALUES (%s, %s, 'pending', 0.0, %s)
        """
        cursor.execute(query, (meeting_id, job_type, datetime.now()))
        conn.commit()
        job_id = cursor.lastrowid
        cursor.close()
    return job_id


def update_job_status(
    job_id: int,
    status: str,
    progress: float,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None
):
    """Update job progress and state."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        completed_at = datetime.now() if status in ["completed", "failed", "cancelled"] else None
        query = """
            UPDATE processing_jobs
            SET status = %s, progress = %s, error_code = %s, error_message = %s, completed_at = %s
            WHERE id = %s
        """
        cursor.execute(query, (status, progress, error_code, error_message, completed_at, job_id))
        conn.commit()
        cursor.close()


def get_meeting_jobs(meeting_id: int) -> List[Dict[str, Any]]:
    """Retrieve all jobs associated with a meeting."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM processing_jobs WHERE meeting_id = %s ORDER BY id DESC",
            (meeting_id,)
        )
        jobs = cursor.fetchall()
        cursor.close()
    return jobs


def run_meeting_pipeline(meeting_id: int, audio_path: Optional[str] = None) -> bool:
    """
    Main asynchronous pipeline for processing a meeting recording.
    Steps:
      1. Prepare audio (resolve path & duration)
      2. Run Diarization & Whisper Transcription
      3. Save transcript segments and speakers to DB
      4. Multilingual variants (transliterate & translate)
      5. Meeting Intelligence extraction (summary, decisions, actions, dates)
      6. Finalize statuses
    """
    job_id = create_processing_job(meeting_id, "full_pipeline")
    logger.info(f"🚀 Starting meeting processing pipeline [Job #{job_id}] for meeting #{meeting_id}")

    try:
        update_job_status(job_id, "running", 5.0)
        update_meeting(meeting_id, {"processing_status": "processing"})

        # Step 1: Resolve audio
        if not audio_path or not os.path.exists(audio_path):
            audio_path = get_meeting_audio_path(meeting_id)

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found for meeting {meeting_id}")

        duration = get_audio_duration_seconds(audio_path)
        if duration:
            update_meeting(meeting_id, {"duration_seconds": duration})

        update_job_status(job_id, "running", 20.0)

        # Step 2: Diarize and Transcribe
        from app.transcription.transcribe import diarize_and_transcribe_audio
        logger.info(f"Running diarization and transcription on {audio_path}")
        _, speaker_segments = diarize_and_transcribe_audio(audio_path)
        from app.transcription.transcribe import whisper_translate_audio
        translated_segments = whisper_translate_audio(audio_path, target_lang)

        update_job_status(job_id, "running", 60.0)

        # Step 3 & 4: Save Segments and Variants
        logger.info(f"Persisting {len(speaker_segments)} segments for meeting #{meeting_id}")
        meeting_data = get_meeting(meeting_id) or {}
        target_lang = meeting_data.get("target_language", "en")
        source_lang = meeting_data.get("source_language", "auto")

        for idx, seg in enumerate(speaker_segments):
            start_ms = int(float(seg.get("start", 0)) * 1000)
            end_ms = int(float(seg.get("end", 0)) * 1000)
            text = seg.get("text", "").strip()
            spk_label = seg.get("speaker") or "SPEAKER_00"

            if not text:
                continue

            saved_seg = add_transcript_segment(
                meeting_id=meeting_id,
                speaker_label=spk_label,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
                original_text=text,
                segment_index=idx
            )
            seg_id = saved_seg["id"]

            # Romanized transliteration (if non-ASCII Indic text)
            try:
                romanized = transliterate_text(text)
                if romanized and romanized.strip() != text:
                    add_transcript_variant(
                        transcript_segment_id=seg_id,
                        variant_type="transliteration",
                        text=romanized,
                        model_name="indic-transliterate"
                    )
            except Exception as e:
                logger.debug(f"Transliteration skipped: {e}")

            # Translation (if target is English or specified)
            try:
                translated = translated_segments[idx] if idx < len(translated_segments) else None
                if translated and translated.strip().lower() != text.lower():
                    add_transcript_variant(
                        transcript_segment_id=seg_id,
                        variant_type="translation",
                        text=translated,
                        target_language=target_lang,
                        model_name="whisper-translation"
                    )
            except Exception as e:
                logger.debug(f"Translation skipped: {e}")

        update_job_status(job_id, "running", 80.0)

        # Step 5: Meeting Intelligence (Summary, Actions, Decisions, etc.)
        logger.info(f"Extracting meeting intelligence for meeting #{meeting_id}")
        extract_and_save_meeting_intelligence(meeting_id)

        # Step 6: Mark Complete
        update_job_status(job_id, "completed", 100.0)
        update_meeting(meeting_id, {
            "processing_status": "completed",
            "status": "completed"
        })
        logger.info(f"🎉 Pipeline successfully completed for meeting #{meeting_id}")
        return True

    except Exception as e:
        err_msg = str(e)
        stack = traceback.format_exc()
        logger.error(f"❌ Meeting pipeline failed for meeting {meeting_id}: {err_msg}\n{stack}")
        update_job_status(job_id, "failed", 0.0, error_code="PROCESSING_ERROR", error_message=err_msg)
        update_meeting(meeting_id, {"processing_status": "failed"})
        return False
