import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quasi', ROOT / 'scripts/quasi_jev_advisory.py')
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)
FIXTURE_ID = 'orchestration-pending-results-v1'

class QuasiJevAdvisoryTests(unittest.TestCase):
    def test_registered_fixture_is_public_synthetic_and_has_no_expected_label(self):
        path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        self.assertTrue(fixture['public_synthetic'])
        self.assertNotIn('expected', json.dumps(fixture).lower())
        self.assertEqual(path.relative_to(ROOT).as_posix(), 'fixtures/advisory/orchestration-pending-results-v1.json')

    def test_semif_projection_preserves_option_ids(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / 'semif.jsonl'
            MOD.cmd_prepare_semif(type('A', (), {'fixture_id': FIXTURE_ID, 'out': str(out)})())
            row = json.loads(out.read_text().strip())
        self.assertEqual([x['id'] for x in row['options']], [x['id'] for x in fixture['options']])

    def test_kev_projection_uses_dummy_label_not_expected_target(self):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / 'kev.json'
            MOD.cmd_prepare_kev(type('A', (), {'fixture_id': FIXTURE_ID, 'out': str(out)})())
            value = json.loads(out.read_text())
        self.assertEqual(value['questions'][0]['label'], 0)
        self.assertEqual(value['_theseus']['label_semantics'], 'DUMMY_REQUIRED_BY_KEV_ENCODER_NOT_EXPECTED_TARGET')

    def test_probability_tie_does_not_invent_choice(self):
        selected, status = MOD.select_option({'A': 0.5, 'B': 0.5})
        self.assertIsNone(selected); self.assertEqual(status, 'TIE')

    def test_aggregate_agreement_has_no_authority(self):
        fixture_path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        probs = {ids[0]: 0.7, ids[1]: 0.1, ids[2]: 0.1, ids[3]: 0.1}
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); raw = td / 'raw.json'; raw.write_text('{}')
            base = {
                'schema': 'theseus.quasi-jev-advisory-candidate.v1', 'claim_scope': 'ADVISORY_ONLY',
                'fixture': {'id': FIXTURE_ID}, 'option_ids': ids, 'probabilities': probs,
                'selected_option': ids[0], 'decision_status': 'SELECTED', 'acceptance_authority': False,
                'permission_authority': False, 'verification_authority': False, 'promotion_authority': False,
            }
            semif = td / 'semif.json'; kev = td / 'kev.json'; out = td / 'out.json'
            semif.write_text(json.dumps({**base, 'candidate': 'semif_qwen3_0_6b_q8'}))
            kev.write_text(json.dumps({**base, 'candidate': 'kev_0_8b'}))
            MOD.cmd_aggregate(type('A', (), {'fixture_id': FIXTURE_ID, 'semif': str(semif), 'kev': str(kev), 'semif_job_status':'success', 'kev_job_status':'success', 'out': str(out)})())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt['council_state'], 'AGREE')
        self.assertFalse(receipt['consensus_grants_authority'])
        self.assertFalse(receipt['permission_authority'])


    def test_aggregate_rejects_cross_fixture_candidate_receipt(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        base = {
            'schema':'theseus.quasi-jev-advisory-candidate.v1','claim_scope':'ADVISORY_ONLY',
            'fixture':{'id':FIXTURE_ID},'option_ids':ids,'acceptance_authority':False,
            'permission_authority':False,'verification_authority':False,'promotion_authority':False,
            'selected_option':ids[0],'decision_status':'SELECTED',
            'probabilities':{ids[0]:1.0,ids[1]:0.0,ids[2]:0.0,ids[3]:0.0},
        }
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); semif=td/'semif.json'; kev=td/'kev.json'; out=td/'out.json'
            semif.write_text(json.dumps({**base,'candidate':'semif_qwen3_0_6b_q8'}))
            wrong={**base,'candidate':'kev_0_8b','fixture':{'id':'other-fixture'}}; kev.write_text(json.dumps(wrong))
            with self.assertRaisesRegex(ValueError, 'fixture/options'):
                MOD.cmd_aggregate(type('A', (), {'fixture_id':FIXTURE_ID,'semif':str(semif),'kev':str(kev),'semif_job_status':'success','kev_job_status':'success','out':str(out)})())

    def test_aggregate_missing_candidate_is_incomplete(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); semif = td / 'semif.json'; missing = td / 'missing.json'; out = td / 'out.json'
            semif.write_text(json.dumps({'schema':'theseus.quasi-jev-advisory-candidate.v1','claim_scope':'ADVISORY_ONLY','candidate':'semif_qwen3_0_6b_q8','fixture':{'id':FIXTURE_ID},'option_ids':ids,'acceptance_authority':False,'permission_authority':False,'verification_authority':False,'promotion_authority':False,'selected_option':ids[0],'decision_status':'SELECTED','probabilities':{ids[0]:1.0,ids[1]:0.0,ids[2]:0.0,ids[3]:0.0}}))
            MOD.cmd_aggregate(type('A', (), {'fixture_id': FIXTURE_ID, 'semif': str(semif), 'kev': str(missing), 'semif_job_status':'success', 'kev_job_status':'failure', 'out': str(out)})())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt['council_state'], 'INCOMPLETE')
        self.assertEqual(receipt['candidate_jobs']['kev_0_8b'], 'failure')

if __name__ == '__main__': unittest.main()
