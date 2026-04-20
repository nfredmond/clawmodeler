"""Congestion Mitigation and Air Quality (CMAQ) emissions-reduction screen.

The Congestion Mitigation and Air Quality Improvement Program (CMAQ,
23 USC 149) is the primary federal funding source for transportation
projects that reduce criteria-pollutant emissions in nonattainment and
maintenance areas. The FHWA *CMAQ Reference Guide* (current edition)
governs eligibility and reporting: every application must attach a
defensible per-pollutant emissions-reduction estimate (kilograms per
day) plus a cost-effectiveness value (USD per kilogram reduced),
grouped by the Reference Guide's eligibility categories.

This module reads a finished ClawModeler run's ``project_scores.csv``
together with an optional ``cmaq_overlay.csv`` sidecar a lead agency
stages in long format — one row per (project, pollutant) with
``kg_per_day_reduced``, ``cost_effectiveness_usd_per_kg``,
``eligibility_category``, ``nonattainment_area``, and
``data_source_ref``. It produces per-estimate records, a portfolio
summary aggregating kilograms per day by pollutant, and a lead-agency
cycle packet ready for CMAQ cycle submission.

ClawModeler does not synthesize CMAQ inputs. When the sidecar is
absent the run is reported as *overlay not yet supplied*; the projects
are screened only for eligibility-category placement if the overlay
lists them, otherwise they are marked ``not yet screened``.

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

ALLOWED_POLLUTANTS: tuple[str, ...] = ("pm2_5", "pm10", "nox", "voc", "co")
POLLUTANT_LABELS: dict[str, str] = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "nox": "NOx",
    "voc": "VOC",
    "co": "CO",
}
DEFAULT_NONATTAINMENT_AREA = "Nonattainment area to be provided"
DEFAULT_ELIGIBILITY_CATEGORY = "Eligibility category to be provided"


@dataclass
class CmaqEmissionsEstimate:
    project_id: str
    name: str
    total_score: float
    sensitivity_flag: str
    pollutant: str
    kg_per_day_reduced: float
    cost_effectiveness_usd_per_kg: float | None
    eligibility_category: str
    nonattainment_area: str
    overlay_supplied: bool
    data_source_ref: str


@dataclass
class CmaqPortfolioSummary:
    project_count: int
    estimate_count: int
    overlay_supplied_project_count: int
    total_kg_per_day_by_pollutant: dict[str, float]
    mean_cost_effectiveness_usd_per_kg_by_pollutant: dict[str, float | None]
    eligibility_categories: list[str]


@dataclass
class CmaqResult:
    run_id: str
    analysis_year: int
    pollutants: list[str]
    project_count: int
    estimates: list[CmaqEmissionsEstimate] = field(default_factory=list)
    summary: CmaqPortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "analysis_year": self.analysis_year,
            "pollutants": list(self.pollutants),
            "project_count": self.project_count,
            "generated_at": self.generated_at,
            "estimates": [asdict(e) for e in self.estimates],
            "summary": asdict(self.summary) if self.summary is not None else None,
        }


def _normalize_pollutant(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "").replace("-", "").replace(".", "")
    if not text:
        return None
    mapping = {
        "pm25": "pm2_5",
        "pm2_5": "pm2_5",
        "pm2point5": "pm2_5",
        "pm10": "pm10",
        "nox": "nox",
        "voc": "voc",
        "co": "co",
    }
    return mapping.get(text)


def _resolve_pollutant_filter(pollutants: list[str] | None) -> list[str]:
    if not pollutants:
        return list(ALLOWED_POLLUTANTS)
    selected: list[str] = []
    for raw in pollutants:
        normalized = _normalize_pollutant(raw)
        if normalized is None:
            raise ValueError(
                f"Unrecognized CMAQ pollutant: {raw!r}. Allowed values: "
                f"{', '.join(ALLOWED_POLLUTANTS)}."
            )
        if normalized not in selected:
            selected.append(normalized)
    return selected


def compute_cmaq(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    analysis_year: int,
    pollutants: list[str] | None = None,
    overlay_rows: list[dict[str, Any]] | None = None,
) -> CmaqResult:
    """Build CMAQ emissions-reduction estimates from scores + optional overlay.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict.
    ``overlay_rows`` is an optional long-format sidecar: one row per
    ``(project_id, pollutant)`` with ``kg_per_day_reduced``,
    ``cost_effectiveness_usd_per_kg``, ``eligibility_category``,
    ``nonattainment_area``, and ``data_source_ref``. When the overlay is
    absent the result reports ``project_count`` but no estimates (no
    CMAQ kilograms are synthesized).
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before "
            "generating the CMAQ screen."
        )
    if analysis_year <= 0:
        raise ValueError("analysis_year must be a positive integer.")

    selected_pollutants = _resolve_pollutant_filter(pollutants)

    score_by_id: dict[str, dict[str, Any]] = {}
    for row in score_rows:
        pid = coerce_str(row.get("project_id"))
        if pid and pid not in score_by_id:
            score_by_id[pid] = row
    if not score_by_id:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    estimates: list[CmaqEmissionsEstimate] = []
    overlay_project_ids: set[str] = set()
    totals_kg: dict[str, float] = {p: 0.0 for p in selected_pollutants}
    cost_values: dict[str, list[float]] = {p: [] for p in selected_pollutants}
    categories: list[str] = []

    for raw in overlay_rows or []:
        pid = coerce_str(raw.get("project_id"))
        if not pid or pid not in score_by_id:
            continue
        pollutant = _normalize_pollutant(raw.get("pollutant"))
        if pollutant is None or pollutant not in selected_pollutants:
            continue
        kg = parse_optional_float(raw.get("kg_per_day_reduced"))
        if kg is None or kg < 0:
            continue

        overlay_project_ids.add(pid)
        score_row = score_by_id[pid]
        cost = parse_optional_float(raw.get("cost_effectiveness_usd_per_kg"))
        eligibility = coerce_str(
            raw.get("eligibility_category"), DEFAULT_ELIGIBILITY_CATEGORY
        )
        area = coerce_str(
            raw.get("nonattainment_area"), DEFAULT_NONATTAINMENT_AREA
        )
        source = coerce_str(
            raw.get("data_source_ref"),
            "CMAQ emissions data source to be provided by lead agency.",
        )

        totals_kg[pollutant] += kg
        if cost is not None:
            cost_values[pollutant].append(cost)
        if eligibility not in categories:
            categories.append(eligibility)

        estimates.append(
            CmaqEmissionsEstimate(
                project_id=pid,
                name=coerce_str(score_row.get("name"), pid),
                total_score=round(
                    parse_optional_float(score_row.get("total_score")) or 0.0,
                    3,
                ),
                sensitivity_flag=coerce_str(
                    score_row.get("sensitivity_flag"), "UNKNOWN"
                ),
                pollutant=pollutant,
                kg_per_day_reduced=round(kg, 3),
                cost_effectiveness_usd_per_kg=(
                    round(cost, 2) if cost is not None else None
                ),
                eligibility_category=eligibility,
                nonattainment_area=area,
                overlay_supplied=True,
                data_source_ref=source,
            )
        )

    summary = CmaqPortfolioSummary(
        project_count=len(score_by_id),
        estimate_count=len(estimates),
        overlay_supplied_project_count=len(overlay_project_ids),
        total_kg_per_day_by_pollutant={
            p: round(totals_kg[p], 3) for p in selected_pollutants
        },
        mean_cost_effectiveness_usd_per_kg_by_pollutant={
            p: (
                round(sum(cost_values[p]) / len(cost_values[p]), 2)
                if cost_values[p]
                else None
            )
            for p in selected_pollutants
        },
        eligibility_categories=categories,
    )

    return CmaqResult(
        run_id=run_id,
        analysis_year=analysis_year,
        pollutants=selected_pollutants,
        project_count=len(score_by_id),
        estimates=estimates,
        summary=summary,
        generated_at=utc_now(),
    )


def cmaq_fact_blocks(
    result: CmaqResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for the CMAQ estimates and portfolio summary."""
    blocks: list[dict[str, Any]] = []
    artifact_refs = [{"path": str(source_path), "type": "table"}]

    for estimate in result.estimates:
        cost_text = (
            f"{estimate.cost_effectiveness_usd_per_kg:.2f} USD/kg"
            if estimate.cost_effectiveness_usd_per_kg is not None
            else "cost-effectiveness not yet supplied"
        )
        pollutant_label = POLLUTANT_LABELS.get(estimate.pollutant, estimate.pollutant)
        claim = (
            f"Per the FHWA CMAQ Reference Guide (23 USC 149), candidate "
            f"project `{estimate.project_id}` ({estimate.name}) is estimated "
            f"to reduce {estimate.kg_per_day_reduced:.3f} kg/day of "
            f"{pollutant_label} in {estimate.nonattainment_area}; "
            f"eligibility category: {estimate.eligibility_category}; "
            f"cost-effectiveness: {cost_text}."
        )
        block = {
            "fact_id": (
                f"cmaq-estimate-{estimate.project_id}-{estimate.pollutant}"
            ),
            "fact_type": "cmaq_emissions_estimate",
            "project_id": estimate.project_id,
            "pollutant": estimate.pollutant,
            "claim_text": claim,
            "method_ref": "planner_pack.cmaq",
            "artifact_refs": artifact_refs,
            "analysis_year": result.analysis_year,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    if result.summary is not None:
        summary = result.summary
        totals_text = ", ".join(
            f"{POLLUTANT_LABELS.get(p, p)} {summary.total_kg_per_day_by_pollutant[p]:.3f} kg/day"
            for p in result.pollutants
        ) or "no pollutants in scope"
        claim = (
            f"CMAQ analysis year {result.analysis_year} portfolio: "
            f"{summary.project_count} candidate(s), "
            f"{summary.overlay_supplied_project_count} with overlay data; "
            f"pollutant totals: {totals_text}."
        )
        block = {
            "fact_id": f"cmaq-portfolio-{result.run_id}",
            "fact_type": "cmaq_portfolio_summary",
            "claim_text": claim,
            "method_ref": "planner_pack.cmaq",
            "artifact_refs": artifact_refs,
            "analysis_year": result.analysis_year,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    return blocks


def render_cmaq_markdown(result: CmaqResult, *, run_id: str) -> str:
    """Render the CMAQ cycle packet as Markdown."""
    template = jinja_env().get_template("cmaq.md.j2")
    payload = result.to_json()
    pollutant_rows = [
        {
            "pollutant": p,
            "label": POLLUTANT_LABELS.get(p, p),
            "total_kg_per_day": payload["summary"][
                "total_kg_per_day_by_pollutant"
            ].get(p, 0.0) if payload["summary"] else 0.0,
            "mean_cost_effectiveness_usd_per_kg": (
                payload["summary"][
                    "mean_cost_effectiveness_usd_per_kg_by_pollutant"
                ].get(p)
                if payload["summary"]
                else None
            ),
        }
        for p in payload["pollutants"]
    ]
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=payload,
        estimates=payload["estimates"],
        summary=payload["summary"],
        pollutant_rows=pollutant_rows,
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_overlay_rows(workspace: Path, run_root: Path) -> list[dict[str, Any]]:
    """Find a CMAQ overlay CSV the lead agency staged for the workspace."""
    for candidate_path in manifest_artifact_paths(
        workspace, run_root, "cmaq_overlay_csv"
    ):
        rows = _read_csv(candidate_path)
        if rows:
            return rows
    for candidate in (
        workspace / "inputs" / "cmaq_overlay.csv",
        workspace / "inputs" / "processed" / "cmaq_overlay.csv",
        workspace / "inputs" / "raw" / "cmaq_overlay.csv",
    ):
        rows = _read_csv(candidate)
        if rows:
            return rows
    return []


def write_cmaq(
    workspace: Path,
    run_id: str,
    *,
    analysis_year: int,
    pollutants: list[str] | None = None,
) -> dict[str, Any]:
    """Compute CMAQ estimates, append fact_blocks, render the packet, return paths."""
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

    result = compute_cmaq(
        score_rows,
        run_id=run_id,
        analysis_year=analysis_year,
        pollutants=pollutants,
        overlay_rows=overlay_rows,
    )

    cmaq_csv_path = run_root / "outputs" / "tables" / "cmaq.csv"
    cmaq_json_path = run_root / "outputs" / "tables" / "cmaq.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_cmaq.md"

    cmaq_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with cmaq_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "total_score",
                "sensitivity_flag",
                "pollutant",
                "kg_per_day_reduced",
                "cost_effectiveness_usd_per_kg",
                "eligibility_category",
                "nonattainment_area",
                "overlay_supplied",
                "data_source_ref",
            ],
        )
        writer.writeheader()
        for estimate in result.estimates:
            writer.writerow(asdict(estimate))

    write_json(cmaq_json_path, result.to_json())

    new_blocks = cmaq_fact_blocks(result, cmaq_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_cmaq_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    summary_json = asdict(result.summary) if result.summary is not None else None
    return {
        "report_path": str(report_path),
        "csv_path": str(cmaq_csv_path),
        "json_path": str(cmaq_json_path),
        "fact_block_count": appended,
        "project_count": result.project_count,
        "estimate_count": len(result.estimates),
        "analysis_year": analysis_year,
        "pollutants": list(result.pollutants),
        "overlay_supplied_project_count": (
            summary_json["overlay_supplied_project_count"]
            if summary_json
            else 0
        ),
        "total_kg_per_day_by_pollutant": (
            summary_json["total_kg_per_day_by_pollutant"] if summary_json else {}
        ),
        "summary": summary_json,
    }
