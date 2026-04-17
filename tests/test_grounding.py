from __future__ import annotations

import unittest

from clawmodeler_engine.llm import (
    GroundingMode,
    split_sentences,
    validate_and_ground,
)


class GroundingStrictTest(unittest.TestCase):
    def test_strict_drops_sentences_with_no_citation(self) -> None:
        known = {"vmt_s1"}
        text = "VMT drops. [fact:vmt_s1] Access improves."

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertFalse(out.is_fully_grounded)
        self.assertEqual(out.ungrounded_sentence_count, 1)
        self.assertIn("VMT drops.", out.text)
        self.assertNotIn("Access improves.", out.text)

    def test_strict_rejects_unknown_fact_ids(self) -> None:
        known = {"vmt_s1"}
        text = "VMT drops. [fact:vmt_s1] Access improves. [fact:not_real]"

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertEqual(out.unknown_fact_ids, ["not_real"])
        self.assertEqual(out.ungrounded_sentence_count, 1)
        self.assertNotIn("Access improves.", out.text)

    def test_strict_keeps_multi_citation_when_all_known(self) -> None:
        known = {"vmt_s1", "access_s2"}
        text = "Both effects land in the corridor. [fact:vmt_s1] [fact:access_s2]"

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertTrue(out.is_fully_grounded)
        self.assertEqual(out.ungrounded_sentence_count, 0)
        self.assertIn("Both effects land in the corridor.", out.text)

    def test_strict_flags_multi_citation_when_any_unknown(self) -> None:
        known = {"vmt_s1"}
        text = "Both effects land in the corridor. [fact:vmt_s1] [fact:ghost]"

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertFalse(out.is_fully_grounded)
        self.assertEqual(out.unknown_fact_ids, ["ghost"])
        self.assertNotIn("corridor", out.text)


class GroundingAnnotatedTest(unittest.TestCase):
    def test_annotated_keeps_ungrounded_with_warning_prefix(self) -> None:
        known = {"vmt_s1"}
        text = "VMT drops. [fact:vmt_s1] Access improves."

        out = validate_and_ground(text, known, mode=GroundingMode.ANNOTATED)

        self.assertFalse(out.is_fully_grounded)
        self.assertEqual(out.ungrounded_sentence_count, 1)
        self.assertIn("VMT drops.", out.text)
        self.assertIn("\u26A0 Access improves.", out.text)


class GroundingStructuralSkipTest(unittest.TestCase):
    def test_headings_rules_and_code_fences_are_not_required_to_cite(self) -> None:
        known = {"vmt_s1"}
        text = "\n".join(
            [
                "## Key Findings",
                "---",
                "```python",
                "no_citation_needed()",
                "```",
                "> blockquote intro",
                "| col | col |",
                "- Scenario 1 cuts VMT by 6.4%. [fact:vmt_s1]",
            ]
        )

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertTrue(out.is_fully_grounded)
        self.assertEqual(out.ungrounded_sentence_count, 0)

    def test_bullet_and_numbered_markers_are_stripped(self) -> None:
        text = "\n".join(
            [
                "- first claim.",
                "1. second claim.",
                "2) third claim.",
            ]
        )

        sentences = split_sentences(text)

        self.assertEqual(
            sentences,
            ["first claim.", "second claim.", "third claim."],
        )


class GroundingTrailingCitationRegressionTest(unittest.TestCase):
    """Regression: the first smoke test showed trailing `. [fact:xxx]`
    was being split off as its own sentence, stripping the claim of its
    anchor. The fix merges citation-only fragments into the preceding
    sentence. This test guards that fix so a future splitter rewrite
    can't silently re-break grounding enforcement."""

    def test_trailing_citation_stays_with_claim_sentence(self) -> None:
        known = {"vmt_s1", "access_s2"}
        text = (
            "- Scenario 1 cuts VMT per capita by 6.4%. [fact:vmt_s1]\n"
            "- Access in scenario 2 rises 12%. [fact:access_s2]\n"
        )

        out = validate_and_ground(text, known, mode=GroundingMode.STRICT)

        self.assertTrue(out.is_fully_grounded)
        self.assertEqual(len(out.sentences), 2)
        self.assertIn("Scenario 1 cuts VMT", out.sentences[0].text)
        self.assertIn("[fact:vmt_s1]", out.sentences[0].text)
        self.assertIn("Access in scenario 2", out.sentences[1].text)
        self.assertIn("[fact:access_s2]", out.sentences[1].text)


class GroundingOutputShapeTest(unittest.TestCase):
    def test_cited_and_unknown_fact_ids_are_unique_and_ordered(self) -> None:
        known = {"a", "b"}
        text = "one [fact:a]. two [fact:b]. three [fact:a]. four [fact:x]. five [fact:x]."

        out = validate_and_ground(text, known, mode=GroundingMode.ANNOTATED)

        self.assertEqual(out.cited_fact_ids, ["a", "b", "x"])
        self.assertEqual(out.unknown_fact_ids, ["x"])

    def test_empty_input_is_fully_grounded(self) -> None:
        out = validate_and_ground("", {"a"}, mode=GroundingMode.STRICT)
        self.assertTrue(out.is_fully_grounded)
        self.assertEqual(out.text, "")
        self.assertEqual(out.sentences, [])


if __name__ == "__main__":
    unittest.main()
