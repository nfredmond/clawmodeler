from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import utc_now


class ChartDependencyMissingError(RuntimeError):
    pass


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ModuleNotFoundError as error:
        raise ChartDependencyMissingError(
            "matplotlib is not installed. Install the standard profile: "
            "`bash scripts/install-profile.sh standard`."
        ) from error


def scenario_comparison_bar(
    rows: list[dict[str, Any]],
    metric: str,
    figures_dir: Path,
    *,
    title: str | None = None,
    ylabel: str | None = None,
    filename: str | None = None,
) -> Path:
    plt = _require_matplotlib()
    aggregated: dict[str, float] = {}
    for row in rows:
        scenario_id = str(row.get("scenario_id", "unknown"))
        value = float(row.get(metric, 0) or 0)
        aggregated[scenario_id] = aggregated.get(scenario_id, 0.0) + value

    scenarios = sorted(aggregated)
    values = [aggregated[scenario_id] for scenario_id in scenarios]

    figures_dir.mkdir(parents=True, exist_ok=True)
    output = figures_dir / (filename or f"scenario_comparison_{metric}.png")

    figure, axis = plt.subplots(figsize=(8, 5))
    bars = axis.bar(scenarios, values, color="#2b6cb0")
    axis.set_title(title or f"Scenario comparison: {metric}")
    axis.set_xlabel("Scenario")
    axis.set_ylabel(ylabel or metric.replace("_", " "))
    axis.grid(axis="y", linestyle="--", alpha=0.4)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return output


def vmt_co2e_trend(vmt_rows: list[dict[str, Any]], figures_dir: Path) -> Path:
    plt = _require_matplotlib()
    scenarios = [str(row["scenario_id"]) for row in vmt_rows]
    vmt_values = [float(row.get("daily_vmt", 0) or 0) for row in vmt_rows]
    co2e_values = [float(row.get("daily_kg_co2e", 0) or 0) for row in vmt_rows]

    figures_dir.mkdir(parents=True, exist_ok=True)
    output = figures_dir / "vmt_co2e_trend.png"

    figure, axis_vmt = plt.subplots(figsize=(8, 5))
    x_positions = range(len(scenarios))
    bar_width = 0.38
    axis_vmt.bar(
        [position - bar_width / 2 for position in x_positions],
        vmt_values,
        width=bar_width,
        color="#2b6cb0",
        label="Daily VMT",
    )
    axis_vmt.set_xlabel("Scenario")
    axis_vmt.set_ylabel("Daily VMT", color="#2b6cb0")
    axis_vmt.set_xticks(list(x_positions))
    axis_vmt.set_xticklabels(scenarios)
    axis_vmt.tick_params(axis="y", labelcolor="#2b6cb0")
    axis_vmt.grid(axis="y", linestyle="--", alpha=0.4)

    axis_co2 = axis_vmt.twinx()
    axis_co2.bar(
        [position + bar_width / 2 for position in x_positions],
        co2e_values,
        width=bar_width,
        color="#c53030",
        label="Daily kg CO2e",
    )
    axis_co2.set_ylabel("Daily kg CO2e", color="#c53030")
    axis_co2.tick_params(axis="y", labelcolor="#c53030")

    figure.suptitle("VMT and CO2e screening by scenario")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return output


def project_score_distribution(
    score_rows: list[dict[str, Any]],
    figures_dir: Path,
    *,
    top_n: int = 15,
) -> Path:
    plt = _require_matplotlib()
    ranked = sorted(
        score_rows,
        key=lambda row: float(row.get("total_score", 0) or 0),
        reverse=True,
    )[:top_n]
    names = [str(row.get("name") or row.get("project_id") or "project") for row in ranked]
    totals = [float(row.get("total_score", 0) or 0) for row in ranked]

    figures_dir.mkdir(parents=True, exist_ok=True)
    output = figures_dir / "project_score_distribution.png"

    figure, axis = plt.subplots(figsize=(9, max(3, 0.35 * len(names) + 1.5)))
    axis.barh(names[::-1], totals[::-1], color="#2f855a")
    axis.set_title(f"Top {len(names)} scored projects")
    axis.set_xlabel("Total score (weighted rubric)")
    axis.grid(axis="x", linestyle="--", alpha=0.4)
    for index, value in enumerate(totals[::-1]):
        axis.text(value, index, f" {value:.1f}", va="center", fontsize=9)
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return output


def accessibility_histogram(
    accessibility_rows: list[dict[str, Any]],
    scenario_id: str,
    figures_dir: Path,
    *,
    cutoff_min: int | None = None,
) -> Path:
    plt = _require_matplotlib()
    filtered = [
        row
        for row in accessibility_rows
        if str(row.get("scenario_id")) == scenario_id
        and (cutoff_min is None or int(row.get("cutoff_min", 0)) == cutoff_min)
    ]
    values = [float(row.get("jobs_accessible", 0) or 0) for row in filtered]

    figures_dir.mkdir(parents=True, exist_ok=True)
    cutoff_suffix = f"_{cutoff_min}min" if cutoff_min else ""
    output = figures_dir / f"accessibility_hist_{scenario_id}{cutoff_suffix}.png"

    figure, axis = plt.subplots(figsize=(8, 5))
    if values:
        axis.hist(values, bins=min(20, max(5, len(values) // 4)), color="#805ad5", edgecolor="white")
    axis.set_title(
        f"Jobs-accessible distribution — {scenario_id}"
        + (f" ({cutoff_min}-min cutoff)" if cutoff_min else "")
    )
    axis.set_xlabel("Jobs accessible (proxy)")
    axis.set_ylabel("Zones")
    axis.grid(axis="y", linestyle="--", alpha=0.4)
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return output


def figure_fact_block(
    fact_id: str,
    fact_type: str,
    claim_text: str,
    figure_path: Path,
    method_ref: str,
    *,
    scenario_id: str | None = None,
    table_path: Path | None = None,
) -> dict[str, Any]:
    artifact_refs: list[dict[str, str]] = [
        {"type": "figure", "path": str(figure_path)},
    ]
    if table_path is not None:
        artifact_refs.append({"type": "table", "path": str(table_path)})
    return {
        "fact_id": fact_id,
        "fact_type": fact_type,
        "claim_text": claim_text,
        "artifact_refs": artifact_refs,
        "figure_ref": str(figure_path),
        "scenario_id": scenario_id,
        "method_ref": method_ref,
        "created_at": utc_now(),
    }


def render_standard_figures(
    accessibility_rows: list[dict[str, Any]],
    vmt_rows: list[dict[str, Any]],
    score_rows: list[dict[str, Any]],
    delta_rows: list[dict[str, Any]],
    figures_dir: Path,
    *,
    accessibility_table: Path | None = None,
    vmt_table: Path | None = None,
    score_table: Path | None = None,
    delta_table: Path | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    figure_paths: list[Path] = []
    fact_blocks: list[dict[str, Any]] = []

    if vmt_rows:
        path = scenario_comparison_bar(
            vmt_rows,
            metric="daily_vmt",
            figures_dir=figures_dir,
            title="Screening daily VMT by scenario",
            ylabel="Daily VMT",
            filename="vmt_by_scenario.png",
        )
        figure_paths.append(path)
        fact_blocks.append(
            figure_fact_block(
                "figure-vmt-by-scenario",
                "figure_vmt_screening",
                "Screening daily VMT per scenario visualized as a bar chart.",
                path,
                "figure.vmt_bar",
                table_path=vmt_table,
            )
        )

        trend_path = vmt_co2e_trend(vmt_rows, figures_dir)
        figure_paths.append(trend_path)
        fact_blocks.append(
            figure_fact_block(
                "figure-vmt-co2e-trend",
                "figure_vmt_co2e",
                "Dual-axis chart of daily VMT and CO2e by scenario.",
                trend_path,
                "figure.vmt_co2e_trend",
                table_path=vmt_table,
            )
        )

    if delta_rows:
        path = scenario_comparison_bar(
            delta_rows,
            metric="delta_jobs_accessible",
            figures_dir=figures_dir,
            title="Change in proxy jobs-access vs. baseline",
            ylabel="Delta jobs accessible",
            filename="access_delta_by_scenario.png",
        )
        figure_paths.append(path)
        fact_blocks.append(
            figure_fact_block(
                "figure-access-delta",
                "figure_accessibility_delta",
                "Accessibility delta vs. baseline summarized per scenario.",
                path,
                "figure.access_delta_bar",
                table_path=delta_table,
            )
        )

    if score_rows:
        path = project_score_distribution(score_rows, figures_dir)
        figure_paths.append(path)
        fact_blocks.append(
            figure_fact_block(
                "figure-project-scores",
                "figure_project_scores",
                "Top project scores from the weighted rubric.",
                path,
                "figure.project_score_bar",
                table_path=score_table,
            )
        )

    if accessibility_rows:
        scenarios = sorted({str(row["scenario_id"]) for row in accessibility_rows})
        for scenario_id in scenarios:
            path = accessibility_histogram(accessibility_rows, scenario_id, figures_dir)
            figure_paths.append(path)
            fact_blocks.append(
                figure_fact_block(
                    f"figure-access-hist-{scenario_id}",
                    "figure_accessibility_distribution",
                    f"Distribution of jobs-accessible values for scenario {scenario_id}.",
                    path,
                    "figure.access_histogram",
                    scenario_id=scenario_id,
                    table_path=accessibility_table,
                )
            )

    return figure_paths, fact_blocks
