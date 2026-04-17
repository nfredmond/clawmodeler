"""Deterministic citation validator for AI-generated narrative text.

Every sentence in a narrative must carry at least one inline
``[fact:<fact_id>]`` citation that matches a known fact_id. This
module does the check with regex + set membership only — it does
not call a language model to judge correctness, because the whole
point of the grounding contract is that the check itself cannot
hallucinate.

Two modes are supported:

* ``strict`` — ungrounded sentences are removed from the narrative.
  The caller (QA gate) then blocks export if any sentence was
  removed, so shipped reports cannot contain ungrounded prose.
* ``annotated`` — ungrounded sentences are kept but prefixed with
  ``⚠`` so a planner reviewer can see them. Useful during
  development, never acceptable for shipped exports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

CITATION_PATTERN = re.compile(r"\[fact:([A-Za-z0-9][A-Za-z0-9_\-.]*)\]")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9\"'`(])")

_STRUCTURAL_PREFIXES = ("#", "---", "===", "```", "|", ">")

_ANNOTATION_PREFIX = "\u26A0 "


class GroundingMode(str, Enum):
    STRICT = "strict"
    ANNOTATED = "annotated"


@dataclass
class Sentence:
    text: str
    cited_fact_ids: list[str]
    is_grounded: bool
    unknown_fact_ids: list[str]


@dataclass
class GroundingIssue:
    kind: str
    detail: str
    sentence: str


@dataclass
class GroundedOutput:
    text: str
    sentences: list[Sentence]
    cited_fact_ids: list[str]
    unknown_fact_ids: list[str]
    ungrounded_sentence_count: int
    issues: list[GroundingIssue] = field(default_factory=list)

    @property
    def is_fully_grounded(self) -> bool:
        return self.ungrounded_sentence_count == 0 and not self.unknown_fact_ids


def _is_citation_only(piece: str) -> bool:
    return CITATION_PATTERN.sub("", piece).strip() == ""


def split_sentences(text: str) -> list[str]:
    """Split block text into sentence-level claims.

    Lines that are purely structural (headings, horizontal rules,
    code fences, table rows, blank lines) are skipped — they are
    not factual claims and do not need citations. Bullet markers,
    numbered-list markers, and blockquote markers are stripped so
    the sentence itself is what gets validated. Trailing
    citation-only fragments (``. [fact:abc]``) are re-attached to
    the preceding sentence so the citation stays anchored to the
    claim it supports.
    """

    sentences: list[str] = []
    in_code_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if any(line.startswith(p) for p in _STRUCTURAL_PREFIXES):
            continue
        line = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", line)
        if not line:
            continue
        raw_pieces = [p.strip() for p in _SENTENCE_SPLIT.split(line) if p.strip()]
        merged: list[str] = []
        for piece in raw_pieces:
            if merged and _is_citation_only(piece):
                merged[-1] = f"{merged[-1]} {piece}".strip()
            else:
                merged.append(piece)
        sentences.extend(merged)
    return sentences


def _classify(sentence: str, known_fact_ids: frozenset[str]) -> Sentence:
    matches = CITATION_PATTERN.findall(sentence)
    cited = list(dict.fromkeys(matches))
    unknown = [fid for fid in cited if fid not in known_fact_ids]
    is_grounded = bool(cited) and not unknown
    return Sentence(
        text=sentence,
        cited_fact_ids=cited,
        is_grounded=is_grounded,
        unknown_fact_ids=unknown,
    )


def validate_and_ground(
    text: str,
    known_fact_ids: Iterable[str],
    *,
    mode: GroundingMode = GroundingMode.STRICT,
) -> GroundedOutput:
    """Validate ``text`` against ``known_fact_ids`` and return a
    :class:`GroundedOutput` whose ``text`` has ungrounded sentences
    removed (``strict``) or visibly annotated (``annotated``).
    """

    known = frozenset(str(fid) for fid in known_fact_ids)
    raw_sentences = split_sentences(text)
    classified = [_classify(s, known) for s in raw_sentences]

    issues: list[GroundingIssue] = []
    kept_sentences: list[Sentence] = []
    kept_text_lines: list[str] = []
    ungrounded_count = 0
    unknown_all: list[str] = []
    cited_all: list[str] = []

    for sentence in classified:
        cited_all.extend(sentence.cited_fact_ids)
        if sentence.is_grounded:
            kept_sentences.append(sentence)
            kept_text_lines.append(sentence.text)
            continue

        ungrounded_count += 1
        unknown_all.extend(sentence.unknown_fact_ids)
        if not sentence.cited_fact_ids:
            issues.append(
                GroundingIssue(
                    kind="missing_citation",
                    detail="sentence has no [fact:*] citation",
                    sentence=sentence.text,
                )
            )
        else:
            issues.append(
                GroundingIssue(
                    kind="unknown_fact_id",
                    detail=f"unknown fact_ids: {sentence.unknown_fact_ids}",
                    sentence=sentence.text,
                )
            )

        if mode is GroundingMode.ANNOTATED:
            kept_sentences.append(sentence)
            kept_text_lines.append(_ANNOTATION_PREFIX + sentence.text)

    grounded_text = " ".join(kept_text_lines).strip()

    return GroundedOutput(
        text=grounded_text,
        sentences=kept_sentences,
        cited_fact_ids=list(dict.fromkeys(cited_all)),
        unknown_fact_ids=list(dict.fromkeys(unknown_all)),
        ungrounded_sentence_count=ungrounded_count,
        issues=issues,
    )
