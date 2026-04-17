"""Caltrans LAPM project programming exhibits.

The California Department of Transportation's *Local Assistance Procedures
Manual* (LAPM) governs how local agencies administer federal-aid and
state-funded transportation projects. Chapter 3 (Project Authorization)
and Chapter 7 (Field Review) both reference a *project programming fact
sheet* as the canonical summary exhibit that a lead agency prepares for
each candidate project — identifiers, location, description, estimated
phase costs, schedule, and anticipated benefits.

ClawModeler does not know most of the administrative fields on that
exhibit (district, county, PM begin/end, funding sources, dates), so this
module is honest about what it can populate from a run and what the lead
agency must still provide. It pulls project identifiers, names, and the
four-dimension screening scores (safety, equity, climate, feasibility)
from a finished run's ``project_scores.csv`` and emits, per project, a
Markdown programming fact sheet plus a ``lapm_programming_exhibit``
fact_block so downstream narrative and chat turns remain grounded.

This module does not call an LLM. Every field is either read from the
run's outputs or clearly labeled as a lead-agency placeholder.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..report import read_fact_blocks
from ..workspace import ENGINE_VERSION, InsufficientDataError, utc_now, write_json

DEFAULT_LEAD_AGENCY = "Lead agency to be provided"
DEFAULT_DISTRICT = "District to be provided by lead agency"


@dataclass
class LapmProgrammingExhibit:
    project_id: str
    name: str
    lead_agency: str
    district: str
    safety_score: float
    equity_score: float
    climate_score: float
    feasibility_score: float
    total_score: float
    sensitivity_flag: str
    location_note: str
    description: str
    estimated_cost_usd: float | None
    project_type: str
    schedule_note: str


@dataclass
class LapmExhibitResult:
    run_id: str
    lead_agency: str
    district: str
    project_count: int
    exhibits: list[LapmProgrammingExhibit] = field(default_factory=list)
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "lead_agency": self.lead_agency,
            "district": self.district,
            "project_count": self.project_count,
            "generated_at": self.generated_at,
            "exhibits": [asdict(e) for e in self.exhibits],
        }


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any, default: str = "") -> str:
    if value in (None, ""):
        return default
    return str(value).strip() or default


def compute_lapm_exhibit(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    lead_agency: str = DEFAULT_LEAD_AGENCY,
    district: str = DEFAULT_DISTRICT,
    project_rows: list[dict[str, Any]] | None = None,
) -> LapmExhibitResult:
    """Build LAPM programming exhibits from project scores.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict
    (``csv.DictReader`` output). ``project_rows`` is an optional sidecar
    of the candidate-projects CSV, keyed by ``project_id``, used to
    enrich each exhibit with lat/lon, cost, description, and project
    type when the lead agency supplied them.
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before generating "
            "LAPM exhibits."
        )

    project_by_id: dict[str, dict[str, Any]] = {}
    for row in project_rows or []:
        project_id = _coerce_str(row.get("project_id"))
        if project_id:
            project_by_id[project_id] = row

    exhibits: list[LapmProgrammingExhibit] = []
    for row in score_rows:
        project_id = _coerce_str(row.get("project_id"))
        if not project_id:
            continue
        sidecar = project_by_id.get(project_id, {})
        lat = _parse_optional_float(sidecar.get("lat"))
        lon = _parse_optional_float(sidecar.get("lon"))
        if lat is not None and lon is not None:
            location_note = f"{lat:.5f}, {lon:.5f}"
        else:
            location_note = "Location to be provided by lead agency"
        description = _coerce_str(
            sidecar.get("description"),
            "Project description to be provided by lead agency.",
        )
        project_type = _coerce_str(
            sidecar.get("project_type"),
            "Project type to be provided by lead agency",
        )
        schedule_note = _coerce_str(
            sidecar.get("schedule"),
            "PA&ED, PS&E, R/W, and CON schedule to be provided by lead agency",
        )
        estimated_cost = _parse_optional_float(sidecar.get("estimated_cost_usd"))
        exhibits.append(
            LapmProgrammingExhibit(
                project_id=project_id,
                name=_coerce_str(row.get("name"), project_id),
                lead_agency=lead_agency,
                district=district,
                safety_score=round(
                    _parse_optional_float(row.get("safety_score")) or 0.0, 3
                ),
                equity_score=round(
                    _parse_optional_float(row.get("equity_score")) or 0.0, 3
                ),
                climate_score=round(
                    _parse_optional_float(row.get("climate_score")) or 0.0, 3
                ),
                feasibility_score=round(
                    _parse_optional_float(row.get("feasibility_score")) or 0.0, 3
                ),
                total_score=round(
                    _parse_optional_float(row.get("total_score")) or 0.0, 3
                ),
                sensitivity_flag=_coerce_str(
                    row.get("sensitivity_flag"), "UNKNOWN"
                ),
                location_note=location_note,
                description=description,
                estimated_cost_usd=estimated_cost,
                project_type=project_type,
                schedule_note=schedule_note,
            )
        )

    if not exhibits:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    return LapmExhibitResult(
        run_id=run_id,
        lead_agency=lead_agency,
        district=district,
        project_count=len(exhibits),
        exhibits=exhibits,
        generated_at=utc_now(),
    )


def lapm_fact_blocks(
    result: LapmExhibitResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for each LAPM programming exhibit."""
    blocks: list[dict[str, Any]] = []
    for exhibit in result.exhibits:
        claim = (
            f"Per Caltrans LAPM Chapter 3, candidate project "
            f"`{exhibit.project_id}` ({exhibit.name}) screens with total score "
            f"{exhibit.total_score:.1f}/100 — safety {exhibit.safety_score:.1f}, "
            f"equity {exhibit.equity_score:.1f}, climate "
            f"{exhibit.climate_score:.1f}, feasibility "
            f"{exhibit.feasibility_score:.1f}; sensitivity flag "
            f"{exhibit.sensitivity_flag}."
        )
        blocks.append(
            {
                "fact_id": f"lapm-programming-{exhibit.project_id}",
                "fact_type": "lapm_programming_exhibit",
                "project_id": exhibit.project_id,
                "claim_text": claim,
                "source_table": str(source_path),
                "source_row": exhibit.project_id,
            }
        )
    return blocks


def render_lapm_markdown(result: LapmExhibitResult, *, run_id: str) -> str:
    """Render the LAPM programming exhibits packet as Markdown."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    templates_dir = Path(__file__).parent.parent / "templates" / "planner_pack"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    template = env.get_template("lapm_exhibit.md.j2")
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=result.to_json(),
        exhibits=[asdict(e) for e in result.exhibits],
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_project_rows(workspace: Path, run_root: Path) -> list[dict[str, Any]]:
    """Find a candidate-projects CSV for enrichment, if the user staged one."""
    manifest_path = run_root / "outputs" / "run_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
        if isinstance(artifacts, dict):
            candidates = artifacts.get("candidate_projects_csv") or []
            for candidate in candidates:
                candidate_path = Path(str(candidate))
                if not candidate_path.is_absolute():
                    candidate_path = workspace / candidate_path
                rows = _read_csv(candidate_path)
                if rows:
                    return rows
    for candidate in (
        workspace / "inputs" / "projects.csv",
        workspace / "inputs" / "processed" / "projects.csv",
        workspace / "inputs" / "raw" / "projects.csv",
    ):
        rows = _read_csv(candidate)
        if rows:
            return rows
    return []


def _append_fact_blocks(path: Path, new_blocks: list[dict[str, Any]]) -> int:
    if not new_blocks:
        return 0
    existing_ids: set[str] = set()
    if path.exists():
        existing_ids = {str(b.get("fact_id")) for b in read_fact_blocks(path)}
    appended = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for block in new_blocks:
            if block["fact_id"] in existing_ids:
                continue
            f.write(json.dumps(block) + "\n")
            appended += 1
    return appended


def write_lapm_exhibit(
    workspace: Path,
    run_id: str,
    *,
    lead_agency: str = DEFAULT_LEAD_AGENCY,
    district: str = DEFAULT_DISTRICT,
) -> dict[str, Any]:
    """Compute LAPM exhibits, append fact_blocks, render packet, return paths."""
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

    project_rows = _resolve_project_rows(workspace, run_root)

    result = compute_lapm_exhibit(
        score_rows,
        run_id=run_id,
        lead_agency=lead_agency,
        district=district,
        project_rows=project_rows,
    )

    lapm_csv_path = run_root / "outputs" / "tables" / "lapm_exhibit.csv"
    lapm_json_path = run_root / "outputs" / "tables" / "lapm_exhibit.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_lapm_exhibit.md"

    lapm_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with lapm_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "lead_agency",
                "district",
                "safety_score",
                "equity_score",
                "climate_score",
                "feasibility_score",
                "total_score",
                "sensitivity_flag",
                "location_note",
                "description",
                "estimated_cost_usd",
                "project_type",
                "schedule_note",
            ],
        )
        writer.writeheader()
        for exhibit in result.exhibits:
            writer.writerow(asdict(exhibit))

    write_json(lapm_json_path, result.to_json())

    new_blocks = lapm_fact_blocks(result, lapm_csv_path)
    appended = _append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_lapm_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "csv_path": str(lapm_csv_path),
        "json_path": str(lapm_json_path),
        "fact_block_count": appended,
        "project_count": result.project_count,
        "lead_agency": lead_agency,
        "district": district,
    }
