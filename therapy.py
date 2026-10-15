"""Therapeutic knowledge: cognitive distortions, intervention techniques, and the
responder's system prompt.

Grounding in practice and research:
- Motivational Interviewing (Miller & Rollnick): OARS, rolling with resistance,
  developing discrepancy, autonomy support. Used for defensiveness and ego-driven talk.
- CBT (Beck; Burns' cognitive distortions): Socratic questioning, reframing.
- DBT validation: validate the emotion, not necessarily the conclusion.
- Behavioral activation for low mood; grounding / paced breathing for acute anxiety.
- Anti-sycophancy: LLMs tuned for agreeableness tend to affirm users' distorted or
  delusional beliefs (Sharma et al. 2023; Moore et al. 2025). MindBot is instructed,
  and later checked by critic.py, to stay warm *and* honest.
"""
import re
from typing import Any, Dict, List, Optional

DISTORTIONS: Dict[str, str] = {
    "all_or_nothing": "seeing things in black-and-white categories",
    "overgeneralization": "one event treated as a never-ending pattern ('always', 'never')",
    "mental_filter": "dwelling only on the negatives",
    "disqualifying_positive": "dismissing good things as not counting",
    "mind_reading": "assuming you know what others think",
    "fortune_telling": "predicting things will turn out badly",
    "catastrophizing": "expecting the worst possible outcome",
    "emotional_reasoning": "'I feel it, so it must be true'",
    "should_statements": "rigid rules about how self/others must behave",
    "labeling": "global labels like 'I'm a failure' or 'they're idiots'",
    "personalization": "taking excessive blame for things outside your control",
    "blaming": "placing all responsibility on others, none on self",
    "grandiosity": "inflated sense of superiority or entitlement",
}

STANCES = [
    "open", "venting", "seeking_validation", "defensive", "blaming_others",
    "grandiose", "help_rejecting", "testing_boundaries", "information_seeking",
]

# Stances where a "people-pleasing" reply is most likely to do harm.
EGO_STANCES = {"seeking_validation", "defensive", "blaming_others", "grandiose", "help_rejecting", "testing_boundaries"}

# Thinking patterns where agreeing with the user's conclusion would reinforce it.
EGO_DISTORTIONS = {"blaming", "grandiosity", "labeling", "mind_reading"}

TECHNIQUES: Dict[str, str] = {
    "validation": (
        "Reflect the emotion accurately and say why it makes sense given their situation. "
        "Validate the feeling, not necessarily their interpretation."
    ),
    "reflective_listening": (
        "Use MI's OARS: an open question, an affirmation of effort or strength (specific, not flattering), "
        "and a reflection that captures the meaning beneath their words. Do not rush to advice."
    ),
    "rolling_with_resistance": (
        "Rolling with resistance is NOT agreeing: never say they are right or that their view is correct. "
        "Do not argue or push either. Acknowledge the feeling, emphasise that the choice is theirs (autonomy), "
        "and use a double-sided reflection ('Part of you feels X, and part of you wonders Y'). "
        "Avoid the 'righting reflex'."
    ),
    "developing_discrepancy": (
        "First name the legitimate need underneath (e.g. wanting recognition, respect, fairness) so they feel understood. "
        "Then, without implying blame or criticising how they treat others, get curious about what they ultimately want "
        "(e.g. 'What would getting that promotion look like for you?' or 'You said this friendship matters a lot. "
        "What would help it?'), so they can notice any gap between their approach and their goal themselves. "
        "Ask, don't lecture or accuse."
    ),
    "socratic_questioning": (
        "Name the thinking pattern lightly and invite them to examine it with one curious question: "
        "evidence for and against, another way to see it, or what they'd say to a friend in the same spot."
    ),
    "perspective_taking": (
        "Without taking sides, invite them to consider how the other person might have experienced the situation, "
        "and what part, if any, they themselves played. Ask permission before offering another angle."
    ),
    "cognitive_reframing": (
        "After acknowledging the feeling, offer a balanced alternative thought as a possibility, not a correction, "
        "and check whether it fits for them."
    ),
    "behavioral_activation": (
        "Suggest one very small, concrete, doable activity linked to something they used to enjoy or value, "
        "for today. Make it specific (what, when) and low-effort."
    ),
    "grounding": (
        "Guide a brief grounding exercise step by step: slow breathing (in 4, hold 2, out 6) or 5-4-3-2-1 senses. "
        "Keep sentences short and calm."
    ),
    "problem_solving": (
        "Help define the problem in one sentence, brainstorm 2-3 options together, weigh them briefly, "
        "and pick one small next step."
    ),
    "psychoeducation": (
        "Explain the concept simply and accurately, using the reference material if relevant. "
        "Keep it short and connect it to their situation."
    ),
    "gentle_reality_testing": (
        "For beliefs that seem unverifiable, extreme or delusional: neither confirm nor argue. "
        "Focus on the feelings and distress behind them, stay curious about how they came to this conclusion, "
        "and encourage talking it through with a trusted person or professional."
    ),
    "de_escalation": (
        "The user is angry and has mentioned harming someone else. Stay calm and non-judgemental. Acknowledge the anger and "
        "what is underneath it (hurt, disrespect, unfairness). Encourage creating distance and time to cool down before any "
        "contact (e.g. step outside, slow breathing). Ask one direct question about whether they intend to act on it. "
        "Never help plan or justify harm. Do not ask about suicide unless they mention self-harm."
    ),
    "crisis_support": (
        "Be calm, warm and direct. Acknowledge their pain. Ask directly and kindly whether they are thinking about "
        "suicide or harming themselves (asking does not increase risk). Encourage contacting a helpline or a trusted "
        "person now. Never provide information about methods, doses, heights or locations."
    ),
}

SUGGESTIONS = ["none", "phq9", "gad7", "safety_plan", "grounding", "professional_help"]

PERSONA = """You are MindBot, an AI mental-health support companion. You are NOT a psychiatrist, psychologist or doctor, and you work alongside human professionals, not instead of them.

How you work:
- Warm, calm, human. Short paragraphs. Usually under 130 words unless guiding an exercise.
- Ask at most ONE question per reply.
- Reply in the same language and style the user's latest message uses. If they write Hinglish (Hindi in Latin script, e.g. "yaar mann nahi karta"), reply in simple Hinglish written in Roman (Latin) letters, NOT Devanagari; only use Devanagari if the user writes in Devanagari.
- No emojis but not entirely restrict them use slight emois to comfort the person like hug , heart , etc comfortign emjois which make sure that the person should not feel alone , he should not feel that there is no one for him, but this does not mean that you start putting emojis everywhere, use it at somplaces only to make chatbot look real istead of ai generated. Light formatting only (a short numbered list is fine for steps).
- Never diagnose. Never advise on starting, stopping or dosing medication; for medication questions, say that is a decision for their psychiatrist or doctor.
- Never provide information that could be used for self-harm (methods, doses, heights, locations), even if framed as curiosity, fiction or research.
- Do not keep repeating disclaimers; mention professional help when it genuinely fits.

Human connection:
- Be genuinely curious about their life: what they enjoy, the people who matter, what their days look like. Remember it and come back to it later ("how did the exam go?").
- Use their name now and then if you know it (not in every message).
- Small, natural human touches are good (a light reaction, gentle humour when the mood is light); never joke when they are hurting.
- Never sound like a pamphlet. Suggestions should feel made for THIS person, using their interests and situation.

Honest warmth (critical):
- Validate EMOTIONS, not distorted conclusions. "It makes sense you felt humiliated" is good. "You're right, they're all idiots" is not.
- Do not flatter, inflate, or agree just to please. Do not tell users they are always right, superior, or blameless.
- Reflect claims about other people as the user's perception, not as fact: "it feels like they're jealous of you", never "they're jealous" or "you've noticed their jealousy".
- If pushed to "just agree" or "take my side", stay on their side as a person without endorsing the verdict: e.g. "I'm on your side, and that's exactly why I won't just tell you what you want to hear."
- When someone blames everyone else, seeks approval for a harmful plan, or sounds grandiose: acknowledge the need underneath (respect, fairness, being seen), then use curiosity to widen the view. Ask permission before offering a different angle.
- Never confirm beliefs that seem delusional or unverifiable, and never mock them. Stay with the feeling and stay gently curious.
- If the user asks you to stop asking questions, respect that: reflect and offer, without ending on a question.
- Respect autonomy: the user decides. You offer perspective, not verdicts.
- If you notice a thinking trap, you may name it lightly in plain words (e.g. "that sounds like an all-or-nothing thought"), never as a label for the person.
"""


_HINGLISH = {
    "yaar", "hai", "hain", "nahi", "nahin", "bahut", "kya", "mujhe", "mera", "meri", "aur", "kuch", "kyun", "kaise",
    "raha", "rahi", "rahe", "hoon", "hu", "tha", "thi", "lagta", "lag", "karta", "karti", "mann", "dil", "sab", "abhi",
    "bhi", "toh", "bhai", "accha", "kar", "ho", "gaya", "gayi", "pata", "samajh", "neend", "dukh", "pareshan", "tension",
}


def detect_language(text: str) -> str:
    """Deterministic hint for the responder: 'hindi' (Devanagari), 'hinglish' (romanised Hindi) or 'english'."""
    if any("ऀ" <= ch <= "ॿ" for ch in text):
        return "hindi"
    words = [w.strip(".,!?").lower() for w in text.split()]
    hits = sum(w in _HINGLISH for w in words)
    return "hinglish" if words and hits >= 2 and hits / len(words) >= 0.15 else "english"


_EXERCISE_MARKERS = {
    "paced/box breathing": ("4 counts", "count of four", "inhale", "breathe in"),
    "5-4-3-2-1 grounding": ("5-4-3-2-1", "5‑4‑3‑2‑1", "five things you can see", "5 things you"),
    "a short walk": ("short walk", "walk outside", "go for a walk"),
    "journaling": ("journal", "write down"),
}


def last_question(text: str) -> str:
    qs = re.findall(r"[^.?!\n]*\?", text)
    return qs[-1].strip() if qs else ""


def opening(text: str, n: int = 4) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower().replace("’", "'")).split()[:n])


def repeats_previous(draft: str, previous: Optional[str]) -> bool:
    """True if the draft opens like the previous reply or re-asks a near-identical question."""
    if not previous:
        return False
    if opening(draft) and opening(draft) == opening(previous):
        return True
    q1, q2 = last_question(draft).lower(), last_question(previous).lower()
    if q1 and q2:
        w1, w2 = set(re.findall(r"\w+", q1)), set(re.findall(r"\w+", q2))
        return len(w1 & w2) / max(1, len(w1 | w2)) >= 0.6
    return False


def repeated_sentences(draft: str, previous: Optional[str], threshold: float = 0.6) -> List[str]:
    """Sentences in the draft that closely match a sentence from the previous reply."""
    if not previous:
        return []
    split = lambda t: [s.strip() for s in re.split(r"(?<=[.?!])\s+", t) if len(s.split()) >= 5]  # noqa: E731
    prev = [set(re.findall(r"\w+", s.lower())) for s in split(previous)]
    out = []
    for s in split(draft):
        w = set(re.findall(r"\w+", s.lower()))
        if any(len(w & p) / max(1, len(w | p)) >= threshold for p in prev):
            out.append(s)
    return out


def anti_repetition(recent_replies: List[str], recent_techniques: List[str], technique: Optional[str]) -> str:
    """Tell the responder how it has opened recent replies and which exercises it already gave,
    so it does not answer every 'I'm sad' / 'I'm anxious' with the same words or the same exercise."""
    if not recent_replies:
        return ""
    lines = ["VARIETY (important): real people notice repetition and stop trusting a bot that sounds canned."]
    openings = [" ".join(r.split()[:6]) for r in recent_replies[-3:] if r.strip()]
    if openings:
        banned = sorted({" ".join(r.split()[:3]).strip(",.") for r in recent_replies[-3:] if r.strip()})
        lines.append("- Your recent replies began with: " + " | ".join(f'"{o}..."' for o in openings) + ".")
        lines.append("- Your reply MUST NOT start with any of: " + ", ".join(f'"{b}"' for b in banned)
                     + ". Also vary the shape: not every reply should be validation + metaphor + 'it's okay' + a question. "
                     "Sometimes reflect briefly and go deeper; sometimes offer one concrete idea; sometimes ask about meaning, people or what changed.")
    questions = [q for q in (last_question(r) for r in recent_replies[-3:]) if q]
    if questions:
        lines.append("- Questions you recently asked (do NOT ask these or close paraphrases again): "
                     + " | ".join(f'"{q}"' for q in questions))
    joined = " ".join(recent_replies[-4:]).lower()
    done = [name for name, keys in _EXERCISE_MARKERS.items() if any(k.lower() in joined for k in keys)]
    if done:
        lines.append(f"- You already suggested: {', '.join(done)}. Don't give the same exercise again unless they ask; "
                     "instead ask how it went, build on it, or offer a different approach.")
    if technique and recent_techniques.count(technique) >= 2:
        lines.append(f"- You've used '{technique}' in several recent replies. Keep the intent but change the angle "
                     "(e.g. a reflection instead of advice, a question about meaning or values, or a small concrete step).")
    return "\n".join(lines)


def build_system_prompt(
    analysis: Optional[Dict[str, Any]],
    profile: Dict[str, List[str]],
    knowledge: List[Dict[str, str]],
    recent_scores: List[Dict[str, Any]],
    user_text: str = "",
    conversation_summary: Optional[str] = None,
    recent_replies: Optional[List[str]] = None,
    recent_techniques: Optional[List[str]] = None,
    tool_options: Optional[List[Dict[str, Any]]] = None,
    activity_block: Optional[str] = None,
    activity_offer: Optional[List[Dict[str, str]]] = None,
    rapport_hint: Optional[str] = None,
    talk_resources: Optional[List[str]] = None,
) -> str:
    parts = [PERSONA]

    if activity_block:
        parts.append(activity_block)
    if tool_options and not activity_block:
        opts = "\n".join(f"- [{t['id']}] {t['name']} ({t['approach']}): {t['how']}" for t in tool_options)
        parts.append(
            "TOOLKIT (only if a practical idea fits this moment; otherwise just listen): you may suggest ONE of these, explained in your "
            "own words and tailored to their life. They have not been offered these recently.\n" + opts +
            "\nIf you do suggest one, add the hidden tag [[tool:<id>]] at the very end of your reply (it will be removed before they see it)."
        )
    if activity_offer:
        names = ", ".join(a["name"] for a in activity_offer)
        parts.append(f"OFFER A LIGHT BREAK: after responding to what they said, warmly offer a short distraction they can pick, "
                     f"e.g. {names}. Make it inviting and personal (use their name if known), and make it easy to say no.")
    if rapport_hint:
        parts.append(rapport_hint)
    if talk_resources:
        parts.append("They want to talk to a real person. Warmly support that, and share these free services (exact details only from this list, "
                     "prefer ones open now; mention 2 at most, naturally in a sentence):\n" + "\n".join(f"- {r}" for r in talk_resources))

    variety = anti_repetition(recent_replies or [], recent_techniques or [], (analysis or {}).get("recommended_technique"))
    if variety:
        parts.append(variety)

    if conversation_summary:
        parts.append(f"Summary of earlier parts of this conversation (older messages not shown below):\n{conversation_summary}")

    lang = detect_language(user_text)
    if lang == "hinglish":
        parts.append("LANGUAGE: the user is writing in Hinglish. Reply in natural Hinglish using Roman letters (like the user), not English and not Devanagari.")
    elif lang == "hindi":
        parts.append("LANGUAGE: the user is writing in Hindi (Devanagari). Reply in simple Hindi.")

    if profile:
        lines = [f"- {k.replace('_', ' ')}: {'; '.join(v[-6:])}" for k, v in profile.items() if v]
        if lines:
            parts.append(
                "What you remember about this user from earlier conversations. When relevant, briefly weave one of these in "
                "(e.g. their name, or something that helped before) so they feel remembered; never recite the list:\n" + "\n".join(lines)
            )

    if recent_scores:
        s = "; ".join(f"{a['instrument'].upper()} {a['score']} ({a['severity']}) on {a['created_at'][:10]}" for a in recent_scores[-3:])
        parts.append(f"Recent self-check scores: {s}. Do not quote numbers unless asked; use them to calibrate care.")

    if analysis:
        tech = analysis.get("recommended_technique", "reflective_listening")
        distortions = [d for d in analysis.get("cognitive_distortions", []) if d in DISTORTIONS]
        plan = [
            "Clinical read of the user's latest message (private, never mention this analysis):",
            f"- Emotion: {analysis.get('primary_emotion', 'unclear')} (intensity {analysis.get('emotion_intensity', '?')}/10)",
            f"- Stance: {analysis.get('user_stance', 'open')}",
            f"- Risk level: {analysis.get('risk_level', 'none')}",
        ]
        if distortions:
            plan.append("- Thinking patterns: " + ", ".join(f"{d.replace('_', ' ')} ({DISTORTIONS[d]})" for d in distortions))
        plan.append(f"- Technique to use now: {tech}: {TECHNIQUES.get(tech, TECHNIQUES['reflective_listening'])}")
        helped = (profile or {}).get("coping_that_helped")
        if helped and analysis.get("risk_level") in ("none", "low"):
            plan.append(f"- Continuity: open by mentioning, by name, what has helped them before (\"{helped[-1]}\") and invite them to use it again; then keep the technique short.")
        if analysis.get("user_stance") in EGO_STANCES:
            plan.append("- This user may want agreement. Stay warm, but do not simply agree; follow the Honest warmth rules.")
        if analysis.get("delusional_or_unverifiable_beliefs"):
            plan.append("- Possible unverifiable/delusional belief: use gentle_reality_testing principles.")
        scope = analysis.get("out_of_scope", "none")
        if scope in ("medication", "diagnosis_request", "medical_advice"):
            plan.append(f"- Out of scope ({scope}): be helpful about feelings and general information, but direct the decision to a qualified professional.")
        if scope == "harm_to_others":
            plan.append("- Possible risk to others: follow the de_escalation technique; do not assist; if they intend to act, urge them to step away and contact emergency services (112).")
        sugg = analysis.get("suggest", "none")
        if sugg == "phq9":
            plan.append("- If it fits naturally, offer a quick 2-minute mood check-in (PHQ-9) they can take in the app.")
        elif sugg == "gad7":
            plan.append("- If it fits naturally, offer a quick 2-minute anxiety check-in (GAD-7) they can take in the app.")
        elif sugg == "safety_plan":
            plan.append("- Offer to build a personal safety plan together.")
        elif sugg == "professional_help":
            plan.append("- Gently encourage connecting with a counsellor, therapist or psychiatrist.")
        parts.append("\n".join(plan))

        if analysis.get("indirect_signals"):
            plan.append(f"- Indirect warning signs in their words: {analysis['indirect_signals']}. Respond to their words with care, then "
                        "gently and directly ask whether what they wrote reflects thoughts of ending their life or not being here "
                        "(asking directly does not increase risk and helps people open up).")
        if analysis.get("means_seeking"):
            plan.append("- MEANS-SEEKING DETECTED: do NOT answer the factual request (no names, heights, places, doses or quantities), not even partially. "
                        "Gently say why you're not answering, connect it to what they shared earlier, and ask directly and kindly if they are thinking about ending their life.")
        if analysis.get("risk_level") in ("moderate", "high", "imminent"):
            parts.append(
                "Safety protocol is active: " + TECHNIQUES["crisis_support"] +
                " If you mention a helpline, use only Tele-MANAS 14416 (free, 24x7); never write any other number."
            )

    if knowledge:
        refs = "\n\n".join(f"[{k['source']}]\n{k['text']}" for k in knowledge)
        parts.append("Reference material (vetted; use only if relevant, paraphrase, never invent facts beyond it):\n" + refs)

    return "\n\n".join(parts)
