import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "fixtures/advisory/registry.json"
BASE_ID = "orchestration-pending-results-v1"
CAUSAL_ID = "orchestration-results-consumed-v1"


class OrchestrationCausalControlTests(unittest.TestCase):
    def load_registered(self, fixture_id):
        registry = json.loads(REGISTRY.read_text())
        rel = registry["fixtures"][fixture_id]
        return json.loads((ROOT / rel).read_text())

    def test_causal_pair_changes_state_only(self):
        base = self.load_registered(BASE_ID)
        causal = self.load_registered(CAUSAL_ID)
        self.assertEqual(causal["question"], base["question"])
        self.assertEqual(causal["options"], base["options"])
        self.assertNotEqual(causal["state"], base["state"])
        self.assertIn("No pending bounded result remains", causal["state"])
        self.assertIn("verification/review has completed", causal["state"])
        self.assertTrue(causal["public_synthetic"])

    def test_workflow_exposes_causal_pair(self):
        workflow = (ROOT / ".github/workflows/quasi-jev-advisory.yml").read_text()
        self.assertIn(f"- {BASE_ID}", workflow)
        self.assertIn(f"- {CAUSAL_ID}", workflow)


if __name__ == "__main__":
    unittest.main()
