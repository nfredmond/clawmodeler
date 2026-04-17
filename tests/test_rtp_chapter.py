from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.orchestration import write_intake, write_plan, write_run
from clawmodeler_engine.planner_pack import (
    compute_rtp_chapter,
    rtp_chapter_fact_blocks,
    write_ceqa_vmt,
    write_lapm_exhibit,
    write_rtp_chapter,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "rtp"):
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


class ComputeRtpChapterTest(unittest.TestCase):
    def _score_row(self, project_id: str, total: float) -> dict:
        return {
            "project_id": project_id,
            "name": project_id.title(),
            "safety_score": "50",
            "equity_score": "50",
            "climate_score": "50",
            "feasibility_score": "50",
            "total_score": str(total),
            "sensitivity_flag": "LOW",
        }

    def _vmt_row(self, scenario_id: str, population: float, daily_vmt: float) -> dict:
        return {
            "scenario_id": scenario_id,
            "population": str(population),
            "daily_vmt": str(daily_vmt),
        }

    def test_basic_chapter_composition(self) -> None:
        result = compute_rtp_chapter(
            [self._score_row("p1", 72.5), self._score_row("p2", 60.0)],
            [
                self._vmt_row("baseline", 1000, 22000),
                self._vmt_row("build", 1200, 27600),
            ],
            run_id="r1",
            agency="NCTC",
            rtp_cycle="2026 RTP",
        )
        self.assertEqual(result.agency, "NCTC")
        self.assertEqual(result.rtp_cycle, "2026 RTP")
        self.assertEqual(len(result.projects), 2)
        self.assertEqual(len(result.scenarios), 2)
        by_scenario = {s.scenario_id: s for s in result.scenarios}
        self.assertAlmostEqual(by_scenario["baseline"].vmt_per_capita, 22.0)
        self.assertAlmostEqual(by_scenario["build"].vmt_per_capita, 23.0)
        self.assertEqual(by_scenario["baseline"].ceqa_determination, "not screened")

    def test_ceqa_enrichment_applies(self) -> None:
        result = compute_rtp_chapter(
            [self._score_row("p1", 50)],
            [self._vmt_row("baseline", 1000, 22000)],
            run_id="r1",
            ceqa_rows=[
                {
                    "scenario_id": "baseline",
                    "determination": "potentially significant",
                    "threshold_vmt_per_capita": "18.7",
                }
            ],
        )
        self.assertEqual(
            result.scenarios[0].ceqa_determination, "potentially significant"
        )
        self.assertEqual(result.scenarios[0].ceqa_threshold_vmt_per_capita, 18.7)

    def test_lapm_enrichment_applies(self) -> None:
        result = compute_rtp_chapter(
            [self._score_row("p1", 50)],
            [self._vmt_row("baseline", 1000, 22000)],
            run_id="r1",
            lapm_rows=[
                {
                    "project_id": "p1",
                    "project_type": "Active Transportation",
                    "estimated_cost_usd": "2500000",
                    "location_note": "38.001, -121.002",
                }
            ],
        )
        project = result.projects[0]
        self.assertEqual(project.lapm_project_type, "Active Transportation")
        self.assertEqual(project.lapm_estimated_cost_usd, 2500000.0)
        self.assertEqual(project.lapm_location, "38.001, -121.002")

    def test_delta_rows_aggregate_across_zones(self) -> None:
        result = compute_rtp_chapter(
            [self._score_row("p1", 50)],
            [self._vmt_row("build", 1000, 22000)],
            run_id="r1",
            delta_rows=[
                {"scenario_id": "build", "delta_jobs_accessible": "100"},
                {"scenario_id": "build", "delta_jobs_accessible": "250"},
                {"scenario_id": "other", "delta_jobs_accessible": "999"},
            ],
        )
        build = next(s for s in result.scenarios if s.scenario_id == "build")
        self.assertEqual(build.accessibility_delta_jobs, 350.0)

    def test_zero_population_vmt_per_capita_none(self) -> None:
        result = compute_rtp_chapter(
            [self._score_row("p1", 50)],
            [self._vmt_row("empty", 0, 0)],
            run_id="r1",
        )
        self.assertIsNone(result.scenarios[0].vmt_per_capita)

    def test_empty_scores_raise(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_rtp_chapter([], [self._vmt_row("b", 1000, 100)], run_id="r1")

    def test_empty_vmt_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_rtp_chapter([self._score_row("p1", 50)], [], run_id="r1")

    def test_all_empty_project_ids_raises(self) -> None:
        with self.assertRaises(InsufficientDataError):
            compute_rtp_chapter(
                [{"project_id": "", "name": "nope"}],
                [self._vmt_row("b", 1, 1)],
                run_id="r1",
            )


class RtpFactBlocksTest(unittest.TestCase):
    def test_fact_blocks_cover_projects_and_scenarios(self) -> None:
        result = compute_rtp_chapter(
            [
                {
                    "project_id": "p1",
                    "name": "Complete Streets",
                    "total_score": "75",
                    "sensitivity_flag": "LOW",
                }
            ],
            [{"scenario_id": "baseline", "population": "1000", "daily_vmt": "22000"}],
            run_id="r1",
            agency="NCTC",
            rtp_cycle="2026 RTP",
        )
        blocks = rtp_chapter_fact_blocks(result, Path("/tmp/rtp.csv"))
        self.assertEqual(len(blocks), 2)
        project_block = next(b for b in blocks if b["fact_id"].startswith("rtp-project-"))
        scenario_block = next(b for b in blocks if b["fact_id"].startswith("rtp-scenario-"))
        self.assertIn("75.0/100", project_block["claim_text"])
        self.assertIn("NCTC 2026 RTP", project_block["claim_text"])
        self.assertIn("22.0 VMT per capita", scenario_block["claim_text"])
        self.assertIn("CEQA §15064.3 screening not yet run", scenario_block["claim_text"])


class WriteRtpChapterTest(unittest.TestCase):
    def test_end_to_end_without_prior_planner_pack(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            before = fact_blocks_path.read_text(encoding="utf-8").count("\n")

            summary = write_rtp_chapter(
                workspace,
                run_id,
                agency="NCTC",
                rtp_cycle="2026 RTP",
            )

            self.assertGreater(summary["project_count"], 0)
            self.assertGreater(summary["scenario_count"], 0)
            self.assertGreater(summary["fact_block_count"], 0)
            for key in ("projects_csv_path", "scenarios_csv_path", "json_path", "report_path"):
                self.assertTrue(Path(summary[key]).exists())

            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertIn("NCTC", report_text)
            self.assertIn("2026 RTP", report_text)
            self.assertIn("CEQA §15064.3 screening has not been run", report_text)

            after = fact_blocks_path.read_text(encoding="utf-8").count("\n")
            self.assertGreater(after, before)

    def test_end_to_end_with_ceqa_and_lapm_enrichment(self) -> None:
        with demo_workspace() as (workspace, run_id):
            write_ceqa_vmt(workspace, run_id, reference_vmt_per_capita=22.0)
            write_lapm_exhibit(
                workspace,
                run_id,
                lead_agency="NCTC",
                district="District 3",
            )

            summary = write_rtp_chapter(
                workspace, run_id, agency="NCTC", rtp_cycle="2026 RTP"
            )
            payload = json.loads(Path(summary["json_path"]).read_text(encoding="utf-8"))
            scenarios = {s["scenario_id"]: s for s in payload["scenarios"]}
            for scenario in scenarios.values():
                self.assertIn(
                    scenario["ceqa_determination"],
                    {"potentially significant", "less than significant"},
                )

            report_text = Path(summary["report_path"]).read_text(encoding="utf-8")
            self.assertNotIn("CEQA §15064.3 screening has not been run", report_text)

    def test_missing_run_raises(self) -> None:
        with demo_workspace() as (workspace, _run_id):
            with self.assertRaises(InsufficientDataError):
                write_rtp_chapter(workspace, "no-such-run")

    def test_idempotent_fact_block_append(self) -> None:
        with demo_workspace() as (workspace, run_id):
            first = write_rtp_chapter(workspace, run_id)
            second = write_rtp_chapter(workspace, run_id)
            self.assertGreater(first["fact_block_count"], 0)
            self.assertEqual(second["fact_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
