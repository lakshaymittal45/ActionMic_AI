"""
Download common Whisper and AI4Bharat models used by Voice EMR.
Usage:
    python scripts/download_models.py --dest ../models

This script reads model ids from app.config and downloads them using
huggingface_hub.snapshot_download. It respects HF_TOKEN or HUGGINGFACE_TOKEN
from environment or backend/.env (dotenv is loaded by app.config).
"""
import argparse
import logging
import os
from pathlib import Path

from huggingface_hub import snapshot_download

# Import config to reuse model IDs defined in the app
try:
    from app.config import (
        TRANSCRIPTION_MODELS,
        INDIC_MULTILINGUAL_MODEL,
        INDIC_LANGUAGE_MODELS,
    )
except Exception:
    # If running outside package, try to add backend to path
    import sys
    BASE = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(BASE))
    from app.config import (
        TRANSCRIPTION_MODELS,
        INDIC_MULTILINGUAL_MODEL,
        INDIC_LANGUAGE_MODELS,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Default model mapping for Whisper nicknames -> likely HF repo ids
WHISPER_CANDIDATES = {
    "small": ["openai/whisper-small", "Systran/faster-whisper-small"],
    "medium": ["openai/whisper-medium", "Systran/faster-whisper-medium"],
    "large-v3": ["openai/whisper-large-v3"],
}


def download_repo(repo_id: str, dest: Path, token: str | None = None):
    logger.info(f"Downloading {repo_id} → {dest}")
    try:
        snapshot_download(repo_id, cache_dir=str(dest), token=token)
        logger.info(f"✔️  Downloaded {repo_id}")
    except Exception as e:
        logger.error(f"Failed to download {repo_id}: {e}")


def main(dest_dir: Path):
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1) Transcription models
    logger.info("Resolving transcription models from config...")
    for nickname, cfg in TRANSCRIPTION_MODELS.items():
        candidates = WHISPER_CANDIDATES.get(nickname, [])
        # If config used full HF id in name, use it directly
        model_name = cfg.get("name")
        if model_name and "/" in model_name:
            candidates.insert(0, model_name)

        for repo in candidates:
            download_repo(repo, dest_dir / repo.replace('/', '_'), token)

    # 2) AI4Bharat Indic multilingual + language models
    logger.info("Downloading AI4Bharat models...")
    if INDIC_MULTILINGUAL_MODEL:
        download_repo(INDIC_MULTILINGUAL_MODEL, dest_dir / INDIC_MULTILINGUAL_MODEL.replace('/', '_'), token)

    for lang, repo in INDIC_LANGUAGE_MODELS.items():
        if repo:
            download_repo(repo, dest_dir / repo.replace('/', '_'), token)

    logger.info("All downloads attempted. Check logs for any failures.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dest', default='../models', help='Destination folder (relative to scripts/)')
    args = parser.parse_args()

    # When running from repo root: scripts/download_models.py --dest backend/models
    main(Path(args.dest))
