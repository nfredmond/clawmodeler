"""Highway Safety Improvement Program (HSIP) cycle screening.

The Highway Safety Improvement Program (23 USC 148; FHWA HSIP Manual
Chapter 3) is the primary federal funding source for infrastructure
safety projects. California administers its HSIP cycles through
Caltrans Division of Local Assistance, with benefit-cost ratio (B/C) and
proven-countermeasure eligibility as two of the hardest screening
filters.

This module reads a finished ClawModeler run's ``project_scores.csv``
together with an optional ``hsip_overlay.csv`` sidecar a lead agency
stages with per-project crash history, systemic risk score,
benefit-cost ratio, and proven-countermeasure flag. It produces a
per-project HSIP screen plus a portfolio summary showing which projects
clear the configurable minimum B/C ratio and which ship a proven
countermeasure, so the lead agency can focus effort on the applicable
applications.

ClawModeler does not synthesize HSIP inputs. When the sidecar is
absent or incomplete the relevant fields are reported as ``unknown`` /
``None`` and the project is flagged as ``not yet screened`` rather than
silently deemed ineligible.

This module does not call an LLM.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..workspace import ENGINE_VERSION, InsufficientDataError, utc_now, write_json
from .utilities import (
    append_fact_blocks,
    coerce_str,
    jinja_env,
    manifest_artifact_paths,
    parse_optional_float,
    validate_fact_block_shape,
)

DEFAULT_MIN_BC_RATIO = 1.0
DEFAULT_CYCLE_LABEL = "HSIP cycle to be provided"


@dataclass
class HsipProjectScreen:
    project_id: str
    name: str
    total_score: float
    sensitivity_flag: str
    crash_history_5yr: float | None
    fatal_serious_5yr: float | None
    systemic_risk_score: float | None
    benefit_cost_ratio: float | None
    proven_countermeasure: bool
    proven_countermeasure_citation: str
    overlay_supplied: bool
    bc_ratio_passes: bool
    screen_status: str
    data_source_ref: str


@dataclass
class HsipPortfolioSummary:
    project_count: int
    overlay_supplied_count: int
    bc_ratio_passes_count: int
    proven_countermeasure_count: int
    mean_benefit_cost_ratio: float | None
    mean_systemic_risk_score: float | None
    total_fatal_serious_5yr: float | None


@dataclass
class HsipResult:
    run_id: str
    cycle_year: int
    cycle_label: str
    min_bc_ratio: float
    project_count: int
    screens: list[HsipProjectScreen] = field(default_factory=list)
    summary: HsipPortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cycle_year": self.cycle_year,
            "cycle_label": self.cycle_label,
            "min_bc_ratio": self.min_bc_ratio,
            "project_count": self.project_count,
            "generated_at": self.generated_at,
            "screens": [asdict(s) for s in self.screens],
            "summary": asdict(self.summary) if self.summary is not None else None,
        }


def _coerce_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return False
    return text in {"true", "t", "1", "yes", "y"}


def _screen_status(*, overlay_supplied: bool, bc_ratio: float | None, passes: bool) -> str:
    if not overlay_supplied:
        return "not yet screened"
    if bc_ratio is None:
        return "awaiting benefit-cost ratio"
    return "eligible" if passes else "below minimum B/C"


def compute_hsip(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    cycle_year: int,
    cycle_label: str = DEFAULT_CYCLE_LABEL,
    min_bc_ratio: float = DEFAULT_MIN_BC_RATIO,
    overlay_rows: list[dict[str, Any]] | None = None,
) -> HsipResult:
    """Build HSIP screens from project scores + optional HSIP overlay sidecar.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict.
    ``overlay_rows`` is an optional sidecar keyed by ``project_id`` with
    columns ``crash_history_5yr``, ``fatal_serious_5yr``,
    ``systemic_risk_score``, ``benefit_cost_ratio``,
    ``proven_countermeasure`` (boolean), ``proven_countermeasure_citation``
    (free text), and ``data_source_ref`` (free text).
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before generating "
            "the HSIP screen."
        )
    if min_bc_ratio < 0:
        raise ValueError("min_bc_ratio must be non-negative.")

    overlay_by_id: dict[str, dict[str, Any]] = {}
    for row in overlay_rows or []:
        project_id = coerce_str(row.get("project_id"))
        if project_id:
            overlay_by_id[project_id] = row

    screens: list[HsipProjectScreen] = []
    bc_values: list[float] = []
    systemic_values: list[float] = []
    fatal_total = 0.0
    fatal_seen = False

    for row in score_rows:
        project_id = coerce_str(row.get("project_id"))
        if not project_id:
            continue
        overlay = overlay_by_id.get(project_id)
        overlay_supplied = overlay is not None
        overlay = overlay or {}

        crash_history = parse_optional_float(overlay.get("crash_history_5yr"))
        fatal_serious = parse_optional_float(overlay.get("fatal_serious_5yr"))
        systemic_risk = parse_optional_float(overlay.get("systemic_risk_score"))
        bc_ratio = parse_optional_float(overlay.get("benefit_cost_ratio"))
        proven = _coerce_bool(overlay.get("proven_countermeasure"))
        proven_citation = coerce_str(
            overlay.get("proven_countermeasure_citation"),
            "FHWA Proven Safety Countermeasure citation to be provided.",
        )
        data_source = coerce_str(
            overlay.get("data_source_ref"),
            "Crash/systemic data source to be provided by lead agency.",
        )

        passes = bc_ratio is not None and bc_ratio >= min_bc_ratio
        status = _screen_status(
            overlay_supplied=overlay_supplied,
            bc_ratio=bc_ratio,
            passes=passes,
        )

        if bc_ratio is not None:
            bc_values.append(bc_ratio)
        if systemic_risk is not None:
            systemic_values.append(systemic_risk)
        if fatal_serious is not None:
            fatal_total += fatal_serious
            fatal_seen = True

        screens.append(
            HsipProjectScreen(
                project_id=project_id,
                name=coerce_str(row.get("name"), project_id),
                total_score=round(
                    parse_optional_float(row.get("total_score")) or 0.0, 3
                ),
                sensitivity_flag=coerce_str(
                    row.get("sensitivity_flag"), "UNKNOWN"
                ),
                crash_history_5yr=crash_history,
                fatal_serious_5yr=fatal_serious,
                systemic_risk_score=systemic_risk,
                benefit_cost_ratio=bc_ratio,
                proven_countermeasure=proven,
                proven_countermeasure_citation=proven_citation,
                overlay_supplied=overlay_supplied,
                bc_ratio_passes=passes,
                screen_status=status,
                data_source_ref=data_source,
            )
        )

    if not screens:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    summary = HsipPortfolioSummary(
        project_count=len(screens),
        overlay_supplied_count=sum(1 for s in screens if s.overlay_supplied),
        bc_ratio_passes_count=sum(1 for s in screens if s.bc_ratio_passes),
        proven_countermeasure_count=sum(1 for s in screens if s.proven_countermeasure),
        mean_benefit_cost_ratio=(
            round(sum(bc_values) / len(bc_values), 3) if bc_values else None
        ),
        mean_systemic_risk_score=(
            round(sum(systemic_values) / len(systemic_values), 3)
            if systemic_values
            else None
        ),
        total_fatal_serious_5yr=round(fatal_total, 3) if fatal_seen else None,
    )

    return HsipResult(
        run_id=run_id,
        cycle_year=cycle_year,
        cycle_label=cycle_label,
        min_bc_ratio=min_bc_ratio,
        project_count=len(screens),
        screens=screens,
        summary=summary,
        generated_at=utc_now(),
    )


def hsip_fact_blocks(
    result: HsipResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for the HSIP screen and portfolio summary."""
    blocks: list[dict[str, Any]] = []
    artifact_refs = [{"path": str(source_path), "type": "table"}]

    for screen in result.screens:
        bc_text = (
            f"B/C {screen.benefit_cost_ratio:.2f}"
            if screen.benefit_cost_ratio is not None
            else "B/C not yet supplied"
        )
        claim = (
            f"Per FHWA HSIP Manual Chapter 3, candidate project "
            f"`{screen.project_id}` ({screen.name}) — {bc_text} versus the "
            f"lead-agency minimum of {result.min_bc_ratio:.2f}; screen status: "
            f"{screen.screen_status}; proven countermeasure: "
            f"{'yes' if screen.proven_countermeasure else 'no'}."
        )
        block = {
            "fact_id": f"hsip-screen-{screen.project_id}",
            "fact_type": "hsip_project_screen",
            "project_id": screen.project_id,
            "claim_text": claim,
            "method_ref": "planner_pack.hsip",
            "artifact_refs": artifact_refs,
            "cycle_year": result.cycle_year,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    if result.summary is not None:
        summary = result.summary
        mean_bc = (
            f"{summary.mean_benefit_cost_ratio:.2f}"
            if summary.mean_benefit_cost_ratio is not None
            else "n/a"
        )
        claim = (
            f"HSIP {result.cycle_label} portfolio: {summary.project_count} "
            f"candidate(s), {summary.overlay_supplied_count} with overlay data, "
            f"{summary.bc_ratio_passes_count} clearing the "
            f"{result.min_bc_ratio:.2f} B/C minimum, "
            f"{summary.proven_countermeasure_count} using an FHWA proven "
            f"countermeasure; mean B/C {mean_bc}."
        )
        block = {
            "fact_id": f"hsip-portfolio-{result.run_id}",
            "fact_type": "hsip_portfolio_summary",
            "claim_text": claim,
            "method_ref": "planner_pack.hsip",
            "artifact_refs": artifact_refs,
            "cycle_year": result.cycle_year,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    return blocks


def render_hsip_markdown(result: HsipResult, *, run_id: str) -> str:
    """Render the HSIP screen packet as Markdown."""
    template = jinja_env().get_template("hsip.md.j2")
    payload = result.to_json()
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=payload,
        screens=payload["screens"],
        summary=payload["summary"],
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_overlay_rows(workspace: Path, run_root: Path) -> list[dict[str, Any]]:
    """Find an HSIP overlay CSV the lead agency staged for the workspace."""
    for candidate_path in manifest_artifact_paths(
        workspace, run_root, "hsip_overlay_csv"
    ):
        rows = _read_csv(candidate_path)
        if rows:
            return rows
    for candidate in (
        workspace / "inputs" / "hsip_overlay.csv",
        workspace / "inputs" / "processed" / "hsip_overlay.csv",
        workspace / "inputs" / "raw" / "hsip_overlay.csv",
    ):
        rows = _read_csv(candidate)
        if rows:
            return rows
    return []


def write_hsip(
    workspace: Path,
    run_id: str,
    *,
    cycle_year: int,
    cycle_label: str = DEFAULT_CYCLE_LABEL,
    min_bc_ratio: float = DEFAULT_MIN_BC_RATIO,
) -> dict[str, Any]:
    """Compute HSIP screens, append fact_blocks, render the packet, return paths."""
    run_root = workspace / "runs" / run_id
    if not run_root.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} does not exist under {workspace}."
        )
    score_path = run_root / "outputs" / "tables" / "project_scores.csv"
    if not score_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no project_scores.csv; run a workflow first."
        )

    score_rows = _read_csv(score_path)
    if not score_rows:
        raise InsufficientDataError(
            f"Run {run_id!r} project_scores.csv has no rows."
        )
    overlay_rows = _resolve_overlay_rows(workspace, run_root)

    result = compute_hsip(
        score_rows,
        run_id=run_id,
        cycle_year=cycle_year,
        cycle_label=cycle_label,
        min_bc_ratio=min_bc_ratio,
        overlay_rows=overlay_rows,
    )

    hsip_csv_path = run_root / "outputs" / "tables" / "hsip.csv"
    hsip_json_path = run_root / "outputs" / "tables" / "hsip.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_hsip.md"

    hsip_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with hsip_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "total_score",
                "sensitivity_flag",
                "crash_history_5yr",
                "fatal_serious_5yr",
                "systemic_risk_score",
                "benefit_cost_ratio",
                "proven_countermeasure",
                "proven_countermeasure_citation",
                "overlay_supplied",
                "bc_ratio_passes",
                "screen_status",
                "data_source_ref",
            ],
        )
        writer.writeheader()
        for screen in result.screens:
            writer.writerow(asdict(screen))

    write_json(hsip_json_path, result.to_json())

    new_blocks = hsip_fact_blocks(result, hsip_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_hsip_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    summary_json = asdict(result.summary) if result.summary is not None else None
    return {
        "report_path": str(report_path),
        "csv_path": str(hsip_csv_path),
        "json_path": str(hsip_json_path),
        "fact_block_count": appended,
        "project_count": result.project_count,
        "cycle_year": cycle_year,
        "cycle_label": cycle_label,
        "min_bc_ratio": min_bc_ratio,
        "overlay_supplied_count": (
            summary_json["overlay_supplied_count"] if summary_json else 0
        ),
        "bc_ratio_passes_count": (
            summary_json["bc_ratio_passes_count"] if summary_json else 0
        ),
        "proven_countermeasure_count": (
            summary_json["proven_countermeasure_count"] if summary_json else 0
        ),
        "summary": summary_json,
    }
