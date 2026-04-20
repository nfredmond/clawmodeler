from __future__ import annotations

import csv
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from clawmodeler_engine.contracts import (
    CURRENT_MANIFEST_VERSION,
    LEGACY_MANIFEST_VERSIONS,
    validate_contract,
)
from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.diff import write_run_diff
from clawmodeler_engine.model import DEFAULT_SCORING_WEIGHTS, _resolve_scoring_weights
from clawmodeler_engine.orchestration import (
    write_export,
    write_intake,
    write_plan,
    write_run,
)
from clawmodeler_engine.planner_pack import write_ceqa_vmt
from clawmodeler_engine.qa import build_qa_report, is_valid_fact_block
from clawmodeler_engine.what_if import (
    WhatIfOverrides,
    _what_if_summary_claim,
    compute_what_if,
    what_if_fact_blocks,
    write_what_if,
)
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


def _read_scores(workspace: Path, run_id: str) -> list[dict[str, str]]:
    path = workspace / "runs" / run_id / "outputs" / "tables" / "project_scores.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


class WhatIfOverrideValidationTest(unittest.TestCase):
    def test_default_weights_constant_matches_pre_refactor_values(self) -> None:
        self.assertEqual(
            DEFAULT_SCORING_WEIGHTS,
            {"safety": 0.30, "equity": 0.25, "climate": 0.25, "feasibility": 0.20},
        )

    def test_resolve_weights_rejects_sub_unity_sum(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_scoring_weights(
                {"safety": 0.25, "equity": 0.25, "climate": 0.25, "feasibility": 0.20}
            )

    def test_resolve_weights_rejects_missing_keys(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_scoring_weights({"safety": 0.5, "equity": 0.5})

    def test_empty_overrides_rejected(self) -> None:
        with self.assertRaises(InsufficientDataError):
            with demo_workspace() as (workspace, base):
                write_what_if(workspace, base, "alt", WhatIfOverrides())

    def test_invalid_threshold_rejected(self) -> None:
        with self.assertRaises(ValueError):
            with demo_workspace() as (workspace, base):
                write_what_if(
                    workspace, base, "alt",
                    WhatIfOverrides(threshold_pct=1.5),
                )

    def test_invalid_sensitivity_floor_rejected(self) -> None:
        with self.assertRaises(ValueError):
            with demo_workspace() as (workspace, base):
                write_what_if(
                    workspace, base, "alt",
                    WhatIfOverrides(sensitivity_floor="URGENT"),
                )

    def test_include_exclude_overlap_rejected(self) -> None:
        with self.assertRaises(ValueError):
            with demo_workspace() as (workspace, base):
                write_what_if(
                    workspace, base, "alt",
                    WhatIfOverrides(
                        project_ids_include=["p1", "p2"],
                        project_ids_exclude=["p2"],
                    ),
                )


class WhatIfRunCreationTest(unittest.TestCase):
    def test_base_run_not_found_raises(self) -> None:
        with demo_workspace() as (workspace, _base):
            with self.assertRaises(InsufficientDataError):
                write_what_if(
                    workspace,
                    "not-a-run",
                    "alt",
                    WhatIfOverrides(
                        scoring_weights={
                            "safety": 0.40, "equity": 0.30,
                            "climate": 0.20, "feasibility": 0.10,
                        }
                    ),
                )

    def test_new_run_id_collision_raises(self) -> None:
        with demo_workspace() as (workspace, base):
            with self.assertRaises(InsufficientDataError):
                write_what_if(
                    workspace, base, base,
                    WhatIfOverrides(threshold_pct=0.10),
                )

    def test_same_base_and_new_id_raises_value_error(self) -> None:
        with demo_workspace() as (workspace, base):
            with self.assertRaises((ValueError, InsufficientDataError)):
                compute_what_if(
                    workspace, base,
                    WhatIfOverrides(threshold_pct=0.10),
                    new_run_id=base,
                )

    def test_weight_override_shifts_scores(self) -> None:
        with demo_workspace() as (workspace, base):
            base_scores = _read_scores(workspace, base)
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.70, "equity": 0.10,
                        "climate": 0.10, "feasibility": 0.10,
                    },
                ),
            )
            new_scores = _read_scores(workspace, "alt")
            self.assertEqual(
                {row["project_id"] for row in base_scores},
                {row["project_id"] for row in new_scores},
            )
            any_shifted = False
            base_lookup = {r["project_id"]: float(r["total_score"]) for r in base_scores}
            for row in new_scores:
                if abs(float(row["total_score"]) - base_lookup[row["project_id"]]) > 1e-6:
                    any_shifted = True
                    break
            self.assertTrue(
                any_shifted,
                "Extreme weight shift must produce at least one score delta",
            )

    def test_project_exclude_filter(self) -> None:
        with demo_workspace() as (workspace, base):
            base_scores = _read_scores(workspace, base)
            drop_id = base_scores[0]["project_id"]
            _, result = write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(project_ids_exclude=[drop_id]),
            )
            new_scores = _read_scores(workspace, "alt")
            self.assertNotIn(
                drop_id, {row["project_id"] for row in new_scores}
            )
            self.assertIn(drop_id, result.dropped_project_ids)

    def test_project_include_filter(self) -> None:
        with demo_workspace() as (workspace, base):
            base_scores = _read_scores(workspace, base)
            keep_id = base_scores[0]["project_id"]
            _, _result = write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(project_ids_include=[keep_id]),
            )
            new_scores = _read_scores(workspace, "alt")
            self.assertEqual(
                [row["project_id"] for row in new_scores], [keep_id]
            )

    def test_idempotent_rerun_collision(self) -> None:
        with demo_workspace() as (workspace, base):
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(threshold_pct=0.10),
            )
            with self.assertRaises(InsufficientDataError):
                write_what_if(
                    workspace, base, "alt",
                    WhatIfOverrides(threshold_pct=0.10),
                )


class WhatIfQaGateTest(unittest.TestCase):
    def test_new_run_passes_qa_gate(self) -> None:
        with demo_workspace() as (workspace, base):
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.40, "equity": 0.30,
                        "climate": 0.20, "feasibility": 0.10,
                    }
                ),
            )
            report = build_qa_report(workspace, "alt")
            self.assertTrue(report["export_ready"])
            self.assertEqual(report["blockers"], [])

    def test_fact_blocks_pass_validator(self) -> None:
        with demo_workspace() as (workspace, base):
            _, result = write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(threshold_pct=0.10),
            )
            path = (
                workspace
                / "runs"
                / "alt"
                / "outputs"
                / "tables"
                / "fact_blocks.jsonl"
            )
            blocks = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            what_if_blocks = [
                b for b in blocks
                if b.get("fact_type", "").startswith("what_if_")
            ]
            self.assertGreater(len(what_if_blocks), 0)
            for block in what_if_blocks:
                self.assertTrue(
                    is_valid_fact_block(block),
                    f"what-if fact_block failed QA validator: {block}",
                )


class WhatIfComposesWithExistingFeaturesTest(unittest.TestCase):
    def test_end_to_end_chain_with_planner_pack_and_diff_and_export(self) -> None:
        with demo_workspace() as (workspace, base):
            write_ceqa_vmt(workspace, base)
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.50, "equity": 0.20,
                        "climate": 0.20, "feasibility": 0.10,
                    },
                ),
            )
            write_ceqa_vmt(workspace, "alt")
            write_run_diff(workspace, base, "alt")
            export_path = write_export(workspace, "alt", "md")
            self.assertTrue(Path(export_path).exists())
            qa = build_qa_report(workspace, "alt")
            self.assertTrue(qa["export_ready"])

    def test_diff_against_what_if_has_run_diff_rows(self) -> None:
        with demo_workspace() as (workspace, base):
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(
                    scoring_weights={
                        "safety": 0.70, "equity": 0.10,
                        "climate": 0.10, "feasibility": 0.10,
                    },
                ),
            )
            summary = write_run_diff(workspace, base, "alt")
            self.assertGreater(summary["totals"]["changed"], 0)


class ManifestSchemaRoundTripTest(unittest.TestCase):
    def test_new_manifest_has_1_2_0_with_base_run_id_and_overrides(self) -> None:
        with demo_workspace() as (workspace, base):
            write_what_if(
                workspace, base, "alt",
                WhatIfOverrides(threshold_pct=0.10),
            )
            manifest_path = workspace / "runs" / "alt" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["manifest_version"], CURRENT_MANIFEST_VERSION
            )
            self.assertEqual(manifest["manifest_version"], "1.2.0")
            self.assertEqual(manifest["base_run_id"], base)
            self.assertEqual(manifest["overrides"], {"threshold_pct": 0.10})
            self.assertIn("detailed_engine_readiness", manifest)
            validate_contract(manifest, "run_manifest")

    def test_legacy_1_0_0_manifest_still_validates(self) -> None:
        self.assertIn("1.0.0", LEGACY_MANIFEST_VERSIONS)
        with demo_workspace() as (workspace, base):
            manifest_path = workspace / "runs" / base / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # simulate a legacy run by re-stamping the version field
            manifest["manifest_version"] = "1.0.0"
            validate_contract(manifest, "run_manifest")


class FactBlockShapeTest(unittest.TestCase):
    def test_summary_claim_mentions_base_and_new(self) -> None:
        overrides = WhatIfOverrides(
            scoring_weights={
                "safety": 0.40, "equity": 0.30,
                "climate": 0.20, "feasibility": 0.10,
            }
        )
        with demo_workspace() as (workspace, base):
            _, result = write_what_if(workspace, base, "alt", overrides)
            claim = _what_if_summary_claim(result)
            self.assertIn("alt", claim)
            self.assertIn(base, claim)

    def test_fact_blocks_helper_emits_method_ref_and_artifact_refs(self) -> None:
        overrides = WhatIfOverrides(threshold_pct=0.10)
        with demo_workspace() as (workspace, base):
            _, result = write_what_if(workspace, base, "alt", overrides)
            path = (
                workspace
                / "runs"
                / "alt"
                / "outputs"
                / "tables"
                / "project_scores.csv"
            )
            blocks = what_if_fact_blocks(result, path)
            self.assertGreater(len(blocks), 0)
            for block in blocks:
                self.assertEqual(
                    block["method_ref"], "what_if.parameter_override"
                )
                self.assertIsInstance(block["artifact_refs"], list)
                self.assertGreater(len(block["artifact_refs"]), 0)


if __name__ == "__main__":
    unittest.main()
