from __future__ import annotations

import unittest
from typing import Any

from clawmodeler_engine.llm import (
    FakeProvider,
    GenerationResult,
    OllamaProvider,
    ProviderProbe,
)


class _StubResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _StubHTTPClient:
    """Captures requests and returns canned responses, like a tiny httpx."""

    def __init__(
        self,
        generate_payload: dict[str, Any] | None = None,
        tags_payload: dict[str, Any] | None = None,
        raise_get: Exception | None = None,
    ) -> None:
        self.generate_payload = generate_payload or {"response": ""}
        self.tags_payload = tags_payload or {"models": []}
        self.raise_get = raise_get
        self.post_calls: list[tuple[str, dict[str, Any], float | None]] = []
        self.get_calls: list[tuple[str, float | None]] = []

    def post(
        self, url: str, json: dict[str, Any], timeout: float | None = None
    ) -> _StubResponse:
        self.post_calls.append((url, json, timeout))
        return _StubResponse(self.generate_payload)

    def get(self, url: str, timeout: float | None = None) -> _StubResponse:
        self.get_calls.append((url, timeout))
        if self.raise_get is not None:
            raise self.raise_get
        return _StubResponse(self.tags_payload)


class FakeProviderTest(unittest.TestCase):
    def test_generate_returns_canned_text_and_records_call(self) -> None:
        provider = FakeProvider(
            canned_text="VMT drops. [fact:vmt_s1]", model="fake-v2"
        )
        facts = [{"fact_id": "vmt_s1", "value": 6.4}]

        result = provider.generate("prompt text", facts)

        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.text, "VMT drops. [fact:vmt_s1]")
        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.model, "fake-v2")
        self.assertEqual(provider.calls, [("prompt text", facts)])

    def test_probe_is_always_ok(self) -> None:
        provider = FakeProvider()

        probe = provider.probe()

        self.assertIsInstance(probe, ProviderProbe)
        self.assertTrue(probe.ok)
        self.assertEqual(probe.provider, "fake")

    def test_is_cloud_is_false(self) -> None:
        self.assertFalse(FakeProvider().is_cloud)


class OllamaProviderGenerateTest(unittest.TestCase):
    def test_generate_posts_expected_body_and_returns_result(self) -> None:
        stub = _StubHTTPClient(
            generate_payload={
                "response": "Scenario 1 cuts VMT. [fact:vmt_s1]",
                "eval_count": 42,
                "eval_duration": 1_000_000,
            }
        )
        provider = OllamaProvider(
            model="llama3.1:8b-instruct",
            endpoint="http://localhost:11434/",
            temperature=0.1,
            http_client=stub,
        )

        result = provider.generate("Summarize the run.", [{"fact_id": "vmt_s1"}])

        self.assertEqual(len(stub.post_calls), 1)
        url, body, timeout = stub.post_calls[0]
        self.assertEqual(url, "http://localhost:11434/api/generate")
        self.assertEqual(body["model"], "llama3.1:8b-instruct")
        self.assertEqual(body["prompt"], "Summarize the run.")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"], {"temperature": 0.1})
        self.assertIsNotNone(timeout)

        self.assertEqual(result.text, "Scenario 1 cuts VMT. [fact:vmt_s1]")
        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.model, "llama3.1:8b-instruct")
        self.assertEqual(result.metadata["eval_count"], 42)

    def test_endpoint_trailing_slash_is_stripped(self) -> None:
        stub = _StubHTTPClient(generate_payload={"response": ""})
        provider = OllamaProvider(
            endpoint="http://localhost:11434///", http_client=stub
        )

        provider.generate("x", [])

        self.assertEqual(
            stub.post_calls[0][0], "http://localhost:11434/api/generate"
        )

    def test_is_cloud_is_false(self) -> None:
        self.assertFalse(OllamaProvider(http_client=_StubHTTPClient()).is_cloud)


class OllamaProviderProbeTest(unittest.TestCase):
    def test_probe_reports_installed_models_and_match(self) -> None:
        stub = _StubHTTPClient(
            tags_payload={
                "models": [
                    {"name": "llama3.1:8b-instruct"},
                    {"name": "phi3:mini"},
                ]
            }
        )
        provider = OllamaProvider(
            model="llama3.1:8b-instruct", http_client=stub
        )

        probe = provider.probe()

        self.assertTrue(probe.ok)
        self.assertTrue(probe.metadata["model_installed"])
        self.assertEqual(
            probe.metadata["installed_models"],
            ["llama3.1:8b-instruct", "phi3:mini"],
        )
        self.assertIn("is installed", probe.detail)

    def test_probe_flags_missing_model(self) -> None:
        stub = _StubHTTPClient(
            tags_payload={"models": [{"name": "phi3:mini"}]}
        )
        provider = OllamaProvider(
            model="llama3.1:8b-instruct", http_client=stub
        )

        probe = provider.probe()

        self.assertTrue(probe.ok)
        self.assertFalse(probe.metadata["model_installed"])
        self.assertIn("is NOT installed", probe.detail)

    def test_probe_reports_unreachable_on_network_error(self) -> None:
        stub = _StubHTTPClient(
            raise_get=ConnectionRefusedError("connection refused")
        )
        provider = OllamaProvider(http_client=stub)

        probe = provider.probe()

        self.assertFalse(probe.ok)
        self.assertIn("unreachable", probe.detail)


if __name__ == "__main__":
    unittest.main()
