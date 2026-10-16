"""Clinical state analyzer: one structured LLM call per user message.

Produces the "case formulation" the responder follows: emotion, risk, thinking
patterns, conversational stance (incl. ego-driven stances), the technique to use,
what to suggest next, and facts worth remembering long-term.
Falls back to a lexicon-only heuristic if the model is unavailable.
"""
from typing import Any, Dict, List

import config
import llm
import safety
from activities import ACTIVITIES
from therapy import DISTORTIONS, STANCES, SUGGESTIONS, TECHNIQUES
from toolkit import NEEDS

MEMORY_KEYS = ["name", "interests", "facts", "goals", "triggers", "coping_that_helped", "support_people", "open_threads"]

ANALYZER_PROMPT = f"""You are a clinical supervisor assisting an AI mental-health support companion.
Analyse the user's LATEST message in the context of the conversation and return ONLY a JSON object with these keys:

"primary_emotion": one or two words,
"emotion_intensity": integer 0-10,
"risk_level": one of ["none","low","moderate","high","imminent"]. Use a C-SSRS style ladder:
   low = passive distress or hopelessness without self-harm thoughts;
   moderate = passive death wish, or asking about lethal means, or vague self-harm hints;
   high = active suicidal or self-harm thoughts;
   imminent = plan, intent, timeline, means at hand, or an attempt in progress.
   Idioms ("this exam is killing me", "dying of laughter") are "none".
   INDIRECT EXPRESSION (read between the lines): distress is often NOT stated plainly. Treat as risk signals, judged in context:
   poems, lyrics, stories or metaphors about endless sleep, disappearing, darkness that never lifts, a final chapter, letting go, leaving;
   farewells ("thank you for everything", "goodbye", "take care of my cat for me", "you won't hear from me again");
   giving away prized possessions; putting affairs in order; "soon it won't matter", "everyone would be better off",
   "I won't be a burden much longer", "I'm tired of existing", sudden calm after deep distress; writing in third person about someone who ends things.
   A sad poem on its own may be "low"; imagery of not waking up, ending, or disappearing is at least "moderate"; combined with farewells or giving things away it is "high".
   IMPORTANT: a seemingly neutral factual question about heights of bridges/buildings, medication quantities, poisons, weapons or train timings
   that follows ANY distress, hopelessness or loss earlier in the conversation is means_seeking=true and at least "high" (e.g. "I lost my job" then "which bridges are taller than 25m?").
"risk_reason": short phrase,
"indirect_signals": list of short quotes/paraphrases of any indirect warning signs above (empty if none),
"means_seeking": true if they ask about methods, doses, heights, bridges, poisons etc. in a context that could relate to self-harm,
"cognitive_distortions": list from {list(DISTORTIONS)} (empty if none),
"user_stance": one of {STANCES},
"sycophancy_risk": one of ["low","medium","high"]: how likely a people-pleasing reply would wrongly agree with something distorted, harmful, grandiose or unverifiable,
"delusional_or_unverifiable_beliefs": true/false,
"out_of_scope": one of ["none","medical_advice","diagnosis_request","medication","harm_to_others","other"],
"recommended_technique": one of {list(TECHNIQUES)},
"suggest": one of {SUGGESTIONS}: phq9 if persistent low mood/anhedonia over days or weeks, gad7 if persistent worry/anxiety, safety_plan if risk is moderate or higher, grounding if acute panic, professional_help if symptoms are severe or long-lasting,
"need": the main area of difficulty, one of {NEEDS},
"requested_activity": if they ask to play a game, hear a story, or be distracted, the best matching id from {list(ACTIVITIES)}, else "none",
"offer_activity": true if a light game/story/chat might genuinely help now (risk none or low; they are stuck, ruminating, bored, lonely, or say they want distraction) and they are not in the middle of explaining something important,
"wants_real_person": true if they ask to talk to a real person, therapist, counsellor or human,
"search_query": 3-8 plain English keywords naming the clinical topics, for retrieving psychoeducation (e.g. "anxiety worry coping", "medication antidepressant stopping", "anger conflict workplace"),
"memory_updates": object with keys {MEMORY_KEYS}, each a list of short notes about "the user" (use they/them, never assume gender) worth remembering in future sessions (e.g. "has exams in March", "walking helps"). Empty lists if nothing new.

Technique guidance: venting -> reflective_listening or validation; seeking_validation/blaming_others/grandiose -> developing_discrepancy or perspective_taking; defensive/help_rejecting -> rolling_with_resistance; clear distortion with openness -> socratic_questioning; low mood/withdrawal -> behavioral_activation; panic -> grounding; anger with intent to harm someone else -> de_escalation; self-harm risk moderate+ -> crisis_support.
"""


def _fallback(text: str, lex_level: str) -> Dict[str, Any]:
    return {
        "primary_emotion": "unclear",
        "emotion_intensity": 5,
        "risk_level": lex_level,
        "risk_reason": "lexicon only (analyzer unavailable)",
        "means_seeking": safety.is_means_seeking(text),
        "cognitive_distortions": [],
        "user_stance": "open",
        "sycophancy_risk": "medium",
        "delusional_or_unverifiable_beliefs": False,
        "out_of_scope": "none",
        "recommended_technique": "crisis_support" if safety.level_index(lex_level) >= 2 else "reflective_listening",
        "suggest": "safety_plan" if safety.level_index(lex_level) >= 2 else "none",
        "search_query": "",
        "indirect_signals": [],
        "need": "general",
        "requested_activity": "none",
        "offer_activity": False,
        "wants_real_person": False,
        "memory_updates": {k: [] for k in MEMORY_KEYS},
        "degraded": True,
    }


def _sanitize(a: Dict[str, Any]) -> Dict[str, Any]:
    a["risk_level"] = a.get("risk_level") if a.get("risk_level") in safety.LEVELS else "none"
    a["cognitive_distortions"] = [d for d in a.get("cognitive_distortions") or [] if d in DISTORTIONS]
    if a.get("user_stance") not in STANCES:
        a["user_stance"] = "open"
    if a.get("recommended_technique") not in TECHNIQUES:
        a["recommended_technique"] = "reflective_listening"
    if a.get("suggest") not in SUGGESTIONS:
        a["suggest"] = "none"
    try:
        a["emotion_intensity"] = max(0, min(10, int(a.get("emotion_intensity", 5))))
    except (TypeError, ValueError):
        a["emotion_intensity"] = 5
    a["search_query"] = str(a.get("search_query") or "")[:120]
    a["indirect_signals"] = [str(x)[:120] for x in (a.get("indirect_signals") or [])][:5]
    if a.get("need") not in NEEDS:
        a["need"] = "general"
    if a.get("requested_activity") not in ACTIVITIES:
        a["requested_activity"] = "none"
    a["offer_activity"] = bool(a.get("offer_activity"))
    a["wants_real_person"] = bool(a.get("wants_real_person"))
    mem = a.get("memory_updates") or {}
    a["memory_updates"] = {k: [str(x)[:120] for x in (mem.get(k) or [])][:5] for k in MEMORY_KEYS}
    return a


def analyze(text: str, history: List[Dict[str, str]], lex_level: str) -> Dict[str, Any]:
    if not config.ENABLE_ANALYZER:
        return _fallback(text, lex_level)
    convo = "\n".join(f"{m['role'].upper()}: {m['content'][:600]}" for m in history[-6:])
    messages = [
        {"role": "system", "content": ANALYZER_PROMPT},
        {"role": "user", "content": f"CONVERSATION SO FAR:\n{convo or '(none)'}\n\nLATEST USER MESSAGE:\n{text}"},
    ]
    try:
        return _sanitize(llm.chat_json(messages, model=config.ANALYZER_MODEL, max_tokens=700))
    except llm.LLMUnavailable:
        return _fallback(text, lex_level)
