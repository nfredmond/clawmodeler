"""California Active Transportation Program (ATP) grant packet generator.

The ATP is administered by the California Transportation Commission
(Streets & Highways Code §§2380–2383) and funds bicycle, pedestrian,
and safe-routes-to-school projects. Each cycle's application is
evaluated against a published scoring rubric that covers project
benefits, disadvantaged-community (DAC) benefit, scope/schedule/budget,
project readiness, and past performance.

This module composes an ATP application **packet** for every candidate
project in a finished ClawModeler run. The packet is a structured
narrative outline populated with every fact ClawModeler has evidence
for — project scoring (v0.3 engine), Caltrans LAPM programming fields
(v0.6.1), CEQA §15064.3 VMT determinations (v0.6.0), SB 535 / AB 1550
equity findings (v0.6.3), and RTP chapter context (v0.6.2) — and
honest about the application sections that remain lead-agency
judgment (past performance, letters of support, detailed cost
estimates, final schedule, environmental determination).

ClawModeler does *not* draft prose that isn't tied to a run fact_block.
Every sentence in a rendered packet either cites a fact_id from the
run or is labeled as lead-agency-supplied.

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
DEFAULT_CYCLE = "ATP cycle to be provided"

ATP_DAC_SCORING_CATEGORIES = {"DAC", "Low-income near DAC", "Low-income"}


@dataclass
class AtpProjectApplication:
    project_id: str
    name: str
    agency: str
    cycle: str
    total_score: float
    safety_score: float
    equity_score: float
    climate_score: float
    feasibility_score: float
    sensitivity_flag: str
    location_note: str
    description: str
    project_type: str
    estimated_cost_usd: float | None
    schedule_note: str
    ceqa_determination: str
    dac_sb535: bool
    low_income_ab1550: bool
    tribal_area: bool
    benefit_category: str
    atp_dac_benefit_eligible: bool
    rtp_consistency_note: str
    readiness_note: str


@dataclass
class AtpPortfolioSummary:
    application_count: int
    dac_application_count: int
    low_income_application_count: int
    tribal_application_count: int
    dac_share: float
    mean_total_score: float


@dataclass
class AtpGrantResult:
    run_id: str
    agency: str
    cycle: str
    applications: list[AtpProjectApplication] = field(default_factory=list)
    summary: AtpPortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agency": self.agency,
            "cycle": self.cycle,
            "generated_at": self.generated_at,
            "applications": [asdict(a) for a in self.applications],
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


def _group_ceqa_by_project(
    ceqa_rows: list[dict[str, Any]] | None,
) -> str:
    """Summarize CEQA VMT determinations across scenarios for the packet.

    The Planner Pack CEQA module keys determinations by scenario, not
    by project. For the ATP packet we collapse them into a per-run
    phrase that callers can drop into the "Benefits — environmental
    findings" section alongside scenario-specific evidence.
    """
    if not ceqa_rows:
        return "CEQA §15064.3 VMT screening has not been run for this workspace."
    determinations = [
        coerce_str(r.get("determination")) for r in ceqa_rows
    ]
    determinations = [d for d in determinations if d]
    if not determinations:
        return "CEQA §15064.3 VMT screening produced no determinations."
    significant = sum(1 for d in determinations if "potentially significant" in d.lower())
    less_than = sum(1 for d in determinations if "less than significant" in d.lower())
    return (
        f"Across {len(determinations)} scenario(s): "
        f"{significant} potentially significant and "
        f"{less_than} less-than-significant VMT determination(s)."
    )


def compute_atp_packet(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    agency: str = DEFAULT_AGENCY,
    cycle: str = DEFAULT_CYCLE,
    lapm_rows: list[dict[str, Any]] | None = None,
    equity_rows: list[dict[str, Any]] | None = None,
    ceqa_rows: list[dict[str, Any]] | None = None,
    rtp_cycle_label: str | None = None,
) -> AtpGrantResult:
    """Build per-project ATP application packets from run evidence.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict.
    ``lapm_rows`` (from ``lapm_exhibit.csv``), ``equity_rows`` (from
    ``equity_lens.csv``), and ``ceqa_rows`` (from ``ceqa_vmt.csv``) are
    optional Planner Pack outputs used for enrichment. ``rtp_cycle_label``
    is an optional free-text note if the lead agency has identified the
    RTP cycle the projects are consistent with.
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before generating "
            "an ATP packet."
        )

    lapm_by_id: dict[str, dict[str, Any]] = {}
    for row in lapm_rows or []:
        pid = coerce_str(row.get("project_id"))
        if pid:
            lapm_by_id[pid] = row

    equity_by_id: dict[str, dict[str, Any]] = {}
    for row in equity_rows or []:
        pid = coerce_str(row.get("project_id"))
        if pid:
            equity_by_id[pid] = row

    ceqa_summary = _group_ceqa_by_project(ceqa_rows)
    rtp_consistency_note = (
        f"Consistent with the agency's adopted {rtp_cycle_label} Regional "
        f"Transportation Plan (lead agency to confirm chapter citation)."
        if rtp_cycle_label
        else "RTP consistency to be documented by lead agency."
    )

    applications: list[AtpProjectApplication] = []
    for row in score_rows:
        pid = coerce_str(row.get("project_id"))
        if not pid:
            continue

        safety = parse_optional_float(row.get("safety_score")) or 0.0
        equity = parse_optional_float(row.get("equity_score")) or 0.0
        climate = parse_optional_float(row.get("climate_score")) or 0.0
        feasibility = parse_optional_float(row.get("feasibility_score")) or 0.0
        total = parse_optional_float(row.get("total_score")) or 0.0
        sensitivity = coerce_str(row.get("sensitivity_flag"), "UNKNOWN")

        lapm = lapm_by_id.get(pid, {})
        location_note = coerce_str(
            lapm.get("location_note"),
            "Location to be provided by lead agency",
        )
        description = coerce_str(
            lapm.get("description"),
            "Project description to be provided by lead agency.",
        )
        project_type = coerce_str(
            lapm.get("project_type"),
            "Project type to be provided by lead agency",
        )
        schedule_note = coerce_str(
            lapm.get("schedule_note"),
            "PA&ED, PS&E, R/W, and CON schedule to be provided by lead agency",
        )
        estimated_cost = parse_optional_float(lapm.get("estimated_cost_usd"))

        equity_row = equity_by_id.get(pid, {})
        overlay_supplied = _coerce_bool(equity_row.get("overlay_supplied"))
        dac = _coerce_bool(equity_row.get("dac_sb535"))
        low_income = _coerce_bool(equity_row.get("low_income_ab1550"))
        tribal = _coerce_bool(equity_row.get("tribal_area"))
        benefit_category = coerce_str(
            equity_row.get("benefit_category"),
            "Unknown" if not overlay_supplied else "Other",
        )
        atp_dac_eligible = benefit_category in ATP_DAC_SCORING_CATEGORIES

        if sensitivity == "LOW":
            readiness_note = (
                "All four screening dimensions used lead-agency-supplied "
                "evidence; project is ready for PA&ED scoping."
            )
        elif sensitivity == "MEDIUM":
            readiness_note = (
                "One of four screening dimensions used a placeholder; lead "
                "agency should refine before final submittal."
            )
        else:
            readiness_note = (
                "Two or more screening dimensions used placeholders; lead "
                "agency must supply project-specific evidence before final "
                "submittal."
            )

        applications.append(
            AtpProjectApplication(
                project_id=pid,
                name=coerce_str(row.get("name"), pid),
                agency=agency,
                cycle=cycle,
                total_score=round(total, 3),
                safety_score=round(safety, 3),
                equity_score=round(equity, 3),
                climate_score=round(climate, 3),
                feasibility_score=round(feasibility, 3),
                sensitivity_flag=sensitivity,
                location_note=location_note,
                description=description,
                project_type=project_type,
                estimated_cost_usd=estimated_cost,
                schedule_note=schedule_note,
                ceqa_determination=ceqa_summary,
                dac_sb535=dac,
                low_income_ab1550=low_income,
                tribal_area=tribal,
                benefit_category=benefit_category,
                atp_dac_benefit_eligible=atp_dac_eligible,
                rtp_consistency_note=rtp_consistency_note,
                readiness_note=readiness_note,
            )
        )

    if not applications:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    application_count = len(applications)
    dac_count = sum(1 for a in applications if a.dac_sb535)
    low_income_count = sum(
        1 for a in applications if a.low_income_ab1550 and not a.dac_sb535
    )
    tribal_count = sum(1 for a in applications if a.tribal_area)
    mean_score = (
        sum(a.total_score for a in applications) / application_count
        if application_count
        else 0.0
    )
    dac_share = dac_count / application_count if application_count else 0.0

    summary = AtpPortfolioSummary(
        application_count=application_count,
        dac_application_count=dac_count,
        low_income_application_count=low_income_count,
        tribal_application_count=tribal_count,
        dac_share=round(dac_share, 3),
        mean_total_score=round(mean_score, 3),
    )

    return AtpGrantResult(
        run_id=run_id,
        agency=agency,
        cycle=cycle,
        applications=applications,
        summary=summary,
        generated_at=utc_now(),
    )


def atp_grant_fact_blocks(
    result: AtpGrantResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks per application + portfolio summary."""
    blocks: list[dict[str, Any]] = []
    for app in result.applications:
        dac_phrase = (
            "SB 535 DAC"
            if app.dac_sb535
            else (
                "AB 1550 low-income"
                if app.low_income_ab1550
                else "non-DAC / non-AB-1550"
            )
        )
        claim = (
            f"ATP application draft for project `{app.project_id}` "
            f"({app.name}): total screening score {app.total_score:.1f}/100 "
            f"(safety {app.safety_score:.1f}, equity {app.equity_score:.1f}, "
            f"climate {app.climate_score:.1f}, feasibility "
            f"{app.feasibility_score:.1f}); community context "
            f"{dac_phrase}; sensitivity flag {app.sensitivity_flag}."
        )
        blocks.append(
            {
                "fact_id": f"atp-application-{app.project_id}",
                "fact_type": "atp_application_project",
                "project_id": app.project_id,
                "claim_text": claim,
                "method_ref": "planner_pack.atp_packet",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": app.project_id,
            }
        )

    if result.summary is not None:
        summary = result.summary
        portfolio_claim = (
            f"ATP portfolio for {result.agency} ({result.cycle}): "
            f"{summary.application_count} application draft(s), "
            f"mean total score {summary.mean_total_score:.1f}/100; "
            f"{summary.dac_application_count} SB 535 DAC "
            f"({summary.dac_share * 100:.1f}%), "
            f"{summary.low_income_application_count} AB 1550 low-income (not DAC), "
            f"{summary.tribal_application_count} in a tribal area."
        )
        blocks.append(
            {
                "fact_id": "atp-application-summary",
                "fact_type": "atp_application_summary",
                "claim_text": portfolio_claim,
                "method_ref": "planner_pack.atp_packet",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "source_table": str(source_path),
                "source_row": "portfolio",
            }
        )

    return blocks


def render_atp_markdown(result: AtpGrantResult, *, run_id: str) -> str:
    """Render the ATP application packet as Markdown."""
    template = jinja_env().get_template("atp_packet.md.j2")
    payload = result.to_json()
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=payload,
        applications=payload["applications"],
        summary=payload["summary"],
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_atp_packet(
    workspace: Path,
    run_id: str,
    *,
    agency: str = DEFAULT_AGENCY,
    cycle: str = DEFAULT_CYCLE,
    rtp_cycle_label: str | None = None,
) -> dict[str, Any]:
    """Compute ATP packet, append fact_blocks, render packet, return paths."""
    run_root = workspace / "runs" / run_id
    if not run_root.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} does not exist under {workspace}."
        )
    tables = run_root / "outputs" / "tables"
    score_path = tables / "project_scores.csv"
    if not score_path.exists():
        raise InsufficientDataError(
            f"Run {run_id!r} has no project_scores.csv; run a workflow first."
        )
    score_rows = _read_csv(score_path)
    if not score_rows:
        raise InsufficientDataError(
            f"Run {run_id!r} project_scores.csv has no rows."
        )

    lapm_rows = _read_csv(tables / "lapm_exhibit.csv")
    equity_rows = _read_csv(tables / "equity_lens.csv")
    ceqa_rows = _read_csv(tables / "ceqa_vmt.csv")

    result = compute_atp_packet(
        score_rows,
        run_id=run_id,
        agency=agency,
        cycle=cycle,
        lapm_rows=lapm_rows or None,
        equity_rows=equity_rows or None,
        ceqa_rows=ceqa_rows or None,
        rtp_cycle_label=rtp_cycle_label,
    )

    atp_csv_path = tables / "atp_packet.csv"
    atp_json_path = tables / "atp_packet.json"
    fact_blocks_path = tables / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_atp_packet.md"

    atp_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with atp_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "agency",
                "cycle",
                "total_score",
                "safety_score",
                "equity_score",
                "climate_score",
                "feasibility_score",
                "sensitivity_flag",
                "location_note",
                "description",
                "project_type",
                "estimated_cost_usd",
                "schedule_note",
                "ceqa_determination",
                "dac_sb535",
                "low_income_ab1550",
                "tribal_area",
                "benefit_category",
                "atp_dac_benefit_eligible",
                "rtp_consistency_note",
                "readiness_note",
            ],
        )
        writer.writeheader()
        for app in result.applications:
            writer.writerow(asdict(app))

    write_json(atp_json_path, result.to_json())

    new_blocks = atp_grant_fact_blocks(result, atp_csv_path)
    appended = append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_atp_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    summary_json = asdict(result.summary) if result.summary is not None else None
    return {
        "report_path": str(report_path),
        "csv_path": str(atp_csv_path),
        "json_path": str(atp_json_path),
        "fact_block_count": appended,
        "application_count": len(result.applications),
        "agency": agency,
        "cycle": cycle,
        "summary": summary_json,
    }
