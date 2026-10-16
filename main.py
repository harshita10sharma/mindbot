import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

import config  # loads .env and validates GROQ_API_KEY via llm
import activities
import assessments
import resources
import chat_engine
import clinician
import knowledge
import llm
import safety
import storage
from models import AssessmentRequest, ChatRequest, MoodRequest, SafetyPlan, StartRequest

VERSION = "4.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    try:
        knowledge.load()
    except FileNotFoundError:
        pass
    yield


app = FastAPI(
    title="MindBot API",
    version=VERSION,
    description=(
        "AI mental-health support companion with clinical-state analysis, anti-sycophancy review, "
        "layered crisis detection, validated screening (PHQ-9, GAD-7, C-SSRS), safety planning, "
        "long-term memory, document retrieval and clinician-in-the-loop oversight. "
        "Not a replacement for licensed professionals."
    ),
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,  # browsers reject credentials with a wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)


_RATE: dict = {}
RATE_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "12"))


def _check_rate(session_id: str) -> None:
    """Per-session sliding window so one user can't exhaust the shared free-tier quota."""
    now = time.time()
    window = [t for t in _RATE.get(session_id, []) if now - t < 60]
    if len(window) >= RATE_PER_MINUTE:
        raise HTTPException(status_code=429, detail="You're sending messages very quickly. Please wait a few seconds and try again.")
    window.append(now)
    _RATE[session_id] = window


def _sid(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id cannot be empty.")
    return sid


def require_clinician(x_clinician_token: Optional[str] = Header(None)):
    if config.CLINICIAN_TOKEN and x_clinician_token != config.CLINICIAN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Clinician-Token header.")


# ---------------- health ----------------
@app.get("/healthz", tags=["system"])
def healthz():
    return {"ok": True}


@app.get("/", tags=["system"])
def home():
    return {
        "status": "MindBot is running",
        "version": VERSION,
        "docs": "/docs",
        "developer": "Harshita Sharma",
        "models": {"responder": config.RESPONDER_MODEL, "analyzer": config.ANALYZER_MODEL, "critic": config.CRITIC_MODEL},
        "knowledge": knowledge.stats(),
    }


# ---------------- conversation ----------------
@app.post("/start", tags=["chat"])
def start_chat(request: StartRequest):
    greeting = chat_engine.start_session(_sid(request.session_id))
    return {"response": greeting, "crisis_detected": False, "autostart": True}


@app.post("/chat", tags=["chat"])
def chat_with_memory(request: ChatRequest):
    session_id, query = _sid(request.session_id), request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    _check_rate(session_id)
    try:
        return chat_engine.process_message(session_id, query)
    except Exception as e:
        # Never leave a user in distress with an error: answer safely, report the failure.
        level, _ = safety.lexicon_risk(query)
        reply = safety.crisis_message(level) or chat_engine.FALLBACK_REPLY
        return {"response": reply, "crisis_detected": safety.level_index(level) >= 3,
                "risk_level": level, "error": f"{type(e).__name__}: {e}"}


@app.post("/doc-chat", tags=["chat"])
def chat_with_documents(request: ChatRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        return chat_engine.query_documents(query)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data folder not found.")


@app.post("/voice-chat", tags=["chat"])
async def voice_chat(session_id: str = Form(...), audio: UploadFile = File(...), language: Optional[str] = Form(None)):
    """Speech-to-text with Whisper, then the normal /chat pipeline. Returns the transcript too."""
    _check_rate(_sid(session_id))
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    try:
        text = llm.transcribe(audio.filename or "audio.webm", data, language)
    except llm.LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not text:
        raise HTTPException(status_code=422, detail="Could not detect speech in the audio.")
    result = await run_in_threadpool(chat_engine.process_message, _sid(session_id), text)
    return {"transcript": text, **result}


@app.get("/history/{session_id}", tags=["chat"])
def history(session_id: str):
    return {"session_id": session_id, "messages": storage.get_transcript(session_id)}


# ---------------- screening ----------------
@app.get("/assessments/{instrument}", tags=["screening"])
def get_assessment(instrument: str):
    try:
        return assessments.get_instrument(instrument)
    except assessments.AssessmentError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/assessments/{instrument}", tags=["screening"])
def submit_assessment(instrument: str, request: AssessmentRequest):
    sid = _sid(request.session_id)
    try:
        result = assessments.score(instrument, request.answers)
    except assessments.AssessmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    storage.add_assessment(sid, instrument, request.answers, result["score"], result["severity"])
    flag = safety.level_index(result["risk_level"]) >= safety.level_index("moderate") or (
        instrument == "cssrs" and result["risk_level"] != "none"  # any suicide-screen endorsement reaches a human
    )
    if flag:
        storage.add_risk_event(sid, result["risk_level"], f"assessment:{instrument}", f"score {result['score']} ({result['severity']})")
        result["resources"] = resources.public(resources.select("crisis", k=4))
        result["suggested_action"] = {"type": "safety_plan"}
    return result


@app.get("/assessments-history/{session_id}", tags=["screening"])
def assessment_history(session_id: str):
    return {"session_id": session_id, "results": storage.get_assessments(session_id)}


# ---------------- wellbeing tools ----------------
@app.post("/mood", tags=["wellbeing"])
def log_mood(request: MoodRequest):
    storage.add_mood(_sid(request.session_id), request.score, request.note, "check-in")
    return {"ok": True}


@app.get("/mood/{session_id}", tags=["wellbeing"])
def mood_history(session_id: str):
    moods = storage.get_moods(session_id)
    avg = round(sum(m["score"] for m in moods) / len(moods), 2) if moods else None
    return {"session_id": session_id, "entries": moods, "average": avg}


@app.get("/safety-plan-template", tags=["wellbeing"])
def safety_plan_template():
    return {"fields": assessments.SAFETY_PLAN_FIELDS, "based_on": "Stanley & Brown (2012) Safety Planning Intervention"}


@app.get("/safety-plan/{session_id}", tags=["wellbeing"])
def get_safety_plan(session_id: str):
    return {"session_id": session_id, "plan": storage.get_safety_plan(session_id), "resources": resources.public(resources.select("crisis", k=4))}


@app.put("/safety-plan/{session_id}", tags=["wellbeing"])
def save_safety_plan(session_id: str, plan: SafetyPlan):
    storage.save_safety_plan(_sid(session_id), plan.model_dump())
    return {"ok": True}


@app.get("/resources", tags=["wellbeing"])
def resources_directory():
    """Full verified directory with live open-now status (IST)."""
    return {"last_verified": resources.LAST_VERIFIED, "resources": resources.full_directory()}


@app.get("/resources/talk", tags=["wellbeing"])
def talk_to_someone(language: str = "english", need: str = "talk"):
    """Free counsellors / helplines that are open right now, ranked for this person."""
    return {"resources": resources.public(resources.select(need if need in ("talk", "crisis") else "talk", language=language, k=4))}


@app.get("/activities", tags=["wellbeing"])
def list_activities():
    return {"activities": activities.menu(limit=len(activities.ACTIVITIES))}


@app.post("/activities/{activity_id}/start", tags=["wellbeing"])
def start_activity(activity_id: str, request: StartRequest):
    """Start a game/story from a button tap; returns MindBot's first move."""
    if activity_id not in activities.ACTIVITIES:
        raise HTTPException(status_code=404, detail="Unknown activity.")
    sid = _sid(request.session_id)
    _check_rate(sid)
    return chat_engine.process_message(sid, f"Let's do this: {activities.ACTIVITIES[activity_id]['name']}")


# ---------------- privacy ----------------
@app.delete("/users/{session_id}", tags=["privacy"])
def delete_user_data(session_id: str):
    """Right to erasure: removes every stored record for this session/user."""
    return {"deleted_records": storage.delete_session(_sid(session_id))}


# ---------------- clinician ----------------
@app.get("/clinician/sessions", tags=["clinician"], dependencies=[Depends(require_clinician)])
def clinician_sessions():
    return {"sessions": storage.list_sessions()}


@app.get("/clinician/flags", tags=["clinician"], dependencies=[Depends(require_clinician)])
def clinician_flags(only_open: bool = True):
    return {"flags": storage.get_risk_events(only_open=only_open)}


@app.post("/clinician/flags/{event_id}/review", tags=["clinician"], dependencies=[Depends(require_clinician)])
def clinician_review_flag(event_id: int):
    if not storage.mark_risk_reviewed(event_id):
        raise HTTPException(status_code=404, detail="Flag not found.")
    return {"ok": True}


@app.get("/clinician/insights/{session_id}", tags=["clinician"], dependencies=[Depends(require_clinician)])
def clinician_insights(session_id: str):
    return clinician.insights(session_id)


@app.get("/clinician/summary/{session_id}", tags=["clinician"], dependencies=[Depends(require_clinician)])
def clinician_summary(session_id: str):
    return clinician.session_summary(session_id)


# ---------------- knowledge ----------------
@app.get("/knowledge/search", tags=["knowledge"])
def knowledge_search(q: str, k: int = 3):
    return {"results": knowledge.search(q, k=min(max(k, 1), 8))}


@app.post("/knowledge/reload", tags=["knowledge"], dependencies=[Depends(require_clinician)])
def knowledge_reload():
    return {"chunks": knowledge.load()}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8090))
    print(f"\nMindBot running on: http://127.0.0.1:{port}")
    print(f"API Docs: http://127.0.0.1:{port}/docs")
    uvicorn.run("main:app", host="0.0.0.0", port=port, proxy_headers=True)
