import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

BASE_IDS = [
    'CDCLEAN_LEAN_REUSE',
    'SUZUKI_V3_SEAM',
    'NON_RH_CORPUS_MINING',
    'WOLFRAM_PAYLOAD_HARDENING',
]


class RoadmapAdvisoryFixtureTests(unittest.TestCase):
    def load_registered(self, fixture_id):
        registry = json.loads((ROOT / 'fixtures/advisory/registry.json').read_text())
        rel = registry['fixtures'][fixture_id]
        return json.loads((ROOT / rel).read_text())

    def test_registered_roadmap_fixture_is_bounded_and_unlabeled(self):
        fixture = self.load_registered('math-roadmap-parallel-v1')
        self.assertTrue(fixture['public_synthetic'])
        self.assertNotIn('expected', fixture)
        self.assertEqual([option['id'] for option in fixture['options']], BASE_IDS)
        self.assertEqual(len(fixture['options']), 4)

    def test_compact_condition_changes_state_only(self):
        baseline = self.load_registered('math-roadmap-parallel-v1')
        compact = self.load_registered('math-roadmap-compact-v1')
        self.assertEqual(compact['question'], baseline['question'])
        self.assertEqual(compact['options'], baseline['options'])
        self.assertNotEqual(compact['state'], baseline['state'])
        self.assertIn('goal=', compact['state'])
        self.assertIn('constraints=', compact['state'])
        self.assertIn('candidate.CDCLEAN_LEAN_REUSE=', compact['state'])
        self.assertIn('hosted_Lean_mathlib_calculator', compact['state'])
        self.assertIn('Suzuki_v3_compact_uniform_arithmetic_limit_audit', compact['state'])
        self.assertNotIn('expected', compact)

    def test_abstain_condition_changes_option_set_only(self):
        compact = self.load_registered('math-roadmap-compact-v1')
        abstain = self.load_registered('math-roadmap-compact-abstain-v1')
        self.assertEqual(abstain['state'], compact['state'])
        self.assertEqual(abstain['question'], compact['question'])
        self.assertEqual(
            [option['id'] for option in abstain['options'][:-1]],
            BASE_IDS,
        )
        self.assertEqual(
            abstain['options'][-1]['id'],
            'ABSTAIN_NEED_MORE_STATE',
        )
        self.assertEqual(len(abstain['options']), 5)
        self.assertNotIn('expected', abstain)


    def test_workflow_exposes_all_three_roadmap_conditions(self):
        workflow = (ROOT / '.github/workflows/quasi-jev-advisory.yml').read_text()
        for fixture_id in (
            'math-roadmap-parallel-v1',
            'math-roadmap-compact-v1',
            'math-roadmap-compact-abstain-v1',
        ):
            self.assertIn(f'- {fixture_id}', workflow)



if __name__ == '__main__':
    unittest.main()
