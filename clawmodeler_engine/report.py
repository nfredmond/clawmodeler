from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .workspace import ENGINE_VERSION, read_json, utc_now

REPORT_TYPES = ("technical", "layperson", "brief")


class ReportDependencyMissingError(RuntimeError):
    pass


def _require_jinja():
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined

        return Environment, FileSystemLoader, StrictUndefined
    except ModuleNotFoundError as error:
        raise ReportDependencyMissingError(
            "jinja2 is not installed. Install the light profile: "
            "`bash scripts/install-profile.sh light`."
        ) from error


def _templates_dir() -> Path:
    return Path(__file__).parent / "templates"


def _environment():
    Environment, FileSystemLoader, StrictUndefined = _require_jinja()
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    return env


def render_report(
    manifest: dict[str, Any],
    report_type: str = "technical",
    *,
    ai_narrative: dict[str, Any] | None = None,
) -> str:
    if report_type not in REPORT_TYPES:
        raise ValueError(
            f"Unknown report_type {report_type!r}; expected one of {REPORT_TYPES}"
        )
    context = build_context(
        manifest, report_type=report_type, ai_narrative=ai_narrative
    )
    env = _environment()
    template_name = {
        "technical": "technical.md.j2",
        "layperson": "layperson.md.j2",
        "brief": "stakeholder_brief.md.j2",
    }[report_type]
    template = env.get_template(template_name)
    return template.render(**context)


def render_technical_report(manifest: dict[str, Any]) -> str:
    return render_report(manifest, report_type="technical")


def render_layperson_report(manifest: dict[str, Any]) -> str:
    return render_report(manifest, report_type="layperson")


def render_stakeholder_brief(manifest: dict[str, Any]) -> str:
    return render_report(manifest, report_type="brief")


def render_markdown_report(manifest: dict[str, Any]) -> str:
    return render_technical_report(manifest)


def build_context(
    manifest: dict[str, Any],
    *,
    report_type: str,
    ai_narrative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(manifest.get("run_id", "unknown"))
    workspace_root = Path(str(manifest["workspace"]["root"]))
    run_root = workspace_root / "runs" / run_id
    reports_dir = workspace_root / "reports"
    fact_blocks_path = run_root / "outputs" / "tables" / "fact_blocks.jsonl"
    qa_path = run_root / "qa_report.json"

    fact_blocks = read_fact_blocks(fact_blocks_path) if fact_blocks_path.exists() else []
    qa_raw = read_json(qa_path) if qa_path.exists() else {}
    qa = summarize_qa(qa_raw, fact_blocks)

    outputs = manifest.get("outputs", {}) or {}
    scenarios = read_scenarios(run_root, manifest)
    figures = describe_figures(outputs.get("figures", []), reports_dir, fact_blocks)
    maps = describe_maps(outputs.get("maps", []), reports_dir, fact_blocks)
    headlines = build_headlines(fact_blocks, manifest)
    findings = build_findings(fact_blocks, manifest)
    bridges = read_bridge_statuses(run_root / "outputs" / "bridges")

    title_by_type = {
        "technical": "ClawModeler Technical Report",
        "layperson": "ClawModeler Planner Report",
        "brief": "ClawModeler Stakeholder Brief",
    }

    return {
        "title": title_by_type.get(report_type, "ClawModeler Report"),
        "run_id": run_id,
        "generated_at": utc_now(),
        "engine_version": manifest.get("app", {}).get("engine_version") or ENGINE_VERSION,
        "routing_engine": manifest.get("engine", {}).get("routing_engine", "unknown"),
        "qa_status": "READY" if qa.get("export_allowed") else "BLOCKED",
        "qa": qa,
        "methods": manifest.get("methods", []),
        "scenarios": scenarios,
        "fact_blocks": fact_blocks,
        "figures": figures,
        "maps": maps,
        "assumptions": manifest.get("assumptions", []),
        "outputs": outputs,
        "bridges": bridges,
        "headlines": headlines,
        "findings": findings,
        "question_summary": extract_question_summary(workspace_root),
        "ai_narrative": ai_narrative,
    }


def read_fact_blocks(path: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                blocks.append(json.loads(line))
    return blocks


def summarize_qa(qa_raw: dict[str, Any], fact_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "export_allowed": bool(qa_raw.get("export_ready", False)),
        "manifest_present": bool(qa_raw.get("manifest_present", True)),
        "fact_blocks_present": bool(
            qa_raw.get("fact_blocks_present", len(fact_blocks) > 0)
        ),
        "fact_block_count": qa_raw.get("fact_block_count", len(fact_blocks)),
        "blockers": qa_raw.get("blockers", []) or [],
    }


def read_scenarios(run_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    summary_path = run_root / "outputs" / "tables" / "scenario_diff_summary.csv"
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        return [
            {
                "scenario_id": row.get("scenario_id", ""),
                "name": row.get("name", row.get("scenario_id", "")),
                "population_multiplier": row.get("population_multiplier", ""),
                "jobs_multiplier": row.get("jobs_multiplier", ""),
            }
            for row in rows
        ]
    return [
        {
            "scenario_id": scenario.get("scenario_id", ""),
            "name": scenario.get("scenario_id", ""),
            "population_multiplier": "",
            "jobs_multiplier": "",
        }
        for scenario in manifest.get("scenarios", [])
    ]


def describe_figures(
    figure_paths: list[str],
    reports_dir: Path,
    fact_blocks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    captions_by_path = {
        str(block.get("figure_ref")): block.get("claim_text", "")
        for block in fact_blocks
        if block.get("figure_ref")
    }
    described: list[dict[str, str]] = []
    for raw_path in figure_paths:
        path = Path(str(raw_path))
        described.append(
            {
                "title": path.stem.replace("_", " ").title(),
                "relative_path": _relative_or_absolute(path, reports_dir),
                "caption": captions_by_path.get(str(path), ""),
            }
        )
    return described


def describe_maps(
    map_paths: list[str],
    reports_dir: Path,
    fact_blocks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    captions_by_path = {
        str(block.get("map_ref")): block.get("claim_text", "")
        for block in fact_blocks
        if block.get("map_ref")
    }
    described: list[dict[str, str]] = []
    for raw_path in map_paths:
        path = Path(str(raw_path))
        described.append(
            {
                "title": path.stem.replace("_", " ").title(),
                "relative_path": _relative_or_absolute(path, reports_dir),
                "caption": captions_by_path.get(str(path), ""),
            }
        )
    return described


def _relative_or_absolute(target: Path, base: Path) -> str:
    try:
        return str(Path("..") / target.resolve().relative_to(base.resolve().parent))
    except ValueError:
        return str(target)


def build_headlines(
    fact_blocks: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    headlines: list[dict[str, str]] = []

    vmt_blocks = [block for block in fact_blocks if block.get("fact_type") == "vmt_screening"]
    for block in vmt_blocks:
        headlines.append(
            {
                "label": f"Daily VMT — {block.get('scenario_id') or 'scenario'}",
                "value": _extract_numeric_phrase(block.get("claim_text", ""), suffix=" VMT"),
                "context": "Screening-level per-capita proxy.",
            }
        )

    delta_blocks = [
        block for block in fact_blocks if block.get("fact_type") == "accessibility_delta"
    ]
    for block in delta_blocks:
        headlines.append(
            {
                "label": f"Jobs-access delta — {block.get('scenario_id')}",
                "value": _extract_numeric_phrase(block.get("claim_text", ""), suffix=" jobs"),
                "context": "Change in proxy jobs accessible vs. baseline.",
            }
        )

    score_blocks = [block for block in fact_blocks if block.get("fact_type") == "project_scoring"]
    for block in score_blocks[:1]:
        headlines.append(
            {
                "label": "Top-ranked project",
                "value": block.get("claim_text", ""),
                "context": "From the weighted rubric.",
            }
        )

    fact_count = len(fact_blocks)
    if fact_count:
        headlines.append(
            {
                "label": "Evidence depth",
                "value": f"{fact_count} fact-blocks",
                "context": "Every claim in this report is grounded in one.",
            }
        )
    return headlines[:6]


def build_findings(
    fact_blocks: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[str]:
    findings: list[str] = []
    for block in fact_blocks:
        fact_type = block.get("fact_type", "")
        if fact_type in {
            "accessibility_delta",
            "vmt_screening",
            "project_scoring",
            "transit",
        }:
            findings.append(str(block.get("claim_text", "")).strip())
        elif fact_type.startswith("figure_") or fact_type.startswith("map_"):
            continue
    return [finding for finding in findings if finding][:8]


def _extract_numeric_phrase(text: str, *, suffix: str) -> str:
    return text.strip() or f"— {suffix.strip()}"


def extract_question_summary(workspace_root: Path) -> str | None:
    path = workspace_root / "analysis_plan.json"
    if not path.exists():
        return None
    try:
        question = read_json(path).get("question", {})
    except Exception:
        return None
    summary = question.get("summary") or question.get("description") or question.get(
        "question_type"
    )
    return str(summary) if summary else None


def read_bridge_statuses(path: Path) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    if not path.exists():
        return statuses
    for manifest_path in sorted(path.glob("*/bridge_manifest.json")):
        manifest = read_json(manifest_path)
        counts: list[str] = []
        for key, label in (
            ("sumo_trip_count", "trips"),
            ("matsim_person_count", "persons"),
            ("urbansim_household_count", "households"),
            ("urbansim_job_count", "jobs"),
            ("dtalite_demand_row_count", "demand rows"),
            ("tbest_route_count", "routes"),
        ):
            value = manifest.get(key)
            if value is not None:
                counts.append(f"{label}: {value}")
        if manifest.get("bridge_qa_export_ready") is not None:
            counts.append(f"bridge QA ready: {manifest['bridge_qa_export_ready']}")
        statuses.append(
            {
                "bridge": manifest.get("bridge", manifest_path.parent.name),
                "status": manifest.get("status", "unknown"),
                "notes": ", ".join(counts) if counts else "—",
            }
        )
    return statuses


__all__ = [
    "REPORT_TYPES",
    "ReportDependencyMissingError",
    "build_context",
    "render_layperson_report",
    "render_markdown_report",
    "render_report",
    "render_stakeholder_brief",
    "render_technical_report",
]
