"""LLM integration for ClawModeler AI-narrative reports.

The grounding contract is load-bearing: every narrative sentence must
cite a fact_id that exists in the run's fact_blocks.jsonl. Citation
enforcement is deterministic (regex + set membership), not an LLM judge.
"""

from .grounding import (
    CITATION_PATTERN,
    GroundedOutput,
    GroundingIssue,
    GroundingMode,
    Sentence,
    split_sentences,
    validate_and_ground,
)

__all__ = [
    "CITATION_PATTERN",
    "GroundedOutput",
    "GroundingIssue",
    "GroundingMode",
    "Sentence",
    "split_sentences",
    "validate_and_ground",
]
