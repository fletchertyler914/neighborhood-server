"""Lightweight keyword retrieval over the curated knowledge base.

For our use case (~3 hand-curated docs, short prompts), full embedding-based
RAG is overkill. We chunk by markdown section heading and rank by keyword
overlap. This gives us the right slice of block IDs / FAWE syntax / patterns
to inject into the system prompt without bloat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent / "knowledge"

# Tokens too generic to count (would match every prompt).
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "by", "to", "for",
    "is", "are", "be", "with", "me", "my", "i", "you", "we", "us", "it", "its",
    "this", "that", "these", "those", "do", "does", "make", "build", "create",
    "give", "set", "put", "place", "use", "want", "need", "around", "near",
    "here", "there", "now", "then", "from", "as", "so", "if", "but", "any",
    "block", "blocks",
}


@dataclass
class Chunk:
    source: str
    heading: str
    body: str
    tokens: set[str]

    def render(self) -> str:
        return f"### {self.source}: {self.heading}\n{self.body.strip()}"


def _tokenize(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9_/\s]", " ", text)
    return {t for t in text.split() if t and t not in _STOPWORDS and len(t) > 2}


@lru_cache(maxsize=1)
def _load_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    if not KB_DIR.exists():
        return chunks
    for md in sorted(KB_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        sections = re.split(r"^##\s+", text, flags=re.M)
        first = sections[0]
        if first.strip():
            chunks.append(
                Chunk(
                    source=md.stem,
                    heading="overview",
                    body=first,
                    tokens=_tokenize(first),
                )
            )
        for sec in sections[1:]:
            head, _, body = sec.partition("\n")
            chunks.append(
                Chunk(
                    source=md.stem,
                    heading=head.strip(),
                    body=body,
                    tokens=_tokenize(head + " " + body),
                )
            )
    return chunks


def retrieve(prompt: str, top_k: int = 3, max_chars: int = 2400) -> list[Chunk]:
    """Return up to top_k knowledge chunks most relevant to the prompt."""
    query_tokens = _tokenize(prompt)
    if not query_tokens:
        return []
    chunks = _load_chunks()
    scored: list[tuple[int, Chunk]] = []
    for c in chunks:
        score = len(query_tokens & c.tokens)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    out: list[Chunk] = []
    used = 0
    for _, c in scored[: top_k * 2]:
        if used + len(c.body) > max_chars:
            continue
        out.append(c)
        used += len(c.body)
        if len(out) >= top_k:
            break
    return out


def render_block(prompt: str) -> str:
    """Render retrieved knowledge as a Markdown block for the system prompt."""
    chunks = retrieve(prompt)
    if not chunks:
        return ""
    body = "\n\n".join(c.render() for c in chunks)
    return f"## Relevant Minecraft knowledge\n\n{body}"
