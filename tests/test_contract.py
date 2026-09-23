import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

class FixtureTests(unittest.TestCase):
    def test_smoke_fixture_is_semif_native_and_unique(self):
        rows = [
            json.loads(line)
            for line in (ROOT / "fixtures/smoke/semif-native.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(rows), 3)
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        for row in rows:
            self.assertIsInstance(row["state"], str)
            self.assertTrue(row["state"])
            self.assertIsInstance(row["question"], str)
            self.assertTrue(row["question"])
            options = row["options"]
            self.assertGreaterEqual(len(options), 2)
            option_ids = [item["id"] for item in options]
            self.assertEqual(len(option_ids), len(set(option_ids)))
            for item in options:
                self.assertTrue(item["description"])

class UpstreamTests(unittest.TestCase):
    def test_upstreams_are_exactly_pinned(self):
        data = json.loads((ROOT / "config/upstreams.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "theseus.typed-decision-upstreams.v1")
        required = {"system_one_adapter", "semif", "nanojev", "kev", "qwen3_0_6b_base", "qwen3_0_6b_gguf"}
        self.assertEqual(set(data["sources"]), required)
        for item in data["sources"].values():
            revision = item["revision"]
            self.assertEqual(len(revision), 40)
            int(revision, 16)
            self.assertTrue(item["license"])

class ReceiptTests(unittest.TestCase):
    def test_receipt_writer_binds_ids_and_hashes(self):
        from scripts import write_runtime_receipt
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fixture = tmp / "fixture.jsonl"
            output = tmp / "output.jsonl"
            runtime = tmp / "runtime.json"
            gguf = tmp / "model.gguf"
            receipt = tmp / "receipt.json"
            fixture.write_text('{"id":"a","state":"s","question":"q","options":[{"id":"x","description":"x"},{"id":"y","description":"y"}]}\n', encoding="utf-8")
            output.write_text(
                '{"id":"a","option_ids":["x","y"],"probabilities":[0.6,0.4],'
                '"option_logits":[1.0,0.0],"model":{"backend":"llamacpp"}}\n',
                encoding="utf-8",
            )
            runtime.write_text('{"schema":"theseus.typed-decision-runtime.v1"}\n', encoding="utf-8")
            gguf.write_bytes(b"tiny")
            argv = [
                "write_runtime_receipt.py",
                "--output", str(output),
                "--runtime", str(runtime),
                "--fixture", str(fixture),
                "--gguf", str(gguf),
                "--upstreams", str(ROOT / "config/upstreams.json"),
                "--out", str(receipt)
            ]
            with mock.patch("sys.argv", argv):
                write_runtime_receipt.main()
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["claim_scope"], "RUNTIME_FEASIBILITY_ONLY")
            self.assertEqual(data["output"]["ids"], ["a"])
            self.assertEqual(data["fixture"]["rows"], 1)
            self.assertEqual(data["gguf"]["bytes"], 4)

    def test_receipt_writer_rejects_missing_probabilities(self):
        from scripts import write_runtime_receipt
        input_rows = [{
            "id": "a",
            "state": "s",
            "question": "q",
            "options": [
                {"id": "x", "description": "x"},
                {"id": "y", "description": "y"},
            ],
        }]
        output_rows = [{"id": "a", "error": "inference failed"}]
        with self.assertRaises(SystemExit):
            write_runtime_receipt.validate_semif_output(input_rows, output_rows)

    def test_receipt_writer_rejects_option_mismatch(self):
        from scripts import write_runtime_receipt
        input_rows = [{
            "id": "a",
            "state": "s",
            "question": "q",
            "options": [
                {"id": "x", "description": "x"},
                {"id": "y", "description": "y"},
            ],
        }]
        output_rows = [{
            "id": "a",
            "option_ids": ["y", "x"],
            "probabilities": [0.5, 0.5],
            "option_logits": [0.0, 0.0],
            "model": {"backend": "llamacpp"},
        }]
        with self.assertRaises(SystemExit):
            write_runtime_receipt.validate_semif_output(input_rows, output_rows)

    def test_receipt_writer_rejects_unnormalized_probabilities(self):
        from scripts import write_runtime_receipt
        input_rows = [{
            "id": "a",
            "state": "s",
            "question": "q",
            "options": [
                {"id": "x", "description": "x"},
                {"id": "y", "description": "y"},
            ],
        }]
        output_rows = [{
            "id": "a",
            "option_ids": ["x", "y"],
            "probabilities": [0.9, 0.9],
            "option_logits": [1.0, 1.0],
            "model": {"backend": "llamacpp"},
        }]
        with self.assertRaises(SystemExit):
            write_runtime_receipt.validate_semif_output(input_rows, output_rows)

if __name__ == "__main__":
    unittest.main()

class CommittedWhitespaceTests(unittest.TestCase):
    def _git(self, cwd, *args, env=None):
        import os
        import subprocess
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=merged,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_github_push_guard_rejects_committed_trailing_whitespace(self):
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._git(tmp, "init", "-b", "main")
            self._git(tmp, "config", "user.email", "qa@example.invalid")
            self._git(tmp, "config", "user.name", "QA")
            (tmp / "sample.txt").write_text("clean\n", encoding="utf-8")
            self._git(tmp, "add", "sample.txt")
            self._git(tmp, "commit", "-m", "base")
            (tmp / "sample.txt").write_text("bad trailing whitespace \n", encoding="utf-8")
            self._git(tmp, "add", "sample.txt")
            self._git(tmp, "commit", "-m", "bad")
            env = os.environ.copy()
            env["GITHUB_ACTIONS"] = "true"
            env.pop("GITHUB_BASE_REF", None)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/check_committed_whitespace.py")],
                cwd=tmp,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("trailing whitespace", result.stdout + result.stderr)

    def test_github_push_guard_accepts_clean_commit(self):
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._git(tmp, "init", "-b", "main")
            self._git(tmp, "config", "user.email", "qa@example.invalid")
            self._git(tmp, "config", "user.name", "QA")
            (tmp / "sample.txt").write_text("clean\n", encoding="utf-8")
            self._git(tmp, "add", "sample.txt")
            self._git(tmp, "commit", "-m", "base")
            (tmp / "sample.txt").write_text("still clean\n", encoding="utf-8")
            self._git(tmp, "add", "sample.txt")
            self._git(tmp, "commit", "-m", "clean")
            env = os.environ.copy()
            env["GITHUB_ACTIONS"] = "true"
            env.pop("GITHUB_BASE_REF", None)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/check_committed_whitespace.py")],
                cwd=tmp,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
