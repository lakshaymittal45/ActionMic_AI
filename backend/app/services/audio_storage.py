"""
Audio Storage Service for ActionMic_AI.
Handles meeting audio file persistence, streaming chunk management,
assembly of live recording chunks, metadata extraction, and streaming playback.
"""
import os
import hashlib
import wave
import io
import logging
import subprocess
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Base storage directory - defaults to storage/audio within the ActionMic project
DEFAULT_STORAGE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "storage", "audio")
)
STORAGE_ROOT = os.getenv("ACTIONMIC_AUDIO_DIR", DEFAULT_STORAGE_ROOT)


def ensure_dir(path: str) -> str:
    """Ensure directory exists and return the path."""
    os.makedirs(path, exist_ok=True)
    return path


def get_storage_root() -> str:
    """Return the base audio storage directory."""
    return ensure_dir(STORAGE_ROOT)


def get_meeting_dir(meeting_id: int) -> str:
    """Get the dedicated storage directory for a specific meeting."""
    meeting_path = os.path.join(get_storage_root(), "meetings", str(meeting_id))
    return ensure_dir(meeting_path)


def get_chunks_dir(meeting_id: int) -> str:
    """Get the chunks directory for live recording sessions."""
    chunks_path = os.path.join(get_meeting_dir(meeting_id), "chunks")
    return ensure_dir(chunks_path)


def calculate_sha256(file_path: str) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_audio_duration_seconds(file_path: str) -> Optional[float]:
    """
    Attempt to read audio duration using wave, soundfile, or mutagen.
    Gracefully handles different audio formats.
    """
    if not os.path.exists(file_path):
        return None

    # 1. Try standard wave module
    try:
        with wave.open(file_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return round(frames / float(rate), 2)
    except Exception:
        pass

    # 2. Try soundfile
    try:
        import soundfile as sf
        info = sf.info(file_path)
        return round(float(info.duration), 2)
    except Exception:
        pass

    # 3. Try mutagen
    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio and audio.info and hasattr(audio.info, "length"):
            return round(float(audio.info.length), 2)
    except Exception:
        pass

    # 4. Try torchaudio
    try:
        import torchaudio
        info = torchaudio.info(file_path)
        if info.sample_rate > 0:
            return round(float(info.num_frames) / float(info.sample_rate), 2)
    except Exception:
        pass

    return None


def save_uploaded_audio(
    meeting_id: int,
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save an uploaded audio file into the meeting's directory.
    Returns metadata dict with path, size, checksum, duration, and mime type.
    """
    meeting_dir = get_meeting_dir(meeting_id)
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".wav"
    target_filename = f"original_recording{ext.lower()}"
    target_path = os.path.join(meeting_dir, target_filename)

    with open(target_path, "wb") as f:
        f.write(content)

    size_bytes = os.path.getsize(target_path)
    checksum = calculate_sha256(target_path)
    duration = get_audio_duration_seconds(target_path)

    logger.info(
        f"Saved audio for meeting {meeting_id}: {target_path} "
        f"({size_bytes} bytes, duration: {duration}s)"
    )

    return {
        "file_path": target_path,
        "filename": target_filename,
        "original_filename": filename,
        "size_bytes": size_bytes,
        "checksum": checksum,
        "duration_seconds": duration,
        "mime_type": mime_type or "audio/wav"
    }


def save_uploaded_media(
    meeting_id: int,
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None
) -> Dict[str, Any]:
    """Save audio directly or extract a normalized WAV track from video."""
    extension = os.path.splitext(filename)[1].lower()
    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    if extension not in video_extensions and not (mime_type or "").startswith("video/"):
        return save_uploaded_audio(meeting_id, filename, content, mime_type)

    meeting_dir = get_meeting_dir(meeting_id)
    source_path = os.path.join(meeting_dir, f"source_video{extension or '.bin'}")
    output_path = os.path.join(meeting_dir, "extracted_audio.wav")
    with open(source_path, "wb") as handle:
        handle.write(content)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", source_path, "-vn", "-ac", "1", "-ar", "16000", output_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is required to process video uploads") from exc
    except subprocess.CalledProcessError as exc:
        logger.error("FFmpeg conversion failed: %s", exc.stderr[-2000:])
        raise RuntimeError("Could not extract audio from this video") from exc

    return {
        "file_path": output_path,
        "filename": os.path.basename(output_path),
        "original_filename": filename,
        "size_bytes": os.path.getsize(output_path),
        "checksum": calculate_sha256(output_path),
        "duration_seconds": get_audio_duration_seconds(output_path),
        "mime_type": "audio/wav",
        "source_media_type": "video",
        "source_path": source_path,
    }


def save_audio_chunk(
    meeting_id: int,
    chunk_index: int,
    pcm16_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1
) -> Dict[str, Any]:
    """
    Save an individual PCM16 audio chunk from a live recording session.
    Stored as a WAV file so it can be independently processed or transcribed.
    """
    chunks_dir = get_chunks_dir(meeting_id)
    chunk_filename = f"chunk_{chunk_index:06d}.wav"
    chunk_path = os.path.join(chunks_dir, chunk_filename)

    with wave.open(chunk_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_data)

    size_bytes = os.path.getsize(chunk_path)
    duration = round(len(pcm16_data) / (sample_rate * channels * 2), 3)

    return {
        "chunk_path": chunk_path,
        "chunk_index": chunk_index,
        "size_bytes": size_bytes,
        "duration_seconds": duration
    }


def assemble_recording_from_chunks(
    meeting_id: int,
    sample_rate: int = 16000,
    channels: int = 1
) -> Optional[Dict[str, Any]]:
    """
    Assembles all saved audio chunks in sequence into a single master WAV file.
    Returns metadata dict or None if no chunks were found.
    """
    chunks_dir = get_chunks_dir(meeting_id)
    if not os.path.exists(chunks_dir):
        return None

    chunk_files = sorted([
        f for f in os.listdir(chunks_dir)
        if f.startswith("chunk_") and f.endswith(".wav")
    ])

    if not chunk_files:
        return None

    meeting_dir = get_meeting_dir(meeting_id)
    output_path = os.path.join(meeting_dir, "master_recording.wav")

    total_frames = 0
    with wave.open(output_path, "wb") as outfile:
        outfile.setnchannels(channels)
        outfile.setsampwidth(2)
        outfile.setframerate(sample_rate)

        for cf in chunk_files:
            cpath = os.path.join(chunks_dir, cf)
            try:
                with wave.open(cpath, "rb") as infile:
                    frames = infile.readframes(infile.getnframes())
                    outfile.writeframes(frames)
                    total_frames += infile.getnframes()
            except Exception as e:
                logger.error(f"Error reading chunk {cpath}: {e}")

    size_bytes = os.path.getsize(output_path)
    checksum = calculate_sha256(output_path)
    duration = round(total_frames / float(sample_rate), 2) if sample_rate > 0 else 0.0

    logger.info(
        f"Assembled {len(chunk_files)} chunks for meeting {meeting_id} -> {output_path} "
        f"({duration}s, {size_bytes} bytes)"
    )

    return {
        "file_path": output_path,
        "size_bytes": size_bytes,
        "duration_seconds": duration,
        "checksum": checksum,
        "chunk_count": len(chunk_files),
        "mime_type": "audio/wav"
    }


def get_meeting_audio_path(meeting_id: int) -> Optional[str]:
    """Find the primary playable audio file for a meeting."""
    meeting_dir = get_meeting_dir(meeting_id)
    if not os.path.exists(meeting_dir):
        return None

    # Check preferred candidates in order
    candidates = [
        "master_recording.wav",
        "original_recording.wav",
        "original_recording.mp3",
        "original_recording.m4a",
        "original_recording.flac",
        "original_recording.webm",
        "original_recording.ogg"
    ]

    for cand in candidates:
        cand_path = os.path.join(meeting_dir, cand)
        if os.path.exists(cand_path) and os.path.getsize(cand_path) > 0:
            return cand_path

    # Check for any audio file in meeting directory
    for f in os.listdir(meeting_dir):
        if f.lower().endswith((".wav", ".mp3", ".m4a", ".flac", ".webm", ".ogg")):
            p = os.path.join(meeting_dir, f)
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return p

    return None
