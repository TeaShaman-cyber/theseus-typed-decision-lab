import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_ID = "orchestration-results-consumed-v1"
DELEX_ID = "orchestration-results-consumed-delex-v1"


class SemIf4BLexicalOverlapTests(unittest.TestCase):
    def load_registered(self, fixture_id):
        reg = json.loads((ROOT / "fixtures/advisory/registry.json").read_text())
        return json.loads((ROOT / reg["fixtures"][fixture_id]).read_text())

    def test_delex_fixture_preserves_question_options_and_causal_facts(self):
        base = self.load_registered(BASE_ID)
        probe = self.load_registered(DELEX_ID)
        self.assertEqual(probe["question"], base["question"])
        self.assertEqual(probe["options"], base["options"])
        self.assertNotEqual(probe["state"], base["state"])
        state = probe["state"].lower()
        for forbidden in ("pending", "read", "interpret", "results"):
            self.assertNotIn(forbidden, state)
        self.assertIn("verification", state)
        self.assertIn("review", state)
        self.assertIn("no unresolved external evidence remains", state)

    def test_4b_workflow_scores_c1_and_c2_in_one_load(self):
        wf = (ROOT / ".github/workflows/semif-4b-lexical-overlap.yml").read_text()
        self.assertIn(BASE_ID, wf)
        self.assertIn(DELEX_ID, wf)
        self.assertIn("one 4B model load", wf)
        self.assertIn("semif_qwen3_5_4b", wf)
        self.assertIn("semif_qwen3_5_4b_gguf", wf)

    def test_analyzer_uses_target_raw_logit_as_primary_endpoint(self):
        script = (ROOT / "scripts/analyze_semif_lexical_overlap.py").read_text()
        self.assertIn('TARGET = "READ_PENDING_RESULTS"', script)
        self.assertIn('raw_logit_direction_pass', script)
        self.assertIn('target_logit', script)
        self.assertIn('target_probability', script)


if __name__ == "__main__":
    unittest.main()
