import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_clef_hbr1", ROOT / "scripts/prepare_clef_hbr1.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClefHBR1PreflightTests(unittest.TestCase):
    def test_exact_clef_pin_and_no_policy_threshold(self):
        self.assertEqual(MOD.CLEF_REPOSITORY, "Cloudflare/clef")
        self.assertEqual(MOD.CLEF_REVISION, "2f3de3dd85f379784083b0814d997ab627200f0c")
        self.assertEqual(MOD.POLICY_VERSION, "NONE")
        self.assertEqual(MOD.THRESHOLD_VERSION, "NONE")

    def test_projection_preserves_hbr1_state_question_and_options(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = MOD.generate(pathlib.Path(td))
            for entry in manifest["surfaces"]:
                source = json.loads((ROOT / "fixtures/anyjev/hbr1" / entry["source_path"]).read_text())
                request = json.loads((pathlib.Path(td) / entry["request_path"]).read_text())
                question = request["questions"][MOD.QUESTION_ID]
                self.assertEqual(request["state"], source["state"])
                self.assertEqual(question["instructions"], source["question"])
                self.assertEqual(list(question["criteria"].items()), [(x["id"], x["description"]) for x in source["options"]])
                self.assertEqual(question["type"], "choice")

    def test_projection_contains_only_system_one_model_state_questions(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = MOD.generate(pathlib.Path(td))
            for entry in manifest["surfaces"]:
                request = json.loads((pathlib.Path(td) / entry["request_path"]).read_text())
                self.assertEqual(set(request), {"model", "state", "questions"})
                self.assertEqual(request["model"], "clef")
                self.assertNotIn("expected_semantics", json.dumps(request))
                self.assertNotIn("outcome", json.dumps(request).lower())

    def test_committed_requests_match_fresh_regeneration(self):
        committed = ROOT / "fixtures/clef/hbr1"
        with tempfile.TemporaryDirectory() as td:
            MOD.generate(pathlib.Path(td))
            expected = sorted(path.name for path in committed.iterdir())
            actual = sorted(path.name for path in pathlib.Path(td).iterdir())
            self.assertEqual(actual, expected)
            for name in expected:
                self.assertEqual((committed / name).read_bytes(), (pathlib.Path(td) / name).read_bytes())

    def test_manifest_binds_existing_hbr1_surface_hashes(self):
        source_manifest = json.loads((ROOT / "fixtures/anyjev/hbr1/manifest.json").read_text())
        expected = {x["surface_id"]: x["model_input_sha256"] for x in source_manifest["surfaces"]}
        with tempfile.TemporaryDirectory() as td:
            manifest = MOD.generate(pathlib.Path(td))
        actual = {x["surface_id"]: x["source_sha256"] for x in manifest["surfaces"]}
        self.assertEqual(actual, expected)
        self.assertFalse(manifest["outcome_escrow_in_candidate_input"])
        self.assertEqual(manifest["policy_version"], "NONE")
        self.assertEqual(manifest["threshold_version"], "NONE")


if __name__ == "__main__":
    unittest.main()
