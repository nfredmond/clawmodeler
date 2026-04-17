"""SB 535 / AB 1550 / tribal equity lens overlay.

California's climate-investment statutes require agencies administering
California Climate Investments to report the share of benefits flowing
to disadvantaged communities (DACs, designated by CalEPA under
**SB 535** via CalEnviroScreen) and low-income communities and
households (**AB 1550**, H&S Code §39713). Tribal cultural resources
consultation (AB 52, 2014) is a distinct statutory trigger that overlaps
with project-area screening.

This module reads a finished run's ``project_scores.csv`` and an
optional ``equity_overlay.csv`` sidecar that a lead agency stages with
per-project DAC / AB 1550 / tribal flags (either hand-populated or
produced by an upstream GIS overlay). It classifies each project into
the AB 1550 benefit category the lead agency would report to CARB and
emits a portfolio summary that shows whether the AB 1550 statutory
minima are met.

ClawModeler does *not* compute SB 535 or AB 1550 eligibility from raw
census tracts here — that requires the authoritative CalEPA DAC layer
and the HCD AB 1550 low-income tract list, both of which are updated on
statutory cycles outside the engine. Projects the lead agency has not
flagged are reported as ``Unknown`` rather than silently assumed
non-disadvantaged; the lead agency must stage the overlay or label its
absence before relying on the summary.

This module does not call an LLM. Every claim is either read from the
run / overlay or clearly labeled as lead-agency-supplied.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..report import read_fact_blocks
from ..workspace import ENGINE_VERSION, InsufficientDataError, utc_now, write_json

DEFAULT_AGENCY = "Lead agency to be provided"
DEFAULT_DATASET_NOTE = (
    "CalEPA DAC designations per SB 535 (CalEnviroScreen 4.0) and AB 1550 "
    "low-income community / household lists per H&S Code §39713 — lead "
    "agency to stage `inputs/equity_overlay.csv`."
)

AB1550_TARGET_DAC_SHARE = 0.25
AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE = 0.10
AB1550_TARGET_LOW_INCOME_SHARE = 0.05

BENEFIT_CATEGORY_DAC = "DAC"
BENEFIT_CATEGORY_LI_NEAR_DAC = "Low-income near DAC"
BENEFIT_CATEGORY_LOW_INCOME = "Low-income"
BENEFIT_CATEGORY_OTHER = "Other"
BENEFIT_CATEGORY_UNKNOWN = "Unknown"

BENEFIT_CATEGORIES = (
    BENEFIT_CATEGORY_DAC,
    BENEFIT_CATEGORY_LI_NEAR_DAC,
    BENEFIT_CATEGORY_LOW_INCOME,
    BENEFIT_CATEGORY_OTHER,
    BENEFIT_CATEGORY_UNKNOWN,
)


@dataclass
class EquityProjectFinding:
    project_id: str
    name: str
    total_score: float
    sensitivity_flag: str
    dac_sb535: bool
    low_income_ab1550: bool
    low_income_near_dac: bool
    tribal_area: bool
    ces_percentile: float | None
    benefit_category: str
    overlay_supplied: bool
    notes: str


@dataclass
class EquityPortfolioSummary:
    project_count: int
    dac_count: int
    low_income_near_dac_count: int
    low_income_count: int
    tribal_count: int
    unknown_count: int
    dac_share: float
    low_income_near_dac_share: float
    low_income_share: float
    ab1550_dac_target_met: bool
    ab1550_low_income_near_dac_target_met: bool
    ab1550_low_income_target_met: bool


@dataclass
class EquityLensResult:
    run_id: str
    agency: str
    dataset_note: str
    project_count: int
    findings: list[EquityProjectFinding] = field(default_factory=list)
    summary: EquityPortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agency": self.agency,
            "dataset_note": self.dataset_note,
            "project_count": self.project_count,
            "generated_at": self.generated_at,
            "findings": [asdict(f) for f in self.findings],
            "summary": asdict(self.summary) if self.summary is not None else None,
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


def _coerce_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return False
    return text in {"true", "t", "1", "yes", "y"}


def _classify_benefit_category(
    *,
    dac: bool,
    low_income: bool,
    low_income_near_dac: bool,
    overlay_supplied: bool,
) -> str:
    if not overlay_supplied:
        return BENEFIT_CATEGORY_UNKNOWN
    if dac:
        return BENEFIT_CATEGORY_DAC
    if low_income and low_income_near_dac:
        return BENEFIT_CATEGORY_LI_NEAR_DAC
    if low_income:
        return BENEFIT_CATEGORY_LOW_INCOME
    return BENEFIT_CATEGORY_OTHER


def compute_equity_lens(
    score_rows: list[dict[str, Any]],
    *,
    run_id: str,
    agency: str = DEFAULT_AGENCY,
    dataset_note: str | None = None,
    overlay_rows: list[dict[str, Any]] | None = None,
) -> EquityLensResult:
    """Build an equity-lens overlay from project scores + optional overlay sidecar.

    ``score_rows`` is the engine's ``project_scores.csv`` as list-of-dict.
    ``overlay_rows`` is an optional sidecar keyed by ``project_id`` with
    boolean-ish columns ``dac_sb535``, ``low_income_ab1550``,
    ``low_income_near_dac``, ``tribal_area``; an optional numeric
    ``ces_percentile`` (0–100); and a free-text ``notes`` column.
    """
    if not score_rows:
        raise InsufficientDataError(
            "project_scores rows are empty; run a workflow before generating "
            "the equity lens."
        )

    overlay_by_id: dict[str, dict[str, Any]] = {}
    for row in overlay_rows or []:
        project_id = _coerce_str(row.get("project_id"))
        if project_id:
            overlay_by_id[project_id] = row

    findings: list[EquityProjectFinding] = []
    for row in score_rows:
        project_id = _coerce_str(row.get("project_id"))
        if not project_id:
            continue
        overlay = overlay_by_id.get(project_id)
        overlay_supplied = overlay is not None
        overlay = overlay or {}
        dac = _coerce_bool(overlay.get("dac_sb535"))
        low_income = _coerce_bool(overlay.get("low_income_ab1550"))
        low_income_near_dac = _coerce_bool(overlay.get("low_income_near_dac"))
        tribal = _coerce_bool(overlay.get("tribal_area"))
        ces = _parse_optional_float(overlay.get("ces_percentile"))
        notes = _coerce_str(
            overlay.get("notes"),
            (
                "No equity overlay staged for this project; lead agency must "
                "verify SB 535 / AB 1550 / tribal status."
            ),
        )
        benefit = _classify_benefit_category(
            dac=dac,
            low_income=low_income,
            low_income_near_dac=low_income_near_dac,
            overlay_supplied=overlay_supplied,
        )
        findings.append(
            EquityProjectFinding(
                project_id=project_id,
                name=_coerce_str(row.get("name"), project_id),
                total_score=round(
                    _parse_optional_float(row.get("total_score")) or 0.0, 3
                ),
                sensitivity_flag=_coerce_str(
                    row.get("sensitivity_flag"), "UNKNOWN"
                ),
                dac_sb535=dac,
                low_income_ab1550=low_income,
                low_income_near_dac=low_income_near_dac,
                tribal_area=tribal,
                ces_percentile=round(ces, 2) if ces is not None else None,
                benefit_category=benefit,
                overlay_supplied=overlay_supplied,
                notes=notes,
            )
        )

    if not findings:
        raise InsufficientDataError(
            "project_scores rows had no usable project_id values."
        )

    project_count = len(findings)
    dac_count = sum(1 for f in findings if f.dac_sb535)
    low_income_near_dac_count = sum(
        1 for f in findings if f.low_income_ab1550 and f.low_income_near_dac and not f.dac_sb535
    )
    low_income_count = sum(
        1 for f in findings if f.low_income_ab1550 and not f.low_income_near_dac and not f.dac_sb535
    )
    tribal_count = sum(1 for f in findings if f.tribal_area)
    unknown_count = sum(1 for f in findings if not f.overlay_supplied)

    dac_share = dac_count / project_count if project_count else 0.0
    low_income_near_dac_share = (
        low_income_near_dac_count / project_count if project_count else 0.0
    )
    low_income_share = low_income_count / project_count if project_count else 0.0

    summary = EquityPortfolioSummary(
        project_count=project_count,
        dac_count=dac_count,
        low_income_near_dac_count=low_income_near_dac_count,
        low_income_count=low_income_count,
        tribal_count=tribal_count,
        unknown_count=unknown_count,
        dac_share=round(dac_share, 3),
        low_income_near_dac_share=round(low_income_near_dac_share, 3),
        low_income_share=round(low_income_share, 3),
        ab1550_dac_target_met=dac_share >= AB1550_TARGET_DAC_SHARE,
        ab1550_low_income_near_dac_target_met=(
            low_income_near_dac_share >= AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE
        ),
        ab1550_low_income_target_met=low_income_share >= AB1550_TARGET_LOW_INCOME_SHARE,
    )

    return EquityLensResult(
        run_id=run_id,
        agency=agency,
        dataset_note=dataset_note or DEFAULT_DATASET_NOTE,
        project_count=project_count,
        findings=findings,
        summary=summary,
        generated_at=utc_now(),
    )


def equity_lens_fact_blocks(
    result: EquityLensResult, source_path: Path
) -> list[dict[str, Any]]:
    """Produce grounded fact_blocks for each project finding + portfolio summary."""
    blocks: list[dict[str, Any]] = []
    for finding in result.findings:
        flags: list[str] = []
        if finding.dac_sb535:
            flags.append("SB 535 DAC")
        if finding.low_income_ab1550:
            if finding.low_income_near_dac:
                flags.append("AB 1550 low-income within 1/2 mile of DAC")
            else:
                flags.append("AB 1550 low-income")
        if finding.tribal_area:
            flags.append("tribal area (AB 52 consultation trigger)")
        if not flags:
            flags_text = (
                "no SB 535, AB 1550, or tribal overlay flags"
                if finding.overlay_supplied
                else "no equity overlay staged — lead agency to verify"
            )
        else:
            flags_text = "; ".join(flags)
        claim = (
            f"Equity lens: project `{finding.project_id}` ({finding.name}) "
            f"classified as {finding.benefit_category} for AB 1550 reporting — "
            f"{flags_text}."
        )
        blocks.append(
            {
                "fact_id": f"equity-lens-project-{finding.project_id}",
                "fact_type": "equity_lens_project",
                "project_id": finding.project_id,
                "claim_text": claim,
                "source_table": str(source_path),
                "source_row": finding.project_id,
            }
        )

    if result.summary is not None:
        summary = result.summary
        portfolio_claim = (
            f"Equity portfolio: {summary.project_count} project(s) screened — "
            f"{summary.dac_count} SB 535 DAC ({summary.dac_share * 100:.1f}%), "
            f"{summary.low_income_near_dac_count} AB 1550 low-income within 1/2 "
            f"mile of DAC ({summary.low_income_near_dac_share * 100:.1f}%), "
            f"{summary.low_income_count} AB 1550 low-income outside 1/2 mile "
            f"({summary.low_income_share * 100:.1f}%), "
            f"{summary.tribal_count} in a tribal area, "
            f"{summary.unknown_count} with no overlay staged."
        )
        blocks.append(
            {
                "fact_id": "equity-lens-summary",
                "fact_type": "equity_lens_summary",
                "claim_text": portfolio_claim,
                "source_table": str(source_path),
                "source_row": "portfolio",
            }
        )

    return blocks


def render_equity_lens_markdown(result: EquityLensResult, *, run_id: str) -> str:
    """Render the equity-lens packet as Markdown."""
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
    template = env.get_template("equity_lens.md.j2")
    payload = result.to_json()
    return template.render(
        run_id=run_id,
        engine_version=ENGINE_VERSION,
        result=payload,
        findings=payload["findings"],
        summary=payload["summary"],
        targets={
            "dac": AB1550_TARGET_DAC_SHARE,
            "low_income_near_dac": AB1550_TARGET_LOW_INCOME_NEAR_DAC_SHARE,
            "low_income": AB1550_TARGET_LOW_INCOME_SHARE,
        },
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_equity_overlay_rows(
    workspace: Path, run_root: Path
) -> list[dict[str, Any]]:
    """Find an equity overlay CSV in the run manifest or under inputs/."""
    manifest_path = run_root / "outputs" / "run_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
        if isinstance(artifacts, dict):
            candidates = artifacts.get("equity_overlay_csv") or []
            for candidate in candidates:
                candidate_path = Path(str(candidate))
                if not candidate_path.is_absolute():
                    candidate_path = workspace / candidate_path
                rows = _read_csv(candidate_path)
                if rows:
                    return rows
    for candidate in (
        workspace / "inputs" / "equity_overlay.csv",
        workspace / "inputs" / "processed" / "equity_overlay.csv",
        workspace / "inputs" / "raw" / "equity_overlay.csv",
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


def write_equity_lens(
    workspace: Path,
    run_id: str,
    *,
    agency: str = DEFAULT_AGENCY,
    dataset_note: str | None = None,
) -> dict[str, Any]:
    """Compute equity lens, append fact_blocks, render packet, return paths."""
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

    overlay_rows = _resolve_equity_overlay_rows(workspace, run_root)

    result = compute_equity_lens(
        score_rows,
        run_id=run_id,
        agency=agency,
        dataset_note=dataset_note,
        overlay_rows=overlay_rows,
    )

    equity_csv_path = run_root / "outputs" / "tables" / "equity_lens.csv"
    equity_json_path = run_root / "outputs" / "tables" / "equity_lens.json"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    report_path = workspace / "reports" / f"{run_id}_equity_lens.md"

    equity_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with equity_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "project_id",
                "name",
                "total_score",
                "sensitivity_flag",
                "dac_sb535",
                "low_income_ab1550",
                "low_income_near_dac",
                "tribal_area",
                "ces_percentile",
                "benefit_category",
                "overlay_supplied",
                "notes",
            ],
        )
        writer.writeheader()
        for finding in result.findings:
            writer.writerow(asdict(finding))

    write_json(equity_json_path, result.to_json())

    new_blocks = equity_lens_fact_blocks(result, equity_csv_path)
    appended = _append_fact_blocks(fact_blocks_path, new_blocks)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_equity_lens_markdown(result, run_id=run_id)
    report_path.write_text(markdown, encoding="utf-8")

    summary_json = asdict(result.summary) if result.summary is not None else None
    return {
        "report_path": str(report_path),
        "csv_path": str(equity_csv_path),
        "json_path": str(equity_json_path),
        "fact_block_count": appended,
        "project_count": result.project_count,
        "agency": agency,
        "overlay_supplied_count": result.project_count
        - (result.summary.unknown_count if result.summary else 0),
        "summary": summary_json,
    }
