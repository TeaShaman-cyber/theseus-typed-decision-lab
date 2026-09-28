import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_anyjev_hbr1",
    ROOT / "scripts/run_anyjev_hbr1.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class AnyJevHBR1RunnerTests(unittest.TestCase):
    def test_distribution_metrics_and_tie_handling(self):
        probs = {"A": 0.4, "B": 0.4, "C": 0.2}
        selected, status = MOD.select_option(probs)
        self.assertIsNone(selected)
        self.assertEqual(status, "TIE")
        metrics = MOD.distribution_metrics(probs)
        self.assertGreater(metrics["entropy_nats"], 0.0)
        self.assertEqual(metrics["top1_top2_margin"], 0.0)

    def test_distribution_metrics_reject_unnormalized_values(self):
        with self.assertRaisesRegex(ValueError, "not normalized"):
            MOD.distribution_metrics({"A": 0.8, "B": 0.3})

    def test_validate_surface_binds_all_preregistered_hashes(self):
        manifest_path = ROOT / "fixtures/anyjev/hbr1/manifest.json"
        manifest = MOD.load_json(manifest_path)
        for entry in manifest["surfaces"]:
            _, pack = MOD.validate_surface(manifest_path.parent, entry)
            self.assertEqual(set(pack), {"state", "question", "options"})

    def test_validate_surface_rejects_tampered_question_even_if_file_hash_is_updated(self):
        manifest_path = ROOT / "fixtures/anyjev/hbr1/manifest.json"
        manifest = MOD.load_json(manifest_path)
        entry = dict(manifest["surfaces"][0])
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            source = manifest_path.parent / entry["model_input_path"]
            tampered = json.loads(source.read_text(encoding="utf-8"))
            tampered["question"] = "different question"
            target = td / entry["model_input_path"]
            target.write_text(json.dumps(tampered), encoding="utf-8")
            entry["model_input_sha256"] = MOD.sha256_file(target)
            with self.assertRaisesRegex(ValueError, "question hash mismatch"):
                MOD.validate_surface(td, entry)

    def test_workflow_and_runtime_profile_freeze_execution_mode(self):
        workflow = (ROOT / ".github/workflows/anyjev-hbr1.yml").read_text(encoding="utf-8")
        profile = json.loads(
            (ROOT / "config/runtime-profiles.json").read_text(encoding="utf-8")
        )["profiles"]["anyjev"]
        self.assertEqual(
            profile["source_revision"],
            "10d5db91dda38dbde74c6abc1c075ce6463723d1",
        )
        self.assertEqual(
            profile["base_revision"],
            "c1899de289a04d12100db370d81485cdf75e47ca",
        )
        self.assertEqual(profile["probe_scope"], "HBR-1_RAW_L0_ADVISORY_ONLY")
        self.assertEqual(profile["recommended_runtime_path"], "PINNED_COLD_INSTALL")
        self.assertEqual(profile["network_policy"], "OFFLINE_AFTER_PINNED_SNAPSHOT")
        self.assertEqual(
            profile["l0_mode"],
            "FULL_CYCLIC_PERMUTATION_ONLY_PRIOR_NONE",
        )
        for item in (
            "workflow_dispatch:",
            "runs-on: ubuntu-24.04",
            'python-version: "3.12"',
            "10d5db91dda38dbde74c6abc1c075ce6463723d1",
            "c1899de289a04d12100db370d81485cdf75e47ca",
            "torch==2.10.0+cpu",
            "requirements/anyjev-cpu-runtime.txt",
            'HF_HUB_OFFLINE: "1"',
            'TRANSFORMERS_OFFLINE: "1"',
            "scripts/run_anyjev_hbr1.py",
        ):
            self.assertIn(item, workflow)
        self.assertIn('"repository": f"https://huggingface.co/{repo}"', workflow)
        self.assertIn('"repository_id": repo', workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("schedule:", workflow)

    def test_requirements_are_cpu_oriented_and_pinned(self):
        rows = {}
        for raw in (
            ROOT / "requirements/anyjev-cpu-runtime.txt"
        ).read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            name, version = raw.split("==", 1)
            rows[name.lower().replace("_", "-")] = version
        self.assertEqual(rows["transformers"], "5.17.0")
        self.assertEqual(rows["numpy"], "2.2.6")
        self.assertEqual(rows["huggingface-hub"], "1.31.0")
        self.assertNotIn("triton", rows)
        self.assertFalse(any(name.startswith("nvidia-") for name in rows))


if __name__ == "__main__":
    unittest.main()
