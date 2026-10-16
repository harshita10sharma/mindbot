"""Anti-sycophancy and safety critic.

Runs only when the analyzer flags a risky conversational state (ego-driven stance,
high sycophancy risk, delusional content, distortions, or elevated risk), so normal
messages cost a single responder call. It reviews the draft reply against a rubric and
rewrites it if needed.
"""
from typing import Any, Dict, Tuple

import config
import llm
from therapy import EGO_DISTORTIONS, EGO_STANCES

CRITIC_PROMPT = """You review draft replies from an AI mental-health support companion before they are sent.
Check the draft against this rubric:
1. Sycophancy: does it agree with, praise, or reinforce a distorted, blaming, grandiose, harmful or unverifiable belief? (Validating the FEELING is fine; endorsing the CONCLUSION is not.) Does it state the user's claims about others as facts ("they're jealous") instead of perceptions ("it feels like they're jealous")? Does it cave to "just agree with me" ("it's okay to hold that view", "you're right")? For a harmful plan, does it fail to name the other person's boundaries or the likely consequences?
2. Safety: any self-harm method/dose/height/location information (including lists of bridges, buildings or medicines with heights or quantities), or failure to address risk when risk is moderate or higher?
3. Scope: does it diagnose or give medication instructions?
4. Style: more than one question, preachy/lecturing tone, or cold/dismissive tone? Does it list helpline names or phone numbers itself? (A verified list is appended automatically, so remove any it contains.)

5. Indirect risk: if the analyzer notes indirect warning signs (poems or metaphors about fading, not waking, farewells, giving things away),
   does the reply gently and DIRECTLY ask whether they are having thoughts of ending their life? If not, revise to add that question.
6. Repetition: does it open with the same words as the previous reply, or ask the same (or nearly the same) question? Repetition makes the user feel they are talking to a script; if so, revise the opening and/or question while keeping the content.

Return ONLY JSON: {"verdict": "pass" or "revise", "issues": [short strings], "revised_reply": "<improved reply if revise, else empty string>"}
Never turn a reply into a bare refusal such as "I can't help with that": when declining a request, stay warm, explain briefly that it is out of care for their safety, and check in on how they are doing.
If revising, make the smallest change that fixes the issues and keep the original's therapeutic content. A revised reply must keep the warmth and language of the original, follow the rubric, stay under 150 words, ask at most one question, and use no emojis."""


def should_review(analysis: Dict[str, Any]) -> bool:
    if not config.ENABLE_CRITIC or analysis.get("degraded"):
        return False
    return (
        analysis.get("user_stance") in EGO_STANCES
        or analysis.get("sycophancy_risk") in ("medium", "high")
        or bool(EGO_DISTORTIONS & set(analysis.get("cognitive_distortions") or []))
        or bool(analysis.get("delusional_or_unverifiable_beliefs"))
        or analysis.get("risk_level") in ("moderate", "high", "imminent")
        or bool(analysis.get("means_seeking"))
        or bool(analysis.get("indirect_signals"))
        or analysis.get("out_of_scope") in ("medication", "diagnosis_request", "harm_to_others")
    )


def review(user_message: str, draft: str, analysis: Dict[str, Any], previous_reply: str = "") -> Tuple[str, Dict[str, Any]]:
    context = (
        f"Analyzer notes: stance={analysis.get('user_stance')}, risk={analysis.get('risk_level')}, "
        f"distortions={analysis.get('cognitive_distortions')}, "
        f"delusional={analysis.get('delusional_or_unverifiable_beliefs')}, scope={analysis.get('out_of_scope')}, "
        f"indirect_warning_signs={analysis.get('indirect_signals') or 'none'}"
    )
    previous = f"\n\nPREVIOUS ASSISTANT REPLY (for the repetition check):\n{previous_reply[:800]}" if previous_reply else ""
    messages = [
        {"role": "system", "content": CRITIC_PROMPT},
        {"role": "user", "content": f"{context}{previous}\n\nUSER MESSAGE:\n{user_message}\n\nDRAFT REPLY:\n{draft}"},
    ]
    try:
        result = llm.chat_json(messages, model=config.CRITIC_MODEL, max_tokens=700)
    except llm.LLMUnavailable:
        return draft, {"verdict": "skipped", "issues": []}
    revised = (result.get("revised_reply") or "").strip()
    if result.get("verdict") == "revise" and revised:
        return revised, {"verdict": "revised", "issues": result.get("issues", [])}
    return draft, {"verdict": "pass", "issues": result.get("issues", [])}
