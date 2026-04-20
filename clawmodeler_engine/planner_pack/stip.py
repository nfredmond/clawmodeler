"""State Transportation Improvement Program (STIP) programming packet.

The STIP (Streets and Highways Code §§14525-14529.11; CTC STIP
Guidelines) is California's four-year programming document for the
Regional Improvement Program (RIP, 75% share) and the Interregional
Improvement Program (IIP, 25% share). Every two years the California
Transportation Commission (CTC) adopts a fresh STIP; each RTPA nominates
the Regional Improvement Program projects for its county share, and
Caltrans nominates the Interregional Improvement Program projects. S&HC
§188 further requires that 40% of STIP capacity flow to the 10-county
northern region and 60% to the 12-county southern region.

Every programming row the RTPA nominates carries a project phase
(PA&ED, PS&E, R/W, CON), a fiscal year (e.g. ``2026-27``), a cost in
thousands of dollars, a funding source (``RIP``, ``IIP``, ``SB1``, etc.),
and — where one has been assigned — a Caltrans PPNO (project programming
number).

This module reads a finished ClawModeler run's ``project_scores.csv``
together with an optional ``stip_overlay.csv`` sidecar a lead agency
stages in long format — one row per ``(project_id, phase, fiscal_year)``
— and produces the CTC cycle packet: per-row programming entries, a
portfolio summary grouping costs by fiscal year and funding source, and
an N/S split table scored against the 40/60 S&HC §188 target.

ClawModeler does not synthesize STIP inputs. When the sidecar is absent
each project is reported as ``not yet programmed``; no dollar figures
are invented.

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

ALLOWED_PHASES: tuple[str, ...] = ("PA&ED", "PS&E", "R/W", "CON", "other")
_PHASE_ALIASES: dict[str, str] = {
    "paed": "PA&ED",
    "pae": "PA&ED",
    "pa&ed": "PA&ED",
    "pse": "PS&E",
    "pse&e": "PS&E",
    "ps&e": "PS&E",
    "rw": "R/W",
    "r/w": "R/W",
    "row": "R/W",
    "rightofway": "R/W",
    "con": "CON",
    "construction": "CON",
    "other": "other",
}
ALLOWED_REGIONS: tuple[str, ...] = ("north", "south")
TARGET_NORTH_SHARE: float = 0.40
TARGET_SOUTH_SHARE: float = 0.60
DEFAULT_CYCLE_LABEL: str = "2026 STIP"
DEFAULT_FUNDING_SOURCE: str = "Funding source to be provided"
DEFAULT_FISCAL_YEAR: str = "Fiscal year to be provided"


@dataclass
class StipProgrammingRow:
    project_id: str
    name: str
    total_score: float
    sensitivity_flag: str
    phase: str
    fiscal_year: str
    cost_thousands: float
    funding_source: str
    ppno: str | None
    region: str | None
    overlay_supplied: bool
    data_source_ref: str


@dataclass
class StipPortfolioSummary:
    cycle_label: str
    project_count: int
    programming_row_count: int
    overlay_supplied_project_count: int
    fiscal_years: list[str]
    total_cost_thousands_by_fiscal_year: dict[str, float]
    total_cost_thousands_by_funding_source: dict[str, float]
    north_south_split: dict[str, Any]


@dataclass
class StipResult:
    run_id: str
    cycle_label: str
    region_filter: str | None
    project_count: int
    programming_rows: list[StipProgrammingRow] = field(default_factory=list)
    summary: StipPortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "cycle_label": self.cycle_label,
            "region_filter": self.region_filter,
            "project_count": self.project_count,
            "generated_at": self.generated_at,
            "programming_rows": [asdict(r) for r in self.programming_rows],
            "summary": asdict(self.summary) if self.summary is not None else None,
        }


def _normalize_phase(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "").replace("-", "")
    if not text:
        return None
    if text in _PHASE_ALIASES:
        return _PHASE_ALIASES[text]
    collapsed = text.replace("&", "").replace("/", "")
    for key, phase in _PHASE_ALIASES.items():
        if key.replace("&", "").replace("/", "") == collapsed:
            return phase
    return None


def _normalize_region(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in ALLOWED_REGIONS:
        return text
    return None


def _resolve_region_filter(region: str | None) -> str | None:
    if region is None:
        return None
    normalized = _normalize_region(region)
    if normalized is None:
        raise ValueError(
            f"Unrecognized STIP region: {region!r}. Allowed values: "
            f"{', '.join(ALLOWED_REGIONS)}."
        )
    return normalized


def compute_stip(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    cycle_label: str,
    region: str | None = None,
    overlay_rows: list[dict[str, Any]] | None = None,
) -> StipResult:
    """Build STIP programming rows from scores + optional overlay.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict.
    ``overlay_rows`` is an optional long-format sidecar: one row per
    ``(project_id, phase, fiscal_year)`` with ``cost_thousands``,
    ``funding_source``, ``ppno``, ``region``, and ``data_source_ref``.
    When the overlay is absent the result reports ``project_count`` but
    no programming rows (no STIP dollars are synthesized).
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before "
            "generating the STIP packet."
        )
    if not cycle_label or not str(cycle_label).strip():
        raise ValueError("cycle_label must be a non-empty string.")

    region_filter = _resolve_region_filter(region)

    score_by_id: dict[str, dict[str, Any]] = {}
    for row in score_rows:
        pid = coerce_str(row.get("project_id"))
        if pid and pid not in score_by_id:
            score_by_id[pid] = row
    if not score_by_id:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    programming_rows: list[StipProgrammingRow] = []
    overlay_project_ids: set[str] = set()
    totals_by_fy: dict[str, float] = {}
    totals_by_source: dict[str, float] = {}
    north_cost = 0.0
    south_cost = 0.0

    for raw in overlay_rows or []:
        pid = coerce_str(raw.get("project_id"))
        if not pid or pid not in score_by_id:
            continue
        phase = _normalize_phase(raw.get("phase"))
        if phase is None:
            raise ValueError(
                f"Unrecognized STIP phase for project {pid!r}: "
                f"{raw.get('phase')!r}. Allowed values: "
                f"{', '.join(ALLOWED_PHASES)}."
            )
        cost = parse_optional_float(raw.get("cost_thousands"))
        if cost is None or cost < 0:
            continue

        fiscal_year = coerce_str(raw.get("fiscal_year"), DEFAULT_FISCAL_YEAR)
        funding_source = coerce_str(
            raw.get("funding_source"), DEFAULT_FUNDING_SOURCE
        )
        ppno_raw = coerce_str(raw.get("ppno"))
        ppno = ppno_raw or None
        row_region = _normalize_region(raw.get("region"))

        if region_filter is not None and row_region not in (None, region_filter):
            continue

        overlay_project_ids.add(pid)
        score_row = score_by_id[pid]
        source = coerce_str(
            raw.get("data_source_ref"),
            "STIP programming source to be provided by lead agency.",
        )

        totals_by_fy[fiscal_year] = totals_by_fy.get(fiscal_year, 0.0) + cost
        totals_by_source[funding_source] = (
            totals_by_source.get(funding_source, 0.0) + cost
        )
        if row_region == "north":
            north_cost += cost
        elif row_region == "south":
            south_cost += cost

        programming_rows.append(
            StipProgrammingRow(
                project_id=pid,
                name=coerce_str(score_row.get("name"), pid),
                total_score=round(
                    parse_optional_float(score_row.get("total_score")) or 0.0,
                    3,
                ),
                sensitivity_flag=coerce_str(
                    score_row.get("sensitivity_flag"), "UNKNOWN"
                ),
                phase=phase,
                fiscal_year=fiscal_year,
                cost_thousands=round(cost, 2),
                funding_source=funding_source,
                ppno=ppno,
                region=row_region,
                overlay_supplied=True,
                data_source_ref=source,
            )
        )

    programming_rows.sort(
        key=lambda r: (r.fiscal_year, r.phase, r.project_id)
    )

    fiscal_years = sorted(totals_by_fy.keys())
    ns_total = north_cost + south_cost
    if ns_total > 0:
        north_share = north_cost / ns_total
        south_share = south_cost / ns_total
        meets_target = (
            abs(north_share - TARGET_NORTH_SHARE) <= 0.05
            and abs(south_share - TARGET_SOUTH_SHARE) <= 0.05
        )
        ns_notes = (
            "S&HC §188 targets 40% north / 60% south statewide; a ±5% "
            "tolerance is applied here for cycle-level reporting."
        )
    else:
        north_share = 0.0
        south_share = 0.0
        meets_target = False
        ns_notes = (
            "No overlay rows carried a north/south region designation; "
            "S&HC §188 split is not yet evaluated."
        )

    split = {
        "north_cost_thousands": round(north_cost, 2),
        "south_cost_thousands": round(south_cost, 2),
        "north_share": round(north_share, 4),
        "south_share": round(south_share, 4),
        "target_north_share": TARGET_NORTH_SHARE,
        "target_south_share": TARGET_SOUTH_SHARE,
        "meets_target": meets_target,
        "notes": ns_notes,
    }

    summary = StipPortfolioSummary(
        cycle_label=str(cycle_label).strip(),
        project_count=len(score_by_id),
        programming_row_count=len(programming_rows),
        overlay_supplied_project_count=len(overlay_project_ids),
        fiscal_years=fiscal_years,
        total_cost_thousands_by_fiscal_year={
            fy: round(v, 2) for fy, v in sorted(totals_by_fy.items())
        },
        total_cost_thousands_by_funding_source={
            src: round(v, 2) for src, v in sorted(totals_by_source.items())
        },
        north_south_split=split,
    )

    return StipResult(
        run_id=run_id,
        cycle_label=str(cycle_label).strip(),
        region_filter=region_filter,
        project_count=len(score_by_id),
        programming_rows=programming_rows,
        summary=summary,
        generated_at=utc_now(),
    )


def stip_fact_blocks(
    result: StipResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for the STIP programming rows and summary."""
    blocks: list[dict[str, Any]] = []
    artifact_refs = [{"path": str(source_path), "type": "table"}]

    for row in result.programming_rows:
        ppno_text = f"PPNO {row.ppno}" if row.ppno else "PPNO not yet assigned"
        region_text = (
            f"{row.region} region"
            if row.region in ALLOWED_REGIONS
            else "region not recorded"
        )
        claim = (
            f"Per the CTC {result.cycle_label} STIP Guidelines (S&HC §§14525-"
            f"14529.11), candidate project `{row.project_id}` ({row.name}) is "
            f"programmed for {row.phase} in FY {row.fiscal_year} at "
            f"${row.cost_thousands:,.0f}K from {row.funding_source} "
            f"({region_text}; {ppno_text})."
        )
        block = {
            "fact_id": (
                f"stip-row-{row.project_id}-{row.phase}-{row.fiscal_year}"
            ),
            "fact_type": "stip_programming_row",
            "project_id": row.project_id,
            "phase": row.phase,
            "fiscal_year": row.fiscal_year,
            "claim_text": claim,
            "method_ref": "planner_pack.stip",
            "artifact_refs": artifact_refs,
            "cycle_label": result.cycle_label,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    if result.summary is not None:
        summary = result.summary
        split = summary.north_south_split
        fy_text = ", ".join(
            f"FY {fy} ${summary.total_cost_thousands_by_fiscal_year[fy]:,.0f}K"
            for fy in summary.fiscal_years
        ) or "no fiscal years in scope"
        split_text = (
            f"north {split['north_share']*100:.1f}% / "
            f"south {split['south_share']*100:.1f}% "
            f"({'meets' if split['meets_target'] else 'does not yet meet'} "
            f"S&HC §188 40/60 target)"
        )
        claim = (
            f"STIP {result.cycle_label} portfolio: {summary.project_count} "
            f"candidate(s), {summary.overlay_supplied_project_count} with "
            f"programming data; fiscal-year totals: {fy_text}; N/S split: "
            f"{split_text}."
        )
        block = {
            "fact_id": f"stip-portfolio-{result.run_id}",
            "fact_type": "stip_portfolio_summary",
            "claim_text": claim,
            "method_ref": "planner_pack.stip",
            "artifact_refs": artifact_refs,
            "cycle_label": result.cycle_label,
        }
        validate_fact_block_shape(block)
        blocks.append(block)

    return blocks


def render_stip_markdown(result: StipResult, *, run_id: str) -> str:
    """Render the STIP cycle packet as Markdown."""
    template = jinja_env().get_template("stip.md.j2")
    payload = result.to_json()
    summary = payload["summary"] or {}
    fy_rows = [
        {"fiscal_year": fy, "total_cost_thousands": cost}
        for fy, cost in sorted(
            summary.get("total_cost_thousands_by_fiscal_year", {}).items()
        )
    ]
    source_rows = [
        {"funding_source": src, "total_cost_thousands": cost}
        for src, cost in sorted(
            summary.get("total_cost_thousands_by_funding_source", {}).items()
        )
    ]
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=payload,
        programming_rows=payload["programming_rows"],
        summary=summary,
        fiscal_year_rows=fy_rows,
        funding_source_rows=source_rows,
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_overlay_rows(workspace: Path, run_root: Path) -> list[dict[str, Any]]:
    """Find a STIP overlay CSV the lead agency staged for the workspace."""
    for candidate_path in manifest_artifact_paths(
        workspace, run_root, "stip_overlay_csv"
    ):
        rows = _read_csv(candidate_path)
        if rows:
            return rows
    for candidate in (
        workspace / "inputs" / "stip_overlay.csv",
        workspace / "inputs" / "processed" / "stip_overlay.csv",
        workspace / "inputs" / "raw" / "stip_overlay.csv",
    ):
        rows = _read_csv(candidate)
        if rows:
            return rows
    return []


def write_stip(
    workspace: Path,
    run_id: str,
    *,
    cycle_label: str = DEFAULT_CYCLE_LABEL,
    region: str | None = None,
) -> dict[str, Any]:
    """Compute STIP programming rows, append fact_blocks, render the packet."""
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

    result = compute_stip(
        score_rows,
        run_id=run_id,
        cycle_label=cycle_label,
        region=region,
        overlay_rows=overlay_rows,
    )

    stip_csv_path = run_root / "outputs" / "tables" / "stip.csv"
    stip_json_path = run_root / "outputs" / "tables" / "stip.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_stip.md"

    stip_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with stip_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "total_score",
                "sensitivity_flag",
                "phase",
                "fiscal_year",
                "cost_thousands",
                "funding_source",
                "ppno",
                "region",
                "overlay_supplied",
                "data_source_ref",
            ],
        )
        writer.writeheader()
        for row in result.programming_rows:
            writer.writerow(asdict(row))

    write_json(stip_json_path, result.to_json())

    new_blocks = stip_fact_blocks(result, stip_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_stip_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    summary_json = asdict(result.summary) if result.summary is not None else None
    return {
        "report_path": str(report_path),
        "csv_path": str(stip_csv_path),
        "json_path": str(stip_json_path),
        "fact_block_count": appended,
        "project_count": result.project_count,
        "programming_row_count": len(result.programming_rows),
        "cycle_label": result.cycle_label,
        "region_filter": result.region_filter,
        "overlay_supplied_project_count": (
            summary_json["overlay_supplied_project_count"]
            if summary_json
            else 0
        ),
        "fiscal_years": list(summary_json["fiscal_years"]) if summary_json else [],
        "total_cost_thousands_by_fiscal_year": (
            summary_json["total_cost_thousands_by_fiscal_year"]
            if summary_json
            else {}
        ),
        "north_south_split": (
            summary_json["north_south_split"] if summary_json else {}
        ),
        "summary": summary_json,
    }
