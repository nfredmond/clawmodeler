"""CEQA §15064.3 VMT significance analysis.

California Public Resources Code §21099 and CEQA Guidelines §15064.3
(revised after SB 743) make vehicle miles traveled (VMT) the preferred
metric for transportation-impact significance. This module derives
per-capita daily VMT per scenario from a finished run's
``vmt_screening.csv``, compares each scenario to an
agency-configurable reference VMT per capita, and issues a
``less-than-significant`` / ``potentially significant`` determination.

The Governor's Office of Planning and Research (OPR) *Technical
Advisory on Evaluating Transportation Impacts in CEQA* (December 2018)
recommends 15 percent below the reference baseline (regional or
citywide VMT per capita) as the default residential screening
threshold. That recommendation is the default here, but agencies can
override both the reference and the percentage.

Every determination is written back as a new
``ceqa_vmt_determination`` fact_block so subsequent narrative or chat
turns remain subject to the same citation contract that gates
``export --ai-narrative``. Nothing in this module calls an LLM; the
determination is purely arithmetic.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..workspace import ENGINE_VERSION, InsufficientDataError, read_json, utc_now, write_json
from .utilities import append_fact_blocks, jinja_env

OPR_DEFAULT_THRESHOLD_PCT = 0.15
PROJECT_TYPES = ("residential", "employment", "retail")
REFERENCE_LABELS = ("regional", "citywide", "custom")
DEFAULT_REFERENCE_VMT_PER_CAPITA = 22.0


@dataclass
class CeqaVmtScenario:
    scenario_id: str
    population: float
    daily_vmt: float
    vmt_per_capita: float
    threshold_vmt_per_capita: float
    delta_pct: float
    significant: bool
    determination: str
    mitigation_required: bool


@dataclass
class CeqaVmtResult:
    project_type: str
    reference_label: str
    reference_vmt_per_capita: float
    threshold_pct: float
    threshold_vmt_per_capita: float
    scenarios: list[CeqaVmtScenario] = field(default_factory=list)
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "project_type": self.project_type,
            "reference_label": self.reference_label,
            "reference_vmt_per_capita": self.reference_vmt_per_capita,
            "threshold_pct": self.threshold_pct,
            "threshold_vmt_per_capita": self.threshold_vmt_per_capita,
            "generated_at": self.generated_at,
            "scenarios": [asdict(s) for s in self.scenarios],
        }


def compute_ceqa_vmt(
    vmt_rows: list[dict[str, Any]],
    *,
    reference_vmt_per_capita: float,
    project_type: str = "residential",
    reference_label: str = "regional",
    threshold_pct: float = OPR_DEFAULT_THRESHOLD_PCT,
) -> CeqaVmtResult:
    """Compute per-scenario CEQA §15064.3 VMT determinations.

    ``vmt_rows`` is the engine's ``vmt_screening.csv`` in list-of-dict
    form (``csv.DictReader`` output is directly compatible).
    ``reference_vmt_per_capita`` is the regional or citywide reference.
    The cut line is ``reference * (1 - threshold_pct)`` and any scenario
    at or above that line is ``potentially significant``.
    """
    if project_type not in PROJECT_TYPES:
        raise ValueError(
            f"Unknown project_type {project_type!r}; expected one of {PROJECT_TYPES}"
        )
    if reference_label not in REFERENCE_LABELS:
        raise ValueError(
            f"Unknown reference_label {reference_label!r}; expected one of {REFERENCE_LABELS}"
        )
    if reference_vmt_per_capita <= 0:
        raise ValueError(
            f"reference_vmt_per_capita must be > 0, got {reference_vmt_per_capita}"
        )
    if not 0 < threshold_pct < 1:
        raise ValueError(
            f"threshold_pct must be a fraction between 0 and 1, got {threshold_pct}"
        )
    if not vmt_rows:
        raise InsufficientDataError(
            "vmt_screening rows are empty; run a workflow before computing CEQA VMT."
        )

    threshold = reference_vmt_per_capita * (1 - threshold_pct)
    scenarios: list[CeqaVmtScenario] = []
    for row in vmt_rows:
        scenario_id = str(row.get("scenario_id") or "").strip()
        if not scenario_id:
            continue
        population = float(row.get("population") or 0)
        daily_vmt = float(row.get("daily_vmt") or 0)
        if population <= 0:
            continue
        vmt_per_capita = daily_vmt / population
        delta_pct = (vmt_per_capita - threshold) / threshold if threshold > 0 else 0.0
        significant = vmt_per_capita >= threshold
        scenarios.append(
            CeqaVmtScenario(
                scenario_id=scenario_id,
                population=round(population, 3),
                daily_vmt=round(daily_vmt, 3),
                vmt_per_capita=round(vmt_per_capita, 3),
                threshold_vmt_per_capita=round(threshold, 3),
                delta_pct=round(delta_pct, 4),
                significant=significant,
                determination=(
                    "potentially significant" if significant else "less than significant"
                ),
                mitigation_required=significant,
            )
        )

    return CeqaVmtResult(
        project_type=project_type,
        reference_label=reference_label,
        reference_vmt_per_capita=round(reference_vmt_per_capita, 3),
        threshold_pct=threshold_pct,
        threshold_vmt_per_capita=round(threshold, 3),
        scenarios=scenarios,
        generated_at=utc_now(),
    )


def ceqa_vmt_fact_blocks(
    result: CeqaVmtResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for each scenario determination."""
    blocks: list[dict[str, Any]] = []
    for scenario in result.scenarios:
        direction = "above" if scenario.significant else "below"
        delta_pct_display = abs(scenario.delta_pct) * 100
        claim = (
            f"Under CEQA §15064.3, scenario {scenario.scenario_id} VMT per "
            f"capita is {scenario.vmt_per_capita:.1f} — {scenario.determination}, "
            f"{delta_pct_display:.1f}% {direction} the "
            f"{result.threshold_pct * 100:.0f}%-below-"
            f"{result.reference_label} threshold of "
            f"{scenario.threshold_vmt_per_capita:.1f} VMT/capita."
        )
        blocks.append(
            {
                "fact_id": f"ceqa-vmt-{scenario.scenario_id}",
                "fact_type": "ceqa_vmt_determination",
                "scenario_id": scenario.scenario_id,
                "claim_text": claim,
                "method_ref": "planner_pack.ceqa_vmt",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": f"{result.project_type}.{result.reference_label}",
            }
        )
    return blocks


def render_ceqa_vmt_markdown(result: CeqaVmtResult, *, run_id: str) -> str:
    """Render the CEQA §15064.3 VMT memo as Markdown."""
    template = jinja_env().get_template("ceqa_vmt.md.j2")
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=result.to_json(),
        scenarios=[asdict(s) for s in result.scenarios],
    )


def _read_vmt_screening_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_reference_vmt_per_capita(workspace: Path) -> float:
    """Default to the question's `daily_vmt_per_capita`; fall back to 22.0."""
    analysis_plan_path = workspace / "analysis_plan.json"
    if not analysis_plan_path.exists():
        return DEFAULT_REFERENCE_VMT_PER_CAPITA
    try:
        plan = read_json(analysis_plan_path)
    except Exception:
        return DEFAULT_REFERENCE_VMT_PER_CAPITA
    question = plan.get("question") if isinstance(plan, dict) else None
    if not isinstance(question, dict):
        return DEFAULT_REFERENCE_VMT_PER_CAPITA
    value = question.get("daily_vmt_per_capita")
    try:
        return float(value) if value is not None else DEFAULT_REFERENCE_VMT_PER_CAPITA
    except (TypeError, ValueError):
        return DEFAULT_REFERENCE_VMT_PER_CAPITA


def write_ceqa_vmt(
    workspace: Path,
    run_id: str,
    *,
    project_type: str = "residential",
    reference_label: str = "regional",
    reference_vmt_per_capita: float | None = None,
    threshold_pct: float = OPR_DEFAULT_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Compute CEQA VMT, append fact_blocks, render the memo, return paths."""
    run_root = workspace / "runs" / run_id
    if not run_root.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} does not exist under {workspace}."
        )
    vmt_path = run_root / "outputs" / "tables" / "vmt_screening.csv"
    if not vmt_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no vmt_screening.csv; run a workflow first."
        )
    vmt_rows = _read_vmt_screening_csv(vmt_path)
    if not vmt_rows:
        raise InsufficientDataError(
            f"Run {run_id!r} vmt_screening.csv has no rows."
        )

    if reference_vmt_per_capita is None:
        reference_vmt_per_capita = _resolve_reference_vmt_per_capita(workspace)

    result = compute_ceqa_vmt(
        vmt_rows,
        reference_vmt_per_capita=reference_vmt_per_capita,
        project_type=project_type,
        reference_label=reference_label,
        threshold_pct=threshold_pct,
    )

    ceqa_csv_path = run_root / "outputs" / "tables" / "ceqa_vmt.csv"
    ceqa_json_path = run_root / "outputs" / "tables" / "ceqa_vmt.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_ceqa_vmt.md"

    ceqa_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with ceqa_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario_id",
                "population",
                "daily_vmt",
                "vmt_per_capita",
                "threshold_vmt_per_capita",
                "delta_pct",
                "significant",
                "determination",
                "mitigation_required",
            ],
        )
        writer.writeheader()
        for scenario in result.scenarios:
            writer.writerow(asdict(scenario))

    write_json(ceqa_json_path, result.to_json())

    new_blocks = ceqa_vmt_fact_blocks(result, ceqa_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_ceqa_vmt_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "csv_path": str(ceqa_csv_path),
        "json_path": str(ceqa_json_path),
        "fact_block_count": appended,
        "scenario_count": len(result.scenarios),
        "project_type": project_type,
        "reference_label": reference_label,
        "reference_vmt_per_capita": result.reference_vmt_per_capita,
        "threshold_pct": threshold_pct,
        "threshold_vmt_per_capita": result.threshold_vmt_per_capita,
    }
