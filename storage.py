"""SQLite persistence: conversations, analyses, risk events, assessments, mood,
long-term user memory and safety plans. Stdlib only, thread-safe enough for FastAPI's
threadpool via a short-lived connection per call."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_session ON analyses(session_id, id);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence TEXT,
    reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    answers TEXT NOT NULL,
    score INTEGER NOT NULL,
    severity TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    note TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    session_id TEXT PRIMARY KEY,
    memory TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summaries (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    covered_messages INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interventions_used (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_state (
    session_id TEXT PRIMARY KEY,
    activity TEXT,
    turn INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS safety_plans (
    session_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


# ---------- messages ----------
def add_message(session_id: str, role: str, content: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES (?,?,?,?)",
            (session_id, role, content, _now()),
        )
        return cur.lastrowid


def get_history(session_id: str, limit_messages: int) -> List[Dict[str, str]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit_messages),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_transcript(session_id: str) -> List[Dict[str, str]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def count_messages(session_id: str) -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)).fetchone()[0]


def get_messages_range(session_id: str, offset: int, limit: int) -> List[Dict[str, str]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id LIMIT ? OFFSET ?",
            (session_id, limit, offset),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_summary(session_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT summary, covered_messages FROM summaries WHERE session_id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def save_summary(session_id: str, summary: str, covered_messages: int) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO summaries(session_id, summary, covered_messages, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, "
            "covered_messages=excluded.covered_messages, updated_at=excluded.updated_at",
            (session_id, summary, covered_messages, _now()),
        )


def session_exists(session_id: str) -> bool:
    with _conn() as c:
        return c.execute("SELECT 1 FROM messages WHERE session_id=? LIMIT 1", (session_id,)).fetchone() is not None


def list_sessions() -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """WITH activity AS (
                   SELECT session_id, created_at FROM messages
                   UNION ALL SELECT session_id, created_at FROM assessments
                   UNION ALL SELECT session_id, created_at FROM moods
                   UNION ALL SELECT session_id, created_at FROM risk_events
               )
               SELECT a.session_id,
                      (SELECT COUNT(*) FROM messages m WHERE m.session_id=a.session_id) AS message_count,
                      MIN(a.created_at) AS first_seen,
                      MAX(a.created_at) AS last_seen,
                      (SELECT COUNT(*) FROM risk_events r WHERE r.session_id=a.session_id AND r.reviewed=0) AS open_flags,
                      (SELECT level FROM risk_events r WHERE r.session_id=a.session_id ORDER BY r.id DESC LIMIT 1) AS last_risk
               FROM activity a GROUP BY a.session_id ORDER BY open_flags DESC, last_seen DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- analyses ----------
def add_analysis(session_id: str, message_id: Optional[int], data: Dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO analyses(session_id, message_id, data, created_at) VALUES (?,?,?,?)",
            (session_id, message_id, json.dumps(data), _now()),
        )


def get_analyses(session_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT data, created_at FROM analyses WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
    return [{**json.loads(r["data"]), "created_at": r["created_at"]} for r in rows]


# ---------- risk ----------
def add_risk_event(session_id: str, level: str, source: str, evidence: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO risk_events(session_id, level, source, evidence, created_at) VALUES (?,?,?,?,?)",
            (session_id, level, source, evidence[:500], _now()),
        )


def get_risk_events(session_id: Optional[str] = None, only_open: bool = False) -> List[Dict[str, Any]]:
    q, args = "SELECT * FROM risk_events WHERE 1=1", []
    if session_id:
        q += " AND session_id=?"
        args.append(session_id)
    if only_open:
        q += " AND reviewed=0"
    q += " ORDER BY id DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def mark_risk_reviewed(event_id: int) -> bool:
    with _conn() as c:
        return c.execute("UPDATE risk_events SET reviewed=1 WHERE id=?", (event_id,)).rowcount > 0


# ---------- assessments ----------
def add_assessment(session_id: str, instrument: str, answers: List[int], score: int, severity: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO assessments(session_id, instrument, answers, score, severity, created_at) VALUES (?,?,?,?,?,?)",
            (session_id, instrument, json.dumps(answers), score, severity, _now()),
        )


def get_assessments(session_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT instrument, answers, score, severity, created_at FROM assessments WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [{**dict(r), "answers": json.loads(r["answers"])} for r in rows]


# ---------- mood ----------
def add_mood(session_id: str, score: int, note: Optional[str], source: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO moods(session_id, score, note, source, created_at) VALUES (?,?,?,?,?)",
            (session_id, score, note, source, _now()),
        )


def get_moods(session_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT score, note, source, created_at FROM moods WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- long-term memory ----------
def get_profile(session_id: str) -> Dict[str, List[str]]:
    with _conn() as c:
        row = c.execute("SELECT memory FROM profiles WHERE session_id=?", (session_id,)).fetchone()
    return json.loads(row["memory"]) if row else {}


def save_profile(session_id: str, memory: Dict[str, List[str]]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles(session_id, memory, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET memory=excluded.memory, updated_at=excluded.updated_at",
            (session_id, json.dumps(memory), _now()),
        )


# ---------- safety plan ----------
def get_safety_plan(session_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT plan, updated_at FROM safety_plans WHERE session_id=?", (session_id,)).fetchone()
    return {**json.loads(row["plan"]), "updated_at": row["updated_at"]} if row else None


def save_safety_plan(session_id: str, plan: Dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO safety_plans(session_id, plan, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET plan=excluded.plan, updated_at=excluded.updated_at",
            (session_id, json.dumps(plan), _now()),
        )


# ---------- interventions (variety across days) ----------
def add_intervention(session_id: str, tool_id: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO interventions_used(session_id, tool_id, created_at) VALUES (?,?,?)", (session_id, tool_id, _now()))


def recent_interventions(session_id: str, days: int = 14) -> List[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _conn() as c:
        rows = c.execute(
            "SELECT tool_id FROM interventions_used WHERE session_id=? AND created_at>=? ORDER BY id", (session_id, cutoff)
        ).fetchall()
    return [r["tool_id"] for r in rows]


# ---------- activity state ----------
def get_activity(session_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT activity, turn FROM session_state WHERE session_id=? AND activity IS NOT NULL", (session_id,)).fetchone()
    return dict(row) if row else None


def set_activity(session_id: str, activity: Optional[str], turn: int = 0) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO session_state(session_id, activity, turn, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET activity=excluded.activity, turn=excluded.turn, updated_at=excluded.updated_at",
            (session_id, activity, turn, _now()),
        )


# ---------- privacy ----------
def delete_session(session_id: str) -> int:
    tables = ["messages", "analyses", "risk_events", "assessments", "moods", "profiles", "safety_plans", "summaries",
              "interventions_used", "session_state"]
    total = 0
    with _conn() as c:
        for t in tables:
            total += c.execute(f"DELETE FROM {t} WHERE session_id=?", (session_id,)).rowcount
    return total
