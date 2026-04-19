from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from clawmodeler_engine.cli import build_parser
from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import write_equity_lens
from clawmodeler_engine.portfolio import (
    compute_portfolio,
    list_runs,
    portfolio_fact_blocks,
    write_portfolio,
)
from clawmodeler_engine.qa import is_valid_fact_block
from clawmodeler_engine.what_if import WhatIfOverrides, write_what_if
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "base"):
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


def _stage_equity_overlay(workspace: Path) -> None:
    overlay = workspace / "inputs" / "equity_overlay.csv"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    # Seed three project_ids with DAC flags; project_scores.csv in the
    # demo workspace has more rows, the rest will be classified Unknown.
    with overlay.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "project_id",
                "dac_sb535",
                "low_income_ab1550",
                "low_income_near_dac",
                "tribal_area",
                "ces_percentile",
                "notes",
            ],
        )
        writer.writeheader()
        scores_csv = (
            workspace / "runs"
        ).glob("*/outputs/tables/project_scores.csv")
        first = next(scores_csv, None)
        if first is None:
            return
        with first.open("r", encoding="utf-8-sig", newline="") as src:
            reader = csv.DictReader(src)
            for index, row in enumerate(reader):
                pid = row["project_id"]
                writer.writerow(
                    {
                        "project_id": pid,
                        "dac_sb535": "true" if index == 0 else "false",
                        "low_income_ab1550": "false",
                        "low_income_near_dac": "false",
                        "tribal_area": "false",
                        "ces_percentile": "",
                        "notes": "",
                    }
                )


class PortfolioEmptyWorkspaceTest(unittest.TestCase):
    def test_empty_workspace_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            with self.assertRaises(InsufficientDataError):
                compute_portfolio(workspace)

    def test_list_runs_returns_empty_list_on_missing_runs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self.assertEqual(list_runs(workspace), [])


class PortfolioSingleRunTest(unittest.TestCase):
    def test_single_run_summary_has_kpis(self) -> None:
        with demo_workspace("alpha") as (workspace, run_id):
            result = compute_portfolio(workspace)
            self.assertEqual(result.run_count, 1)
            run = result.runs[0]
            self.assertEqual(run.run_id, run_id)
            self.assertEqual(run.base_run_id, None)
            self.assertGreater(run.project_count, 0)
            self.assertIsNotNone(run.mean_total_score)
            self.assertIsNotNone(run.top_project_id)
            self.assertTrue(run.export_ready)
            self.assertEqual(run.has_what_if_overrides, False)

    def test_single_run_has_no_planner_pack_yet(self) -> None:
        with demo_workspace("alpha") as (workspace, _):
            result = compute_portfolio(workspace)
            self.assertEqual(result.runs[0].planner_pack_artifacts, [])
            self.assertIsNone(result.runs[0].dac_share)


class PortfolioWithPlannerPackTest(unittest.TestCase):
    def test_equity_lens_populates_dac_share_and_artifact_label(self) -> None:
        with demo_workspace("alpha") as (workspace, run_id):
            _stage_equity_overlay(workspace)
            write_equity_lens(workspace, run_id, agency="Test RTPA")
            result = compute_portfolio(workspace)
            run = result.runs[0]
            self.assertIn("equity_lens", run.planner_pack_artifacts)
            self.assertIsNotNone(run.dac_share)


class PortfolioLineageTest(unittest.TestCase):
    def test_what_if_run_surfaces_base_run_id(self) -> None:
        with demo_workspace("alpha") as (workspace, base_id):
            write_what_if(
                workspace,
                base_id,
                "alpha-safety",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.50,
                        "equity": 0.20,
                        "climate": 0.20,
                        "feasibility": 0.10,
                    }
                ),
            )
            result = compute_portfolio(workspace)
            self.assertEqual(result.run_count, 2)
            what_if_row = next(
                r for r in result.runs if r.run_id == "alpha-safety"
            )
            self.assertEqual(what_if_row.base_run_id, base_id)
            self.assertTrue(what_if_row.has_what_if_overrides)
            self.assertEqual(
                result.summary.lineage_edges,
                [{"from": base_id, "to": "alpha-safety"}],
            )


class PortfolioWritePersistsArtifactsTest(unittest.TestCase):
    def test_write_portfolio_creates_csv_json_report_factblocks(self) -> None:
        with demo_workspace("alpha") as (workspace, _):
            summary = write_portfolio(workspace)
            self.assertTrue(Path(summary["csv_path"]).exists())
            self.assertTrue(Path(summary["json_path"]).exists())
            self.assertTrue(Path(summary["report_path"]).exists())
            self.assertTrue(Path(summary["fact_blocks_path"]).exists())
            self.assertGreater(summary["fact_block_count"], 0)
            with open(summary["csv_path"], newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "alpha")

    def test_fact_blocks_pass_qa_gate_schema(self) -> None:
        with demo_workspace("alpha") as (workspace, _):
            result = compute_portfolio(workspace)
            blocks = portfolio_fact_blocks(result, workspace / "portfolio" / "summary.csv")
            self.assertGreater(len(blocks), 0)
            for block in blocks:
                self.assertTrue(is_valid_fact_block(block))
                self.assertEqual(block["method_ref"], "portfolio.run_summary")
                self.assertEqual(block["artifact_refs"][0]["type"], "table")


class PortfolioSkipsInvalidRunTest(unittest.TestCase):
    def test_directory_without_manifest_is_ignored(self) -> None:
        with demo_workspace("alpha") as (workspace, _):
            (workspace / "runs" / "scratch").mkdir()
            result = compute_portfolio(workspace)
            run_ids = {r.run_id for r in result.runs}
            self.assertEqual(run_ids, {"alpha"})


class PortfolioCliTest(unittest.TestCase):
    def test_cli_portfolio_subcommand_produces_json(self) -> None:
        with demo_workspace("alpha") as (workspace, _):
            parser = build_parser()
            args = parser.parse_args(
                ["portfolio", "--workspace", str(workspace), "--json"]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                args.func(args)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["run_count"], 1)
            self.assertTrue(Path(payload["csv_path"]).exists())


if __name__ == "__main__":
    unittest.main()
