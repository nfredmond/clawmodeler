"""Workspace-level portfolio dashboard.

Summarizes every run in a workspace as a single KPI row so a lead
agency can compare alternatives at a glance. Reads each run's
``manifest.json``, ``qa_report.json``, ``project_scores.csv``,
``vmt_screening.csv``, and ``equity_lens.csv`` (when present) and
emits:

- ``portfolio/summary.csv`` — one row per run with KPI columns.
- ``portfolio/summary.json`` — the same data as a structured payload.
- ``portfolio/fact_blocks.jsonl`` — one ``portfolio_run`` fact_block
  per run plus one ``portfolio_summary`` block for the workspace.
- ``reports/portfolio.md`` — a Markdown overview.

The module is deterministic. No LLM is called. Every fact_block carries
``method_ref="portfolio.run_summary"`` + ``artifact_refs`` so the
v0.7.1 QA gate accepts the emitted blocks.

Missing artifacts are reported as ``None`` rather than silently
dropped; a run that never produced Planner Pack output still shows up
in the portfolio with its engine-level KPIs.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .workspace import (
    ENGINE_VERSION,
    InsufficientDataError,
    read_json,
    utc_now,
    write_json,
)


@dataclass
class RunSummary:
    run_id: str
    engine_version: str | None
    created_at: str | None
    base_run_id: str | None
    scenario_count: int
    project_count: int
    mean_total_score: float | None
    top_project_id: str | None
    top_project_name: str | None
    top_project_score: float | None
    vmt_flagged_count: int
    dac_share: float | None
    fact_block_count: int
    export_ready: bool
    qa_blockers: list[str]
    planner_pack_artifacts: list[str]
    has_what_if_overrides: bool

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["planner_pack_artifacts"] = list(self.planner_pack_artifacts)
        payload["qa_blockers"] = list(self.qa_blockers)
        return payload


@dataclass
class PortfolioSummary:
    run_count: int
    export_ready_count: int
    mean_portfolio_score: float | None
    total_vmt_flagged_count: int
    mean_dac_share: float | None
    engine_versions: list[str]
    lineage_edges: list[dict[str, str]]

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["engine_versions"] = list(self.engine_versions)
        payload["lineage_edges"] = [dict(edge) for edge in self.lineage_edges]
        return payload


@dataclass
class PortfolioResult:
    workspace_path: str
    run_count: int
    runs: list[RunSummary] = field(default_factory=list)
    summary: PortfolioSummary | None = None
    generated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "run_count": self.run_count,
            "runs": [run.to_json() for run in self.runs],
            "summary": self.summary.to_json() if self.summary is not None else None,
            "generated_at": self.generated_at,
        }


_PLANNER_PACK_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("ceqa_vmt", "ceqa_vmt.csv"),
    ("lapm_exhibit", "lapm_exhibit.csv"),
    ("rtp_chapter", "rtp_chapter_projects.csv"),
    ("equity_lens", "equity_lens.csv"),
    ("atp_packet", "atp_packet.csv"),
    ("hsip", "hsip.csv"),
    ("cmaq", "cmaq.csv"),
    ("stip", "stip.csv"),
)


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _count_vmt_flagged(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        tier = str(row.get("tier", "")).strip().lower()
        if tier in {"above", "above_reference", "flagged", "potentially_significant"}:
            count += 1
            continue
        delta = _coerce_float(row.get("daily_vmt_delta"))
        if delta is not None and delta > 0:
            count += 1
    return count


def _dac_share_from_equity(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    dac = 0
    total = 0
    for row in rows:
        total += 1
        if str(row.get("dac_sb535", "")).strip().lower() in {"true", "1", "yes", "t"}:
            dac += 1
    if total == 0:
        return None
    return round(dac / total, 3)


def _count_fact_blocks(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                count += 1
    return count


def _summarize_run(workspace: Path, run_id: str) -> RunSummary | None:
    run_root = workspace / "runs" / run_id
    manifest_path = run_root / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = read_json(manifest_path)
    except Exception:
        return None

    qa_path = run_root / "qa_report.json"
    qa: dict[str, Any]
    if qa_path.exists():
        try:
            qa = read_json(qa_path)
        except Exception:
            qa = {}
    else:
        qa = {}

    tables = run_root / "outputs" / "tables"
    score_rows = _read_csv(tables / "project_scores.csv")
    vmt_rows = _read_csv(tables / "vmt_screening.csv")
    equity_rows = _read_csv(tables / "equity_lens.csv")

    scores = [
        _coerce_float(row.get("total_score"))
        for row in score_rows
        if row.get("project_id")
    ]
    scores = [s for s in scores if s is not None]
    mean_score = round(sum(scores) / len(scores), 3) if scores else None

    top_id: str | None = None
    top_name: str | None = None
    top_score: float | None = None
    if score_rows:
        def _score_key(row: dict[str, Any]) -> float:
            value = _coerce_float(row.get("total_score"))
            return value if value is not None else float("-inf")
        top = max(score_rows, key=_score_key)
        if _coerce_float(top.get("total_score")) is not None:
            top_id = str(top.get("project_id", "")) or None
            top_name = str(top.get("name", top_id or ""))
            top_score = _coerce_float(top.get("total_score"))
            top_score = round(top_score, 3) if top_score is not None else None

    artifacts = [
        label for (label, filename) in _PLANNER_PACK_ARTIFACTS
        if (tables / filename).exists()
    ]

    scenario_count = len(manifest.get("scenarios", []) or [])
    base_run_id = manifest.get("base_run_id")
    if base_run_id is not None:
        base_run_id = str(base_run_id)
    overrides = manifest.get("overrides")
    has_overrides = bool(overrides) if isinstance(overrides, dict) else False

    app = manifest.get("app") or {}
    engine_version = app.get("engine_version")
    if engine_version is not None:
        engine_version = str(engine_version)

    fact_block_count = int(
        qa.get("checks", {}).get("fact_block_count", 0)
        if isinstance(qa.get("checks"), dict)
        else 0
    )
    if fact_block_count == 0:
        fact_block_count = _count_fact_blocks(tables / "fact_blocks.jsonl")

    qa_blockers_raw = qa.get("blockers") if isinstance(qa, dict) else None
    qa_blockers = [str(b) for b in qa_blockers_raw] if isinstance(qa_blockers_raw, list) else []
    export_ready = bool(qa.get("export_ready")) if isinstance(qa, dict) else False

    return RunSummary(
        run_id=run_id,
        engine_version=engine_version,
        created_at=str(manifest.get("created_at")) if manifest.get("created_at") else None,
        base_run_id=base_run_id,
        scenario_count=scenario_count,
        project_count=len(score_rows),
        mean_total_score=mean_score,
        top_project_id=top_id,
        top_project_name=top_name,
        top_project_score=top_score,
        vmt_flagged_count=_count_vmt_flagged(vmt_rows),
        dac_share=_dac_share_from_equity(equity_rows),
        fact_block_count=fact_block_count,
        export_ready=export_ready,
        qa_blockers=qa_blockers,
        planner_pack_artifacts=artifacts,
        has_what_if_overrides=has_overrides,
    )


def list_runs(workspace: Path) -> list[RunSummary]:
    """List every run in the workspace as a summary row.

    Runs without a ``manifest.json`` are skipped (they're not real
    runs; they are leftover scratch directories). Returns a list sorted
    by ``created_at`` descending (most recent first), falling back to
    ``run_id`` ascending when timestamps are missing.
    """
    runs_dir = workspace / "runs"
    if not runs_dir.exists():
        return []
    summaries: list[RunSummary] = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        summary = _summarize_run(workspace, child.name)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(
        key=lambda s: (s.created_at or "", s.run_id),
        reverse=True,
    )
    return summaries


def compute_portfolio(workspace: Path) -> PortfolioResult:
    """Build the full workspace portfolio result.

    Raises ``InsufficientDataError`` if the workspace has no valid
    runs yet (either the ``runs/`` directory is missing or every
    subdirectory lacks a manifest).
    """
    runs = list_runs(workspace)
    if not runs:
        raise InsufficientDataError(
            f"Workspace {workspace} has no runs with a valid manifest.json; "
            "run at least one `clawmodeler-engine run` before compiling a portfolio."
        )

    scores = [r.mean_total_score for r in runs if r.mean_total_score is not None]
    mean_portfolio_score = (
        round(sum(scores) / len(scores), 3) if scores else None
    )
    dac_shares = [r.dac_share for r in runs if r.dac_share is not None]
    mean_dac_share = (
        round(sum(dac_shares) / len(dac_shares), 3) if dac_shares else None
    )
    engine_versions = sorted({r.engine_version for r in runs if r.engine_version})
    lineage_edges = [
        {"from": r.base_run_id or "", "to": r.run_id}
        for r in runs
        if r.base_run_id
    ]

    summary = PortfolioSummary(
        run_count=len(runs),
        export_ready_count=sum(1 for r in runs if r.export_ready),
        mean_portfolio_score=mean_portfolio_score,
        total_vmt_flagged_count=sum(r.vmt_flagged_count for r in runs),
        mean_dac_share=mean_dac_share,
        engine_versions=engine_versions,
        lineage_edges=lineage_edges,
    )

    return PortfolioResult(
        workspace_path=str(workspace),
        run_count=len(runs),
        runs=runs,
        summary=summary,
        generated_at=utc_now(),
    )


def portfolio_fact_blocks(
    result: PortfolioResult, source_path: Path
) -> list[dict[str, Any]]:
    """Emit grounded fact_blocks for every run plus a workspace summary.

    Every block carries ``method_ref="portfolio.run_summary"`` and
    ``artifact_refs=[{"path": <source_path>, "type": "table"}]`` so the
    v0.7.1 QA gate (``qa.is_valid_fact_block``) accepts them.
    """
    blocks: list[dict[str, Any]] = []
    for run in result.runs:
        lineage = (
            f" derived from `{run.base_run_id}`"
            if run.base_run_id
            else ""
        )
        score_phrase = (
            f"mean total_score {run.mean_total_score:.3f}"
            if run.mean_total_score is not None
            else "no scored projects"
        )
        dac_phrase = (
            f", SB 535 DAC share {run.dac_share * 100:.1f}%"
            if run.dac_share is not None
            else ""
        )
        artifacts_phrase = (
            f", Planner Pack artifacts present: {', '.join(run.planner_pack_artifacts)}"
            if run.planner_pack_artifacts
            else ""
        )
        ready_phrase = (
            "export-ready" if run.export_ready else "not export-ready"
        )
        blocks.append(
            {
                "fact_id": f"portfolio-run-{run.run_id}",
                "fact_type": "portfolio_run",
                "scenario_id": None,
                "run_id": run.run_id,
                "claim_text": (
                    f"Portfolio row for run `{run.run_id}`{lineage}: "
                    f"{run.project_count} project(s), {score_phrase}, "
                    f"{run.vmt_flagged_count} VMT-flagged scenario(s)"
                    f"{dac_phrase}{artifacts_phrase}; {ready_phrase}."
                ),
                "method_ref": "portfolio.run_summary",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "created_at": utc_now(),
            }
        )

    if result.summary is not None:
        summary = result.summary
        mean_phrase = (
            f"mean portfolio score {summary.mean_portfolio_score:.3f}"
            if summary.mean_portfolio_score is not None
            else "no scored runs"
        )
        dac_phrase = (
            f", mean SB 535 DAC share {summary.mean_dac_share * 100:.1f}%"
            if summary.mean_dac_share is not None
            else ""
        )
        lineage_phrase = (
            f", {len(summary.lineage_edges)} what-if lineage edge(s)"
            if summary.lineage_edges
            else ""
        )
        blocks.append(
            {
                "fact_id": "portfolio-summary",
                "fact_type": "portfolio_summary",
                "scenario_id": None,
                "claim_text": (
                    f"Portfolio: {summary.run_count} run(s), "
                    f"{summary.export_ready_count} export-ready, "
                    f"{mean_phrase}, "
                    f"{summary.total_vmt_flagged_count} total VMT-flagged scenario(s)"
                    f"{dac_phrase}{lineage_phrase}."
                ),
                "method_ref": "portfolio.run_summary",
                "artifact_refs": [{"path": str(source_path), "type": "table"}],
                "created_at": utc_now(),
            }
        )
    return blocks


def render_portfolio_markdown(result: PortfolioResult) -> str:
    """Render the portfolio dashboard as Markdown."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template("portfolio.md.j2")
    payload = result.to_json()
    return template.render(
        result=payload,
        runs=payload["runs"],
        summary=payload["summary"],
        generated_at=result.generated_at,
        engine_version=ENGINE_VERSION,
    )


def _portfolio_csv_fieldnames() -> list[str]:
    return [
        "run_id",
        "engine_version",
        "created_at",
        "base_run_id",
        "scenario_count",
        "project_count",
        "mean_total_score",
        "top_project_id",
        "top_project_name",
        "top_project_score",
        "vmt_flagged_count",
        "dac_share",
        "fact_block_count",
        "export_ready",
        "qa_blockers",
        "planner_pack_artifacts",
        "has_what_if_overrides",
    ]


def _write_portfolio_csv(path: Path, runs: list[RunSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=_portfolio_csv_fieldnames())
        writer.writeheader()
        for run in runs:
            row = run.to_json()
            row["qa_blockers"] = ";".join(row["qa_blockers"])
            row["planner_pack_artifacts"] = ";".join(row["planner_pack_artifacts"])
            writer.writerow(row)


def write_portfolio(workspace: Path) -> dict[str, Any]:
    """Compute the portfolio, persist CSV/JSON/fact_blocks + Markdown report.

    Returns a summary dict with paths and headline counts that the CLI
    and the Tauri bridge surface to the caller.
    """
    result = compute_portfolio(workspace)

    portfolio_dir = workspace / "portfolio"
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    csv_path = portfolio_dir / "summary.csv"
    json_path = portfolio_dir / "summary.json"
    fact_blocks_path = portfolio_dir / "fact_blocks.jsonl"
    report_path = workspace / "reports" / "portfolio.md"

    _write_portfolio_csv(csv_path, result.runs)
    write_json(json_path, result.to_json())

    blocks = portfolio_fact_blocks(result, csv_path)
    with fact_blocks_path.open("w", encoding="utf-8") as file:
        for block in blocks:
            file.write(json.dumps(block) + "\n")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_portfolio_markdown(result), encoding="utf-8")

    summary_payload = result.summary.to_json() if result.summary is not None else None
    return {
        "workspace": str(workspace),
        "workspace_path": str(workspace),
        "run_count": result.run_count,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "report_path": str(report_path),
        "fact_blocks_path": str(fact_blocks_path),
        "fact_block_count": len(blocks),
        "summary": summary_payload,
        "runs": [run.to_json() for run in result.runs],
        "generated_at": result.generated_at,
    }
