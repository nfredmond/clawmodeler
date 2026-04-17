from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.llm import (
    FakeProvider,
    GroundingMode,
    build_narrative_prompt,
    generate_narrative,
    save_config,
)
from clawmodeler_engine.llm.config import LLMConfig
from clawmodeler_engine.orchestration import (
    write_export,
    write_intake,
    write_plan,
    write_run,
)
from clawmodeler_engine.workspace import InsufficientDataError, QaGateBlockedError


@contextmanager
def demo_workspace(run_id: str = "ai"):
    """Set up a full demo workspace with a finished run in-process."""
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


def _fact_ids_from_run(workspace: Path, run_id: str) -> list[str]:
    path = (
        workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
    )
    ids: list[str] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.append(json.loads(line)["fact_id"])
    return ids


class BuildNarrativePromptTest(unittest.TestCase):
    def test_prompt_lists_every_fact_id(self) -> None:
        manifest = {"run_id": "r1", "scenarios": [{"scenario_id": "baseline"}]}
        fact_blocks = [
            {
                "fact_id": "vmt_s1",
                "fact_type": "vmt_screening",
                "scenario_id": "baseline",
                "claim_text": "Daily VMT is 1,000.",
            },
            {
                "fact_id": "acc_s1",
                "fact_type": "accessibility_delta",
                "scenario_id": "build",
                "claim_text": "Jobs access improves.",
            },
        ]
        prompt = build_narrative_prompt(manifest, fact_blocks)
        self.assertIn("[fact:<fact_id>]", prompt)
        self.assertIn("fact_id='vmt_s1'", prompt)
        self.assertIn("fact_id='acc_s1'", prompt)
        self.assertIn("Run ID: r1", prompt)
        self.assertIn("Scenarios: baseline", prompt)

    def test_prompt_handles_empty_facts(self) -> None:
        prompt = build_narrative_prompt({"run_id": "r1"}, [])
        self.assertIn("no fact_blocks available", prompt)


class GenerateNarrativeUnitTest(unittest.TestCase):
    def test_provider_called_once_and_result_populated(self) -> None:
        fact_blocks = [
            {"fact_id": "vmt_s1", "fact_type": "vmt_screening", "claim_text": "x"},
        ]
        provider = FakeProvider(
            canned_text="VMT is steady. [fact:vmt_s1]", model="fake-m"
        )
        result = generate_narrative(
            {"run_id": "r"}, fact_blocks, provider, mode=GroundingMode.STRICT
        )
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.model, "fake-m")
        self.assertTrue(result.is_fully_grounded)
        self.assertEqual(result.ungrounded_sentence_count, 0)
        self.assertIn("[fact:vmt_s1]", result.text)

    def test_strict_mode_drops_ungrounded(self) -> None:
        fact_blocks = [
            {"fact_id": "vmt_s1", "fact_type": "vmt_screening", "claim_text": "x"},
        ]
        provider = FakeProvider(
            canned_text=(
                "Grounded claim. [fact:vmt_s1] "
                "Ungrounded claim with no citation."
            ),
            model="fake-m",
        )
        result = generate_narrative({}, fact_blocks, provider)
        self.assertFalse(result.is_fully_grounded)
        self.assertEqual(result.ungrounded_sentence_count, 1)
        self.assertNotIn("no citation", result.text)

    def test_unknown_fact_id_is_recorded(self) -> None:
        fact_blocks = [
            {"fact_id": "vmt_s1", "fact_type": "vmt_screening", "claim_text": "x"},
        ]
        provider = FakeProvider(
            canned_text="Claim cites a nonexistent fact. [fact:not_real]",
            model="fake-m",
        )
        result = generate_narrative({}, fact_blocks, provider)
        self.assertFalse(result.is_fully_grounded)
        self.assertIn("not_real", result.unknown_fact_ids)


class AiNarrativeEndToEndTest(unittest.TestCase):
    def test_grounded_narrative_renders_and_qa_passes(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            self.assertGreater(len(fact_ids), 0)
            fid, fid2 = fact_ids[0], fact_ids[1]
            provider = FakeProvider(
                canned_text=(
                    f"The baseline VMT comes in low. [fact:{fid}] "
                    f"Build scenario jobs access improves. [fact:{fid2}]"
                ),
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                report_path = write_export(
                    workspace,
                    run_id,
                    "md",
                    report_type="technical",
                    ai_narrative=True,
                )

            content = Path(report_path).read_text(encoding="utf-8")
            self.assertIn("## Narrative summary", content)
            self.assertIn(f"[fact:{fid}]", content)
            self.assertIn("AI-generated narrative", content)
            self.assertIn("fake/canned-test", content)

            qa = json.loads(
                (workspace / "runs" / run_id / "qa_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(qa["export_ready"])
            self.assertTrue(qa["checks"]["ai_narrative_grounded"])
            self.assertEqual(qa["checks"]["narrative_claims_without_factblocks"], 0)
            self.assertEqual(provider.calls[0][0].count("Available fact_blocks"), 1)

    def test_ungrounded_narrative_blocks_export_via_qa(self) -> None:
        with demo_workspace() as (workspace, run_id):
            provider = FakeProvider(
                canned_text="Totally fake claim with no citation at all.",
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                with self.assertRaises(QaGateBlockedError):
                    write_export(
                        workspace,
                        run_id,
                        "md",
                        report_type="technical",
                        ai_narrative=True,
                    )

            qa = json.loads(
                (workspace / "runs" / run_id / "qa_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(qa["export_ready"])
            self.assertFalse(qa["checks"]["ai_narrative_grounded"])
            self.assertIn("ai_narrative_ungrounded", qa["blockers"])

            blocked = (workspace / "reports" / f"{run_id}_export_blocked.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("AI narrative grounding failure", blocked)
            self.assertIn("canned-test", blocked)

    def test_cloud_provider_requires_confirmation(self) -> None:
        with demo_workspace() as (workspace, run_id):
            save_config(
                workspace,
                LLMConfig(
                    provider="anthropic",
                    model="claude-sonnet-4-6",
                    endpoint="",
                    cloud_confirmed=False,
                ),
            )
            with self.assertRaises(InsufficientDataError) as ctx:
                write_export(
                    workspace,
                    run_id,
                    "md",
                    report_type="technical",
                    ai_narrative=True,
                )
            self.assertIn("cloud_confirmed", str(ctx.exception))

    def test_without_ai_narrative_no_provider_call(self) -> None:
        with demo_workspace() as (workspace, run_id):
            provider = FakeProvider(canned_text="should not be called.")
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                report_path = write_export(
                    workspace, run_id, "md", report_type="technical"
                )
            self.assertEqual(provider.calls, [])
            content = Path(report_path).read_text(encoding="utf-8")
            self.assertNotIn("## Narrative summary", content)
            self.assertNotIn("AI-generated narrative", content)


class AiNarrativeReportTypesTest(unittest.TestCase):
    def test_all_three_report_types_include_narrative(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            fid = fact_ids[0]
            provider = FakeProvider(
                canned_text=f"Grounded statement. [fact:{fid}]",
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.llm.build_provider", return_value=provider
            ):
                paths = write_export(
                    workspace,
                    run_id,
                    "md",
                    report_type="all",
                    ai_narrative=True,
                )

            self.assertIsInstance(paths, list)
            self.assertEqual(len(paths), 3)
            for path in paths:
                text = Path(path).read_text(encoding="utf-8")
                self.assertIn(f"[fact:{fid}]", text)
                self.assertIn("AI-generated narrative", text)
            self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
