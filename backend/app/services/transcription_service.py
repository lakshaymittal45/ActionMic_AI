"""
Transcription Service for ActionMic_AI.
Handles segment persistence, translation/transliteration variants,
speaker alignment, and multi-format export (JSON, Markdown, TXT, SRT, VTT).
"""
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.db.mysql_connection import get_db_connection
from app.services.meeting_service import get_or_create_speaker

logger = logging.getLogger(__name__)


# =====================================================================
# SEGMENT PERSISTENCE
# =====================================================================

def add_transcript_segment(
    meeting_id: int,
    start_time_ms: int,
    end_time_ms: int,
    original_text: str,
    speaker_label: Optional[str] = "SPEAKER_00",
    normalized_text: Optional[str] = None,
    language_code: Optional[str] = "auto",
    confidence_score: Optional[float] = 1.0,
    is_final: bool = True,
    segment_index: Optional[int] = None
) -> Dict[str, Any]:
    """Persist an individual transcript segment with its speaker."""
    speaker = get_or_create_speaker(meeting_id, speaker_label or "SPEAKER_00")
    speaker_id = speaker["id"]

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        if segment_index is None:
            cursor.execute(
                "SELECT COALESCE(MAX(segment_index), -1) + 1 AS next_idx FROM transcript_segments WHERE meeting_id = %s",
                (meeting_id,)
            )
            segment_index = cursor.fetchone()["next_idx"]

        query = """
            INSERT INTO transcript_segments (
                meeting_id, speaker_id, speaker_label, start_time_ms, end_time_ms,
                original_text, normalized_text, language_code, confidence_score,
                is_final, segment_index
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            meeting_id, speaker_id, speaker_label, start_time_ms, end_time_ms,
            original_text.strip(), normalized_text, language_code,
            confidence_score, is_final, segment_index
        ))
        conn.commit()
        segment_id = cursor.lastrowid

        cursor.execute("SELECT * FROM transcript_segments WHERE id = %s", (segment_id,))
        segment = cursor.fetchone()
        cursor.close()

    segment["variants"] = []
    return segment


def add_transcript_variant(
    transcript_segment_id: int,
    variant_type: str,  # 'translation', 'transliteration', 'normalized'
    text: str,
    target_language: Optional[str] = "en",
    source_language: Optional[str] = None,
    model_name: Optional[str] = None,
    confidence_score: Optional[float] = 1.0
) -> Dict[str, Any]:
    """Add or update a translation/transliteration variant for a segment."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            INSERT INTO transcript_variants (
                transcript_segment_id, variant_type, source_language,
                target_language, text, model_name, confidence_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                text = VALUES(text),
                confidence_score = VALUES(confidence_score),
                model_name = VALUES(model_name)
        """
        cursor.execute(query, (
            transcript_segment_id, variant_type, source_language,
            target_language, text.strip(), model_name, confidence_score
        ))
        conn.commit()
        variant_id = cursor.lastrowid
        cursor.execute("SELECT * FROM transcript_variants WHERE id = %s", (variant_id,))
        variant = cursor.fetchone()
        cursor.close()

    return variant


def get_meeting_segments(
    meeting_id: int,
    include_variants: bool = True
) -> List[Dict[str, Any]]:
    """Fetch all transcript segments for a meeting in chronological order with variants."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT ts.*, s.display_name AS speaker_name
            FROM transcript_segments ts
            LEFT JOIN speakers s ON ts.speaker_id = s.id
            WHERE ts.meeting_id = %s
            ORDER BY ts.start_time_ms ASC, ts.id ASC
        """
        cursor.execute(query, (meeting_id,))
        segments = cursor.fetchall()

        if include_variants and segments:
            seg_ids = [s["id"] for s in segments]
            format_strings = ",".join(["%s"] * len(seg_ids))
            var_query = f"""
                SELECT * FROM transcript_variants
                WHERE transcript_segment_id IN ({format_strings})
                ORDER BY id ASC
            """
            cursor.execute(var_query, seg_ids)
            variants = cursor.fetchall()

            # Group variants by segment
            var_map: Dict[int, List[Dict[str, Any]]] = {}
            for v in variants:
                sid = v["transcript_segment_id"]
                var_map.setdefault(sid, []).append(v)

            for seg in segments:
                seg["variants"] = var_map.get(seg["id"], [])
        else:
            for seg in segments:
                seg["variants"] = []

        cursor.close()

    return segments


# =====================================================================
# MULTILINGUAL HELPERS: TRANSLATION & TRANSLITERATION
# =====================================================================

def transliterate_text(text: str, source_lang: str = "hi") -> Optional[str]:
    """Transliterate Indic text with the established Indic library backend."""
    if not text or not text.strip():
        return None
    try:
        from app.transcription.offline_indic import transliterate_indic_text
        return transliterate_indic_text(text, source_lang=source_lang)
    except Exception as e:
        logger.debug(f"Transliteration fallback warning: {e}")
        return None


def translate_text(text: str, target_lang: str = "en", source_lang: str = "auto") -> Optional[str]:
    """Text-only translation is intentionally disabled; use Whisper audio translation."""
    return None


# =====================================================================
# MULTI-FORMAT EXPORTERS
# =====================================================================

def ms_to_timestamp(ms: int, srt_format: bool = True) -> str:
    """Format milliseconds into HH:MM:SS,mmm or HH:MM:SS.mmm."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    sep = "," if srt_format else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{milliseconds:03d}"


def export_transcript_markdown(meeting_info: Dict[str, Any], segments: List[Dict[str, Any]]) -> str:
    """Export meeting transcript as beautiful Markdown."""
    title = meeting_info.get("title", "Meeting Transcript")
    date_str = str(meeting_info.get("meeting_date") or datetime.now().strftime("%Y-%m-%d %H:%M"))

    lines = [
        f"# {title}",
        f"**Date**: {date_str}  ",
        f"**Source Language**: {meeting_info.get('source_language', 'auto')}  ",
        f"**Duration**: {meeting_info.get('duration_seconds', 0)} seconds  \n",
        "---",
        "## Transcript\n"
    ]

    current_speaker = None
    for seg in segments:
        speaker = seg.get("speaker_name") or seg.get("speaker_label") or "Speaker"
        start_str = ms_to_timestamp(seg.get("start_time_ms", 0), srt_format=False)

        if speaker != current_speaker:
            lines.append(f"\n### {speaker} `[{start_str}]`")
            current_speaker = speaker

        text = seg.get("original_text", "")
        lines.append(f"{text}")

        # Check for translation variant
        for v in seg.get("variants", []):
            if v.get("variant_type") == "translation":
                lines.append(f"> *[Translation]* {v.get('text', '')}")
            elif v.get("variant_type") == "transliteration":
                lines.append(f"> *[Romanized]* {v.get('text', '')}")

    return "\n".join(lines)


def export_transcript_txt(meeting_info: Dict[str, Any], segments: List[Dict[str, Any]]) -> str:
    """Export transcript as clean plain text."""
    lines = [
        f"{meeting_info.get('title', 'Meeting Transcript')}",
        f"Date: {meeting_info.get('meeting_date') or ''}",
        "=" * 60,
        ""
    ]
    for seg in segments:
        speaker = seg.get("speaker_name") or seg.get("speaker_label") or "Speaker"
        start_str = ms_to_timestamp(seg.get("start_time_ms", 0), srt_format=False)
        text = seg.get("original_text", "")
        lines.append(f"[{start_str}] {speaker}: {text}")
    return "\n".join(lines)


def export_transcript_srt(segments: List[Dict[str, Any]]) -> str:
    """Export transcript as standard SubRip SRT subtitles."""
    blocks = []
    for idx, seg in enumerate(segments, 1):
        start = ms_to_timestamp(seg.get("start_time_ms", 0), srt_format=True)
        end = ms_to_timestamp(seg.get("end_time_ms", 0), srt_format=True)
        speaker = seg.get("speaker_name") or seg.get("speaker_label") or ""
        prefix = f"{speaker}: " if speaker else ""
        text = f"{prefix}{seg.get('original_text', '')}"

        blocks.append(f"{idx}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def export_transcript_vtt(segments: List[Dict[str, Any]]) -> str:
    """Export transcript as WebVTT subtitles."""
    lines = ["WEBVTT\n"]
    for idx, seg in enumerate(segments, 1):
        start = ms_to_timestamp(seg.get("start_time_ms", 0), srt_format=False)
        end = ms_to_timestamp(seg.get("end_time_ms", 0), srt_format=False)
        speaker = seg.get("speaker_name") or seg.get("speaker_label") or ""
        prefix = f"<v {speaker}>" if speaker else ""
        suffix = "</v>" if speaker else ""
        text = f"{prefix}{seg.get('original_text', '')}{suffix}"

        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)
