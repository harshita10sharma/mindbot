"""Layered risk detection and crisis response.

Layer 1 (this file): fast deterministic lexicon. Catches explicit statements, slang,
Hinglish phrases and *means-seeking* questions (e.g. "how tall is the bridge") that
plain keyword lists and many LLM bots miss (Moore et al., FAccT 2025).
Layer 2 (analyzer.py): LLM risk assessment with full conversation context.
The final level is fused in `fuse_risk`: high/imminent lexicon hits can never be
downgraded by the LLM (safety first); moderate hits can be softened, never erased.

Levels follow a C-SSRS-style ladder: none < low < moderate < high < imminent.
"""
import re
from typing import Dict, List, Optional, Tuple

LEVELS = ["none", "low", "moderate", "high", "imminent"]


def level_index(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def max_level(*levels: str) -> str:
    return max(levels, key=level_index)


_P = lambda *pats: [re.compile(p, re.IGNORECASE) for p in pats]  # noqa: E731

IMMINENT = _P(
    r"\b(going to|gonna|about to|will) (kill myself|end (it|my life)|die tonight)\b",
    r"\bkill myself (tonight|today|now|right now)\b",
    r"\b(took|swallowed|taken) (a lot of|all|too many|many|\d+) (my )?(pills|tablets|sleeping pills)\b",
    r"\b(i'?ve|i have) (overdosed|taken an overdose)\b",
    r"\bsuicide note\b",
    r"\b(this is|consider this) my (last|final) (message|goodbye)\b",
    r"\bstanding on (the|a) (roof|ledge|bridge|edge)\b",
    r"\b(have|got) (the )?(rope|gun|pills|blade) (ready|with me|right here)\b",
)

HIGH = _P(
    r"\bkill(ing)? myself\b", r"\bkms\b", r"\bkys\b",
    r"\bend(ing)? (my life|it all)\b", r"\btake my (own )?life\b",
    r"\b(want|wanna|wish|going) to die\b", r"\bwanna die\b", r"\bwish i (was|were) dead\b",
    r"\bsuicid(e|al)\b", r"\bunalive\b",
    r"\b(want|wanna|going|gonna|plan(ning)?|thinking of|about) to jump (off|from)\b",
    r"\bjump(ing)? (off|from) (the |a |my )?(\d+\w* )?(floor|roof|terrace|building|bridge|balcony|cliff|tower)\b",
    r"\b(don'?t|do not) want to (live|be alive|exist|wake up)( anymore)?\b",
    r"\bno reason to (live|go on)\b", r"\bbetter off (dead|without me)\b",
    r"\bself[- ]?harm(ing)?\b", r"\bcut(ting)? myself\b", r"\bhurt(ing)? myself\b",
    # Hinglish / Hindi (romanised)
    r"\bmar(na| jaana| jana) chaht[aie]\b", r"\bmarna hai\b", r"\bjeena nahi chaht[aie]\b",
    r"\bjeene ka (mann|man) nahi\b", r"\bkhudkushi\b", r"\ba+t+ma?hatya\b", r"\bkhud ko (khatam|maar)\b",
)

MODERATE = _P(
    r"\bcan'?t (go on|do this anymore|take (it|this) anymore)\b", r"\bcannot go on\b",
    r"\bno point (in )?(living|life|anything|going on)\b", r"\bnothing matters anymore\b",
    r"\b(feel|feeling|am|i'?m) (so |completely |totally )?(hopeless|worthless)\b",
    r"\b(i'?m|i am) (just )?a burden\b", r"\bdisappear (forever|for good)\b",
    r"\bgive up on (life|everything|living)\b", r"\bsab khatam\b",
    r"\b(everything|life|it all) (feels|is|seems) (so )?(pointless|meaningless)\b",
    r"\bwhat'?s the point (of|in) (living|life|anything)\b",
    # indirect warning signs (AFSP / suicide.ca): farewells, giving things away, "won't be around"
    r"\bgiv(e|ing) away (all )?my (stuff|things|belongings|possessions|books|clothes)\b",
    r"\byou won'?t (hear from|see) me (again|anymore|ever)\b",
    r"\b(won'?t|will not) be (a burden|around|here) (much longer|for long|anymore|for much longer)\b",
    r"\b(sleep|rest) forever\b", r"\bnever (have to )?wake up again\b",
    r"\b(everyone|everybody|they|my family)('d| would) be better off\b",
    r"\bthis is (my )?(goodbye|farewell)\b", r"\bthank you for everything,? (goodbye|bye|farewell)\b",
    r"\btired of (existing|living|being alive)\b", r"\bsoon (it|none of this) (won'?t|will not) matter\b",
)

# Requests for lethal means. On their own they are moderate; combined with any
# distress signal in the conversation they escalate to high.
MEANS = _P(
    r"\bhow many (pills|tablets|paracetamol|sleeping pills)\b", r"\blethal dose\b",
    r"\boverdose on\b", r"\b(tallest|highest) (bridge|building)s?\b",
    r"\bhow (high|tall) (is|are) .{0,40}(bridge|building|tower|cliff)",
    r"\b(bridge|building|tower|cliff|flyover|roof)s? .{0,25}(taller|higher|tall|high) (than|enough)\b",
    r"\b(tall|high|highest|tallest) (bridge|building|tower|cliff|flyover|rooftop)s?\b",
    r"\b(bridge|building|tower|cliff)s? (above|over) \d+ ?(m|meters|metres|feet|ft|floors)\b",
    r"\bpainless way(s)? to die\b", r"\bhow to hang( myself)?\b",
    r"\bhow long (does it|would it) take to die\b", r"\b(rat|rodent) poison\b",
    r"\bwhere (can|do) i (buy|get) (a gun|poison|cyanide)\b",
)

DENIAL = _P(
    r"\b(i'?m|i am) not (suicidal|going to (kill|hurt) myself)\b",
    r"\b(would|will) never (kill|hurt) myself\b",
    r"\bnot (thinking|thought) (about|of) (suicide|killing myself)\b",
)


def _hits(patterns, text: str) -> List[str]:
    return [m.group(0) for p in patterns if (m := p.search(text))]


def lexicon_risk(text: str, recent_distress: bool = False) -> Tuple[str, List[str]]:
    """Return (level, evidence) from the deterministic lexicon."""
    evidence: List[str] = []
    level = "none"
    for lvl, pats in (("imminent", IMMINENT), ("high", HIGH), ("moderate", MODERATE)):
        found = _hits(pats, text)
        if found:
            evidence += found
            level = max_level(level, lvl)
    means = _hits(MEANS, text)
    if means:
        evidence += means
        level = max_level(level, "high" if (recent_distress or level != "none") else "moderate")
    if _hits(DENIAL, text) and level in ("high", "moderate"):
        level = LEVELS[level_index(level) - 1]
    return level, evidence


def is_means_seeking(text: str) -> bool:
    return bool(_hits(MEANS, text))


def fuse_risk(lexicon_level: str, llm_level: Optional[str]) -> str:
    """Safety-first fusion of lexicon and LLM judgements."""
    if llm_level not in LEVELS:
        return lexicon_level
    if level_index(lexicon_level) >= level_index("high"):
        return max_level(lexicon_level, llm_level)
    if lexicon_level == "moderate" and level_index(llm_level) < level_index("moderate"):
        return "low"  # e.g. "hopeless at maths": soften but keep on record
    return max_level(lexicon_level, llm_level)


# ---------------- crisis resources ----------------
RESOURCES: List[Dict[str, str]] = [
    {"region": "India", "name": "Tele-MANAS (Govt. of India, 24x7, free)", "contact": "14416 or 1800-891-4416"},
    {"region": "India", "name": "Vandrevala Foundation (24x7, call or WhatsApp)", "contact": "+91 9999 666 555"},
    {"region": "India", "name": "iCALL (Mon-Sat, 10am-8pm)", "contact": "+91 91529 87821"},
    {"region": "India", "name": "Emergency services", "contact": "112"},
    {"region": "USA", "name": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988"},
    {"region": "UK", "name": "Samaritans", "contact": "116 123"},
]


def _resource_lines() -> str:
    return "\n".join(f"- {r['region']}: {r['name']}: {r['contact']}" for r in RESOURCES)


IMMINENT_MESSAGE = (
    "I'm really glad you told me, and I'm taking what you said seriously. Your safety matters most right now.\n\n"
    "Please call emergency services (112 in India) or go to the nearest hospital emergency department now. "
    "If you can, move away from anything you could use to hurt yourself, and stay with someone or ask someone to come to you.\n\n"
    "You can also talk to a trained person right now:\n" + _resource_lines() + "\n\n"
    "I'm still here with you. Can you tell me: are you somewhere safe at this moment?"
)
IMMINENT_MARKER = "I'm taking what you said seriously. Your safety matters most right now."

HIGH_MESSAGE = (
    "Thank you for trusting me with something this heavy. It sounds like you're in a lot of pain, "
    "and you deserve real support from a person right now, not just from me.\n\n"
    "Please reach out to one of these free, confidential lines:\n" + _resource_lines() + "\n\n"
    "If you are in immediate danger, call 112 (India) or your local emergency number.\n\n"
    "I'm here and I'm not going anywhere. Would you be willing to tell me a little about what's making things feel this way? "
    "We can also make a short safety plan together, step by step."
)

# ---- Fixed safety texts come in variants so a person who keeps talking never sees
# ---- the same sentence twice in a row (repetition makes a bot feel canned and uncaring).
MEANS_CHECKINS = [
    "I'm not going to answer that one, and it's because I care about your safety. "
    "With everything you've been carrying, I want to ask you directly, and you can be honest with me: "
    "are you having thoughts of ending your life? Whatever your answer is, I'm here, and I won't judge you.",
    "I'd rather not share that, because I'm worried about you after what you told me. "
    "Can I ask you something directly? Are you thinking about suicide right now? You can tell me the truth; I'm listening.",
    "I'm going to hold back on that question, and I want to be honest about why: I care about what happens to you. "
    "Are you having thoughts of hurting yourself? Whatever is going on, we can talk about it.",
]
RISK_CHECKINS = [
    "What you're going through sounds really painful, and I'm glad you're talking to me. "
    "I want to make sure you're safe, so I'll ask you directly: are you having thoughts of hurting yourself or ending your life? "
    "Whatever your answer is, I'm here with you.",
    "That sounds incredibly heavy to carry. I'd like to check something with you, plainly and without judgement: "
    "are you thinking about suicide or harming yourself? Your answer won't scare me away.",
    "Thank you for telling me this. Because it matters, I'm going to ask you straight out: "
    "are you having any thoughts of ending your life right now? I'm here, whatever the answer.",
]
# Shown instead of the full helpline list when it was already shown recently.
RESOURCE_REMINDERS = [
    "The helplines I shared earlier, like Tele-MANAS on 14416, are free and open right now if you want to talk to someone.",
    "If it would help to hear a human voice tonight, Tele-MANAS (14416) or Vandrevala (+91 9999 666 555) are there 24x7.",
    "Remember, you can reach a trained counsellor any time: Tele-MANAS 14416, free and confidential.",
    "If things get harder, please call 14416 (Tele-MANAS) or 112 in an emergency. You don't have to wait until it's unbearable.",
]
MODERATE_LINES = [
    "If it ever starts to feel like too much, Tele-MANAS (14416, free, 24x7) is there to talk.",
    "And if you'd ever like to talk to a person, Tele-MANAS on 14416 is free and available around the clock.",
    "You can also reach a trained counsellor any time on 14416 (Tele-MANAS), free and confidential.",
]
IMMINENT_REMINDERS = [
    "Please call 112 now, or ask someone near you to call for you. I'm staying right here with you.",
    "Your safety comes first: please contact 112 or get to the nearest emergency department now. I'm still here.",
    "Please don't stay alone with this. Call 112 or Tele-MANAS (14416) right now, and keep talking to me while you do.",
]
RESOURCE_MARKER = "Free, confidential support is available right now"

# Backward-compatible single names.
MEANS_CHECKIN = MEANS_CHECKINS[0]
RISK_CHECKIN = RISK_CHECKINS[0]


def pick_fresh(options: List[str], recent_texts: List[str]) -> str:
    """Pick a variant that does not appear in the recent conversation; random among the unused ones."""
    import random
    joined = "\n".join(recent_texts)
    unused = [o for o in options if o[:60] not in joined]
    return random.choice(unused or options)


def shown_recently(marker: str, recent_texts: List[str]) -> bool:
    return any(marker in t for t in recent_texts)

_REFUSAL = re.compile(r"\b(i can'?t|i cannot|i'?m (not able|unable) to) (help|assist|provide|do) (with )?(that|this)\b", re.IGNORECASE)


def is_bare_refusal(reply: str) -> bool:
    """Model safety refusals ("Sorry, I can't help with that") feel cold to someone in crisis."""
    return bool(_REFUSAL.search(reply)) and len(reply) < 260


# Kept for backward compatibility with older imports.
SAFETY_MESSAGE = HIGH_MESSAGE


def crisis_message(level: str) -> Optional[str]:
    if level == "imminent":
        return IMMINENT_MESSAGE
    if level == "high":
        return HIGH_MESSAGE
    return None


def contains_crisis_keywords(text: str) -> bool:
    """Backward-compatible helper: True for high or imminent lexicon risk."""
    return level_index(lexicon_risk(text)[0]) >= level_index("high")
