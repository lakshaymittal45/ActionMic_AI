"""
ActionMic_AI API v1 Router.
Aggregates meeting, transcript, intelligence, audio, and recording sub-routers.
"""
from fastapi import APIRouter
from app.api.meetings import router as meetings_router
from app.api.transcripts import router as transcripts_router
from app.api.intelligence import router as intelligence_router
from app.api.audio import router as audio_router
from app.api.recordings import router as recordings_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount sub-routers
api_v1_router.include_router(meetings_router)
api_v1_router.include_router(transcripts_router)
api_v1_router.include_router(intelligence_router)
api_v1_router.include_router(audio_router)
api_v1_router.include_router(recordings_router)
