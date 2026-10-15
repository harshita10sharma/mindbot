"""Validated self-report screening instruments, scored deterministically.

- PHQ-9 (Kroenke, Spitzer & Williams, 2001): depression severity. Free to use.
- GAD-7 (Spitzer et al., 2006): anxiety severity. Free to use.
- C-SSRS Screener (Columbia Lighthouse Project): suicide-risk triage, screen version.

These are screening tools, not diagnoses. Scores are shown with that framing and
can be reviewed by a clinician in the dashboard.
"""
from typing import Any, Dict, List

FREQ_OPTIONS = [
    {"value": 0, "label": "Not at all"},
    {"value": 1, "label": "Several days"},
    {"value": 2, "label": "More than half the days"},
    {"value": 3, "label": "Nearly every day"},
]
YES_NO = [{"value": 0, "label": "No"}, {"value": 1, "label": "Yes"}]

INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "phq9": {
        "title": "PHQ-9 mood check-in",
        "prompt": "Over the last 2 weeks, how often have you been bothered by any of the following problems?",
        "options": FREQ_OPTIONS,
        "items": [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless",
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself, or that you are a failure or have let yourself or your family down",
            "Trouble concentrating on things, such as reading or watching television",
            "Moving or speaking so slowly that other people could have noticed, or being so fidgety or restless that you have been moving around a lot more than usual",
            "Thoughts that you would be better off dead, or of hurting yourself in some way",
        ],
        "bands": [(4, "minimal"), (9, "mild"), (14, "moderate"), (19, "moderately severe"), (27, "severe")],
    },
    "gad7": {
        "title": "GAD-7 anxiety check-in",
        "prompt": "Over the last 2 weeks, how often have you been bothered by the following problems?",
        "options": FREQ_OPTIONS,
        "items": [
            "Feeling nervous, anxious, or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it is hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid, as if something awful might happen",
        ],
        "bands": [(4, "minimal"), (9, "mild"), (14, "moderate"), (21, "severe")],
    },
    "cssrs": {
        "title": "Safety check (C-SSRS screener)",
        "prompt": "In the past month (question 6: in the past 3 months):",
        "options": YES_NO,
        "items": [
            "Have you wished you were dead or wished you could go to sleep and not wake up?",
            "Have you actually had any thoughts of killing yourself?",
            "Have you been thinking about how you might do this?",
            "Have you had these thoughts and had some intention of acting on them?",
            "Have you started to work out or worked out the details of how to kill yourself, and do you intend to carry out this plan?",
            "Have you done anything, started to do anything, or prepared to do anything to end your life?",
        ],
    },
}

INTERPRETATION = {
    "minimal": "Your answers suggest minimal symptoms right now.",
    "mild": "Your answers suggest mild symptoms. Self-care and keeping an eye on how things change can help.",
    "moderate": "Your answers suggest moderate symptoms. Talking to a counsellor or doctor would be a good idea.",
    "moderately severe": "Your answers suggest moderately severe symptoms. We strongly recommend speaking with a mental-health professional soon.",
    "severe": "Your answers suggest severe symptoms. Please reach out to a mental-health professional as soon as possible.",
}


class AssessmentError(ValueError):
    pass


def get_instrument(name: str) -> Dict[str, Any]:
    if name not in INSTRUMENTS:
        raise AssessmentError(f"Unknown instrument '{name}'. Use one of: {', '.join(INSTRUMENTS)}")
    inst = INSTRUMENTS[name]
    return {
        "id": name,
        "title": inst["title"],
        "prompt": inst["prompt"],
        "options": inst["options"],
        "items": [{"index": i, "text": t} for i, t in enumerate(inst["items"])],
        "disclaimer": "This is a screening tool, not a diagnosis.",
    }


def score(name: str, answers: List[int]) -> Dict[str, Any]:
    inst = INSTRUMENTS.get(name)
    if not inst:
        raise AssessmentError(f"Unknown instrument '{name}'")
    if len(answers) != len(inst["items"]):
        raise AssessmentError(f"{name} needs exactly {len(inst['items'])} answers, got {len(answers)}")
    max_val = max(o["value"] for o in inst["options"])
    if any((not isinstance(a, int)) or a < 0 or a > max_val for a in answers):
        raise AssessmentError(f"Each answer must be an integer from 0 to {max_val}")

    total = sum(answers)
    if name == "cssrs":
        if answers[3] or answers[4] or answers[5]:
            severity, risk = "high risk", "high"
        elif answers[2]:
            severity, risk = "moderate risk", "moderate"
        elif answers[0] or answers[1]:
            severity, risk = "low risk", "low"
        else:
            severity, risk = "no risk indicated", "none"
        return {
            "instrument": name, "score": total, "severity": severity, "risk_level": risk,
            "interpretation": "Thank you for answering honestly. " + (
                "Please talk to someone right now; the helplines below are free and confidential." if risk == "high" else
                "It would really help to talk this through with a professional soon." if risk in ("moderate", "low") else
                "Nothing in your answers suggests immediate risk."
            ),
        }

    severity = next(label for cutoff, label in inst["bands"] if total <= cutoff)
    risk = "none"
    if name == "phq9" and answers[8] > 0:
        # Item 9 endorses thoughts of death/self-harm: always escalate for follow-up.
        risk = "high" if answers[8] >= 2 else "moderate"
    elif severity in ("moderately severe", "severe"):
        risk = "low"
    return {
        "instrument": name, "score": total, "max_score": max_val * len(inst["items"]),
        "severity": severity, "risk_level": risk,
        "interpretation": INTERPRETATION[severity],
        "disclaimer": "This is a screening tool, not a diagnosis.",
    }


SAFETY_PLAN_FIELDS = {
    "warning_signs": "Thoughts, feelings or situations that tell me a crisis may be starting",
    "coping_strategies": "Things I can do on my own to take my mind off problems",
    "distraction_people_places": "People and places that help me feel better",
    "people_to_ask_for_help": "People I can reach out to for help",
    "professionals": "Professionals or helplines I can contact",
    "safe_environment": "Ways to make my surroundings safer",
    "reasons_for_living": "The things that are most important to me and worth living for",
}
"""Stanley & Brown (2012) Safety Planning Intervention structure."""
