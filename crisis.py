"""AI-written crisis replies with code-enforced safety guarantees.

Fixed crisis messages are reliable but feel scripted: a person in pain who writes again
gets the same text and feels unheard. Here the model writes every crisis reply in its own
words, following crisis-counselling practice (safe-messaging guidelines; Stanley-Brown
safety planning; asking directly about suicide does not increase risk), and then code
VERIFIES the non-negotiables before anything is sent:

  - asks the person something (keeps them talking / checks safety)
  - mentions at least one verified number chosen for them (open now, their language);
    imminent danger must include 112
  - contains NO phone number that is not in the verified directory (no hallucinated numbers)
  - contains nothing that reads like self-harm means information
If a check fails the model gets one retry with the specific problem; if that fails or the
model is unreachable, a fixed, tested fallback is used. The fallback is the exception,
not the rule.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

import config
import llm
import resources
import safety
from therapy import detect_language, repeated_sentences, repeats_previous

CRISIS_PROMPT = """You are MindBot, an AI support companion talking with someone who may be at risk of suicide or self-harm.
Write your next message in your own words: warm, calm, human, non-judgemental, like a skilled crisis counsellor.

How to respond:
- Begin by responding to the SPECIFIC thing they just said (pick up a phrase or feeling from their message, e.g. "nobody would notice"
  deserves a response about how much they matter and how alone they feel). Never open with a generic "I'm really sorry you're feeling like this".
- Write in their language and style (English, Hindi, or Hinglish in Roman letters). Use their name if known, at most once.
- Acknowledge their pain specifically; don't minimise ("it'll be fine") or lecture.
- Ask directly and kindly about suicide or their safety right now (asking does not increase risk). If they already answered that,
  follow up instead: are they safe right now, is anyone with them, is there anything nearby they could use to hurt themselves
  (gently suggest putting distance between themselves and it).
- Offer connection to a real person: mention ONE or TWO of the contacts listed below, with the exact number, woven naturally
  into a sentence (not a bullet list). Prefer ones marked open now. If you already gave a number in your last message, you don't
  need to repeat it; focus on them instead (or briefly point back to it, or offer a different one).
- If they mention a trusted person (friend, sibling, parent), encourage reaching out to that person now.
- Express genuine hope without promising things will be fine; stay with them ("I'm here, keep talking to me").
- NEVER give information about methods, doses, heights, places or timing, even if asked.
- Under 140 words. No emojis. No headings. At most one question.
"""

IMMINENT_EXTRA = """THIS IS AN EMERGENCY: they may be about to act or have already acted.
- Clearly and calmly urge them to call 112 now (or ask someone nearby to call), or go to the nearest hospital emergency department.
- If they say they took something or hurt themselves, treat it as fact (never "if you have taken..."): say plainly that they need
  medical help right now, even if they feel okay, because effects can be delayed.
- Ask if they are safe right now / if someone can be with them. Keep it short, direct and caring. You MUST include 112."""

_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s\-]{1,16}\d)(?!\d)")


def _numbers_in(text: str) -> List[str]:
    out = []
    for m in _PHONE.finditer(text):
        d = resources.digits(m.group(1))
        if len(d) >= 3 and not re.fullmatch(r"\d{1,2}", d):
            out.append(d)
    return out


_INGESTION = re.compile(r"\b(took|taken|swallowed|overdos\w*|cut|slit|jumped|hanged|drank)\b", re.I)


def validate(reply: str, level: str, chosen: List[Dict[str, Any]], user_text: str = "",
             previous_reply: Optional[str] = None, number_recently_shown: bool = False) -> List[str]:
    """Return a list of problems (empty = safe to send)."""
    problems = []
    if previous_reply and repeats_previous(reply, previous_reply):
        problems.append("repeats the opening or question of your previous message; respond freshly to what they just said")
    dupes = repeated_sentences(reply, previous_reply)
    if len(dupes) >= 2:
        problems.append(f"reuses sentences from your previous message ({dupes[:2]}); say it differently or say something new")
    if level == "imminent" and _INGESTION.search(user_text) and not re.search(r"\b(medical|hospital|ambulance|doctor)\b", reply, re.I):
        problems.append("they may already have harmed themselves: say plainly they need medical help right now (hospital/ambulance/112)")
    if "?" not in reply:
        problems.append("does not ask the person anything (must check in on their safety or keep them talking)")
    nums = _numbers_in(reply)
    verified = resources.verified_numbers()
    allowed_hours_like = {d for d in nums if len(d) <= 4 and d not in verified}  # e.g. "24", "2026", "10"
    unknown = [d for d in nums if d not in verified and d not in allowed_hours_like]
    if unknown:
        problems.append(f"contains phone numbers that are not in the verified list: {unknown}")
    chosen_digits = set()
    for r in chosen:
        for key in ("phone", "alt"):
            if r.get(key):
                d = resources.digits(r[key])
                chosen_digits |= {d, d[2:] if d.startswith("91") and len(d) > 10 else d}
    # A number is required unless one was given in the last couple of messages: repeating the same
    # helpline in every reply is exactly what makes a bot feel scripted. (The frontend card always has them.)
    if not number_recently_shown and not any(d in chosen_digits for d in nums):
        problems.append("does not include any of the provided helpline numbers")
    if level == "imminent" and "112" not in reply:
        problems.append("emergency: must tell them to call 112")
    if safety.is_means_seeking(reply) or re.search(r"\b\d+\s?(mg|tablets|pills|metres|meters|feet|ft|floors)\b", reply, re.I):
        problems.append("contains content that could be read as means information")
    if len(reply) > 1300:
        problems.append("too long")
    return problems


def _recent_number(texts: List[str]) -> bool:
    verified = resources.verified_numbers()
    return any(d in verified for t in texts for d in _numbers_in(t))


def _fallback(level: str, recent_bot: List[str]) -> str:
    if level == "imminent":
        return safety.IMMINENT_MESSAGE
    base = safety.pick_fresh(safety.RISK_CHECKINS, recent_bot)
    return f"{base} You can also talk to a trained counsellor right now on Tele-MANAS, 14416, free and open 24x7."


def respond(
    text: str,
    level: str,
    history: List[Dict[str, str]],
    profile: Dict[str, List[str]],
    recent_bot: List[str],
    analysis: Optional[Dict[str, Any]] = None,
    means_seeking: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    lang = detect_language(text)
    chosen = resources.select("imminent" if level == "imminent" else "crisis", language=lang, k=3)
    contacts = "\n".join(f"- {resources.describe(r)}" + (" [OPEN NOW]" if resources.is_open(r) else "") for r in chosen)

    system = CRISIS_PROMPT
    if lang == "hinglish":
        system += "\nLANGUAGE: they are writing in Hinglish. Reply in natural Hinglish using Roman letters (not English, not Devanagari)."
    elif lang == "hindi":
        system += "\nLANGUAGE: they are writing in Hindi (Devanagari). Reply in simple Hindi."
    if level == "imminent":
        system += "\n" + IMMINENT_EXTRA
    if means_seeking:
        system += ("\nThey just asked for information that could be used for self-harm (e.g. heights, doses). Do not answer it; "
                   "say gently that you won't share that because you care about their safety, and check in directly.")
    known = {k: v for k, v in (profile or {}).items() if v and k in ("name", "facts", "support_people", "coping_that_helped", "interests")}
    if known:
        system += f"\n\nWhat you know about them (use naturally if it helps): {known}"
    if recent_bot:
        system += ("\n\nYour recent messages to them (do NOT repeat their wording, opening or questions; they have already seen these):\n"
                   + "\n".join(f"- {m[:220]}" for m in recent_bot[-3:]))
    if analysis and analysis.get("indirect_signals"):
        system += f"\n\nWarning signs noticed in their words: {analysis['indirect_signals']}"
    system += f"\n\nContacts you may mention (exact numbers only from this list):\n{contacts}"

    messages = [{"role": "system", "content": system}] + history[-8:] + [{"role": "user", "content": text}]
    meta: Dict[str, Any] = {"verdict": "ai_crisis", "attempts": 0, "resources": resources.public(chosen)}
    previous = recent_bot[-1] if recent_bot else None
    models = [config.CRISIS_MODEL, config.RESPONDER_MODEL]
    for attempt in range(2):
        meta["attempts"] = attempt + 1
        reply = None
        for model in models:
            try:
                reply = llm.chat(messages, model=model, temperature=0.8, max_tokens=900)
                break
            except llm.LLMUnavailable:
                continue
        if reply is None:
            break
        problems = validate(reply, level, chosen, user_text=text, previous_reply=previous,
                            number_recently_shown=level != "imminent" and _recent_number(recent_bot[-2:]))
        if not problems:
            return reply, meta
        # On the last attempt, mild repetition alone is not worth falling back to a fixed message.
        if attempt == 1 and all(p.startswith(("repeats", "reuses")) for p in problems):
            meta["accepted_with"] = problems
            return reply, meta
        meta["failed_checks"] = problems
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "[SYSTEM CHECK - rewrite your last message. Problems: " + "; ".join(problems)
             + ". Keep it warm and personal, and follow all the rules.]"},
        ]
    meta["verdict"] = "fallback"
    return _fallback(level, recent_bot), meta
