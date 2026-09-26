"""The actual "AI view minus human view" comparison (pure Python, tested).

agent_text: exactly what the agent received (html2text of what browse_web fetched).
human_text: html2text of the rendered page after removing every element a human can't see
            and every attribute a human never reads (alt, aria-label, title).
Anything in agent_text that is not in human_text was fed to the AI but invisible to the person.

Because we diff against what the agent actually got:
- JS-injected text is NOT flagged for a raw-mode agent (it never received it).
- Stripping is exact: we remove the gap sentences from agent_text, nothing else.
"""
from __future__ import annotations

import re
import unicodedata

import html2text

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MD_NOISE = re.compile(r"[*_#>`\[\]()!|-]")


def to_text(html: str) -> str:
    """Same converter settings as sandbox/tools.py so both views are comparable."""
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = False
    return h.handle(html)


_INVISIBLE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff\u00ad]|[\U000e0000-\U000e007f]")


def _norm(s: str) -> str:
    s = _INVISIBLE.sub("", unicodedata.normalize("NFKC", s))
    s = _MD_NOISE.sub(" ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if len(_norm(s)) >= 12]


def gap(agent_text: str, human_text: str) -> list[str]:
    """Sentences the agent received that don't appear anywhere in the human view."""
    human = _norm(human_text)
    out, seen = [], set()
    for s in sentences(agent_text):
        n = _norm(s)
        if n and n not in human and n not in seen:
            seen.add(n)
            out.append(s)
    return out


def strip(agent_text: str, spans: list[str]) -> str:
    """Remove each gap sentence from the agent's text."""
    out = agent_text
    for s in spans:
        out = out.replace(s, "[hidden content removed by shield]")
    return out
