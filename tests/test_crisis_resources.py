"""Offline tests for the verified helpline directory and the crisis-reply validator."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activities  # noqa: E402
import crisis  # noqa: E402
import resources  # noqa: E402
import toolkit  # noqa: E402

TUESDAY_3PM = datetime(2026, 10, 6, 15, 0, tzinfo=resources.IST)
SUNDAY_3AM = datetime(2026, 10, 4, 3, 0, tzinfo=resources.IST)


def by_id(i):
    return next(r for r in resources.DIRECTORY if r["id"] == i)


def test_opening_hours():
    assert resources.is_open(by_id("tele_manas"), SUNDAY_3AM) is True          # 24x7
    assert resources.is_open(by_id("icall"), TUESDAY_3PM) is True              # Mon-Sat 8-21
    assert resources.is_open(by_id("icall"), SUNDAY_3AM) is False
    assert resources.is_open(by_id("one_life"), TUESDAY_3PM) is None           # hours unverified


def test_select_only_open_services():
    night = resources.select("talk", k=4, now=SUNDAY_3AM)
    assert all(resources.is_open(r, SUNDAY_3AM) is not False for r in night)
    assert "icall" not in [r["id"] for r in night]                             # closed at 3am Sunday
    day = resources.select("talk", k=3, now=TUESDAY_3PM)
    assert any(r["type"] == "counselling" for r in day)                        # counsellors preferred when open


def test_imminent_always_includes_112():
    assert resources.select("imminent", k=3)[0]["phone"] == "112"


def test_verified_numbers_include_formats():
    v = resources.verified_numbers()
    for n in ("14416", "18008914416", "9999666555", "919999666555", "112", "9152987821"):
        assert n in v


CHOSEN = [by_id("tele_manas"), by_id("vandrevala")]


def test_validator_accepts_good_crisis_reply():
    reply = ("That sounds unbearably heavy, Riya, and I'm really glad you told me. Are you thinking about ending your life right now? "
             "If you'd like to talk to someone tonight, Tele-MANAS on 14416 is free and open all night. I'm here with you.")
    assert crisis.validate(reply, "high", CHOSEN) == []


def test_validator_rejects_hallucinated_number():
    reply = "Please call the helpline at 98765 43210. Are you safe?"
    problems = crisis.validate(reply, "high", CHOSEN)
    assert any("not in the verified list" in p for p in problems)


def test_validator_requires_question_and_number():
    problems = crisis.validate("I'm so sorry you feel this way. You matter.", "high", CHOSEN)
    assert any("does not ask" in p for p in problems) and any("does not include" in p for p in problems)


def test_validator_imminent_needs_112():
    reply = "Please call Tele-MANAS on 14416 right now. Are you safe?"
    assert any("112" in p for p in crisis.validate(reply, "imminent", [by_id("emergency_112")] + CHOSEN))


def test_validator_blocks_means_content():
    reply = "Taking 20 pills is dangerous. Call 14416. Are you safe?"
    assert any("means" in p for p in crisis.validate(reply, "high", CHOSEN))


def test_toolkit_variety_excludes_recent():
    used = [t["id"] for t in toolkit.TOOLS if "low_mood" in t["needs"]][:5]
    for _ in range(10):
        assert not set(t["id"] for t in toolkit.options_for("low_mood", used)) & set(used)
    assert len(toolkit.TOOLS) >= 40


def test_activity_exit_and_menu():
    assert activities.wants_exit("stop") and activities.wants_exit("can we stop now")
    assert not activities.wants_exit("I can't stop thinking about it")
    assert len(activities.menu(3)) == 3


def test_number_not_required_if_recently_shown():
    reply = "Nobody noticing sounds so lonely, and you matter more than that feeling says. Are you safe right now?"
    assert crisis.validate(reply, "high", CHOSEN) != []
    assert crisis.validate(reply, "high", CHOSEN, number_recently_shown=True) == []


def test_validator_rejects_repeat_of_previous():
    prev = "I hear how painful this is. Are you safe right now? Tele-MANAS is on 14416."
    reply = "I hear how painful this is for you. Are you safe right now? Call 14416."
    assert any("repeats" in p for p in crisis.validate(reply, "high", CHOSEN, previous_reply=prev))


def test_activity_exit_variants():
    for t in ["ok stop the game now", "let's stop", "can we end the game", "stop", "bas", "game band karo", "enough!"]:
        assert activities.wants_exit(t), t
    for t in ["I can't stop thinking about it", "it never ends", "my exams end next week"]:
        assert not activities.wants_exit(t), t


def test_real_person_backup_regex():
    import chat_engine
    for t in ["I need to talk to a real counsellor, a human", "can I talk to a therapist", "I want a psychologist",
              "is there a real person I can speak to"]:
        assert chat_engine._REAL_PERSON.search(t), t
    assert not chat_engine._REAL_PERSON.search("my friend is a real person")


def test_infer_used_tool():
    offered = [toolkit.TOOL_BY_ID["sunlight_move"], toolkit.TOOL_BY_ID["kindness_act"], toolkit.TOOL_BY_ID["three_good_things"]]
    reply = "One simple experiment: step outside into the daylight for ten minutes and take a slow walk; movement and light both help."
    assert toolkit.infer_used(reply, offered) == "sunlight_move"
    assert toolkit.infer_used("That sounds really hard. What happened today?", offered) == ""
