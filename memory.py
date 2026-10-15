"""Conversation memory beyond the responder's recent-message window.

The responder sees the last HISTORY_TURNS*2 messages verbatim. Older messages are
folded into a rolling summary (updated incrementally every few messages, in a
background thread so the user never waits for it) and injected into the prompt.
Together with the long-term profile (facts, goals, triggers, what helped), this gives
MindBot continuity across long and repeated conversations.
"""
import threading
from typing import Optional

import config
import llm
import storage

UPDATE_EVERY = 6  # messages that must fall out of the window before re-summarising

SUMMARY_PROMPT = """You maintain a running summary of a supportive conversation between a user and MindBot, an AI mental-health companion.
Update the summary with the new messages. Keep: what the user is going through, key events and people, feelings and how they changed,
what was tried and whether it helped, any risk concerns, and open threads to follow up. Refer to the person as "the user" or they/them; never assume gender. Factual, under 150 words. Plain text."""

_locks: dict = {}


def get_summary_text(session_id: str) -> Optional[str]:
    s = storage.get_summary(session_id)
    return s["summary"] if s else None


def _summarize(session_id: str) -> None:
    lock = _locks.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        window = config.HISTORY_TURNS * 2
        older = storage.count_messages(session_id) - window
        existing = storage.get_summary(session_id)
        covered = existing["covered_messages"] if existing else 0
        if older - covered < UPDATE_EVERY:
            return
        new_msgs = storage.get_messages_range(session_id, covered, older - covered)
        convo = "\n".join(f"{m['role'].upper()}: {m['content'][:600]}" for m in new_msgs)
        prev = existing["summary"] if existing else "(none yet)"
        summary = llm.chat(
            [{"role": "system", "content": SUMMARY_PROMPT},
             {"role": "user", "content": f"CURRENT SUMMARY:\n{prev}\n\nNEW MESSAGES:\n{convo}"}],
            model=config.SUMMARY_MODEL, temperature=0.2, max_tokens=500,
        )
        storage.save_summary(session_id, summary, older)
    except llm.LLMUnavailable:
        pass  # try again after the next message
    finally:
        lock.release()


def maybe_update_summary(session_id: str, background: bool = True) -> None:
    if background:
        threading.Thread(target=_summarize, args=(session_id,), daemon=True).start()
    else:
        _summarize(session_id)
