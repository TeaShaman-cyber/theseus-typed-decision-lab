import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

MUTATION_FIXTURE = "math-mutation-routing-v1"
CAPABILITY_FIXTURE = "math-capability-routing-v1"

MUTATION_IDS = [
    "M4_INLINE_GAMMA_BRIDGE",
    "M5_DROP_DECIDABLE_EQ_E",
    "M6_CORRUPT_JAEGER_DEP_EDGE",
    "M7_CORRUPT_GAMMA_BRIDGE_EDGE",
    "ABSTAIN_NEED_MORE_STATE",
]

CAPABILITY_IDS = [
    "LEAN_KERNEL",
    "REPO_SEARCH",
    "WOLFRAM_MCP_WITNESS",
    "PRECISE_SPECIAL_FUNCTIONS",
    "ALPHAXIV",
    "ACUMEN",
    "EXA",
    "PARALLEL_SEARCH",
    "ABSTAIN_NEED_MORE_STATE",
]


class MathResearchRoutingFixtureTests(unittest.TestCase):
    def load_registered(self, fixture_id):
        registry = json.loads((ROOT / "fixtures/advisory/registry.json").read_text())
        rel = registry["fixtures"][fixture_id]
        return json.loads((ROOT / rel).read_text())

    def test_two_axes_share_exact_frozen_state(self):
        mutation = self.load_registered(MUTATION_FIXTURE)
        capability = self.load_registered(CAPABILITY_FIXTURE)
        self.assertEqual(mutation["state"], capability["state"])
        self.assertIn("math_main=ca3303dc2c73bb3caf092198db98bc715b08bc19", mutation["state"])
        self.assertIn("M1=KILLED_BY_FORMAL_DERIVATION/ASSUMPTION_OBSERVED", mutation["state"])
        self.assertIn("M2=KILLED/BRIDGE_SEGMENT_REMOVED", mutation["state"])
        self.assertIn("M3=KILLED/ALTERNATE_PREMISE_ROUTE", mutation["state"])
        self.assertNotIn("expected", mutation)
        self.assertNotIn("expected", capability)

    def test_mutation_axis_is_bounded_and_abstainable(self):
        fixture = self.load_registered(MUTATION_FIXTURE)
        self.assertTrue(fixture["public_synthetic"])
        self.assertEqual([x["id"] for x in fixture["options"]], MUTATION_IDS)
        self.assertIn("bounded experiment", fixture["question"].lower())
        self.assertIn("hypothesis", " ".join(x["description"] for x in fixture["options"]).lower())

    def test_capability_axis_preserves_availability_authority_boundary(self):
        fixture = self.load_registered(CAPABILITY_FIXTURE)
        self.assertTrue(fixture["public_synthetic"])
        self.assertEqual([x["id"] for x in fixture["options"]], CAPABILITY_IDS)
        state = fixture["state"]
        self.assertIn("tool.PRECISE_SPECIAL_FUNCTIONS=state:COMPLETED", state)
        self.assertIn("tool.ALPHAXIV=state:COMPLETED", state)
        self.assertIn("tool.ACUMEN=state:COMPLETED", state)
        self.assertIn("tool.EXA=state:EXPOSED", state)
        self.assertIn("tool.PARALLEL_SEARCH=state:EXPOSED", state)
        self.assertIn("availability_does_not_grant_authority", state)
        self.assertIn("reverify_before_execution", state)

    def test_workflow_exposes_both_routing_axes(self):
        workflow = (ROOT / ".github/workflows/quasi-jev-advisory.yml").read_text()
        self.assertIn(f"- {MUTATION_FIXTURE}", workflow)
        self.assertIn(f"- {CAPABILITY_FIXTURE}", workflow)


if __name__ == "__main__":
    unittest.main()
