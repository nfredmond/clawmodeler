from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from clawmodeler_engine.llm import (
    AnthropicNotInstalledError,
    AnthropicProvider,
    OpenAINotInstalledError,
    OpenAIProvider,
)


@dataclass
class _AnthropicBlock:
    text: str


@dataclass
class _AnthropicUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _AnthropicMessage:
    content: list[_AnthropicBlock]
    stop_reason: str
    usage: _AnthropicUsage


class _StubAnthropicMessages:
    def __init__(self, response: _AnthropicMessage) -> None:
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _AnthropicMessage:
        self.calls.append(kwargs)
        return self._response


class _StubAnthropicClient:
    def __init__(self, response: _AnthropicMessage) -> None:
        self.messages = _StubAnthropicMessages(response)


@dataclass
class _OpenAIChoiceMessage:
    content: str


@dataclass
class _OpenAIChoice:
    message: _OpenAIChoiceMessage
    finish_reason: str


@dataclass
class _OpenAIUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _OpenAIResponse:
    choices: list[_OpenAIChoice]
    usage: _OpenAIUsage


class _StubOpenAICompletions:
    def __init__(self, response: _OpenAIResponse) -> None:
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _OpenAIResponse:
        self.calls.append(kwargs)
        return self._response


class _StubOpenAIChat:
    def __init__(self, response: _OpenAIResponse) -> None:
        self.completions = _StubOpenAICompletions(response)


class _StubOpenAIClient:
    def __init__(self, response: _OpenAIResponse) -> None:
        self.chat = _StubOpenAIChat(response)


class AnthropicProviderTest(unittest.TestCase):
    def test_is_cloud_is_true(self) -> None:
        self.assertTrue(AnthropicProvider(api_key="sk-test").is_cloud)

    def test_generate_routes_through_messages_create(self) -> None:
        response = _AnthropicMessage(
            content=[_AnthropicBlock(text="VMT drops. [fact:vmt_s1]")],
            stop_reason="end_turn",
            usage=_AnthropicUsage(input_tokens=50, output_tokens=20),
        )
        stub = _StubAnthropicClient(response)
        provider = AnthropicProvider(
            model="claude-sonnet-4-6",
            temperature=0.1,
            max_tokens=500,
            client=stub,
        )

        result = provider.generate("Summarize.", [{"fact_id": "vmt_s1"}])

        self.assertEqual(len(stub.messages.calls), 1)
        call = stub.messages.calls[0]
        self.assertEqual(call["model"], "claude-sonnet-4-6")
        self.assertEqual(call["temperature"], 0.1)
        self.assertEqual(call["max_tokens"], 500)
        self.assertEqual(call["messages"][0]["role"], "user")
        self.assertEqual(call["messages"][0]["content"], "Summarize.")

        self.assertEqual(result.text, "VMT drops. [fact:vmt_s1]")
        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.metadata["stop_reason"], "end_turn")
        self.assertEqual(result.metadata["input_tokens"], 50)
        self.assertEqual(result.metadata["output_tokens"], 20)

    def test_probe_flags_missing_sdk(self) -> None:
        with patch(
            "clawmodeler_engine.llm.anthropic._load_sdk",
            side_effect=AnthropicNotInstalledError("not installed"),
        ):
            probe = AnthropicProvider(api_key="sk-test").probe()

        self.assertFalse(probe.ok)
        self.assertIn("not installed", probe.detail)

    def test_probe_flags_missing_key(self) -> None:
        with (
            patch("clawmodeler_engine.llm.anthropic._load_sdk", return_value=object()),
            patch.dict(os.environ, {}, clear=True),
        ):
            probe = AnthropicProvider().probe()

        self.assertFalse(probe.ok)
        self.assertIn("ANTHROPIC_API_KEY", probe.detail)

    def test_probe_succeeds_with_sdk_and_key(self) -> None:
        with (
            patch("clawmodeler_engine.llm.anthropic._load_sdk", return_value=object()),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}, clear=True),
        ):
            probe = AnthropicProvider().probe()

        self.assertTrue(probe.ok)
        self.assertEqual(probe.provider, "anthropic")
        self.assertTrue(probe.metadata.get("cloud"))

class OpenAIProviderTest(unittest.TestCase):
    def test_is_cloud_is_true(self) -> None:
        self.assertTrue(OpenAIProvider(api_key="sk-test").is_cloud)

    def test_generate_routes_through_chat_completions(self) -> None:
        response = _OpenAIResponse(
            choices=[
                _OpenAIChoice(
                    message=_OpenAIChoiceMessage(
                        content="Access rises. [fact:access_s2]"
                    ),
                    finish_reason="stop",
                )
            ],
            usage=_OpenAIUsage(prompt_tokens=40, completion_tokens=15),
        )
        stub = _StubOpenAIClient(response)
        provider = OpenAIProvider(
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=500,
            client=stub,
        )

        result = provider.generate("Summarize.", [{"fact_id": "access_s2"}])

        self.assertEqual(len(stub.chat.completions.calls), 1)
        call = stub.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-4o-mini")
        self.assertEqual(call["temperature"], 0.1)
        self.assertEqual(call["max_tokens"], 500)
        self.assertEqual(call["messages"][0]["role"], "user")
        self.assertEqual(call["messages"][0]["content"], "Summarize.")

        self.assertEqual(result.text, "Access rises. [fact:access_s2]")
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.metadata["finish_reason"], "stop")
        self.assertEqual(result.metadata["prompt_tokens"], 40)
        self.assertEqual(result.metadata["completion_tokens"], 15)

    def test_probe_flags_missing_sdk(self) -> None:
        with patch(
            "clawmodeler_engine.llm.openai._load_sdk",
            side_effect=OpenAINotInstalledError("not installed"),
        ):
            probe = OpenAIProvider(api_key="sk-test").probe()

        self.assertFalse(probe.ok)
        self.assertIn("not installed", probe.detail)

    def test_probe_flags_missing_key(self) -> None:
        with (
            patch("clawmodeler_engine.llm.openai._load_sdk", return_value=object()),
            patch.dict(os.environ, {}, clear=True),
        ):
            probe = OpenAIProvider().probe()

        self.assertFalse(probe.ok)
        self.assertIn("OPENAI_API_KEY", probe.detail)

    def test_probe_succeeds_with_sdk_and_key(self) -> None:
        with (
            patch("clawmodeler_engine.llm.openai._load_sdk", return_value=object()),
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}, clear=True),
        ):
            probe = OpenAIProvider().probe()

        self.assertTrue(probe.ok)
        self.assertEqual(probe.provider, "openai")
        self.assertTrue(probe.metadata.get("cloud"))

if __name__ == "__main__":
    unittest.main()
