from __future__ import annotations

import csv
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    CMAQ_ALLOWED_POLLUTANTS,
    cmaq_fact_blocks,
    compute_cmaq,
    write_cmaq,
)
from clawmodeler_engine.qa import build_qa_report, is_valid_fact_block
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "cmaq"):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs = write_demo_inputs(root)
        workspace = root / "workspace"
        write_intake(
            workspace,
            [
                inputs["zones"],
                inputs["socio"],
                inputs["projects"],
                inputs["network_edges"],
                inputs["gtfs"],
            ],
        )
        write_plan(workspace, inputs["question"])
        write_run(workspace, run_id, ["baseline", "infill-growth"])
        yield workspace, run_id


def _stage_cmaq_overlay(workspace: Path, run_id: str) -> Path:
    overlay_path = workspace / "inputs" / "cmaq_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    score_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
    )
    rows: list[dict[str, str]] = []
    pollutant_cycle = ["pm2_5", "nox", "pm10", "voc", "co"]
    with score_path.open("r", encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            pid = row.get("project_id") or ""
            if not pid:
                continue
            pollutant = pollutant_cycle[i % len(pollutant_cycle)]
            rows.append(
                {
                    "project_id": pid,
                    "pollutant": pollutant,
                    "kg_per_day_reduced": f"{0.3 + i * 0.2:.3f}",
                    "cost_effectiveness_usd_per_kg": f"{50_000 + i * 10_000:.2f}",
                    "eligibility_category": (
                        "Transit service / expansion"
                        if pollutant in ("pm2_5", "nox")
                        else "Diesel retrofit"
                    ),
                    "nonattainment_area": (
                        "San Joaquin Valley PM2.5"
                        if pollutant == "pm2_5"
                        else "Sacramento Metro ozone"
                    ),
                    "data_source_ref": f"SJVAPCD tool row {i}.",
                }
            )
    fieldnames = [
        "project_id",
        "pollutant",
        "kg_per_day_reduced",
        "cost_effectiveness_usd_per_kg",
        "eligibility_category",
        "nonattainment_area",
        "data_source_ref",
    ]
    with overlay_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    return overlay_path


class ComputeCmaqTest(unittest.TestCase):
    def test_empty_rows_raise_insufficient_data(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_cmaq([], run_id="x", analysis_year=2027)

    def test_invalid_analysis_year_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_cmaq(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="x",
                analysis_year=0,
            )

    def test_unknown_pollutant_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_cmaq(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="x",
                analysis_year=2027,
                pollutants=["methane"],
            )

    def test_pollutant_aliases_normalize(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        overlay = [
            {
                "project_id": "a",
                "pollutant": "PM2.5",
                "kg_per_day_reduced": "1.0",
            }
        ]
        result = compute_cmaq(
            score_rows,
            run_id="r",
            analysis_year=2027,
            pollutants=["PM2.5"],
            overlay_rows=overlay,
        )
        self.assertEqual(result.pollutants, ["pm2_5"])
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].pollutant, "pm2_5")

    def test_filter_excludes_unselected_pollutants(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        overlay = [
            {"project_id": "a", "pollutant": "pm2_5", "kg_per_day_reduced": "1.0"},
            {"project_id": "a", "pollutant": "nox", "kg_per_day_reduced": "2.0"},
        ]
        result = compute_cmaq(
            score_rows,
            run_id="r",
            analysis_year=2027,
            pollutants=["pm2_5"],
            overlay_rows=overlay,
        )
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].pollutant, "pm2_5")
        self.assertEqual(
            result.summary.total_kg_per_day_by_pollutant, {"pm2_5": 1.0}
        )

    def test_missing_overlay_produces_no_estimates(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        result = compute_cmaq(score_rows, run_id="r", analysis_year=2027)
        self.assertEqual(result.project_count, 1)
        self.assertEqual(result.estimates, [])
        self.assertEqual(result.summary.overlay_supplied_project_count, 0)

    def test_negative_kg_ignored(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        overlay = [
            {"project_id": "a", "pollutant": "pm2_5", "kg_per_day_reduced": "-1.0"},
            {"project_id": "a", "pollutant": "nox", "kg_per_day_reduced": "3.0"},
        ]
        result = compute_cmaq(
            score_rows,
            run_id="r",
            analysis_year=2027,
            overlay_rows=overlay,
        )
        self.assertEqual(len(result.estimates), 1)
        self.assertEqual(result.estimates[0].pollutant, "nox")

    def test_portfolio_totals_aggregate_by_pollutant(self) -> None:
        score_rows = [
            {"project_id": "a", "name": "A", "total_score": "10"},
            {"project_id": "b", "name": "B", "total_score": "20"},
        ]
        overlay = [
            {
                "project_id": "a",
                "pollutant": "nox",
                "kg_per_day_reduced": "2.0",
                "cost_effectiveness_usd_per_kg": "40000",
                "eligibility_category": "Transit service / expansion",
            },
            {
                "project_id": "b",
                "pollutant": "nox",
                "kg_per_day_reduced": "3.5",
                "cost_effectiveness_usd_per_kg": "60000",
                "eligibility_category": "Diesel retrofit",
            },
        ]
        result = compute_cmaq(
            score_rows,
            run_id="r",
            analysis_year=2027,
            overlay_rows=overlay,
        )
        summary = result.summary
        assert summary is not None
        self.assertEqual(summary.total_kg_per_day_by_pollutant["nox"], 5.5)
        self.assertEqual(
            summary.mean_cost_effectiveness_usd_per_kg_by_pollutant["nox"],
            50000.0,
        )
        self.assertEqual(summary.overlay_supplied_project_count, 2)
        self.assertEqual(
            set(summary.eligibility_categories),
            {"Transit service / expansion", "Diesel retrofit"},
        )


class CmaqFactBlockShapeTest(unittest.TestCase):
    def test_blocks_pass_is_valid_fact_block(self) -> None:
        score_rows = [{"project_id": "p1", "name": "P1", "total_score": "10"}]
        overlay = [
            {
                "project_id": "p1",
                "pollutant": "pm2_5",
                "kg_per_day_reduced": "1.0",
                "cost_effectiveness_usd_per_kg": "30000",
                "eligibility_category": "Transit service / expansion",
            }
        ]
        result = compute_cmaq(
            score_rows,
            run_id="r",
            analysis_year=2027,
            overlay_rows=overlay,
        )
        blocks = cmaq_fact_blocks(result, Path("/tmp/cmaq.csv"))
        self.assertGreaterEqual(len(blocks), 2)
        fact_types = {b["fact_type"] for b in blocks}
        self.assertIn("cmaq_emissions_estimate", fact_types)
        self.assertIn("cmaq_portfolio_summary", fact_types)
        for block in blocks:
            self.assertTrue(
                is_valid_fact_block(block),
                f"CMAQ fact_block failed QA validator: {block}",
            )
            self.assertEqual(block["method_ref"], "planner_pack.cmaq")


class WriteCmaqTest(unittest.TestCase):
    def test_end_to_end_without_overlay(self) -> None:
        with demo_workspace() as (workspace, run_id):
            summary = write_cmaq(workspace, run_id, analysis_year=2027)
            self.assertGreater(summary["project_count"], 0)
            self.assertEqual(summary["estimate_count"], 0)
            self.assertEqual(summary["overlay_supplied_project_count"], 0)
            self.assertEqual(
                sorted(summary["pollutants"]), sorted(CMAQ_ALLOWED_POLLUTANTS)
            )
            self.assertTrue(Path(summary["report_path"]).exists())
            self.assertTrue(Path(summary["csv_path"]).exists())
            self.assertTrue(Path(summary["json_path"]).exists())

    def test_end_to_end_with_overlay_passes_qa_gate(self) -> None:
        with demo_workspace("qacmaq") as (workspace, run_id):
            _stage_cmaq_overlay(workspace, run_id)
            summary = write_cmaq(
                workspace,
                run_id,
                analysis_year=2027,
                pollutants=["pm2_5", "nox", "pm10", "voc", "co"],
            )
            self.assertGreater(summary["estimate_count"], 0)
            report_text = Path(summary["report_path"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("23 USC 149", report_text)
            self.assertIn("CMAQ Reference Guide", report_text)
            payload = json.loads(
                Path(summary["json_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["analysis_year"], 2027)

            qa = build_qa_report(workspace, run_id)
            self.assertTrue(qa["export_ready"])
            self.assertEqual(qa["blockers"], [])

    def test_idempotent_append(self) -> None:
        with demo_workspace("idem") as (workspace, run_id):
            _stage_cmaq_overlay(workspace, run_id)
            first = write_cmaq(workspace, run_id, analysis_year=2027)
            second = write_cmaq(workspace, run_id, analysis_year=2027)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_cmaq(workspace, "no-such-run", analysis_year=2027)


if __name__ == "__main__":
    unittest.main()
