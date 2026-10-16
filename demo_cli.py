"""Live terminal demo of MindBot's ML pipeline, for presentations.

After every reply it prints the "clinical read" that drove it: emotion, risk,
thinking traps, conversational stance, chosen technique, critic verdict, retrieved
sources and the next suggested action.

Run from the Mindbot folder:   python demo_cli.py
Commands:  /phq9  /gad7  /cssrs   take a screening questionnaire
           /insights              clinician dashboard data for this session
           /summary               AI-drafted clinician note
           /memory                what MindBot remembers about you
           /new                   start a fresh session
           /quit
"""
import json
import os
import sys
import time

os.environ.setdefault("MINDBOT_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.db"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if os.name == "nt":
    os.system("")  # enable ANSI colours in the Windows console

import assessments  # noqa: E402
import chat_engine  # noqa: E402
import clinician  # noqa: E402
import safety  # noqa: E402
import storage  # noqa: E402

C = {"dim": "\033[2m", "b": "\033[1m", "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m", "x": "\033[0m"}
RISK_COLOR = {"none": "green", "low": "green", "moderate": "yellow", "high": "red", "imminent": "red"}


def c(text, color):
    return f"{C[color]}{text}{C['x']}"


def _action_text(act):
    t = act.get("type", "none")
    if act.get("resources"):
        names = ", ".join(x["name"] + (" [open]" if x.get("open_now") else "") for x in act["resources"])
        return f"{t}: {names}"
    if act.get("options"):
        return f"{t}: " + ", ".join(o["name"] for o in act["options"])
    if t == "activity_in_progress":
        return f"playing {act.get('activity')} (turn {act.get('turn')})"
    if t == "assessment":
        return f"offer {act.get('instrument', '').upper()} check-in"
    return t


def panel(r, secs):
    a = r.get("analysis") or {}
    risk = r.get("risk_level", "none")
    rows = [
        ("emotion", f"{a.get('primary_emotion')} ({a.get('emotion_intensity')}/10)"),
        ("risk", c(risk.upper(), RISK_COLOR.get(risk, "green")) + (c("  [harm to others: " + r["harm_to_others_level"] + "]", "red") if r.get("harm_to_others_level", "none") != "none" else "")),
        ("thinking traps", ", ".join(a.get("cognitive_distortions") or []) or "none"),
        ("stance", a.get("user_stance")),
        ("technique", a.get("recommended_technique")),
        ("review", (r.get("review") or {}).get("verdict")),
        ("sources", ", ".join(r.get("sources") or []) or "none"),
        ("next action", _action_text(r.get("suggested_action") or {})),
        ("safety checks", (("fallback used" if r["review"].get("verdict") == "fallback" else "passed")
                           + f" after {r['review']['attempts']} draft(s)") if (r.get("review") or {}).get("attempts") else "n/a"),
        ("latency", f"{secs:.1f}s"),
    ]
    print(c("  +-- clinical read " + "-" * 40, "dim"))
    for k, v in rows:
        print(c(f"  | {k:<15}", "dim") + f"{v}")
    print(c("  +" + "-" * 58, "dim"))


def run_assessment(sid, name):
    inst = assessments.get_instrument(name)
    print(c(f"\n{inst['title']}: {inst['prompt']}", "b"))
    opts = " / ".join(f"{o['value']}={o['label']}" for o in inst["options"])
    answers = []
    for item in inst["items"]:
        while True:
            raw = input(f"  {item['index'] + 1}. {item['text']}\n     ({opts}): ").strip()
            if raw.isdigit() and int(raw) in [o["value"] for o in inst["options"]]:
                answers.append(int(raw))
                break
    res = assessments.score(name, answers)
    storage.add_assessment(sid, name, answers, res["score"], res["severity"])
    if safety.level_index(res["risk_level"]) >= 2 or (name == "cssrs" and res["risk_level"] != "none"):
        storage.add_risk_event(sid, res["risk_level"], f"assessment:{name}", f"score {res['score']}")
    print(c(f"\n  Score {res['score']}  severity: {res['severity']}  risk: {res['risk_level']}", "cyan"))
    print(f"  {res['interpretation']}\n")


def main():
    sid = f"demo-{int(time.time())}"
    print(c("\nMindBot v4 live demo", "b") + c("  (type /quit to exit, /insights, /summary, /memory, /phq9, /gad7, /cssrs, /new)", "dim"))
    print(c("MindBot: ", "cyan") + chat_engine.start_session(sid) + "\n")
    while True:
        try:
            text = input(c("You: ", "b")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        cmd = text.lower()
        if cmd == "/quit":
            break
        if cmd == "/new":
            sid = f"demo-{int(time.time())}"
            print(c("MindBot: ", "cyan") + chat_engine.start_session(sid) + "\n")
            continue
        if cmd in ("/phq9", "/gad7", "/cssrs"):
            run_assessment(sid, cmd[1:])
            continue
        if cmd == "/insights":
            ins = clinician.insights(sid)
            fmt = lambda pairs: ", ".join(f"{k} x{n}" for k, n in pairs) or "none"  # noqa: E731
            print(c("\n  CLINICIAN INSIGHTS", "b"))
            print(f"  trajectory       {ins['trajectory'].get('status')}")
            for inst, t in ins["assessment_trends"].items():
                print(f"  {inst:<16} {t['first']['score']} -> {t['latest']['score']} ({t['status']})")
            print(f"  emotions         {fmt(ins['top_emotions'])}")
            print(f"  thinking traps   {fmt(ins['thinking_patterns'])}")
            print(f"  stances          {fmt(ins['stances'])}")
            print(f"  techniques       {fmt(ins['techniques_used'])}")
            print(f"  critic verdicts  {', '.join(f'{k} x{v}' for k, v in ins['critic_verdicts'].items()) or 'none'}")
            print(f"  memory           {json.dumps(ins['memory'], ensure_ascii=False)}")
            print(c(f"  risk flags       {[(f['level'], f['source']) for f in ins['risk_events']] or 'none'}\n", "yellow"))
            continue
        if cmd == "/summary":
            print("\n" + clinician.session_summary(sid)["summary"] + "\n")
            continue
        if cmd == "/memory":
            print(json.dumps(storage.get_profile(sid), indent=2, ensure_ascii=False) + "\n")
            continue
        t = time.time()
        r = chat_engine.process_message(sid, text)
        print(c("\nMindBot: ", "cyan") + r["response"])
        panel(r, time.time() - t)
        print()


if __name__ == "__main__":
    main()
