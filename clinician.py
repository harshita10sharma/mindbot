"""Clinician-in-the-loop features: per-user insights for dashboards and
LLM-drafted session notes for review by a licensed professional."""
from collections import Counter
from typing import Any, Dict, List

import config
import llm
import safety
import storage

SUMMARY_PROMPT = """You are drafting a session note for a licensed mental-health professional who supervises an AI support companion.
Write a concise, factual note in this structure (plain text, headings in caps):
SUBJECTIVE: what the user reported, in their own terms (brief quotes allowed).
OBSERVATIONS: emotional themes, recurring thinking patterns, conversational stance, engagement.
RISK: risk indicators and level history; state clearly if none were observed.
SCREENING: any PHQ-9 / GAD-7 / C-SSRS results and trend.
SUPPORT PROVIDED: techniques the AI used and how the user responded.
SUGGESTED FOLLOW-UP: 2-4 items for the clinician to consider.
Refer to the person as "the user" or they/them unless the transcript states their pronouns. Do not diagnose. Flag uncertainty. Under 300 words."""


# Change thresholds commonly used as clinically meaningful (reliable) change.
RELIABLE_CHANGE = {"phq9": 5, "gad7": 4}


def assessment_trends(assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Measurement-based care: first vs latest score per instrument."""
    out: Dict[str, Any] = {}
    for inst in ("phq9", "gad7"):
        rows = [a for a in assessments if a["instrument"] == inst]
        if not rows:
            continue
        first, last = rows[0], rows[-1]
        change = last["score"] - first["score"]
        threshold = RELIABLE_CHANGE[inst]
        status = ("improved" if change <= -threshold else "worsened" if change >= threshold else "no reliable change") if len(rows) > 1 else "baseline only"
        out[inst] = {
            "first": {"score": first["score"], "severity": first["severity"], "at": first["created_at"]},
            "latest": {"score": last["score"], "severity": last["severity"], "at": last["created_at"]},
            "times_taken": len(rows), "change": change, "status": status,
        }
    return out


def trajectory(analyses: List[Dict[str, Any]], window: int = 10) -> Dict[str, Any]:
    """Is emotional intensity / risk trending up across recent messages? Early-warning signal for clinicians."""
    recent = [a for a in analyses if isinstance(a.get("emotion_intensity"), int)][-window:]
    if len(recent) < 4:
        return {"status": "insufficient data", "messages": len(recent)}
    half = len(recent) // 2
    first = sum(a["emotion_intensity"] for a in recent[:half]) / half
    second = sum(a["emotion_intensity"] for a in recent[half:]) / (len(recent) - half)
    risk_first = max(safety.level_index(a.get("risk_level", "none")) for a in recent[:half])
    risk_second = max(safety.level_index(a.get("risk_level", "none")) for a in recent[half:])
    delta = round(second - first, 2)
    if risk_second > risk_first or (delta >= 2 and second >= 7):
        status = "deteriorating"
    elif delta <= -2:
        status = "improving"
    else:
        status = "stable"
    return {"status": status, "intensity_earlier": round(first, 2), "intensity_recent": round(second, 2),
            "intensity_change": delta, "risk_earlier": safety.LEVELS[risk_first], "risk_recent": safety.LEVELS[risk_second]}


def insights(session_id: str) -> Dict[str, Any]:
    analyses = [a for a in storage.get_analyses(session_id) if "primary_emotion" in a]
    emotions = Counter(a.get("primary_emotion", "unclear").lower() for a in analyses)
    distortions = Counter(d for a in analyses for d in a.get("cognitive_distortions", []))
    stances = Counter(a.get("user_stance", "open") for a in analyses)
    techniques = Counter(a.get("recommended_technique") for a in analyses if a.get("recommended_technique"))
    reviews = Counter((a.get("review") or {}).get("verdict", "n/a") for a in analyses)
    assessments = storage.get_assessments(session_id)
    return {
        "session_id": session_id,
        "messages_analyzed": len(analyses),
        "trajectory": trajectory(analyses),
        "assessment_trends": assessment_trends(assessments),
        "conversation_summary": storage.get_summary(session_id),
        "emotion_timeline": [
            {"at": a["created_at"], "emotion": a.get("primary_emotion"), "intensity": a.get("emotion_intensity"),
             "risk": a.get("risk_level")}
            for a in analyses
        ],
        "top_emotions": emotions.most_common(5),
        "thinking_patterns": distortions.most_common(),
        "stances": stances.most_common(),
        "techniques_used": techniques.most_common(),
        "critic_verdicts": dict(reviews),
        "risk_events": storage.get_risk_events(session_id),
        "assessments": assessments,
        "moods": storage.get_moods(session_id),
        "memory": storage.get_profile(session_id),
        "safety_plan": storage.get_safety_plan(session_id),
    }


def session_summary(session_id: str) -> Dict[str, Any]:
    transcript = storage.get_transcript(session_id)
    if not transcript:
        return {"session_id": session_id, "summary": "No conversation found for this session."}
    data = insights(session_id)
    convo = "\n".join(f"{m['role'].upper()}: {m['content'][:700]}" for m in transcript[-40:])
    facts = (
        f"Thinking patterns: {data['thinking_patterns']}\nStances: {data['stances']}\n"
        f"Techniques: {data['techniques_used']}\nRisk events: "
        f"{[(r['level'], r['created_at']) for r in data['risk_events']]}\n"
        f"Assessments: {[(a['instrument'], a['score'], a['severity'], a['created_at'][:10]) for a in data['assessments']]}\n"
        f"Score trends: {data['assessment_trends']}\nEmotional trajectory: {data['trajectory']}\n"
        f"Earlier-conversation summary: {(data['conversation_summary'] or {}).get('summary', 'n/a')}"
    )
    try:
        note = llm.chat(
            [{"role": "system", "content": SUMMARY_PROMPT},
             {"role": "user", "content": f"STRUCTURED DATA:\n{facts}\n\nTRANSCRIPT (most recent):\n{convo}"}],
            model=config.SUMMARY_MODEL, temperature=0.2, max_tokens=900, reasoning_effort="medium",
        )
    except llm.LLMUnavailable as e:
        note = f"Summary unavailable right now ({e}). Structured insights are still available."
    return {
        "session_id": session_id,
        "summary": note,
        "open_risk_flags": [r for r in data["risk_events"] if not r["reviewed"]],
        "disclaimer": "AI-drafted note. Requires review by a licensed professional.",
    }
