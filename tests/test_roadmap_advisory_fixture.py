import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class RoadmapAdvisoryFixtureTests(unittest.TestCase):
    def test_registered_roadmap_fixture_is_bounded_and_unlabeled(self):
        registry = json.loads((ROOT / 'fixtures/advisory/registry.json').read_text())
        rel = registry['fixtures']['math-roadmap-parallel-v1']
        fixture = json.loads((ROOT / rel).read_text())
        self.assertTrue(fixture['public_synthetic'])
        self.assertNotIn('expected', fixture)
        self.assertEqual(
            [option['id'] for option in fixture['options']],
            ['CDCLEAN_LEAN_REUSE','SUZUKI_V3_SEAM','NON_RH_CORPUS_MINING','WOLFRAM_PAYLOAD_HARDENING'],
        )
        self.assertEqual(len(fixture['options']), 4)

if __name__ == '__main__':
    unittest.main()
