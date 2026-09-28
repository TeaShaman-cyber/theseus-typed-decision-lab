import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_anyjev_hbr1", ROOT / "scripts/prepare_anyjev_hbr1.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class AnyJevHBR1Tests(unittest.TestCase):
    def generate(self, directory):
        out = pathlib.Path(directory)
        manifest = MOD.generate(out)
        packs = {
            entry["surface_id"]: json.loads((out / entry["model_input_path"]).read_text(encoding="utf-8"))
            for entry in manifest["surfaces"]
        }
        return manifest, packs

    def test_historical_fixture_and_model_pins_are_exact(self):
        self.assertEqual(MOD.sha256_file(MOD.SOURCE_FIXTURE), MOD.EXPECTED_SOURCE_FIXTURE_SHA256)
        cfg = MOD.load_json(MOD.UPSTREAMS)["sources"]
        self.assertEqual(cfg["anyjev"]["revision"], MOD.EXPECTED_ANYJEV_REVISION)
        self.assertEqual(cfg["anyjev"]["package_version"], "0.2.0")
        self.assertEqual(cfg["anyjev"]["observed_at"], "2026-09-28")
        self.assertEqual(cfg["anyjev"]["license"], "Apache-2.0")
        self.assertEqual(cfg["qwen3_0_6b_base"]["revision"], MOD.EXPECTED_BASE_MODEL_REVISION)

    def test_committed_artifacts_match_fresh_regeneration(self):
        committed = ROOT / "fixtures/anyjev/hbr1"
        with tempfile.TemporaryDirectory() as td:
            MOD.generate(pathlib.Path(td))
            names = sorted(path.name for path in committed.iterdir())
            self.assertEqual(names, sorted(path.name for path in pathlib.Path(td).iterdir()))
            for name in names:
                self.assertEqual((committed / name).read_bytes(), (pathlib.Path(td) / name).read_bytes())

    def test_generation_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            MOD.generate(pathlib.Path(a))
            MOD.generate(pathlib.Path(b))
            names = sorted(path.name for path in pathlib.Path(a).iterdir())
            self.assertEqual(names, sorted(path.name for path in pathlib.Path(b).iterdir()))
            for name in names:
                self.assertEqual((pathlib.Path(a) / name).read_bytes(), (pathlib.Path(b) / name).read_bytes())

    def test_s0_is_exact_historical_question_pack(self):
        source = MOD.load_json(MOD.SOURCE_FIXTURE)
        with tempfile.TemporaryDirectory() as td:
            _, packs = self.generate(td)
        self.assertEqual(packs["S0_ORIGINAL"], MOD.question_pack(source))

    def test_s1_changes_only_option_order(self):
        with tempfile.TemporaryDirectory() as td:
            _, packs = self.generate(td)
        s0 = packs["S0_ORIGINAL"]
        s1 = packs["S1_ORDER_PRESERVE"]
        self.assertEqual(s1["state"], s0["state"])
        self.assertEqual(s1["question"], s0["question"])
        self.assertEqual(
            {x["id"]: x["description"] for x in s1["options"]},
            {x["id"]: x["description"] for x in s0["options"]},
        )
        self.assertNotEqual([x["id"] for x in s1["options"]], [x["id"] for x in s0["options"]])

    def test_s2_reorders_state_lines_without_changing_content(self):
        with tempfile.TemporaryDirectory() as td:
            _, packs = self.generate(td)
        s0 = packs["S0_ORIGINAL"]
        s2 = packs["S2_FORMAT_PRESERVE"]
        self.assertEqual(s2["question"], s0["question"])
        self.assertEqual(s2["options"], s0["options"])
        self.assertEqual(sorted(s2["state"].splitlines()), sorted(s0["state"].splitlines()))
        self.assertNotEqual(s2["state"], s0["state"])

    def test_s3_changes_only_repo_search_availability(self):
        with tempfile.TemporaryDirectory() as td:
            _, packs = self.generate(td)
        s0 = packs["S0_ORIGINAL"]
        s3 = packs["S3_SEMANTIC_CHANGE_CONTROL"]
        self.assertEqual(s3["question"], s0["question"])
        self.assertEqual(s3["options"], s0["options"])
        old = "tool.REPO_SEARCH=state:REPROBE_REQUIRED;"
        new = "tool.REPO_SEARCH=state:UNAVAILABLE;"
        self.assertEqual(s0["state"].count(old), 1)
        self.assertEqual(s3["state"].count(new), 1)
        self.assertEqual(s3["state"].replace(new, old, 1), s0["state"])

    def test_model_inputs_do_not_contain_later_m4_m7_outcome_escrow(self):
        forbidden = (
            "GRAPH_TOPOLOGY_CHANGED",
            "EVIDENCE_GRAPH_CONTRADICTION",
            "UNEXPECTED_EXTRA_EDGE_NOT_DETECTED",
            "REQUIRED_EDGE_PRODUCER_NOT_ENFORCED",
        )
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = self.generate(td)
            self.assertFalse(manifest["outcome_escrow_in_candidate_input"])
            for entry in manifest["surfaces"]:
                text = (pathlib.Path(td) / entry["model_input_path"]).read_text(encoding="utf-8")
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_manifest_separates_expected_transform_semantics_from_model_input(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = self.generate(td)
            expected = {x["surface_id"]: x["expected_semantics"] for x in manifest["surfaces"]}
            self.assertEqual(
                expected,
                {
                    "S0_ORIGINAL": "SAME",
                    "S1_ORDER_PRESERVE": "SAME",
                    "S2_FORMAT_PRESERVE": "SAME",
                    "S3_SEMANTIC_CHANGE_CONTROL": "CHANGED",
                },
            )
            for entry in manifest["surfaces"]:
                pack = json.loads((pathlib.Path(td) / entry["model_input_path"]).read_text(encoding="utf-8"))
                self.assertEqual(set(pack), {"state", "question", "options"})
                self.assertNotIn("expected_semantics", pack)


if __name__ == "__main__":
    unittest.main()
