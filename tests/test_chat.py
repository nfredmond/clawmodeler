from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from clawmodeler_engine.chat import (
    NOT_IN_CONTEXT,
    build_chat_prompt,
    chat_from_workspace,
    chat_history_path,
    chat_with_run,
    load_history,
)
from clawmodeler_engine.demo import write_demo_inputs
from clawmodeler_engine.llm import FakeProvider, GroundingMode, save_config
from clawmodeler_engine.llm.config import LLMConfig
from clawmodeler_engine.orchestration import (
    write_intake,
    write_plan,
    write_run,
)
from clawmodeler_engine.workspace import InsufficientDataError


@contextmanager
def demo_workspace(run_id: str = "chat"):
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


class BuildChatPromptTest(unittest.TestCase):
    def test_prompt_lists_all_fact_ids_and_user_question(self) -> None:
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
        prompt = build_chat_prompt("What changed under build?", fact_blocks)
        self.assertIn("[fact:<fact_id>]", prompt)
        self.assertIn("fact_id='vmt_s1'", prompt)
        self.assertIn("fact_id='acc_s1'", prompt)
        self.assertIn("User question: What changed under build?", prompt)

    def test_prompt_with_history_includes_last_turns(self) -> None:
        history = [
            {"user_message": "q1", "text": "a1"},
            {"user_message": "q2", "text": "a2"},
        ]
        prompt = build_chat_prompt("q3", [], history=history)
        self.assertIn("Recent chat history", prompt)
        self.assertIn("q1", prompt)
        self.assertIn("a2", prompt)

    def test_empty_fact_blocks_hint(self) -> None:
        prompt = build_chat_prompt("anything", [])
        self.assertIn("no fact_blocks available", prompt)


class ChatWithRunTest(unittest.TestCase):
    def test_grounded_response_persists_and_is_fully_grounded(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            self.assertGreaterEqual(len(fact_ids), 2)
            provider = FakeProvider(
                canned_text=(
                    f"VMT screening holds steady. [fact:{fact_ids[0]}] "
                    f"Access improves under build. [fact:{fact_ids[1]}]"
                ),
                model="canned-test",
            )
            turn = chat_with_run(
                workspace,
                run_id,
                "How did the scenarios compare?",
                provider,
                mode=GroundingMode.STRICT,
            )
            self.assertEqual(turn.turn_id, 1)
            self.assertTrue(turn.is_fully_grounded)
            self.assertEqual(turn.ungrounded_sentence_count, 0)
            self.assertIn(f"[fact:{fact_ids[0]}]", turn.text)
            self.assertEqual(
                sorted(turn.cited_fact_ids), sorted([fact_ids[0], fact_ids[1]])
            )

            history = load_history(workspace, run_id)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["turn_id"], 1)
            self.assertEqual(history[0]["user_message"], "How did the scenarios compare?")
            self.assertTrue(chat_history_path(workspace, run_id).exists())

    def test_ungrounded_response_falls_back_to_not_in_context(self) -> None:
        with demo_workspace() as (workspace, run_id):
            provider = FakeProvider(
                canned_text="Totally fake claim with no citation at all.",
                model="canned-test",
            )
            turn = chat_with_run(
                workspace,
                run_id,
                "Anything?",
                provider,
                mode=GroundingMode.STRICT,
            )
            self.assertEqual(turn.text, NOT_IN_CONTEXT)
            self.assertTrue(turn.is_fully_grounded)
            self.assertGreaterEqual(turn.ungrounded_sentence_count, 1)
            self.assertEqual(turn.cited_fact_ids, [])

    def test_unknown_fact_id_is_recorded(self) -> None:
        with demo_workspace() as (workspace, run_id):
            provider = FakeProvider(
                canned_text="Fabricated claim. [fact:not_real]",
                model="canned-test",
            )
            turn = chat_with_run(
                workspace,
                run_id,
                "Anything?",
                provider,
                mode=GroundingMode.STRICT,
            )
            self.assertIn("not_real", turn.unknown_fact_ids)

    def test_turn_ids_increment_across_calls(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            provider = FakeProvider(
                canned_text=f"Grounded. [fact:{fact_ids[0]}]",
                model="canned-test",
            )
            t1 = chat_with_run(workspace, run_id, "q1", provider)
            t2 = chat_with_run(workspace, run_id, "q2", provider)
            t3 = chat_with_run(workspace, run_id, "q3", provider)
            self.assertEqual([t1.turn_id, t2.turn_id, t3.turn_id], [1, 2, 3])
            history = load_history(workspace, run_id)
            self.assertEqual(len(history), 3)
            self.assertEqual([h["user_message"] for h in history], ["q1", "q2", "q3"])

    def test_history_feeds_into_subsequent_prompt(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            provider = FakeProvider(
                canned_text=f"Grounded. [fact:{fact_ids[0]}]",
                model="canned-test",
            )
            chat_with_run(workspace, run_id, "first question", provider)
            chat_with_run(workspace, run_id, "second question", provider)
            self.assertEqual(len(provider.calls), 2)
            second_prompt = provider.calls[1][0]
            self.assertIn("first question", second_prompt)
            self.assertIn("second question", second_prompt)

    def test_missing_fact_blocks_raises(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            fact_blocks_path.unlink()
            provider = FakeProvider(canned_text="x")
            with self.assertRaises(InsufficientDataError):
                chat_with_run(workspace, run_id, "q", provider)

    def test_empty_fact_blocks_raises(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_blocks_path = (
                workspace / "runs" / run_id / "outputs" / "tables" / "fact_blocks.jsonl"
            )
            fact_blocks_path.write_text("", encoding="utf-8")
            provider = FakeProvider(canned_text="x")
            with self.assertRaises(InsufficientDataError):
                chat_with_run(workspace, run_id, "q", provider)


class ChatFromWorkspaceTest(unittest.TestCase):
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
                chat_from_workspace(workspace, run_id, "q")
            self.assertIn("cloud_confirmed", str(ctx.exception))

    def test_uses_configured_provider_via_build_provider(self) -> None:
        with demo_workspace() as (workspace, run_id):
            fact_ids = _fact_ids_from_run(workspace, run_id)
            provider = FakeProvider(
                canned_text=f"Steady. [fact:{fact_ids[0]}]",
                model="canned-test",
            )
            with patch(
                "clawmodeler_engine.chat.build_provider", return_value=provider
            ):
                turn = chat_from_workspace(workspace, run_id, "how does it look?")
            self.assertIn(f"[fact:{fact_ids[0]}]", turn.text)
            self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
