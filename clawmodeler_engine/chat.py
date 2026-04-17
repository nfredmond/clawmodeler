"""Chat With the Run — grounded question-answering against a finished run.

Read-only: the chat module loads an existing run's fact_blocks.jsonl and
answers a user's question by calling the configured LLM provider. Every
sentence in the reply must cite [fact:<fact_id>] against a known
fact_block or it is dropped. When nothing survives grounding, the
module returns the single sentence 'I do not have evidence for that in
this run's fact_blocks.' Chat turns are persisted to
runs/<run_id>/chat_history.jsonl so a replay is always possible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .llm.config import CLOUD_PROVIDERS, build_provider, load_config
from .llm.grounding import GroundingMode, validate_and_ground
from .llm.provider import LLMProvider
from .report import read_fact_blocks
from .workspace import InsufficientDataError, utc_now

NOT_IN_CONTEXT = (
    "I do not have evidence for that in this run's fact_blocks."
)

PROMPT_INSTRUCTIONS = (
    "You are answering a planner's question about a finished "
    "transportation screening run. Every sentence in your answer MUST "
    "include at least one inline citation in the form [fact:<fact_id>] "
    "where <fact_id> is one of the fact_ids listed below. Do not invent "
    "facts, numbers, or fact_ids. If the question cannot be answered "
    "from the listed fact_blocks, reply with exactly one sentence: "
    f"'{NOT_IN_CONTEXT}' Keep answers concise — planner voice, "
    "2-5 sentences."
)


@dataclass
class ChatTurn:
    turn_id: int
    created_at: str
    user_message: str
    provider: str
    model: str
    raw_text: str
    text: str
    is_fully_grounded: bool
    ungrounded_sentence_count: int
    cited_fact_ids: list[str] = field(default_factory=list)
    unknown_fact_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def chat_history_path(workspace: Path, run_id: str) -> Path:
    return workspace / "runs" / run_id / "chat_history.jsonl"


def load_history(workspace: Path, run_id: str) -> list[dict[str, Any]]:
    path = chat_history_path(workspace, run_id)
    if not path.exists():
        return []
    history: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                history.append(json.loads(line))
    return history


def append_turn(workspace: Path, run_id: str, turn: ChatTurn) -> Path:
    path = chat_history_path(workspace, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(turn.to_json()) + "\n")
    return path


def build_chat_prompt(
    user_message: str,
    fact_blocks: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = [PROMPT_INSTRUCTIONS, ""]

    lines.append("Available fact_blocks (cite by fact_id):")
    if not fact_blocks:
        lines.append("  (no fact_blocks available — reply with the not-in-context sentence)")
    for block in fact_blocks:
        fid = block.get("fact_id", "")
        ftype = block.get("fact_type", "")
        scenario = block.get("scenario_id") or "—"
        claim = str(block.get("claim_text", "")).strip()
        lines.append(
            f"  - fact_id={fid!r} type={ftype} scenario={scenario}: {claim}"
        )

    if history:
        lines.append("")
        lines.append("Recent chat history (most recent last):")
        for turn in history[-5:]:
            lines.append(f"  User: {turn.get('user_message', '')}")
            lines.append(f"  Assistant: {turn.get('text', '')}")

    lines.append("")
    lines.append(f"User question: {user_message}")
    lines.append("")
    lines.append("Write your grounded answer now.")
    return "\n".join(lines)


def chat_with_run(
    workspace: Path,
    run_id: str,
    user_message: str,
    provider: LLMProvider,
    *,
    mode: GroundingMode = GroundingMode.STRICT,
    include_history: bool = True,
) -> ChatTurn:
    """Answer ``user_message`` against the run's fact_blocks.

    Loads fact_blocks.jsonl for ``run_id``, calls ``provider``, runs the
    response through the STRICT grounding validator, and appends the
    turn to ``chat_history.jsonl``. Raises
    :class:`InsufficientDataError` if the run has no fact_blocks.
    """

    fact_blocks_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
    )
    if not fact_blocks_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no fact_blocks.jsonl; chat requires a finished run."
        )
    fact_blocks = read_fact_blocks(fact_blocks_path)
    if not fact_blocks:
        raise InsufficientDataError(
            f"Run {run_id!r} has an empty fact_blocks.jsonl; nothing to cite."
        )

    history = load_history(workspace, run_id) if include_history else []
    prompt = build_chat_prompt(user_message, fact_blocks, history=history)
    generation = provider.generate(prompt, fact_blocks)

    known_ids = {
        str(b.get("fact_id", "")) for b in fact_blocks if b.get("fact_id")
    }
    grounded = validate_and_ground(generation.text, known_ids, mode=mode)

    text = grounded.text.strip() or NOT_IN_CONTEXT
    turn = ChatTurn(
        turn_id=len(history) + 1,
        created_at=utc_now(),
        user_message=user_message,
        provider=generation.provider,
        model=generation.model,
        raw_text=generation.text,
        text=text,
        is_fully_grounded=grounded.is_fully_grounded
        if grounded.text.strip()
        else True,
        ungrounded_sentence_count=grounded.ungrounded_sentence_count,
        cited_fact_ids=list(grounded.cited_fact_ids),
        unknown_fact_ids=list(grounded.unknown_fact_ids),
    )
    append_turn(workspace, run_id, turn)
    return turn


def chat_from_workspace(
    workspace: Path,
    run_id: str,
    user_message: str,
    *,
    include_history: bool = True,
) -> ChatTurn:
    """Top-level entry point: load config, enforce cloud gate, answer."""

    config = load_config(workspace)
    if config.provider in CLOUD_PROVIDERS and not config.cloud_confirmed:
        raise InsufficientDataError(
            f"Cloud provider {config.provider!r} requires explicit confirmation. "
            "Run `clawmodeler-engine llm configure cloud_confirmed=true` "
            "before using chat."
        )
    provider = build_provider(config)
    try:
        mode = GroundingMode(config.grounding_mode)
    except ValueError:
        mode = GroundingMode.STRICT
    return chat_with_run(
        workspace,
        run_id,
        user_message,
        provider,
        mode=mode,
        include_history=include_history,
    )
