import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quasi', ROOT / 'scripts/quasi_jev_advisory.py')
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)
FIXTURE_ID = 'orchestration-pending-results-v1'
TEST_REPOSITORY_SHA = os.environ.get('GITHUB_SHA', 'test-sha')

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

    def test_question_custody_binds_registered_state_question_and_options(self):
        fixture_path, fixture = MOD.safe_registered_fixture('math-roadmap-compact-v1')
        custody = MOD.build_question_custody(fixture_path, fixture, repository_sha='abc123')
        self.assertEqual(custody['repository_sha'], 'abc123')
        self.assertEqual(custody['fixture_sha256'], MOD.sha256_file(fixture_path))
        self.assertEqual(custody['policy_version'], 'NONE')
        self.assertEqual(custody['method'], 'REGISTERED_FIXTURE_SHA256_V1')
        self.assertEqual(custody['bound_before_scoring'], True)

        changed = dict(fixture)
        changed['question'] = fixture['question'] + ' changed'
        changed_custody = MOD.build_question_custody(
            fixture_path, changed, repository_sha='abc123'
        )
        self.assertEqual(custody['state_sha256'], changed_custody['state_sha256'])
        self.assertNotEqual(custody['question_sha256'], changed_custody['question_sha256'])
        self.assertNotEqual(
            custody['question_pack_sha256'],
            changed_custody['question_pack_sha256'],
        )

    def test_distribution_metrics_keep_entropy_and_top2_margin(self):
        metrics = MOD.distribution_metrics({'A': 0.5, 'B': 0.5, 'C': 0.0})
        self.assertEqual(metrics['method'], 'SHANNON_NATS_AND_TOP1_TOP2_MARGIN_V1')
        self.assertAlmostEqual(metrics['entropy_nats'], 0.6931471805599453)
        self.assertEqual(metrics['top1_top2_margin'], 0.0)

        decisive = MOD.distribution_metrics({'A': 0.9, 'B': 0.1})
        self.assertAlmostEqual(decisive['top1_top2_margin'], 0.8)
        self.assertLess(decisive['entropy_nats'], metrics['entropy_nats'])

    def test_workflow_writes_custody_before_each_model_call(self):
        workflow = (ROOT / '.github/workflows/quasi-jev-advisory.yml').read_text()
        semif_custody = workflow.index('Prepare SemIf question custody')
        semif_ask = workflow.index('Ask SemIf consultant')
        kev_custody = workflow.index('Prepare Kev question custody')
        kev_ask = workflow.index('Ask Kev consultant')
        self.assertLess(semif_custody, semif_ask)
        self.assertLess(kev_custody, kev_ask)

    def test_probability_tie_does_not_invent_choice(self):
        selected, status = MOD.select_option({'A': 0.5, 'B': 0.5})
        self.assertIsNone(selected); self.assertEqual(status, 'TIE')


    def _valid_kev_raw(self, fixture):
        sources = MOD.upstreams()
        return {
            'fixture': MOD.kev_projection(fixture),
            'probabilities': [[0.7, 0.1, 0.1, 0.1]],
            'checkpoint': {
                'requested': f"jaredpalmer/kev-0.8b@{sources['kev_0_8b']['revision']}",
                'base_revision': sources['qwen3_5_0_8b_base']['revision'],
            },
            'runtime': {'python':'3.12'},
        }

    def _normalize_kev_value(self, value):
        fixture_path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); raw=td/'raw.json'; custody=td/'custody.json'; out=td/'out.json'
            raw.write_text(json.dumps(value))
            custody.write_text(json.dumps(
                MOD.build_question_custody(
                    fixture_path, fixture, repository_sha=TEST_REPOSITORY_SHA
                )
            ))
            MOD.cmd_normalize_kev(type('A', (), {
                'fixture_id':FIXTURE_ID,
                'raw':str(raw),
                'custody':str(custody),
                'out':str(out),
            })())
            return json.loads(out.read_text())

    def test_normalize_kev_accepts_exact_registered_projection(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        receipt = self._normalize_kev_value(self._valid_kev_raw(fixture))
        self.assertEqual(receipt['fixture']['id'], FIXTURE_ID)

    def test_normalize_kev_rejects_stale_state_with_same_option_ids(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['state'] = 'stale unrelated state'
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)

    def test_normalize_kev_rejects_stale_question_with_same_option_ids(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['questions'][0]['instr'] = 'different question'
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)

    def test_normalize_kev_rejects_changed_option_text_with_same_option_ids(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['questions'][0]['options'][0] = 'different option semantics'
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)


    def test_normalize_kev_rejects_boolean_dummy_label(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['questions'][0]['label'] = False
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)

    def test_normalize_kev_rejects_float_dummy_label(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['questions'][0]['label'] = 0.0
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)

    def test_normalize_kev_rejects_changed_dummy_label(self):
        _, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        raw = self._valid_kev_raw(fixture)
        raw['fixture']['questions'][0]['label'] = 1
        with self.assertRaisesRegex(ValueError, 'embedded fixture'):
            self._normalize_kev_value(raw)

    def test_aggregate_agreement_has_no_authority(self):
        fixture_path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        probs = {ids[0]: 0.7, ids[1]: 0.1, ids[2]: 0.1, ids[3]: 0.1}
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); raw = td / 'raw.json'; raw.write_text('{}')
            custody = MOD.build_question_custody(
                fixture_path, fixture, repository_sha=TEST_REPOSITORY_SHA
            )
            base = {
                'schema': 'theseus.quasi-jev-advisory-candidate.v1', 'claim_scope': 'ADVISORY_ONLY',
                'fixture': {'id': FIXTURE_ID}, 'option_ids': ids, 'probabilities': probs,
                'distribution_metrics': MOD.distribution_metrics(probs),
                'question_custody': custody,
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
        fixture_path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        probs = {ids[0]:1.0,ids[1]:0.0,ids[2]:0.0,ids[3]:0.0}
        custody = MOD.build_question_custody(
            fixture_path, fixture, repository_sha=TEST_REPOSITORY_SHA
        )
        base = {
            'schema':'theseus.quasi-jev-advisory-candidate.v1','claim_scope':'ADVISORY_ONLY',
            'fixture':{'id':FIXTURE_ID},'option_ids':ids,'acceptance_authority':False,
            'permission_authority':False,'verification_authority':False,'promotion_authority':False,
            'selected_option':ids[0],'decision_status':'SELECTED',
            'probabilities': probs,
            'distribution_metrics': MOD.distribution_metrics(probs),
            'question_custody': custody,
        }
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); semif=td/'semif.json'; kev=td/'kev.json'; out=td/'out.json'
            semif.write_text(json.dumps({**base,'candidate':'semif_qwen3_0_6b_q8'}))
            wrong={**base,'candidate':'kev_0_8b','fixture':{'id':'other-fixture'}}; kev.write_text(json.dumps(wrong))
            with self.assertRaisesRegex(ValueError, 'fixture/options'):
                MOD.cmd_aggregate(type('A', (), {'fixture_id':FIXTURE_ID,'semif':str(semif),'kev':str(kev),'semif_job_status':'success','kev_job_status':'success','out':str(out)})())

    def test_aggregate_missing_candidate_is_incomplete(self):
        fixture_path, fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        ids = [x['id'] for x in fixture['options']]
        probs = {ids[0]:1.0,ids[1]:0.0,ids[2]:0.0,ids[3]:0.0}
        custody = MOD.build_question_custody(
            fixture_path, fixture, repository_sha=TEST_REPOSITORY_SHA
        )
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td); semif = td / 'semif.json'; missing = td / 'missing.json'; out = td / 'out.json'
            semif.write_text(json.dumps({'schema':'theseus.quasi-jev-advisory-candidate.v1','claim_scope':'ADVISORY_ONLY','candidate':'semif_qwen3_0_6b_q8','fixture':{'id':FIXTURE_ID},'option_ids':ids,'acceptance_authority':False,'permission_authority':False,'verification_authority':False,'promotion_authority':False,'selected_option':ids[0],'decision_status':'SELECTED','probabilities':probs,'distribution_metrics':MOD.distribution_metrics(probs),'question_custody':custody}))
            MOD.cmd_aggregate(type('A', (), {'fixture_id': FIXTURE_ID, 'semif': str(semif), 'kev': str(missing), 'semif_job_status':'success', 'kev_job_status':'failure', 'out': str(out)})())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt['council_state'], 'INCOMPLETE')
        self.assertEqual(receipt['candidate_jobs']['kev_0_8b'], 'failure')

if __name__ == '__main__': unittest.main()
