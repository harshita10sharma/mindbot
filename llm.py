"""Thin, fault-tolerant wrapper around the Groq SDK.

- One shared client for the whole app.
- Low reasoning effort for gpt-oss models (fewer hidden tokens = more requests per day).
- JSON mode with a tolerant parser.
- Typed errors so callers can degrade gracefully when the free tier is rate limited.
"""
import json
import re
import time
from typing import Any, Dict, List, Optional

from groq import Groq, RateLimitError, APIStatusError, APIConnectionError

import config

if not config.GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY missing in .env file. Please add it before starting the app.")

client = Groq(api_key=config.GROQ_API_KEY, max_retries=1, timeout=45)


class LLMUnavailable(Exception):
    """The model could not be reached (rate limit, outage, bad model name)."""


def _is_reasoning_model(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


class _RateLimited(LLMUnavailable):
    def __init__(self, msg: str, per_day: bool):
        super().__init__(msg)
        self.per_day = per_day


# When one model's free-tier bucket is exhausted, use the other instead of degrading the pipeline.
FALLBACK = {"openai/gpt-oss-120b": "openai/gpt-oss-20b", "openai/gpt-oss-20b": "openai/gpt-oss-120b"}
_cooldown_until: Dict[str, float] = {}


def chat(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.6,
    max_tokens: int = 900,
    json_mode: bool = False,
    reasoning_effort: str = "low",
    allow_fallback: bool = True,
) -> str:
    """Call `model`; if it is rate limited (or known to be cooling down), transparently use its fallback model."""
    candidates = [model]
    if allow_fallback and FALLBACK.get(model):
        candidates.append(FALLBACK[model])
    now = time.time()
    ready = [m for m in candidates if _cooldown_until.get(m, 0) <= now] or candidates
    last: Optional[Exception] = None
    for m in ready:
        try:
            return _chat_once(messages, m, temperature, max_tokens, json_mode, reasoning_effort)
        except _RateLimited as e:
            _cooldown_until[m] = time.time() + (600 if e.per_day else 20)
            last = e
    raise LLMUnavailable(str(last) if last else f"{model} unavailable")


def _chat_once(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    reasoning_effort: str,
) -> str:
    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    if _is_reasoning_model(model):
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["include_reasoning"] = False
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise LLMUnavailable(f"{model} returned an empty response")
            return content
        except RateLimitError as e:
            per_day = "per day" in str(e).lower() or "tpd" in str(e).lower() or "rpd" in str(e).lower()
            raise _RateLimited(f"rate limited on {model}" + (" (daily quota)" if per_day else ""), per_day) from e
        except APIStatusError as e:
            last_err = e
            # JSON mode can fail validation on long outputs; retry once without it.
            if json_mode and e.status_code == 400 and attempt == 0:
                kwargs.pop("response_format", None)
                continue
            raise LLMUnavailable(f"{model} error {e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            last_err = e
            time.sleep(1)
    raise LLMUnavailable(f"{model} unreachable: {last_err}")


def chat_json(messages: List[Dict[str, str]], model: str, max_tokens: int = 700, temperature: float = 0.2) -> Dict[str, Any]:
    raw = chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, json_mode=True)
    return parse_json(raw)


def parse_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMUnavailable("model did not return valid JSON")


def guard_score(text: str) -> Optional[float]:
    """Prompt-injection / jailbreak probability from Llama Prompt Guard 2 (0..1), or None."""
    try:
        resp = client.chat.completions.create(
            model=config.GUARD_MODEL,
            messages=[{"role": "user", "content": text[:2000]}],
        )
        return float((resp.choices[0].message.content or "").strip())
    except Exception:
        return None


def transcribe(filename: str, data: bytes, language: Optional[str] = None) -> str:
    kwargs: Dict[str, Any] = dict(file=(filename, data), model=config.TRANSCRIBE_MODEL)
    if language:
        kwargs["language"] = language
    try:
        return client.audio.transcriptions.create(**kwargs).text.strip()
    except RateLimitError as e:
        raise LLMUnavailable("transcription rate limited") from e
    except APIStatusError as e:
        raise LLMUnavailable(f"transcription error {e.status_code}: {e.message}") from e
