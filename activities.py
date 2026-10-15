"""Mood-lifting activities MindBot can host inside the chat: games, stories, and
"getting to know you" conversations.

Why: distraction and positive engagement are legitimate coping skills (DBT "ACCEPTS":
Activities, Contributing, Comparisons, Emotions, Pushing away, Thoughts, Sensations),
behavioural activation shows pleasant activity lifts mood, and rapport (the therapeutic
alliance) is one of the strongest predictors of benefit in any talking therapy.

Each activity is a set of RULES for the model, which hosts it in its own words and
personalises it with what it knows (name, interests). Activities are never offered or
continued when risk is moderate or higher: safety checks run on every message, and a
crisis signal ends the game immediately.
"""
import re
from typing import Any, Dict, List, Optional

ACTIVITIES: Dict[str, Dict[str, Any]] = {
    "riddles": {
        "name": "Riddles", "kind": "game", "max_turns": 10,
        "rules": "Ask one riddle at a time (light, solvable, not morbid). Give a hint if they're stuck; celebrate warmly when they get it; "
                 "let them ask you one too. Keep score playfully if they like.",
    },
    "would_you_rather": {
        "name": "Would you rather", "kind": "game", "max_turns": 10,
        "rules": "Offer fun, light 'would you rather' choices (no dark or risky themes), ideally linked to their interests. "
                 "React to their choice with curiosity and share your own playful pick; ask why sometimes.",
    },
    "twenty_questions": {
        "name": "20 questions", "kind": "game", "max_turns": 22,
        "rules": "Think of an everyday object/animal/place; they ask yes/no questions; answer honestly and count questions. "
                 "Offer to switch roles after.",
    },
    "word_chain": {
        "name": "Word chain", "kind": "game", "max_turns": 15,
        "rules": "Take turns saying a word that starts with the last letter of the previous word, within a fun category they pick "
                 "(movies, foods, places). Be encouraging; keep it quick and light.",
    },
    "story_together": {
        "name": "Build a story together", "kind": "story", "max_turns": 14,
        "rules": "Co-write a light, hopeful story: you write 2-3 sentences, then ask them what happens next. Use a setting or "
                 "character linked to their interests. Keep it uplifting; steer away from dark turns gently.",
    },
    "tell_a_story": {
        "name": "A short uplifting story", "kind": "story", "max_turns": 4,
        "rules": "Tell a short (under 200 words), warm, original story with a gentle hopeful message, tailored to their interests "
                 "or situation without preaching. Then ask what part stayed with them.",
    },
    "gratitude_alphabet": {
        "name": "Gratitude alphabet", "kind": "game", "max_turns": 14,
        "rules": "Take turns naming something you're grateful for or enjoy, going through the alphabet (A, B, C...). "
                 "Share your own playful ones; react warmly to theirs.",
    },
    "three_good_things": {
        "name": "Three good moments", "kind": "conversation", "max_turns": 6,
        "rules": "Invite them to recall three small good moments from today or this week; explore each briefly (what made it good?).",
    },
    "get_to_know_you": {
        "name": "Getting to know you", "kind": "conversation", "max_turns": 8,
        "rules": "Have a relaxed, curious conversation about their life: what they enjoy, a favourite memory, people who matter, "
                 "dreams, comfort food, favourite music or places. One question at a time, share small light reactions, and remember answers.",
    },
    "favourite_things": {
        "name": "Favourite things trivia", "kind": "game", "max_turns": 10,
        "rules": "Run a light trivia round on a topic they love (a sport, a show, music, science...). One question at a time, "
                 "multiple choice, cheerful feedback.",
    },
}

# Curated deck: small models invent riddles with wrong or nonsensical answers, so the puzzles are data
# (classic, unambiguous, non-morbid) and the model only hosts them in its own words.
RIDDLES = [
    ("What has keys but can't open locks?", "a piano"),
    ("What gets wetter the more it dries?", "a towel"),
    ("What has hands but can't clap?", "a clock"),
    ("What can you catch but not throw?", "a cold"),
    ("What has a neck but no head?", "a bottle"),
    ("What goes up but never comes down?", "your age"),
    ("What has many teeth but can't bite?", "a comb"),
    ("What can travel around the world while staying in a corner?", "a stamp"),
    ("I'm tall when I'm young and short when I'm old. What am I?", "a candle"),
    ("What has an eye but cannot see?", "a needle"),
    ("What belongs to you, but other people use it more than you do?", "your name"),
    ("What has words but never speaks?", "a book"),
    ("What runs but never walks, has a mouth but never talks?", "a river"),
    ("The more of these you take, the more you leave behind. What are they?", "footsteps"),
    ("What can fill a room but takes up no space?", "light"),
    ("What has one eye but can't see, and is used to make clothes?", "a needle"),
    ("What has legs but doesn't walk?", "a table"),
    ("What building has the most stories?", "a library"),
    ("What has a thumb and four fingers but isn't alive?", "a glove"),
    ("What is full of holes but still holds water?", "a sponge"),
    ("What comes once in a minute, twice in a moment, but never in a thousand years?", "the letter M"),
    ("What can you hear but not touch or see?", "your voice (or an echo)"),
    ("What has a bottom at the top?", "your legs"),
    ("What kind of band never plays music?", "a rubber band"),
    ("What has a head and a tail but no body?", "a coin"),
    ("What starts with T, ends with T, and has T in it?", "a teapot"),
    ("What room has no doors or windows?", "a mushroom"),
    ("In cricket, what can you hold without ever touching it?", "your breath (it's a trick: it works anywhere!)"),
    ("What is always in front of you but can't be seen?", "the future"),
    ("What has cities, but no houses; forests, but no trees; and water, but no fish?", "a map"),
]


def riddle_for(session_id: str, index: int):
    """Per-session shuffled order so each person gets a different sequence."""
    import random as _r
    order = list(range(len(RIDDLES)))
    _r.Random(session_id).shuffle(order)
    return RIDDLES[order[index % len(order)]]


EXIT_WORDS ={"stop", "quit", "enough", "end game", "stop playing", "let's stop", "lets stop", "no more", "bas", "band karo"}


def menu(limit: int = 4, exclude: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Options for the frontend to render as buttons."""
    ids = [a for a in ACTIVITIES if a not in (exclude or [])]
    order = ["would_you_rather", "riddles", "tell_a_story", "story_together", "gratitude_alphabet", "get_to_know_you",
             "twenty_questions", "word_chain", "favourite_things", "three_good_things"]
    ids = sorted(ids, key=lambda a: order.index(a) if a in order else 99)
    return [{"id": a, "name": ACTIVITIES[a]["name"], "kind": ACTIVITIES[a]["kind"]} for a in ids[:limit]]


_EXIT = re.compile(
    r"\b(stop|end|quit|exit|finish|pause)\b(\s+(the|this|our))?\s+(game|games|playing|story|activity|riddles?|now)\b"
    r"|\b(let'?s|can we|i want to|i wanna) (stop|quit|end)\b|\b(game|khel) (band|khatam)\b|^\s*(stop|enough|bas|no more)\W*$",
    re.IGNORECASE,
)


def wants_exit(text: str) -> bool:
    return bool(_EXIT.search(text.strip()))


def prompt_block(activity_id: str, turn: int, profile: Dict[str, List[str]], session_id: str = "") -> str:
    a = ACTIVITIES[activity_id]
    deck = ""
    if activity_id == "riddles":
        upcoming = [riddle_for(session_id, i) for i in range(turn + 1)]
        listing = "\n".join(f"  {i + 1}. {q} [answer: {ans}]" for i, (q, ans) in enumerate(upcoming))
        deck = ("\nRIDDLE DECK, use in this order (answers are for you only; never invent your own riddles):\n" + listing +
                "\nCheck the conversation: if they're still working on a riddle, judge their guess against its answer "
                "(accept close answers), give a hint or reveal it kindly. Otherwise ask the next riddle from the deck that "
                "hasn't been asked yet.")
    elif activity_id == "favourite_things":
        deck = "\nOnly ask trivia you are completely sure is correct; well-known facts only."
    interests = "; ".join((profile or {}).get("interests", [])[-5:]) or "unknown (you can ask)"
    lines = [
        f"ACTIVITY IN PROGRESS: {a['name']} (turn {turn} of about {a['max_turns']}).",
        f"Rules: {a['rules']}{deck}",
        f"Their interests: {interests}.",
        "On the first turn, jump straight in with your first move (e.g. ask the first riddle or give the first choice); "
        "don't ask whether they're ready. Stay playful and warm; this is a break to lift their mood. Keep messages short. "
        "If they seem to want to talk about something serious, gently pause the activity and listen.",
    ]
    if turn >= a["max_turns"]:
        lines.append("This activity has run its course: wrap it up warmly in this message and ask how they're feeling now compared to before.")
    return "\n".join(lines)
