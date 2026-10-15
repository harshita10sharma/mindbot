"""Retrieval over the vetted documents in data/ (txt, md, pdf, docx).

Uses Okapi BM25 implemented in pure Python: no embedding model or vector DB needed,
which keeps memory low enough for Render's free tier. Documents are split into
paragraph chunks, indexed once at startup, and re-indexed on demand.
"""
import math
import os
import re
from collections import Counter
from typing import Dict, List

import config

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an and are as at be but by for from has have i if in into is it its me my of on or our so that the their them "
    "they this to was we were what when which who will with you your how do does can should would could am been "
    "feel feeling felt really just like im dont cant very much even all one get got know want so not".split()
)


def _stem(t: str) -> str:
    """Tiny suffix stripper so 'stressed'/'stress', 'exams'/'exam', 'worrying'/'worry' match."""
    if len(t) <= 4:
        return t
    if t.endswith("ies"):
        return t[:-3] + "y"
    for suf in ("ing", "ed"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    if t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def _tokens(text: str) -> List[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def _read(path: str) -> str:
    low = path.lower()
    if low.endswith((".txt", ".md")):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if low.endswith(".pdf"):
        from PyPDF2 import PdfReader
        with open(path, "rb") as f:
            return "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
    if low.endswith(".docx"):
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs)
    return ""


def _chunk(text: str, max_chars: int = 900) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > max_chars:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: List[Dict[str, str]] = []
        self.tfs: List[Counter] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0

    def build(self, docs: List[Dict[str, str]]) -> None:
        self.docs = docs
        self.tfs = [Counter(_tokens(d["source"].replace("_", " ") + " " + d["text"])) for d in docs]
        self.df = Counter(t for tf in self.tfs for t in tf)
        self.avgdl = sum(sum(tf.values()) for tf in self.tfs) / max(1, len(self.tfs))

    def search(self, query: str, k: int = 3, min_score: float = 1.0) -> List[Dict[str, str]]:
        q = _tokens(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        scored = []
        for i, tf in enumerate(self.tfs):
            dl = sum(tf.values())
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s >= min_score:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [{**self.docs[i], "score": round(s, 2)} for s, i in scored[:k]]


_index = BM25Index()


def load(data_dir: str = config.DATA_DIR) -> int:
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"data folder missing: {data_dir}")
    docs = []
    for fn in sorted(os.listdir(data_dir)):
        path = os.path.join(data_dir, fn)
        if not os.path.isfile(path):
            continue
        try:
            text = _read(path)
        except Exception:
            continue
        source = os.path.splitext(fn)[0]
        docs += [{"source": source, "text": c} for c in _chunk(text)]
    _index.build(docs)
    return len(docs)


def search(query: str, k: int = 3) -> List[Dict[str, str]]:
    if not _index.docs:
        load()
    return _index.search(query, k=k)


def stats() -> Dict[str, int]:
    return {"chunks": len(_index.docs), "sources": len({d["source"] for d in _index.docs})}
