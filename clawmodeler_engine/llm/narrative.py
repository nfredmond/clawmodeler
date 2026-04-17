"""Build AI-generated narrative sections for reports.

Orchestrates one provider call → one grounding pass → one narrative
payload that the Jinja templates can inject. The provider writes
prose; the deterministic validator decides what prose ships.
Everything that survives validation is already citation-anchored to
the run's fact_blocks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .grounding import GroundingMode, validate_and_ground
from .provider import LLMProvider

PROMPT_INSTRUCTIONS = (
    "You are writing the narrative section of a transportation screening "
    "report. Every sentence in your response MUST include at least one "
    "inline citation in the form [fact:<fact_id>] where <fact_id> is one "
    "of the fact_ids listed below. Do not invent facts, numbers, or "
    "fact_ids. If a claim cannot be anchored to a listed fact_id, do not "
    "make the claim. Write in plain, professional planner voice. Prefer "
    "short, direct sentences. 3–6 sentences total."
)


@dataclass
class NarrativeResult:
    provider: str
    model: str
    raw_text: str
    text: str
    ungrounded_sentence_count: int
    is_fully_grounded: bool
    cited_fact_ids: list[str] = field(default_factory=list)
    unknown_fact_ids: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_template_context(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "is_fully_grounded": self.is_fully_grounded,
        }


def build_narrative_prompt(
    manifest: dict[str, Any], fact_blocks: list[dict[str, Any]]
) -> str:
    lines: list[str] = [PROMPT_INSTRUCTIONS, ""]

    run_id = manifest.get("run_id", "unknown")
    scenarios = manifest.get("scenarios", []) or []
    scenario_ids = [str(s.get("scenario_id", "")) for s in scenarios if s]
    lines.append(f"Run ID: {run_id}")
    if scenario_ids:
        lines.append(f"Scenarios: {', '.join(scenario_ids)}")
    lines.append("")
    lines.append("Available fact_blocks (cite by fact_id):")

    if not fact_blocks:
        lines.append("  (no fact_blocks available — do not generate any claims)")
    for block in fact_blocks:
        fid = block.get("fact_id", "")
        ftype = block.get("fact_type", "")
        scenario = block.get("scenario_id") or "—"
        claim = str(block.get("claim_text", "")).strip()
        lines.append(
            f"  - fact_id={fid!r} type={ftype} scenario={scenario}: {claim}"
        )

    lines.append("")
    lines.append("Write the narrative now.")
    return "\n".join(lines)


def generate_narrative(
    manifest: dict[str, Any],
    fact_blocks: list[dict[str, Any]],
    provider: LLMProvider,
    *,
    mode: GroundingMode = GroundingMode.STRICT,
) -> NarrativeResult:
    prompt = build_narrative_prompt(manifest, fact_blocks)
    generation = provider.generate(prompt, fact_blocks)

    known_ids = {str(b.get("fact_id", "")) for b in fact_blocks if b.get("fact_id")}
    grounded = validate_and_ground(generation.text, known_ids, mode=mode)

    return NarrativeResult(
        provider=generation.provider,
        model=generation.model,
        raw_text=generation.text,
        text=grounded.text,
        ungrounded_sentence_count=grounded.ungrounded_sentence_count,
        is_fully_grounded=grounded.is_fully_grounded,
        cited_fact_ids=list(grounded.cited_fact_ids),
        unknown_fact_ids=list(grounded.unknown_fact_ids),
        issues=[asdict(issue) for issue in grounded.issues],
    )
