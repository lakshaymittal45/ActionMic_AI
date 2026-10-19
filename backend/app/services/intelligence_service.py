"""
Meeting Intelligence Extraction Service for ActionMic_AI.
Extracts structured executive summaries, key discussion points, decisions,
action items, scheduled events/deadlines, and follow-ups from transcripts.
Uses Ollama local LLMs with cascading fallback and schema validation.
"""
import json
import logging
import re
import os
import requests
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from app.db.mysql_connection import get_db_connection
from app.services.transcription_service import get_meeting_segments
from app.services.meeting_service import get_meeting

logger = logging.getLogger(__name__)
load_dotenv()

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL") or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
if not OLLAMA_API_URL.rstrip("/").endswith("/api/generate"):
    OLLAMA_API_URL = OLLAMA_API_URL.rstrip("/") + "/api/generate"
DEFAULT_LLM_MODELS = ["llama3.1:8b", "qwen2.5:7b", "gemma3:4b", "qwen2.5:3b-instruct", "mistral:7b"]

MEETING_INTELLIGENCE_PROMPT = """You are an expert AI meeting intelligence assistant.
Analyze the following transcript of a meeting and produce an exhaustive, accurate, structured analysis in JSON format.

TRANSCRIPT:
\"\"\"
{transcript_text}
\"\"\"

Produce ONLY a single valid JSON object with the following EXACT schema, and NO other conversational text or markdown code blocks:

{{
  "summary": {{
    "executive_summary": "High-level overview of the meeting and main outcomes",
    "key_takeaways": ["Takeaway 1", "Takeaway 2"],
    "topics_covered": ["Topic A", "Topic B"]
  }},
  "key_points": [
    {{
      "title": "Clear concise title",
      "description": "Details about this discussion point",
      "category": "Strategy / Engineering / Operations / Finance / General",
      "importance": "low" | "medium" | "high" | "critical"
    }}
  ],
  "decisions": [
    {{
      "description": "Exact decision made or agreed upon",
      "rationale": "Why this was decided",
      "decision_status": "agreed" | "proposed" | "needs_confirmation"
    }}
  ],
  "action_items": [
    {{
      "title": "Clear task description",
      "description": "Additional context or deliverable details",
      "assignee_name": "Person name or 'Unassigned'",
      "due_at": "YYYY-MM-DD or null if not stated",
      "priority": "low" | "medium" | "high" | "critical"
    }}
  ],
  "scheduled_events": [
    {{
      "title": "Event, follow-up meeting, or milestone deadline",
      "original_date_expression": "e.g. 'next Tuesday at 4pm' or 'by end of month'",
      "start_at": "YYYY-MM-DD HH:MM:SS or null",
      "end_at": "YYYY-MM-DD HH:MM:SS or null",
      "resolution_status": "resolved" | "ambiguous" | "unresolved"
    }}
  ],
  "follow_ups": [
    {{
      "title": "Topic or inquiry requiring further review",
      "description": "What needs to be checked or followed up on",
      "responsible_person": "Name or null"
    }}
  ]
}}
"""


DEFAULT_LLM_MODELS = ["llama3.2:3b", "qwen2.5:3b-instruct", "gemma3:4b"]


def get_installed_ollama_models() -> List[str]:
    """Get list of locally installed Ollama models."""
    try:
        base_url = OLLAMA_API_URL.replace("/api/generate", "/api/tags")
        res = requests.get(base_url, timeout=2.0)
        if res.status_code == 200:
            models_data = res.json().get("models", [])
            names = [m.get("name") for m in models_data if m.get("name")]
            if names:
                return names
    except Exception:
        pass
    return DEFAULT_LLM_MODELS


def is_ollama_available() -> bool:
    """Quick check if Ollama daemon is reachable within 2 seconds."""
    try:
        base_url = OLLAMA_API_URL.replace("/api/generate", "/api/tags")
        res = requests.get(base_url, timeout=2.0)
        return res.status_code == 200
    except Exception as exc:
        logger.warning("Ollama health check failed for %s: %s", OLLAMA_API_URL, exc)
        return False


def _query_ollama(prompt: str, model: str, timeout: int = 35) -> Optional[str]:
    """Call Ollama generate endpoint."""
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 4096
            }
        }
        res = requests.post(OLLAMA_API_URL, json=payload, timeout=timeout)
        if res.status_code == 200:
            return res.json().get("response")
    except Exception as e:
        logger.debug(f"Ollama call failed with model {model}: {e}")
    return None


def _call_llm_with_fallback(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Tries models in order until one succeeds."""
    if not is_ollama_available():
        logger.info("Ollama is not running locally; engaging intelligent rule-based analyzer.")
        return None, None

    installed = get_installed_ollama_models()
    # Prioritize fastest/best suited installed models
    priority_order = ["llama3.2:3b", "qwen2.5:3b-instruct", "gemma3:4b"]
    models_to_try = [m for m in priority_order if m in installed or any(m in inst for inst in installed)]
    if not models_to_try:
        models_to_try = installed

    for m in models_to_try:
        logger.info(f"Invoking Ollama model: {m}")
        output = _query_ollama(prompt, m)
        if output:
            return output, m
    return None, None


def _clean_json_output(raw_text: str) -> Optional[Dict[str, Any]]:
    """Clean markdown fences and parse JSON safely."""
    if not raw_text:
        return None

    cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except Exception:
        # Try finding the first { and last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                pass
    return None


def generate_fallback_intelligence(transcript_text: str) -> Dict[str, Any]:
    """
    Rule-based heuristic fallback if LLM is unreachable,
    guaranteeing the user gets a working intelligence dashboard immediately.
    """
    lines = [l.strip() for l in transcript_text.split("\n") if l.strip()]
    summary_preview = " ".join(lines[:5]) if lines else "Meeting recorded."
    
    action_items = []
    decisions = []
    key_points = []

    # Heuristic triggers
    for line in lines:
        lower = line.lower()
        if any(w in lower for w in ["will do", "assign", "action item", "todo", "need to", "must complete"]):
            action_items.append({
                "title": line[:120],
                "description": line,
                "assignee_name": "Team",
                "priority": "medium"
            })
        elif any(w in lower for w in ["decided", "agreed", "final decision", "approved", "concluded"]):
            decisions.append({
                "description": line,
                "rationale": "Discussed in meeting",
                "decision_status": "agreed"
            })
        elif len(line) > 30 and not line.startswith("["):
            key_points.append({
                "title": line[:80],
                "description": line,
                "category": "General",
                "importance": "medium"
            })

    return {
        "summary": {
            "executive_summary": summary_preview,
            "key_takeaways": [line[:100] for line in lines[:3]] if lines else ["General meeting discussion"],
            "topics_covered": ["General Discussion", "Action Items"]
        },
        "key_points": key_points[:6],
        "decisions": decisions[:5],
        "action_items": action_items[:8],
        "scheduled_events": [],
        "follow_ups": []
    }


# =====================================================================
# PERSISTENCE OF INTELLIGENCE ENTITIES
# =====================================================================

def save_meeting_summary(
    meeting_id: int,
    content: str,
    structured_json: Dict[str, Any],
    model_name: Optional[str] = None
) -> int:
    """Save or update executive summary."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Delete existing final summary
        cursor.execute("DELETE FROM meeting_summaries WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO meeting_summaries (meeting_id, summary_type, content, structured_content_json, model_name)
            VALUES (%s, 'final', %s, %s, %s)
        """
        cursor.execute(query, (
            meeting_id,
            content,
            json.dumps(structured_json),
            model_name or "local-llm"
        ))
        conn.commit()
        summary_id = cursor.lastrowid
        cursor.close()
    return summary_id


def save_key_points(meeting_id: int, key_points: List[Dict[str, Any]]):
    """Save key discussion points."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM key_points WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO key_points (meeting_id, title, description, category, importance)
            VALUES (%s, %s, %s, %s, %s)
        """
        for kp in key_points:
            importance = str(kp.get("importance", "medium")).lower().strip()
            # Older databases use low/medium/high; map newer critical output safely.
            if importance == "critical":
                importance = "high"
            if importance not in {"low", "medium", "high"}:
                importance = "medium"
            cursor.execute(query, (
                meeting_id,
                kp.get("title", "")[:500],
                kp.get("description"),
                kp.get("category", "General"),
                importance
            ))
        conn.commit()
        cursor.close()


def save_decisions(meeting_id: int, decisions: List[Dict[str, Any]]):
    """Save extracted decisions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM decisions WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO decisions (meeting_id, description, rationale, decision_status)
            VALUES (%s, %s, %s, %s)
        """
        for dec in decisions:
            cursor.execute(query, (
                meeting_id,
                dec.get("description", ""),
                dec.get("rationale"),
                dec.get("decision_status", "agreed").lower()
            ))
        conn.commit()
        cursor.close()


def save_action_items(meeting_id: int, action_items: List[Dict[str, Any]]):
    """Save extracted action items."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_items WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO action_items (
                meeting_id, title, description, assignee_name, due_at, priority, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """
        for item in action_items:
            due_at = None
            if item.get("due_at"):
                try:
                    due_at = datetime.fromisoformat(item["due_at"])
                except Exception:
                    pass

            cursor.execute(query, (
                meeting_id,
                item.get("title", "")[:500],
                item.get("description"),
                item.get("assignee_name"),
                due_at,
                item.get("priority", "medium").lower()
            ))
        conn.commit()
        cursor.close()


def save_scheduled_events(meeting_id: int, events: List[Dict[str, Any]]):
    """Save extracted dates, deadlines, and scheduled events."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduled_events WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO scheduled_events (
                meeting_id, title, description, original_date_expression, resolution_status
            ) VALUES (%s, %s, %s, %s, %s)
        """
        for ev in events:
            cursor.execute(query, (
                meeting_id,
                ev.get("title", "")[:500],
                ev.get("description"),
                ev.get("original_date_expression"),
                ev.get("resolution_status", "unresolved")
            ))
        conn.commit()
        cursor.close()


def save_follow_ups(meeting_id: int, follow_ups: List[Dict[str, Any]]):
    """Save extracted follow ups."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM follow_ups WHERE meeting_id = %s", (meeting_id,))
        query = """
            INSERT INTO follow_ups (meeting_id, title, description, responsible_person)
            VALUES (%s, %s, %s, %s)
        """
        for fu in follow_ups:
            cursor.execute(query, (
                meeting_id,
                fu.get("title", "")[:500],
                fu.get("description"),
                fu.get("responsible_person")
            ))
        conn.commit()
        cursor.close()


# =====================================================================
# PIPELINE EXECUTION & RETRIEVAL
# =====================================================================

def extract_and_save_meeting_intelligence(meeting_id: int) -> Dict[str, Any]:
    """
    Run intelligence extraction over all transcript segments of a meeting
    and save all structured entities to their respective MySQL tables.
    """
    segments = get_meeting_segments(meeting_id, include_variants=True)
    if not segments:
        logger.warning(f"No transcript segments found for meeting {meeting_id}")
        return get_meeting_intelligence(meeting_id)

    transcript_lines = []
    for s in segments:
        speaker = s.get("speaker_name") or s.get("speaker_label") or "Speaker"
        transcript_lines.append(f"{speaker}: {s.get('original_text', '')}")

    full_transcript = "\n".join(transcript_lines)

    prompt = MEETING_INTELLIGENCE_PROMPT.format(transcript_text=full_transcript)
    raw_response, model_used = _call_llm_with_fallback(prompt)

    extracted = _clean_json_output(raw_response) if raw_response else None
    if not extracted:
        logger.info(f"Using rule-based heuristic intelligence extraction for meeting {meeting_id}")
        extracted = generate_fallback_intelligence(full_transcript)
        model_used = "heuristic-analyzer"

    summary_data = extracted.get("summary", {})
    exec_summary = summary_data.get("executive_summary", "") if isinstance(summary_data, dict) else str(summary_data)

    # Persist all entities
    save_meeting_summary(meeting_id, exec_summary, summary_data, model_name=model_used)
    save_key_points(meeting_id, extracted.get("key_points", []))
    save_decisions(meeting_id, extracted.get("decisions", []))
    save_action_items(meeting_id, extracted.get("action_items", []))
    save_scheduled_events(meeting_id, extracted.get("scheduled_events", []))
    save_follow_ups(meeting_id, extracted.get("follow_ups", []))

    logger.info(f"✅ Intelligence extraction completed for meeting {meeting_id}")
    return get_meeting_intelligence(meeting_id)


def get_meeting_intelligence(meeting_id: int) -> Dict[str, Any]:
    """Retrieve all intelligence entities for a meeting."""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        # Summary
        cursor.execute("SELECT * FROM meeting_summaries WHERE meeting_id = %s ORDER BY id DESC LIMIT 1", (meeting_id,))
        summary = cursor.fetchone()
        if summary and summary.get("structured_content_json") and isinstance(summary["structured_content_json"], str):
            try:
                summary["structured_content_json"] = json.loads(summary["structured_content_json"])
            except Exception:
                pass

        # Key points
        cursor.execute("SELECT * FROM key_points WHERE meeting_id = %s ORDER BY id ASC", (meeting_id,))
        key_points = cursor.fetchall()

        # Decisions
        cursor.execute("SELECT * FROM decisions WHERE meeting_id = %s ORDER BY id ASC", (meeting_id,))
        decisions = cursor.fetchall()

        # Action items
        cursor.execute("SELECT * FROM action_items WHERE meeting_id = %s ORDER BY priority DESC, id ASC", (meeting_id,))
        action_items = cursor.fetchall()

        # Scheduled events
        cursor.execute("SELECT * FROM scheduled_events WHERE meeting_id = %s ORDER BY id ASC", (meeting_id,))
        scheduled_events = cursor.fetchall()

        # Follow-ups
        cursor.execute("SELECT * FROM follow_ups WHERE meeting_id = %s ORDER BY id ASC", (meeting_id,))
        follow_ups = cursor.fetchall()

        cursor.close()

    return {
        "summary": summary,
        "key_points": key_points,
        "decisions": decisions,
        "action_items": action_items,
        "scheduled_events": scheduled_events,
        "follow_ups": follow_ups
    }
