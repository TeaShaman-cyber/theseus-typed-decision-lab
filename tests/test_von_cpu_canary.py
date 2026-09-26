import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("von_canary", ROOT / "scripts/run_von_cpu_canary.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class VonCPUCanaryContractTests(unittest.TestCase):
    def test_distribution_metrics_are_derived_from_full_distribution(self):
        probs = {"A": 0.6, "B": 0.3, "C": 0.1}
        metrics = MOD.distribution_metrics(probs)
        self.assertAlmostEqual(metrics["top1_top2_margin"], 0.3)
        self.assertGreater(metrics["entropy_nats"], 0.0)
        self.assertEqual(metrics["selected"], "A")

    def test_compare_runs_preserves_option_identity_across_reorder(self):
        first = {"A": 0.6, "B": 0.3, "C": 0.1}
        repeat = {"A": 0.6, "B": 0.3, "C": 0.1}
        reorder = {"C": 0.1, "B": 0.3, "A": 0.6}
        observation = MOD.compare_runs(first, repeat, reorder)
        self.assertTrue(observation["repeat_exact"])
        self.assertTrue(observation["reorder_selected_same"])
        self.assertEqual(observation["reorder_max_abs_probability_delta"], 0.0)

    def test_workflow_freezes_source_model_and_registered_fixture(self):
        workflow = (ROOT / ".github/workflows/von-cpu-canary.yml").read_text()
        self.assertIn("62c0725a85060e6e0e9d4d8f2aa91b363930d767", workflow)
        self.assertIn("5df8185a4f2327ad0a7cd117cc4f701ac557b9ae", workflow)
        self.assertIn("orchestration-pending-results-v1", workflow)
        self.assertIn("snapshot_download", workflow)
        self.assertIn("revision=os.environ[\"VON_MODEL_REV\"]", workflow)
        self.assertIn("\"torch==2.10.0+cpu\"", workflow)
        self.assertIn('HF_HUB_OFFLINE: "1"', workflow)
        self.assertIn('TRANSFORMERS_OFFLINE: "1"', workflow)
        self.assertNotIn("quasi-jev-advisory.yml", workflow)

    def test_runtime_requirements_are_top_level_pinned_and_cuda_free(self):
        lines = [
            line.strip()
            for line in (ROOT / "requirements/von-cpu-runtime.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreaterEqual(len(lines), 5)
        self.assertTrue(all("==" in line for line in lines))
        lowered = [line.lower() for line in lines]
        self.assertFalse(any(line.startswith("nvidia-") for line in lowered))
        self.assertFalse(any(line.startswith("triton==") for line in lowered))

    def test_upstream_config_freezes_von_probe_identity(self):
        upstreams = json.loads((ROOT / "config/upstreams.json").read_text())
        self.assertEqual(
            upstreams["sources"]["von"]["revision"],
            "62c0725a85060e6e0e9d4d8f2aa91b363930d767",
        )
        self.assertEqual(
            upstreams["sources"]["von_model"]["revision"],
            "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae",
        )
        profile = json.loads((ROOT / "config/runtime-profiles.json").read_text())
        self.assertEqual(profile["profiles"]["von"]["classification"], "PACKAGE_CONDITIONAL")
        self.assertEqual(profile["profiles"]["von"]["probe_scope"], "RUNTIME_FEASIBILITY_ONLY")


if __name__ == "__main__":
    unittest.main()
