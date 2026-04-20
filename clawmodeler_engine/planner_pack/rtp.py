"""Regional Transportation Plan (RTP) chapter generator.

Every California MPO/RTPA adopts a long-range Regional Transportation
Plan on a 4-year cycle per California Government Code §65080 and 23 CFR
450. RTP chapters vary by agency, but the *Projects and Performance*
chapter (often Chapter 5 Action Element + Chapter 6 Performance
Monitoring) is the most direct use of the evidence ClawModeler already
produces: scored projects, scenario VMT, accessibility deltas, and —
when the agency has already generated them — CEQA §15064.3 VMT
determinations and Caltrans LAPM programming exhibits.

This module composes a single *Projects and Performance* RTP chapter
from a finished run's ``project_scores.csv`` and ``vmt_screening.csv``,
enriching it with ``accessibility_delta.csv``, ``ceqa_vmt.csv`` (v0.6.0),
and ``lapm_exhibit.csv`` (v0.6.1) when they are present. The rendered
Markdown is grounded: every claim is mirrored as an
``rtp_chapter_entry`` fact_block against a real scenario or project, so
downstream narrative and chat turns remain subject to the ClawModeler
citation contract.

This module does not call an LLM.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..workspace import ENGINE_VERSION, InsufficientDataError, utc_now, write_json
from .utilities import append_fact_blocks, coerce_str, jinja_env, parse_optional_float

DEFAULT_AGENCY = "Lead agency to be provided"
DEFAULT_RTP_CYCLE = "RTP cycle to be provided"
DEFAULT_CHAPTER_TITLE = "Projects and Performance"


@dataclass
class RtpProjectEntry:
    project_id: str
    name: str
    total_score: float
    sensitivity_flag: str
    lapm_location: str
    lapm_project_type: str
    lapm_estimated_cost_usd: float | None


@dataclass
class RtpScenarioEntry:
    scenario_id: str
    population: float
    daily_vmt: float
    vmt_per_capita: float | None
    accessibility_delta_jobs: float | None
    ceqa_determination: str
    ceqa_threshold_vmt_per_capita: float | None


@dataclass
class RtpChapterResult:
    run_id: str
    agency: str
    rtp_cycle: str
    chapter_title: str
    projects: list[RtpProjectEntry] = field(default_factory=list)
    scenarios: list[RtpScenarioEntry] = field(default_factory=list)
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agency": self.agency,
            "rtp_cycle": self.rtp_cycle,
            "chapter_title": self.chapter_title,
            "generated_at": self.generated_at,
            "projects": [asdict(p) for p in self.projects],
            "scenarios": [asdict(s) for s in self.scenarios],
        }


def compute_rtp_chapter(
    score_rows: list[dict[str, Any]],
    vmt_rows: list[dict[str, Any]],
    *,
    run_id: str,
    agency: str = DEFAULT_AGENCY,
    rtp_cycle: str = DEFAULT_RTP_CYCLE,
    chapter_title: str = DEFAULT_CHAPTER_TITLE,
    delta_rows: list[dict[str, Any]] | None = None,
    ceqa_rows: list[dict[str, Any]] | None = None,
    lapm_rows: list[dict[str, Any]] | None = None,
) -> RtpChapterResult:
    """Compose the RTP *Projects and Performance* chapter.

    ``score_rows`` and ``vmt_rows`` come from the engine's standard
    outputs. ``delta_rows`` / ``ceqa_rows`` / ``lapm_rows`` are optional
    enrichments — when a run has been processed with v0.6.0 or v0.6.1,
    those outputs let the chapter cite concrete CEQA determinations and
    LAPM programming fields instead of placeholder text.
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before generating the "
            "RTP chapter."
        )
    if not vmt_rows:
        raise InsufficientDataError(
            "vmt_screening rows are empty; run a workflow before generating the "
            "RTP chapter."
        )

    lapm_by_id: dict[str, dict[str, Any]] = {}
    for row in lapm_rows or []:
        project_id = coerce_str(row.get("project_id"))
        if project_id:
            lapm_by_id[project_id] = row

    projects: list[RtpProjectEntry] = []
    for row in score_rows:
        project_id = coerce_str(row.get("project_id"))
        if not project_id:
            continue
        lapm = lapm_by_id.get(project_id, {})
        projects.append(
            RtpProjectEntry(
                project_id=project_id,
                name=coerce_str(row.get("name"), project_id),
                total_score=round(
                    parse_optional_float(row.get("total_score")) or 0.0, 3
                ),
                sensitivity_flag=coerce_str(
                    row.get("sensitivity_flag"), "UNKNOWN"
                ),
                lapm_location=coerce_str(
                    lapm.get("location_note"),
                    "Location to be provided in LAPM exhibit",
                ),
                lapm_project_type=coerce_str(
                    lapm.get("project_type"),
                    "Project type to be provided in LAPM exhibit",
                ),
                lapm_estimated_cost_usd=parse_optional_float(
                    lapm.get("estimated_cost_usd")
                ),
            )
        )

    if not projects:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    ceqa_by_scenario: dict[str, dict[str, Any]] = {}
    for row in ceqa_rows or []:
        scenario_id = coerce_str(row.get("scenario_id"))
        if scenario_id:
            ceqa_by_scenario[scenario_id] = row

    delta_by_scenario: dict[str, float] = {}
    for row in delta_rows or []:
        scenario_id = coerce_str(row.get("scenario_id"))
        if not scenario_id:
            continue
        delta_value = parse_optional_float(row.get("delta_jobs_accessible"))
        if delta_value is None:
            continue
        delta_by_scenario[scenario_id] = (
            delta_by_scenario.get(scenario_id, 0.0) + delta_value
        )

    scenarios: list[RtpScenarioEntry] = []
    for row in vmt_rows:
        scenario_id = coerce_str(row.get("scenario_id"))
        if not scenario_id:
            continue
        population = parse_optional_float(row.get("population")) or 0.0
        daily_vmt = parse_optional_float(row.get("daily_vmt")) or 0.0
        vmt_per_capita: float | None
        if population > 0:
            vmt_per_capita = round(daily_vmt / population, 3)
        else:
            vmt_per_capita = None
        ceqa = ceqa_by_scenario.get(scenario_id, {})
        scenarios.append(
            RtpScenarioEntry(
                scenario_id=scenario_id,
                population=round(population, 3),
                daily_vmt=round(daily_vmt, 3),
                vmt_per_capita=vmt_per_capita,
                accessibility_delta_jobs=(
                    round(delta_by_scenario[scenario_id], 3)
                    if scenario_id in delta_by_scenario
                    else None
                ),
                ceqa_determination=coerce_str(
                    ceqa.get("determination"), "not screened"
                ),
                ceqa_threshold_vmt_per_capita=parse_optional_float(
                    ceqa.get("threshold_vmt_per_capita")
                ),
            )
        )

    return RtpChapterResult(
        run_id=run_id,
        agency=agency,
        rtp_cycle=rtp_cycle,
        chapter_title=chapter_title,
        projects=projects,
        scenarios=scenarios,
        generated_at=utc_now(),
    )


def rtp_chapter_fact_blocks(
    result: RtpChapterResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for each project + scenario entry."""
    blocks: list[dict[str, Any]] = []
    for project in result.projects:
        claim = (
            f"Per {result.agency} {result.rtp_cycle} RTP Action Element, project "
            f"`{project.project_id}` ({project.name}) carries a ClawModeler "
            f"total score of {project.total_score:.1f}/100; sensitivity flag "
            f"{project.sensitivity_flag}."
        )
        blocks.append(
            {
                "fact_id": f"rtp-project-{project.project_id}",
                "fact_type": "rtp_chapter_entry",
                "project_id": project.project_id,
                "claim_text": claim,
                "method_ref": "planner_pack.rtp_chapter",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": f"projects.{project.project_id}",
            }
        )
    for scenario in result.scenarios:
        if scenario.vmt_per_capita is not None:
            vmt_phrase = f"{scenario.vmt_per_capita:.1f} VMT per capita"
        else:
            vmt_phrase = "VMT per capita unavailable (zero population)"
        if scenario.ceqa_determination != "not screened":
            ceqa_phrase = (
                f"CEQA §15064.3 determination: {scenario.ceqa_determination}"
            )
        else:
            ceqa_phrase = "CEQA §15064.3 screening not yet run"
        claim = (
            f"Per {result.agency} {result.rtp_cycle} RTP Performance Monitoring, "
            f"scenario `{scenario.scenario_id}` — {vmt_phrase}. {ceqa_phrase}."
        )
        blocks.append(
            {
                "fact_id": f"rtp-scenario-{scenario.scenario_id}",
                "fact_type": "rtp_chapter_entry",
                "scenario_id": scenario.scenario_id,
                "claim_text": claim,
                "method_ref": "planner_pack.rtp_chapter",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": f"scenarios.{scenario.scenario_id}",
            }
        )
    return blocks


def render_rtp_chapter_markdown(result: RtpChapterResult, *, run_id: str) -> str:
    """Render the RTP *Projects and Performance* chapter as Markdown."""
    template = jinja_env().get_template("rtp_chapter.md.j2")
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=result.to_json(),
        projects=[asdict(p) for p in result.projects],
        scenarios=[asdict(s) for s in result.scenarios],
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rtp_chapter(
    workspace: Path,
    run_id: str,
    *,
    agency: str = DEFAULT_AGENCY,
    rtp_cycle: str = DEFAULT_RTP_CYCLE,
    chapter_title: str = DEFAULT_CHAPTER_TITLE,
) -> dict[str, Any]:
    """Compose the RTP chapter, append fact_blocks, render packet, return paths."""
    run_root = workspace / "runs" / run_id
    if not run_root.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} does not exist under {workspace}."
        )
    tables = run_root / "outputs" / "tables"
    score_path = tables / "project_scores.csv"
    vmt_path = tables / "vmt_screening.csv"
    if not score_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no project_scores.csv; run a workflow first."
        )
    if not vmt_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no vmt_screening.csv; run a workflow first."
        )
    score_rows = _read_csv(score_path)
    vmt_rows = _read_csv(vmt_path)
    delta_rows = _read_csv(tables / "accessibility_delta.csv")
    ceqa_rows = _read_csv(tables / "ceqa_vmt.csv")
    lapm_rows = _read_csv(tables / "lapm_exhibit.csv")

    result = compute_rtp_chapter(
        score_rows,
        vmt_rows,
        run_id=run_id,
        agency=agency,
        rtp_cycle=rtp_cycle,
        chapter_title=chapter_title,
        delta_rows=delta_rows or None,
        ceqa_rows=ceqa_rows or None,
        lapm_rows=lapm_rows or None,
    )

    rtp_csv_path = tables / "rtp_chapter_projects.csv"
    rtp_scenarios_csv_path = tables / "rtp_chapter_scenarios.csv"
    rtp_json_path = tables / "rtp_chapter.json"
    fact_blocks_path = tables / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_rtp_chapter.md"

    tables.mkdir(parents=True, exist_ok=True)
    with rtp_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "total_score",
                "sensitivity_flag",
                "lapm_location",
                "lapm_project_type",
                "lapm_estimated_cost_usd",
            ],
        )
        writer.writeheader()
        for project in result.projects:
            writer.writerow(asdict(project))
    with rtp_scenarios_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario_id",
                "population",
                "daily_vmt",
                "vmt_per_capita",
                "accessibility_delta_jobs",
                "ceqa_determination",
                "ceqa_threshold_vmt_per_capita",
            ],
        )
        writer.writeheader()
        for scenario in result.scenarios:
            writer.writerow(asdict(scenario))

    write_json(rtp_json_path, result.to_json())

    new_blocks = rtp_chapter_fact_blocks(result, rtp_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_rtp_chapter_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "projects_csv_path": str(rtp_csv_path),
        "scenarios_csv_path": str(rtp_scenarios_csv_path),
        "json_path": str(rtp_json_path),
        "fact_block_count": appended,
        "project_count": len(result.projects),
        "scenario_count": len(result.scenarios),
        "agency": agency,
        "rtp_cycle": rtp_cycle,
        "chapter_title": chapter_title,
    }
