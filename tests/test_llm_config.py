from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clawmodeler_engine.llm import (
    AnthropicProvider,
    FakeProvider,
    LLMConfig,
    LLMConfigError,
    OllamaProvider,
    OpenAIProvider,
    apply_updates,
    build_provider,
    default_config,
    load_config,
    parse_key_value_pairs,
    save_config,
)


class LLMConfigDefaultsTest(unittest.TestCase):
    def test_default_is_local_ollama(self) -> None:
        cfg = default_config()

        self.assertEqual(cfg.provider, "ollama")
        self.assertEqual(cfg.model, "llama3.1:8b-instruct")
        self.assertEqual(cfg.endpoint, "http://localhost:11434")
        self.assertEqual(cfg.grounding_mode, "strict")
        self.assertFalse(cfg.cloud_confirmed)

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        cfg = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-6",
            endpoint="",
            temperature=0.3,
            grounding_mode="annotated",
            max_tokens=1024,
            cloud_confirmed=True,
        )
        roundtrip = LLMConfig.from_dict(cfg.to_dict())
        self.assertEqual(roundtrip, cfg)

    def test_from_dict_rejects_bad_provider(self) -> None:
        with self.assertRaises(LLMConfigError):
            LLMConfig.from_dict({"provider": "mystery-llm"})

    def test_from_dict_rejects_bad_grounding_mode(self) -> None:
        with self.assertRaises(LLMConfigError):
            LLMConfig.from_dict({"grounding_mode": "loose"})

    def test_from_dict_rejects_bad_temperature(self) -> None:
        with self.assertRaises(LLMConfigError):
            LLMConfig.from_dict({"temperature": 5.0})

    def test_from_dict_ignores_unknown_keys(self) -> None:
        cfg = LLMConfig.from_dict({"provider": "ollama", "foo": "bar"})
        self.assertEqual(cfg.provider, "ollama")


class LLMConfigPersistenceTest(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-6")
            path = save_config(ws, cfg)

            self.assertEqual(path, ws / "llm_config.json")
            loaded = load_config(ws)
            self.assertEqual(loaded, cfg)

    def test_load_missing_file_returns_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(Path(tmp))
            self.assertEqual(cfg, default_config())

    def test_saved_file_is_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            save_config(ws, default_config())
            content = (ws / "llm_config.json").read_text(encoding="utf-8")
            data = json.loads(content)
            self.assertEqual(data["provider"], "ollama")
            self.assertIn("\n", content)


class ApplyUpdatesTest(unittest.TestCase):
    def test_updates_string_field(self) -> None:
        cfg = default_config()
        new = apply_updates(cfg, {"model": "phi3:mini"})
        self.assertEqual(new.model, "phi3:mini")
        self.assertEqual(new.provider, "ollama")

    def test_coerces_float_and_int(self) -> None:
        cfg = default_config()
        new = apply_updates(cfg, {"temperature": "0.5", "max_tokens": "1024"})
        self.assertEqual(new.temperature, 0.5)
        self.assertEqual(new.max_tokens, 1024)

    def test_coerces_bool(self) -> None:
        cfg = default_config()
        new = apply_updates(cfg, {"cloud_confirmed": "true"})
        self.assertTrue(new.cloud_confirmed)
        newer = apply_updates(new, {"cloud_confirmed": "false"})
        self.assertFalse(newer.cloud_confirmed)

    def test_provider_switch_resets_model_and_endpoint(self) -> None:
        cfg = default_config()
        switched = apply_updates(cfg, {"provider": "anthropic"})
        self.assertEqual(switched.provider, "anthropic")
        self.assertEqual(switched.model, "claude-sonnet-4-6")
        self.assertEqual(switched.endpoint, "")

    def test_provider_switch_resets_cloud_confirmed(self) -> None:
        cfg = apply_updates(
            default_config(), {"cloud_confirmed": "true"}
        )
        switched = apply_updates(cfg, {"provider": "anthropic"})
        self.assertFalse(switched.cloud_confirmed)

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaises(LLMConfigError):
            apply_updates(default_config(), {"bogus": "value"})

    def test_rejects_bad_temperature(self) -> None:
        with self.assertRaises(LLMConfigError):
            apply_updates(default_config(), {"temperature": "99"})

    def test_rejects_bad_max_tokens(self) -> None:
        with self.assertRaises(LLMConfigError):
            apply_updates(default_config(), {"max_tokens": "0"})

    def test_rejects_bad_bool(self) -> None:
        with self.assertRaises(LLMConfigError):
            apply_updates(default_config(), {"cloud_confirmed": "maybe"})


class ParseKeyValueTest(unittest.TestCase):
    def test_parses_basic_pairs(self) -> None:
        self.assertEqual(
            parse_key_value_pairs(["provider=ollama", "model=phi3:mini"]),
            {"provider": "ollama", "model": "phi3:mini"},
        )

    def test_allows_equals_in_value(self) -> None:
        self.assertEqual(
            parse_key_value_pairs(["endpoint=http://host:11434/a=b"]),
            {"endpoint": "http://host:11434/a=b"},
        )

    def test_rejects_missing_equals(self) -> None:
        with self.assertRaises(LLMConfigError):
            parse_key_value_pairs(["provider"])

    def test_rejects_empty_key(self) -> None:
        with self.assertRaises(LLMConfigError):
            parse_key_value_pairs(["=value"])


class BuildProviderTest(unittest.TestCase):
    def test_builds_ollama(self) -> None:
        provider = build_provider(default_config())
        self.assertIsInstance(provider, OllamaProvider)

    def test_builds_anthropic(self) -> None:
        cfg = apply_updates(default_config(), {"provider": "anthropic"})
        self.assertIsInstance(build_provider(cfg), AnthropicProvider)

    def test_builds_openai(self) -> None:
        cfg = apply_updates(default_config(), {"provider": "openai"})
        self.assertIsInstance(build_provider(cfg), OpenAIProvider)

    def test_builds_fake_provider(self) -> None:
        cfg = LLMConfig(provider="fake", model="fake-configured")
        provider = build_provider(cfg)

        self.assertIsInstance(provider, FakeProvider)
        self.assertEqual(provider.probe().model, "fake-configured")


if __name__ == "__main__":
    unittest.main()
