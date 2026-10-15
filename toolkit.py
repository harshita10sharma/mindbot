"""A library of evidence-based self-help interventions.

Each entry is GUIDANCE for the model, never text shown verbatim: the responder explains the
idea in its own words and tailors it to the person's life (interests, people, situation).
The selector offers 2-3 relevant options the person has NOT been given in the last 14 days
(tracked in the database across sessions), so a week of daily chats keeps feeling fresh.

Approaches: CBT (Beck), Behavioural Activation (Martell), DBT skills (Linehan), ACT (Hayes),
Mindfulness (Kabat-Zinn), Compassion-Focused / Self-Compassion (Gilbert, Neff),
Positive Psychology (Seligman), Problem-Solving Therapy (Nezu), CBT-I, Social connection.
"""
import random
from typing import Any, Dict, List

TOOLS: List[Dict[str, Any]] = [
    # ---- anxiety / panic / overwhelm
    {"id": "paced_breathing", "name": "Paced breathing", "approach": "physiology", "needs": ["anxiety", "anger", "stress"],
     "how": "Breathe in about 4 counts, out about 6; the longer out-breath calms the body. 1-3 minutes."},
    {"id": "54321", "name": "5-4-3-2-1 grounding", "approach": "mindfulness", "needs": ["anxiety", "stress"],
     "how": "Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste; pulls attention to the present."},
    {"id": "tipp_cold", "name": "Cold-water reset (DBT TIPP)", "approach": "DBT", "needs": ["anxiety", "anger"],
     "how": "Cold water on the face or holding something cold for 30 seconds quickly lowers intense arousal."},
    {"id": "worry_time", "name": "Scheduled worry time", "approach": "CBT", "needs": ["anxiety", "sleep"],
     "how": "Postpone worries to a fixed 15-minute slot later in the day; jot them down when they pop up, then return to the present."},
    {"id": "worry_tree", "name": "Worry tree", "approach": "CBT", "needs": ["anxiety", "stress"],
     "how": "Ask: is this a problem I can act on now? If yes, plan one step. If no, consciously let it go and refocus."},
    {"id": "defusion", "name": "Unhooking from thoughts", "approach": "ACT", "needs": ["anxiety", "self_criticism", "low_mood"],
     "how": "Add 'I'm having the thought that...' before a painful thought, or say it in a silly voice; notice it is a thought, not a fact."},
    {"id": "body_scan", "name": "Two-minute body scan", "approach": "mindfulness", "needs": ["anxiety", "sleep", "stress"],
     "how": "Slowly move attention from feet to head, noticing tension and letting each area soften a little."},
    {"id": "pmr", "name": "Progressive muscle relaxation", "approach": "relaxation", "needs": ["anxiety", "sleep", "stress"],
     "how": "Tense a muscle group for 5 seconds, then release for 10, moving through the body; notice the contrast."},
    {"id": "safe_place", "name": "Calm place imagery", "approach": "relaxation", "needs": ["anxiety", "sleep"],
     "how": "Picture a place where you feel safe, using all senses: sounds, light, temperature, smells."},
    # ---- low mood / depression
    {"id": "tiny_activity", "name": "One tiny activity", "approach": "Behavioural Activation", "needs": ["low_mood"],
     "how": "Pick one 5-10 minute activity linked to pleasure or achievement (tie it to their interests); do it before waiting to feel like it."},
    {"id": "activity_mood_log", "name": "Activity and mood log", "approach": "Behavioural Activation", "needs": ["low_mood"],
     "how": "For a day, note activities and rate mood 0-10; patterns show what lifts or drains mood."},
    {"id": "values_step", "name": "One values-based step", "approach": "ACT", "needs": ["low_mood", "general"],
     "how": "Ask what matters most to them (family, learning, kindness...) and choose one small action today that reflects it."},
    {"id": "opposite_action", "name": "Opposite action", "approach": "DBT", "needs": ["low_mood", "anger", "loneliness"],
     "how": "When an emotion urges something unhelpful (withdraw, lash out), gently do the opposite (reach out, step back kindly)."},
    {"id": "sunlight_move", "name": "Daylight and movement", "approach": "lifestyle", "needs": ["low_mood", "sleep"],
     "how": "10 minutes outside in daylight, walking if possible; light and movement both lift mood and help sleep rhythm."},
    {"id": "music_mood", "name": "Mood-shifting music", "approach": "Behavioural Activation", "needs": ["low_mood", "stress"],
     "how": "Start with a song matching the mood, then gradually move to more uplifting songs (link to music they like)."},
    {"id": "small_win", "name": "Small-win list", "approach": "positive psychology", "needs": ["low_mood", "self_criticism"],
     "how": "Write three small things done today, however tiny (got up, drank water, replied to a message)."},
    # ---- self-criticism / shame
    {"id": "friend_voice", "name": "What would you tell a friend?", "approach": "CBT / self-compassion", "needs": ["self_criticism", "low_mood"],
     "how": "Imagine a close friend said this about themselves; what would you say to them? Offer yourself the same words."},
    {"id": "self_compassion_break", "name": "Self-compassion break", "approach": "self-compassion (Neff)", "needs": ["self_criticism", "grief", "low_mood"],
     "how": "Three steps: 'This is hard' (mindfulness), 'others feel this too' (common humanity), 'may I be kind to myself' (kindness)."},
    {"id": "thought_record", "name": "Thought record", "approach": "CBT", "needs": ["self_criticism", "anxiety", "low_mood"],
     "how": "Write the situation, the automatic thought, evidence for and against, and a more balanced thought; re-rate the feeling."},
    {"id": "evidence_check", "name": "Evidence check", "approach": "CBT", "needs": ["self_criticism", "anxiety"],
     "how": "Treat the thought like a hypothesis: what facts support it, what facts don't, what's a fairer conclusion?"},
    {"id": "compassionate_letter", "name": "Compassionate letter", "approach": "compassion-focused", "needs": ["self_criticism", "grief"],
     "how": "Write a short letter to yourself from the perspective of someone who deeply cares about you."},
    # ---- anger / conflict
    {"id": "time_out", "name": "Structured time-out", "approach": "anger management", "needs": ["anger"],
     "how": "Agree to step away for 20-30 minutes when anger is high, calm the body, then return to talk."},
    {"id": "i_statements", "name": "I-statements", "approach": "communication", "needs": ["anger", "relationships"],
     "how": "'I felt ___ when ___ because ___; what I need is ___' instead of 'you always...'."},
    {"id": "dear_man", "name": "DEAR MAN conversation plan", "approach": "DBT", "needs": ["relationships", "anger", "stress"],
     "how": "Describe facts, Express feelings, Assert the request, Reinforce why it helps both; stay Mindful, Appear confident, Negotiate."},
    {"id": "anger_iceberg", "name": "What's under the anger?", "approach": "emotion-focused", "needs": ["anger"],
     "how": "Anger is often the tip; underneath may be hurt, fear, embarrassment or feeling unimportant. Name the feeling below."},
    {"id": "other_view", "name": "Their side of the story", "approach": "perspective taking", "needs": ["anger", "relationships"],
     "how": "Briefly tell the situation as the other person might tell it; it doesn't mean they are right, just more complete."},
    # ---- stress / problems
    {"id": "problem_solving", "name": "Five-step problem solving", "approach": "Problem-Solving Therapy", "needs": ["stress", "general"],
     "how": "Define the problem, brainstorm options without judging, weigh pros and cons, pick one, try it and review."},
    {"id": "brain_dump", "name": "Brain dump and sort", "approach": "CBT", "needs": ["stress", "anxiety", "sleep"],
     "how": "Write everything on your mind, then sort into: do today, schedule, delegate, let go."},
    {"id": "pomodoro", "name": "25-5 focus blocks", "approach": "behavioural", "needs": ["stress", "study"],
     "how": "Work 25 minutes on one thing, then a 5-minute real break; repeat. Starting is the hardest part."},
    {"id": "control_circle", "name": "Circle of control", "approach": "CBT / ACT", "needs": ["stress", "anxiety"],
     "how": "Split worries into what you can control, can influence, and can't control; put energy into the first circle."},
    # ---- sleep
    {"id": "wind_down", "name": "Wind-down routine", "approach": "CBT-I", "needs": ["sleep"],
     "how": "Same 30-minute routine before bed: dim lights, no screens, something calm; the brain learns the cue."},
    {"id": "get_up_rule", "name": "The 20-minute rule", "approach": "CBT-I (stimulus control)", "needs": ["sleep"],
     "how": "If awake for about 20 minutes, get up and do something calm in dim light; return to bed when sleepy."},
    {"id": "fixed_wake", "name": "Fixed wake-up time", "approach": "CBT-I", "needs": ["sleep"],
     "how": "Wake at the same time every day, even after a bad night; it resets the body clock faster than sleeping in."},
    # ---- loneliness / connection
    {"id": "micro_connection", "name": "One micro-connection", "approach": "social connection", "needs": ["loneliness", "low_mood"],
     "how": "Send one low-pressure message today (a meme, a 'thinking of you') to someone; connection grows from small moments."},
    {"id": "shared_interest_group", "name": "Interest-based group", "approach": "social connection", "needs": ["loneliness"],
     "how": "Find one recurring group around an interest (club, class, online community); repeated contact builds friendship."},
    {"id": "kindness_act", "name": "Small act of kindness", "approach": "positive psychology", "needs": ["loneliness", "low_mood"],
     "how": "Do one small kind thing for someone; helping others reliably lifts our own mood."},
    # ---- grief
    {"id": "grief_space", "name": "Making space for grief", "approach": "grief support", "needs": ["grief"],
     "how": "Grief comes in waves; set aside a little time to remember (photos, writing to the person) instead of fighting it all day."},
    # ---- general wellbeing / positive
    {"id": "three_good_things", "name": "Three good things", "approach": "positive psychology (Seligman)", "needs": ["low_mood", "general"],
     "how": "Each night write three things that went well and why; shown to improve mood over weeks."},
    {"id": "savoring", "name": "Savouring a moment", "approach": "positive psychology", "needs": ["general", "low_mood"],
     "how": "Fully notice one pleasant moment today (tea, a song, sunlight) for 30 seconds longer than usual."},
    {"id": "best_self", "name": "Best possible self", "approach": "positive psychology", "needs": ["low_mood", "general"],
     "how": "Imagine life a few years from now where things went well; write about it for a few minutes to build hope and direction."},
    {"id": "nature_break", "name": "Nature break", "approach": "lifestyle", "needs": ["stress", "low_mood", "anxiety"],
     "how": "Spend a few minutes with something green: a park, plants, the sky; noticing nature lowers stress."},
]

TOOL_BY_ID = {t["id"]: t for t in TOOLS}
NEEDS = ["anxiety", "low_mood", "self_criticism", "anger", "relationships", "stress", "study", "sleep", "loneliness", "grief", "general"]


_STOP = set("about after again their there these those which while would could should other where being every "
             "something someone yourself things thing feels small minutes today".split())


def _keywords(text: str) -> set:
    import re
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in _STOP}


def infer_used(reply: str, offered: List[Dict[str, Any]]) -> str:
    """Best-matching offered tool by shared keywords (name weighted double); '' if none is clearly used."""
    words = _keywords(reply)
    best, best_score = "", 0
    for t in offered:
        score = 2 * len(words & _keywords(t["name"])) + len(words & _keywords(t["how"]))
        if score > best_score:
            best, best_score = t["id"], score
    return best if best_score >= 2 else ""


def options_for(need: str, recently_used: List[str], k: int = 3) -> List[Dict[str, Any]]:
    """2-3 relevant tools the person hasn't been given recently; widen to 'general' if exhausted."""
    fresh = [t for t in TOOLS if need in t["needs"] and t["id"] not in recently_used]
    if len(fresh) < k:
        fresh += [t for t in TOOLS if "general" in t["needs"] and t["id"] not in recently_used and t not in fresh]
    random.shuffle(fresh)
    return fresh[:k]
