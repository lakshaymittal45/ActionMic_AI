# ActionMic AI

ActionMic AI is a meeting intelligence platform for recording, importing, transcribing, and analyzing conversations.

## Four workflows

1. Record an online meeting.
2. Record an offline or in-person meeting.
3. Upload a meeting video, extract its audio, and process it.
4. Upload an audio recording and process it.

The processing pipeline creates a speaker-aware transcript and extracts summaries, key points, decisions, action items, follow-ups, and scheduled events.

## Capabilities

- Browser recording with pause, resume, and stop controls
- Audio and video import workflows
- Speaker diarization and multilingual transcription
- Translation and transliteration support for Indic languages
- Searchable meeting workspace and processing status
- AI-generated meeting intelligence
- Editable transcripts and export-ready meeting views
- Local media storage and configurable database persistence

## Repository layout

```text
ActionMic_AI/
├── backend/app/api/          # Meeting, recording, audio, transcript, intelligence APIs
├── backend/app/services/     # Processing and storage services
├── backend/app/transcription # Speech-to-text and language processing
├── backend/app/diarization/  # Speaker separation
├── backend/app/llm/          # Local LLM analysis
├── frontend/app/             # Next.js routes and meeting pages
├── frontend/components/     # Shared UI and recorder components
└── audio/                    # Local runtime media storage
```

## Requirements

- Python 3.11+
- Node.js 20+
- MySQL-compatible database
- FFmpeg for media conversion
- Ollama (optional, for local intelligence extraction)

## Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Configure the environment before starting. Important settings include `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `ACTIONMIC_AUDIO_DIR`, `CORS_ORIGINS`, `OLLAMA_BASE_URL`, and `TRANSCRIPTION_BACKEND`. Defaults and optional settings are defined in `backend/app/config.py`.

## Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. For production, run `npm run build` followed by `npm run start`.

## Main routes

| Route | Purpose |
|---|---|
| `/meetings` | Dashboard and four workflow choices |
| `/meetings/[id]/record` | Live recording workspace |
| `/meetings/upload?mode=audio` | Upload and process audio |
| `/meetings/upload?mode=video` | Upload video for audio extraction and processing |
| `/meetings/[id]` | Transcript and meeting intelligence workspace |

## Processing flow

```text
Record or upload media → Store source → Extract audio from video → Transcribe
→ Identify speakers and language variants → Generate intelligence → Review results
```

## API areas

- `/meetings` — meeting creation, listing, detail, and lifecycle
- `/meetings/{id}/recording` — recording state and live capture
- `/meetings/{id}/audio` — media upload and storage
- `/meetings/{id}/transcript` — transcript retrieval and editing
- `/meetings/{id}/intelligence` — summaries and extracted meeting entities
- `/health` — service health check

The current request payloads are documented by the API wrapper in `frontend/lib/api.js`.

## Development notes

- Keep uploaded media outside source control.
- Install FFmpeg in every environment that supports video uploads.
- Ollama can run the intelligence model locally.
- Add new product functionality under the `meetings` routes and services.

## License

Add the project license before public distribution.
