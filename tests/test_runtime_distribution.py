import json
import tempfile
import unittest
from pathlib import Path

from scripts import write_toolchain_receipt

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements/semif-cpu-runtime.lock.txt"

class RuntimeProfileTests(unittest.TestCase):
    def test_runtime_profile_classifications_are_explicit(self):
        data = json.loads((ROOT / "config/runtime-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "theseus.typed-decision-runtime-profiles.v1")
        profiles = data["profiles"]
        self.assertEqual(profiles["semif"]["classification"], "PACKAGE_REQUIRED")
        self.assertEqual(profiles["semif"]["lock"], "requirements/semif-cpu-runtime.lock.txt")
        self.assertEqual(profiles["nanojev"]["classification"], "RUNTIME_BLOCKED")
        self.assertEqual(profiles["kev"]["classification"], "PACKAGE_CONDITIONAL")
        self.assertEqual(profiles["needle"]["classification"], "PACKAGE_LIGHT")
        self.assertEqual(profiles["system_one_adapter"]["classification"], "PACKAGE_NOT_JUSTIFIED")
        package = profiles["semif"]["package"]
        self.assertEqual(package["artifact_id"], 10772811868)
        self.assertEqual(package["run_id"], 35910243662)
        self.assertEqual(
            package["artifact_digest"],
            "sha256:d0f949f4fcd8cc96f9acd4171f0eb269c9b723b9057afb29f3cb7bf7097638d6",
        )

    def test_cpu_lock_is_hash_complete_and_excludes_cuda_packages(self):
        locked = write_toolchain_receipt.parse_lock(LOCK)
        self.assertGreater(len(locked), 20)
        self.assertEqual(locked["torch"]["version"], "2.10.0+cpu")
        self.assertNotIn("triton", locked)
        self.assertFalse(any(name.startswith("nvidia-") for name in locked))

    def _dist(self, root: Path, name: str, version: str):
        dist = root / f"{name.replace('-', '_')}-{version}.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            encoding="utf-8",
        )

    def _complete_site(self, root: Path):
        for name, version in write_toolchain_receipt.expected_versions(LOCK).items():
            self._dist(root, name, version)
        (root / "payload.py").write_text("x = 1\n", encoding="utf-8")

    def test_toolchain_receipt_accepts_exact_locked_cpu_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            self._complete_site(site)
            receipt = write_toolchain_receipt.build_receipt(site, "a" * 40, LOCK)
            self.assertEqual(receipt["status"], "BUILT")
            self.assertEqual(receipt["cpu_runtime"]["forbidden_cuda_packages"], [])
            self.assertEqual(receipt["distributions"]["torch"], "2.10.0+cpu")
            self.assertEqual(receipt["lock"]["entries"], len(write_toolchain_receipt.parse_lock(LOCK)))
            self.assertFalse(receipt["acceptance_authority"])

    def test_toolchain_receipt_rejects_unexpected_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            self._complete_site(site)
            self._dist(site, "surprise", "1.0")
            with self.assertRaisesRegex(SystemExit, "unexpected distributions"):
                write_toolchain_receipt.build_receipt(site, "a" * 40, LOCK)

    def test_toolchain_receipt_rejects_cuda_runtime_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            self._complete_site(site)
            self._dist(site, "nvidia-cublas-cu12", "12.8.4.1")
            with self.assertRaisesRegex(SystemExit, "unexpected distributions|forbidden CUDA"):
                write_toolchain_receipt.build_receipt(site, "a" * 40, LOCK)

if __name__ == "__main__":
    unittest.main()

class KevRuntimeProfileTests(unittest.TestCase):
    def test_kev_probe_is_exactly_pinned_and_advisory(self):
        data = json.loads((ROOT / "config/runtime-profiles.json").read_text(encoding="utf-8"))
        kev = data["profiles"]["kev"]
        self.assertEqual(kev["classification"], "PACKAGE_CONDITIONAL")
        self.assertEqual(kev["probe_scope"], "RUNTIME_FEASIBILITY_ONLY")
        self.assertEqual(kev["python"], "3.12")
        self.assertEqual(kev["code_revision"], "7405b72e73e2d24787f3720d162a21c974ff2ad2")
        self.assertEqual(kev["checkpoint_revision"], "54f4f8777356cd5bbbb6c6919c657f26e6f2f6d8")
        self.assertEqual(kev["base_revision"], "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68")
