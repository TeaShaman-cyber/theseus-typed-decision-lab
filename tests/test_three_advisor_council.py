import json
import os
import pathlib
import tempfile
import unittest

from scripts import quasi_jev_advisory as MOD

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_ID = "orchestration-pending-results-v1"
TEST_SHA = os.environ.get("GITHUB_SHA", "a" * 40)


class ThreeAdvisorCouncilTests(unittest.TestCase):
    def setUp(self):
        self.fixture_path, self.fixture = MOD.safe_registered_fixture(FIXTURE_ID)
        self.ids = [x["id"] for x in self.fixture["options"]]
        self.custody = MOD.build_question_custody(
            self.fixture_path, self.fixture, repository_sha=TEST_SHA
        )

    def _base_candidate(self, candidate, probs):
        selected, status = MOD.select_option(probs)
        return {
            "schema": "theseus.quasi-jev-advisory-candidate.v1",
            "claim_scope": "ADVISORY_ONLY",
            "candidate": candidate,
            "fixture": {"id": FIXTURE_ID},
            "option_ids": self.ids,
            "probabilities": probs,
            "distribution_metrics": MOD.distribution_metrics(probs),
            "question_custody": self.custody,
            "selected_option": selected,
            "decision_status": status,
            "acceptance_authority": False,
            "permission_authority": False,
            "verification_authority": False,
            "promotion_authority": False,
        }

    def _von_raw(self):
        probs = {
            self.ids[0]: 0.4763,
            self.ids[1]: 0.1281,
            self.ids[2]: 0.2498,
            self.ids[3]: 0.1459,
        }
        return {
            "schema": "theseus.von-cpu-feasibility.v1",
            "claim_scope": "RUNTIME_FEASIBILITY_ONLY",
            "classification": "CPU_FEASIBLE",
            "repository_sha": TEST_SHA,
            "identity": {
                "source_repo": "wfzyx/von",
                "source_revision": "62c0725a85060e6e0e9d4d8f2aa91b363930d767",
                "source_install": {"commit_id": "62c0725a85060e6e0e9d4d8f2aa91b363930d767"},
                "model_repo": "wfzyx/von",
                "model_revision": "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae",
                "model_snapshot": {"manifest_sha256": "807060a2d8aaff8cce10b0277bbccbe883aa00fc972efd409094bbabf4f21034"},
            },
            "fixture": {
                "id": FIXTURE_ID,
                "sha256": MOD.sha256_file(self.fixture_path),
                "question_pack_sha256": self.custody["question_pack_sha256"],
            },
            "runtime": {
                "hf_hub_offline": True,
                "transformers_offline": True,
            },
            "calibration": {
                "status": "CALIBRATED",
                "mode": "INPUT_CONDITIONED_MAP",
                "artifact": {"sha256": "9b32949dcd0cfd122db509c9bd5be67f0cfe35696153aa93d667caf0aae147c9"},
            },
            "observations": {
                "original": {
                    "choice": self.ids[0],
                    "probabilities": probs,
                    "reported_confidence": 0.302,
                }
            },
            "acceptance_authority": False,
            "permission_authority": False,
            "verification_authority": False,
            "promotion_authority": False,
        }

    def test_normalize_von_preserves_identity_calibration_and_distribution(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            raw = td / "von-raw.json"
            custody = td / "custody.json"
            out = td / "candidate.json"
            raw.write_text(json.dumps(self._von_raw()))
            custody.write_text(json.dumps(self.custody))
            MOD.cmd_normalize_von(type("A", (), {
                "fixture_id": FIXTURE_ID,
                "raw": str(raw),
                "custody": str(custody),
                "out": str(out),
            })())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt["candidate"], "von_1_2_0")
        self.assertEqual(receipt["selected_option"], self.ids[0])
        self.assertEqual(receipt["model_identity"]["source_revision"], "62c0725a85060e6e0e9d4d8f2aa91b363930d767")
        self.assertEqual(receipt["model_identity"]["model_revision"], "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae")
        self.assertEqual(receipt["calibration"]["status"], "CALIBRATED")
        self.assertEqual(receipt["reported_confidence"], 0.302)
        self.assertAlmostEqual(sum(receipt["probabilities"].values()), 1.0001)
        self.assertEqual(receipt["probabilities"][self.ids[3]], 0.1459)

    def test_normalize_von_accepts_tied_distribution_as_abstention(self):
        raw_value = self._von_raw()
        tied = {
            self.ids[0]: 0.4,
            self.ids[1]: 0.4,
            self.ids[2]: 0.1,
            self.ids[3]: 0.1,
        }
        raw_value["observations"]["original"]["probabilities"] = tied
        raw_value["observations"]["original"]["choice"] = self.ids[0]
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            raw = td / "von-raw.json"
            custody = td / "custody.json"
            out = td / "candidate.json"
            raw.write_text(json.dumps(raw_value))
            custody.write_text(json.dumps(self.custody))
            MOD.cmd_normalize_von(type("A", (), {
                "fixture_id": FIXTURE_ID,
                "raw": str(raw),
                "custody": str(custody),
                "out": str(out),
            })())
            receipt = json.loads(out.read_text())
        self.assertIsNone(receipt["selected_option"])
        self.assertEqual(receipt["decision_status"], "TIE")
        self.assertEqual(receipt["probabilities"], tied)

    def test_aggregate_three_candidates_preserves_distributions_without_authority(self):
        probs = {self.ids[0]: 0.7, self.ids[1]: 0.1, self.ids[2]: 0.1, self.ids[3]: 0.1}
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            paths = {}
            for name in ("semif_qwen3_0_6b_q8", "kev_0_8b", "von_1_2_0"):
                p = td / f"{name}.json"
                p.write_text(json.dumps(self._base_candidate(name, probs)))
                paths[name] = p
            out = td / "out.json"
            MOD.cmd_aggregate(type("A", (), {
                "fixture_id": FIXTURE_ID,
                "semif": str(paths["semif_qwen3_0_6b_q8"]),
                "kev": str(paths["kev_0_8b"]),
                "von": str(paths["von_1_2_0"]),
                "semif_job_status": "success",
                "kev_job_status": "success",
                "von_job_status": "success",
                "out": str(out),
            })())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt["availability"], "COMPLETE")
        self.assertEqual(receipt["council_state"], "AGREE")
        self.assertEqual(set(receipt["candidates"]), {"semif_qwen3_0_6b_q8", "kev_0_8b", "von_1_2_0"})
        self.assertFalse(receipt["consensus_grants_authority"])

    def test_one_missing_advisor_is_degraded_not_erased(self):
        probs = {self.ids[0]: 0.7, self.ids[1]: 0.1, self.ids[2]: 0.1, self.ids[3]: 0.1}
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            semif = td / "semif.json"
            kev = td / "kev.json"
            missing = td / "von-missing.json"
            out = td / "out.json"
            semif.write_text(json.dumps(self._base_candidate("semif_qwen3_0_6b_q8", probs)))
            kev.write_text(json.dumps(self._base_candidate("kev_0_8b", probs)))
            MOD.cmd_aggregate(type("A", (), {
                "fixture_id": FIXTURE_ID,
                "semif": str(semif),
                "kev": str(kev),
                "von": str(missing),
                "semif_job_status": "success",
                "kev_job_status": "success",
                "von_job_status": "failure",
                "out": str(out),
            })())
            receipt = json.loads(out.read_text())
        self.assertEqual(receipt["availability"], "DEGRADED")
        self.assertEqual(receipt["council_state"], "AGREE")
        self.assertIsNone(receipt["candidates"]["von_1_2_0"])
        self.assertIsNotNone(receipt["candidates"]["semif_qwen3_0_6b_q8"])
        self.assertIsNotNone(receipt["candidates"]["kev_0_8b"])

    def test_von_question_custody_is_written_before_scoring(self):
        workflow = (ROOT / ".github/workflows/quasi-jev-advisory.yml").read_text()
        self.assertLess(
            workflow.index("Prepare Von question custody"),
            workflow.index("Ask Von consultant"),
        )

    def test_workflow_has_third_candidate_but_no_majority_authority(self):
        workflow = (ROOT / ".github/workflows/quasi-jev-advisory.yml").read_text()
        self.assertIn("von:", workflow)
        self.assertIn("normalize-von", workflow)
        self.assertIn("needs: [gate, semif, kev, von]", workflow)
        self.assertNotIn("2-of-3", workflow)
        self.assertNotIn("majority", workflow.lower())


if __name__ == "__main__":
    unittest.main()
