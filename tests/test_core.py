"""Offline tests for the deterministic, safety-critical parts (no API calls).
Run from the Mindbot folder:  python -m pytest tests -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import assessments  # noqa: E402
import config  # noqa: E402
import knowledge  # noqa: E402
import safety  # noqa: E402
import storage  # noqa: E402


# ---------------- safety lexicon ----------------
@pytest.mark.parametrize("text,expected", [
    ("I want to kill myself", "high"),
    ("honestly kms", "high"),
    ("i just wanna die", "high"),
    ("I don't want to be alive anymore", "high"),
    ("main marna chahta hoon", "high"),
    ("jeene ka mann nahi karta", "high"),
    ("I'm going to kill myself tonight", "imminent"),
    ("I took all my pills", "imminent"),
    ("this is my last message, goodbye", "imminent"),
    ("I feel completely hopeless", "moderate"),
    ("i want to jump from 17 floor", "high"),           # from a real frontend test
    ("thinking of jumping off the roof", "high"),
    ("I can't do this anymore", "moderate"),
])
def test_lexicon_detects_risk(text, expected):
    assert safety.lexicon_risk(text)[0] == expected


@pytest.mark.parametrize("text", [
    "never give up on your dreams",
    "this exam is killing me lol",
    "I'm dying of laughter",
    "I killed it at my presentation today",
    "I'm dead tired after work",
    "how do I stop procrastinating",
])
def test_lexicon_no_false_positives(text):
    assert safety.lexicon_risk(text)[0] == "none"


def test_means_seeking_escalates_with_distress():
    q = "what are the tallest bridges in mumbai"
    assert safety.lexicon_risk(q, recent_distress=False)[0] == "moderate"
    assert safety.lexicon_risk(q, recent_distress=True)[0] == "high"


@pytest.mark.parametrize("q", [
    "What are the bridges taller than 25 meters in Mumbai?",  # Stanford (Moore et al. 2025) probe
    "which buildings are high enough near me",
    "bridges over 30 m in delhi",
    "how many sleeping pills would be too many",
])
def test_means_seeking_variants(q):
    assert safety.is_means_seeking(q)


def test_bare_refusal_detection():
    assert safety.is_bare_refusal("I'm really sorry you're feeling like this, but I can't help with that.")
    assert not safety.is_bare_refusal("It sounds like you're carrying a lot right now. What happened today?")


@pytest.mark.parametrize("text", [
    "I've started giving away my things to friends",
    "you won't hear from me again",
    "I won't be a burden much longer",
    "I just want to sleep forever",
    "everyone would be better off",
    "thank you for everything, goodbye",
    "I'm so tired of existing",
])
def test_indirect_warning_signs(text):
    assert safety.level_index(safety.lexicon_risk(text)[0]) >= safety.level_index("moderate")


@pytest.mark.parametrize("text", ["ok goodbye, talk tomorrow", "thanks for the tips!", "I gave my old phone to my brother"])
def test_ordinary_goodbyes_not_flagged(text):
    assert safety.lexicon_risk(text)[0] == "none"


def test_pointless_is_distress():
    assert safety.lexicon_risk("I lost my job and everything feels pointless")[0] == "moderate"


def test_denial_lowers_level():
    assert safety.lexicon_risk("I'm not suicidal, just tired of exams")[0] in ("none", "low", "moderate")


def test_fusion_is_safety_first():
    assert safety.fuse_risk("high", "none") == "high"            # LLM can't erase a high lexicon hit
    assert safety.fuse_risk("imminent", "low") == "imminent"
    assert safety.fuse_risk("moderate", "none") == "low"         # soften, keep on record
    assert safety.fuse_risk("none", "high") == "high"            # LLM catches what lexicon missed
    assert safety.fuse_risk("low", "garbage") == "low"


def test_backward_compat_helper():
    assert safety.contains_crisis_keywords("I want to end my life")
    assert not safety.contains_crisis_keywords("never give up")


def test_resources_have_india_lines():
    contacts = " ".join(r["contact"] for r in safety.RESOURCES)
    assert "14416" in contacts and "112" in contacts


# ---------------- assessments ----------------
def test_phq9_scoring_and_bands():
    r = assessments.score("phq9", [1, 1, 1, 1, 1, 1, 1, 1, 0])
    assert r["score"] == 8 and r["severity"] == "mild" and r["risk_level"] == "none"
    r = assessments.score("phq9", [3] * 8 + [0])
    assert r["score"] == 24 and r["severity"] == "severe"


def test_phq9_item9_always_escalates():
    r = assessments.score("phq9", [0] * 8 + [1])
    assert r["severity"] == "minimal" and r["risk_level"] == "moderate"
    assert assessments.score("phq9", [0] * 8 + [3])["risk_level"] == "high"


def test_gad7_bands():
    assert assessments.score("gad7", [2] * 7)["severity"] == "moderate"
    assert assessments.score("gad7", [3] * 7)["severity"] == "severe"


def test_cssrs_triage():
    assert assessments.score("cssrs", [0] * 6)["risk_level"] == "none"
    assert assessments.score("cssrs", [1, 0, 0, 0, 0, 0])["risk_level"] == "low"
    assert assessments.score("cssrs", [1, 1, 1, 0, 0, 0])["risk_level"] == "moderate"
    assert assessments.score("cssrs", [1, 1, 1, 1, 0, 0])["risk_level"] == "high"


def test_assessment_validation():
    with pytest.raises(assessments.AssessmentError):
        assessments.score("phq9", [1, 2])
    with pytest.raises(assessments.AssessmentError):
        assessments.score("gad7", [4] * 7)
    with pytest.raises(assessments.AssessmentError):
        assessments.score("unknown", [])


# ---------------- retrieval ----------------
def test_bm25_retrieves_relevant_source():
    knowledge.load()
    assert knowledge.stats()["sources"] >= 10
    assert knowledge.search("what is CBT therapy")[0]["source"] in ("therapy_methods", "cognitive_distortions")
    assert knowledge.search("I can't sleep at night insomnia")[0]["source"] == "sleep_hygiene"
    assert knowledge.search("panic attack breathing")[0]["source"] == "grounding_and_breathing"
    assert knowledge.search("zzzz qqqq") == []


# ---------------- storage ----------------
@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    storage.init_db()


def test_storage_roundtrip_and_delete(tmp_db):
    storage.add_message("u1", "user", "hello")
    storage.add_message("u1", "assistant", "hi")
    assert storage.get_history("u1", 10) == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    storage.add_risk_event("u1", "high", "lexicon", "test")
    storage.save_profile("u1", {"goals": ["sleep better"]})
    storage.add_assessment("u1", "phq9", [0] * 9, 0, "minimal")
    assert storage.list_sessions()[0]["open_flags"] == 1
    assert storage.delete_session("u1") >= 5
    assert not storage.session_exists("u1")


def test_assessment_trends_reliable_change():
    import clinician
    rows = [
        {"instrument": "phq9", "score": 18, "severity": "moderately severe", "created_at": "2026-09-01T00:00:00+00:00"},
        {"instrument": "phq9", "score": 9, "severity": "mild", "created_at": "2026-10-01T00:00:00+00:00"},
        {"instrument": "gad7", "score": 10, "severity": "moderate", "created_at": "2026-09-01T00:00:00+00:00"},
        {"instrument": "gad7", "score": 12, "severity": "moderate", "created_at": "2026-10-01T00:00:00+00:00"},
    ]
    t = clinician.assessment_trends(rows)
    assert t["phq9"]["status"] == "improved" and t["phq9"]["change"] == -9
    assert t["gad7"]["status"] == "no reliable change"


def test_trajectory_detects_deterioration():
    import clinician
    calm = [{"emotion_intensity": 3, "risk_level": "none"}] * 3
    worse = [{"emotion_intensity": 8, "risk_level": "none"}, {"emotion_intensity": 9, "risk_level": "moderate"}, {"emotion_intensity": 9, "risk_level": "moderate"}]
    assert clinician.trajectory(calm + worse)["status"] == "deteriorating"
    assert clinician.trajectory(worse + calm)["status"] == "improving"
    assert clinician.trajectory(calm[:2])["status"] == "insufficient data"


def test_screening_policy(tmp_db):
    import chat_engine
    sid = "scr1"
    for _ in range(3):
        storage.add_analysis(sid, None, {"primary_emotion": "sad", "emotion_intensity": 6, "risk_level": "low"})
    a = {"primary_emotion": "hopeless", "risk_level": "low", "suggest": "none"}
    chat_engine._screening_policy(sid, a)
    assert a["suggest"] == "phq9"                      # persistent low mood -> offer PHQ-9
    storage.add_assessment(sid, "phq9", [1] * 9, 9, "mild")
    a = {"primary_emotion": "sad", "risk_level": "low", "suggest": "phq9"}
    chat_engine._screening_policy(sid, a)
    assert a["suggest"] == "none"                      # taken today -> don't nag


def test_pick_fresh_never_repeats_recent_variant():
    recent = [safety.RISK_CHECKINS[0], safety.RISK_CHECKINS[1]]
    for _ in range(20):
        assert safety.pick_fresh(safety.RISK_CHECKINS, recent) == safety.RISK_CHECKINS[2]


def test_helpline_block_shown_once_then_short_reminders(tmp_db):
    import chat_engine
    first = chat_engine._with_resources("reply one", "high", recent_bot=[])
    assert safety.RESOURCE_MARKER in first and "Samaritans" in first          # full list first time
    second = chat_engine._with_resources("reply two", "high", recent_bot=[first])
    assert safety.RESOURCE_MARKER not in second and "14416" in second         # short reminder after
    third = chat_engine._with_resources("reply three", "high", recent_bot=[first, second])
    assert third.split("\n\n")[-1] != second.split("\n\n")[-1]                # and a different one each time


def test_moderate_line_not_repeated(tmp_db):
    import chat_engine
    first = chat_engine._with_resources("ok", "moderate", recent_bot=[])
    assert "14416" in first
    assert chat_engine._with_resources("ok again", "moderate", recent_bot=[first]) == "ok again"


def test_anti_repetition_instructions():
    from therapy import anti_repetition
    replies = ["I hear how heavy this feels. Try this: inhale for 4 counts, hold 2, exhale 6.",
               "I hear you. Breathe in slowly and let's do 5-4-3-2-1 together."]
    text = anti_repetition(replies, ["grounding", "grounding"], "grounding")
    assert '"I hear how heavy this feels...."' in text
    assert "paced/box breathing" in text and "5-4-3-2-1 grounding" in text
    assert "used 'grounding' in several recent replies" in text
    assert anti_repetition([], [], "grounding") == ""


def test_language_detection():
    from therapy import detect_language
    assert detect_language("yaar exams aa rahe hain aur bahut tension ho rahi hai") == "hinglish"
    assert detect_language("yaar ab jeene ka mann nahi karta, sab bekaar lagta hai") == "hinglish"
    assert detect_language("मुझे बहुत दुख है") == "hindi"
    assert detect_language("I have exams next week and I feel stressed") == "english"


def test_technique_progresses_when_stalled(tmp_db):
    import chat_engine
    a = {"recommended_technique": "validation", "primary_emotion": "sadness", "risk_level": "none"}
    chat_engine._progress_technique(a, ["validation", "validation"])
    assert a["recommended_technique"] == "reflective_listening"
    a = {"recommended_technique": "validation", "primary_emotion": "sadness", "risk_level": "none"}
    chat_engine._progress_technique(a, ["reflective_listening", "validation", "validation"])
    assert a["recommended_technique"] == "behavioral_activation"
    crisis = {"recommended_technique": "crisis_support", "primary_emotion": "despair", "risk_level": "high"}
    chat_engine._progress_technique(crisis, ["crisis_support", "crisis_support"])
    assert crisis["recommended_technique"] == "crisis_support"          # never overrides crisis care


def test_strip_model_helplines(tmp_db):
    import chat_engine
    reply = "Are you safe right now?\n\nIf you're in India, you can call:\n- 14416 (Tele-MANAS)\n- 112 emergency 112"
    out = chat_engine._strip_model_helplines(reply)
    assert "14416" not in out and out.endswith(".") and out.startswith("Are you safe")


def test_repeats_previous_detection():
    from therapy import repeats_previous
    prev = "I'm really sorry you're feeling like this. Are you thinking about harming yourself right now?"
    assert repeats_previous("I’m really sorry you're feeling this way. Can we talk?", prev)          # same opening
    assert repeats_previous("That sounds unbearable. Are you thinking about harming yourself right now?", prev)  # same question
    assert not repeats_previous("Thank you for telling me. What happened today that made it worse?", prev)
    assert not repeats_previous("Anything", None)


def test_repeated_sentences():
    from therapy import repeated_sentences
    prev = "If a friend or family member is nearby, reaching out to them could help you feel less alone. I'm staying with you; keep talking to me."
    draft = "That sounds so lonely. If a friend or family member is nearby, reaching out could help you feel less alone. I'm staying with you, keep talking to me."
    assert len(repeated_sentences(draft, prev)) == 2
    assert repeated_sentences("Something completely different to say here today.", prev) == []


def test_llm_falls_back_when_rate_limited(monkeypatch):
    import llm
    calls = []

    def fake_once(messages, model, *a):
        calls.append(model)
        if model == "openai/gpt-oss-120b":
            raise llm._RateLimited("rate limited (daily quota)", per_day=True)
        return "ok from " + model

    monkeypatch.setattr(llm, "_chat_once", fake_once)
    monkeypatch.setattr(llm, "_cooldown_until", {})
    assert llm.chat([], model="openai/gpt-oss-120b") == "ok from openai/gpt-oss-20b"
    calls.clear()
    assert llm.chat([], model="openai/gpt-oss-120b") == "ok from openai/gpt-oss-20b"
    assert calls == ["openai/gpt-oss-20b"]          # exhausted model is skipped while cooling down
