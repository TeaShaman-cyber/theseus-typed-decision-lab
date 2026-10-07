import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SemIf4BCausalReplayTests(unittest.TestCase):
    def test_upstream_pins_exist(self):
        cfg = json.loads((ROOT / "config/upstreams.json").read_text())
        src = cfg["sources"]
        self.assertEqual(src["semif_qwen3_5_4b"]["revision"], "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")
        self.assertEqual(src["semif_qwen3_5_4b_gguf"]["revision"], "4168f45a16a1290d65a4ec0fa312ae917a4c15d6")
        self.assertEqual(src["semif_qwen3_5_4b_gguf"]["file"], "Qwen_Qwen3.5-4B-Q4_K_M.gguf")
        self.assertEqual(src["semif_qwen3_5_4b_gguf"]["bytes"], 3013027808)

    def test_workflow_is_standalone_and_uses_exact_pair(self):
        wf = (ROOT / ".github/workflows/semif-4b-causal-replay.yml").read_text()
        self.assertIn("orchestration-pending-results-v1", wf)
        self.assertIn("orchestration-results-consumed-v1", wf)
        self.assertIn("semif_qwen3_5_4b", wf)
        self.assertIn("semif_qwen3_5_4b_gguf", wf)
        self.assertIn("/usr/bin/time -v", wf)
        self.assertNotIn("quasi-jev-council", wf)


    def test_analyzer_evaluates_direction_and_preserves_raw_logits(self):
        from scripts import analyze_semif_causal_replay as a
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            common = {
                "option_ids": ["READ_PENDING_RESULTS", "OTHER"],
                "prompt_sha256": "a" * 64,
                "input_tokens": 10,
                "model": {"source": "Qwen/Qwen3.5-4B"},
            }
            base = dict(common, id=a.BASE_ID, probabilities=[0.8, 0.2], option_logits=[4.0, 1.0])
            causal = dict(common, id=a.CAUSAL_ID, probabilities=[0.3, 0.7], option_logits=[1.5, 2.0])
            raw = tmp / "raw.jsonl"
            raw.write_text(json.dumps(base)+"\n"+json.dumps(causal)+"\n")
            rows = a.load_rows(raw)
            b = a.metrics(rows[a.BASE_ID]); c = a.metrics(rows[a.CAUSAL_ID])
            self.assertLess(c["probabilities"][a.TARGET], b["probabilities"][a.TARGET])
            self.assertEqual(b["option_logits"][a.TARGET], 4.0)
            timing = tmp / "timing.txt"
            timing.write_text("\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:23.45\n\tMaximum resident set size (kbytes): 456789\n")
            parsed = a.parse_timing(timing)
            self.assertEqual(parsed["elapsed_wall"], "1:23.45")
            self.assertEqual(parsed["max_rss_kib"], 456789)

    def test_analyzer_preregisters_target_direction(self):
        script = (ROOT / "scripts/analyze_semif_causal_replay.py").read_text()
        self.assertIn('TARGET = "READ_PENDING_RESULTS"', script)
        self.assertIn('directional_pass', script)
        self.assertIn('option_logits', script)


if __name__ == "__main__":
    unittest.main()
