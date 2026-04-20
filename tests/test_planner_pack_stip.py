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
    DEFAULT_STIP_CYCLE_LABEL,
    compute_stip,
    stip_fact_blocks,
    write_stip,
)
from clawmodeler_engine.qa import build_qa_report, is_valid_fact_block
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "stip"):
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


def _stage_stip_overlay(workspace: Path, run_id: str) -> Path:
    overlay_path = workspace / "inputs" / "stip_overlay.csv"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    score_path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
    )
    rows: list[dict[str, str]] = []
    phase_cycle = ["PA&ED", "PS&E", "R/W", "CON"]
    fy_cycle = ["2026-27", "2027-28", "2028-29", "2029-30"]
    region_cycle = ["north", "south"]
    source_cycle = ["RIP", "IIP", "SB1"]
    with score_path.open("r", encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            pid = row.get("project_id") or ""
            if not pid:
                continue
            rows.append(
                {
                    "project_id": pid,
                    "phase": phase_cycle[i % len(phase_cycle)],
                    "fiscal_year": fy_cycle[i % len(fy_cycle)],
                    "cost_thousands": f"{(i + 1) * 1250:.2f}",
                    "funding_source": source_cycle[i % len(source_cycle)],
                    "ppno": f"P{i:04d}" if i % 2 == 0 else "",
                    "region": region_cycle[i % len(region_cycle)],
                    "data_source_ref": f"CTC row {i}.",
                }
            )
    fieldnames = [
        "project_id",
        "phase",
        "fiscal_year",
        "cost_thousands",
        "funding_source",
        "ppno",
        "region",
        "data_source_ref",
    ]
    with overlay_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    return overlay_path


class ComputeStipTest(unittest.TestCase):
    def test_empty_rows_raise_insufficient_data(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_stip([], run_id="x", cycle_label="2026 STIP")

    def test_empty_cycle_label_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_stip(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="x",
                cycle_label="   ",
            )

    def test_unknown_phase_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_stip(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="x",
                cycle_label="2026 STIP",
                overlay_rows=[
                    {
                        "project_id": "a",
                        "phase": "mystery",
                        "fiscal_year": "2026-27",
                        "cost_thousands": "500",
                    }
                ],
            )

    def test_phase_aliases_normalize(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        overlay = [
            {
                "project_id": "a",
                "phase": "row",
                "fiscal_year": "2026-27",
                "cost_thousands": "400",
                "funding_source": "RIP",
                "region": "north",
            }
        ]
        result = compute_stip(
            score_rows,
            run_id="r",
            cycle_label="2026 STIP",
            overlay_rows=overlay,
        )
        self.assertEqual(len(result.programming_rows), 1)
        self.assertEqual(result.programming_rows[0].phase, "R/W")

    def test_unknown_region_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_stip(
                [{"project_id": "a", "name": "A", "total_score": "10"}],
                run_id="r",
                cycle_label="2026 STIP",
                region="east",
            )

    def test_missing_overlay_produces_no_rows(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        result = compute_stip(score_rows, run_id="r", cycle_label="2026 STIP")
        self.assertEqual(result.project_count, 1)
        self.assertEqual(result.programming_rows, [])
        self.assertEqual(result.summary.overlay_supplied_project_count, 0)
        self.assertEqual(result.summary.fiscal_years, [])

    def test_negative_cost_filtered(self) -> None:
        score_rows = [{"project_id": "a", "name": "A", "total_score": "10"}]
        overlay = [
            {
                "project_id": "a",
                "phase": "CON",
                "fiscal_year": "2026-27",
                "cost_thousands": "-10",
            },
            {
                "project_id": "a",
                "phase": "PA&ED",
                "fiscal_year": "2026-27",
                "cost_thousands": "500",
                "funding_source": "RIP",
            },
        ]
        result = compute_stip(
            score_rows,
            run_id="r",
            cycle_label="2026 STIP",
            overlay_rows=overlay,
        )
        self.assertEqual(len(result.programming_rows), 1)
        self.assertEqual(result.programming_rows[0].phase, "PA&ED")

    def test_portfolio_totals_aggregate_by_fy_and_source(self) -> None:
        score_rows = [
            {"project_id": "a", "name": "A", "total_score": "10"},
            {"project_id": "b", "name": "B", "total_score": "20"},
        ]
        overlay = [
            {
                "project_id": "a",
                "phase": "PA&ED",
                "fiscal_year": "2026-27",
                "cost_thousands": "1000",
                "funding_source": "RIP",
                "region": "north",
            },
            {
                "project_id": "b",
                "phase": "CON",
                "fiscal_year": "2026-27",
                "cost_thousands": "2500",
                "funding_source": "IIP",
                "region": "south",
            },
            {
                "project_id": "b",
                "phase": "R/W",
                "fiscal_year": "2027-28",
                "cost_thousands": "800",
                "funding_source": "RIP",
                "region": "south",
            },
        ]
        result = compute_stip(
            score_rows,
            run_id="r",
            cycle_label="2026 STIP",
            overlay_rows=overlay,
        )
        summary = result.summary
        assert summary is not None
        self.assertEqual(summary.fiscal_years, ["2026-27", "2027-28"])
        self.assertEqual(
            summary.total_cost_thousands_by_fiscal_year,
            {"2026-27": 3500.0, "2027-28": 800.0},
        )
        self.assertEqual(
            summary.total_cost_thousands_by_funding_source,
            {"IIP": 2500.0, "RIP": 1800.0},
        )
        self.assertEqual(summary.overlay_supplied_project_count, 2)

    def test_north_south_split_meets_target(self) -> None:
        score_rows = [
            {"project_id": f"p{i}", "name": f"P{i}", "total_score": "10"}
            for i in range(2)
        ]
        overlay = [
            {
                "project_id": "p0",
                "phase": "CON",
                "fiscal_year": "2026-27",
                "cost_thousands": "400",
                "funding_source": "RIP",
                "region": "north",
            },
            {
                "project_id": "p1",
                "phase": "CON",
                "fiscal_year": "2026-27",
                "cost_thousands": "600",
                "funding_source": "IIP",
                "region": "south",
            },
        ]
        result = compute_stip(
            score_rows,
            run_id="r",
            cycle_label="2026 STIP",
            overlay_rows=overlay,
        )
        split = result.summary.north_south_split
        self.assertAlmostEqual(split["north_share"], 0.40, places=4)
        self.assertAlmostEqual(split["south_share"], 0.60, places=4)
        self.assertTrue(split["meets_target"])


class StipFactBlockShapeTest(unittest.TestCase):
    def test_blocks_pass_is_valid_fact_block(self) -> None:
        score_rows = [{"project_id": "p1", "name": "P1", "total_score": "10"}]
        overlay = [
            {
                "project_id": "p1",
                "phase": "PA&ED",
                "fiscal_year": "2026-27",
                "cost_thousands": "750",
                "funding_source": "RIP",
                "region": "north",
                "ppno": "P0001",
            }
        ]
        result = compute_stip(
            score_rows,
            run_id="r",
            cycle_label="2026 STIP",
            overlay_rows=overlay,
        )
        blocks = stip_fact_blocks(result, Path("/tmp/stip.csv"))
        self.assertGreaterEqual(len(blocks), 2)
        fact_types = {b["fact_type"] for b in blocks}
        self.assertIn("stip_programming_row", fact_types)
        self.assertIn("stip_portfolio_summary", fact_types)
        for block in blocks:
            self.assertTrue(
                is_valid_fact_block(block),
                f"STIP fact_block failed QA validator: {block}",
            )
            self.assertEqual(block["method_ref"], "planner_pack.stip")


class WriteStipTest(unittest.TestCase):
    def test_end_to_end_without_overlay(self) -> None:
        with demo_workspace() as (workspace, run_id):
            summary = write_stip(workspace, run_id)
            self.assertGreater(summary["project_count"], 0)
            self.assertEqual(summary["programming_row_count"], 0)
            self.assertEqual(summary["overlay_supplied_project_count"], 0)
            self.assertEqual(summary["cycle_label"], DEFAULT_STIP_CYCLE_LABEL)
            self.assertTrue(Path(summary["report_path"]).exists())
            self.assertTrue(Path(summary["csv_path"]).exists())
            self.assertTrue(Path(summary["json_path"]).exists())

    def test_end_to_end_with_overlay_passes_qa_gate(self) -> None:
        with demo_workspace("qastip") as (workspace, run_id):
            _stage_stip_overlay(workspace, run_id)
            summary = write_stip(
                workspace,
                run_id,
                cycle_label="2026 STIP",
            )
            self.assertGreater(summary["programming_row_count"], 0)
            report_text = Path(summary["report_path"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("S&HC §188", report_text)
            self.assertIn("CTC STIP Guidelines", report_text)
            payload = json.loads(
                Path(summary["json_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["cycle_label"], "2026 STIP")

            qa = build_qa_report(workspace, run_id)
            self.assertTrue(qa["export_ready"])
            self.assertEqual(qa["blockers"], [])

    def test_idempotent_append(self) -> None:
        with demo_workspace("idemstip") as (workspace, run_id):
            _stage_stip_overlay(workspace, run_id)
            first = write_stip(workspace, run_id)
            second = write_stip(workspace, run_id)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_stip(workspace, "no-such-run")


if __name__ == "__main__":
    unittest.main()
