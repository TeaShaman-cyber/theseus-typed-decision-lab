import json
import tempfile
import unittest
from pathlib import Path

from scripts import write_toolchain_receipt

ROOT = Path(__file__).resolve().parents[1]

class RuntimeProfileTests(unittest.TestCase):
    def test_runtime_profile_classifications_are_explicit(self):
        data = json.loads((ROOT / "config/runtime-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "theseus.typed-decision-runtime-profiles.v1")
        profiles = data["profiles"]
        self.assertEqual(profiles["semif"]["classification"], "PACKAGE_REQUIRED")
        self.assertEqual(profiles["nanojev"]["classification"], "RUNTIME_BLOCKED")
        self.assertEqual(profiles["kev"]["classification"], "PACKAGE_CONDITIONAL")
        self.assertEqual(profiles["needle"]["classification"], "PACKAGE_LIGHT")
        self.assertEqual(profiles["system_one_adapter"]["classification"], "PACKAGE_NOT_JUSTIFIED")
        self.assertIsNone(profiles["semif"]["package"])

    def _dist(self, root: Path, name: str, version: str):
        dist = root / f"{name.replace('-', '_')}-{version}.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
            encoding="utf-8",
        )

    def test_toolchain_receipt_accepts_cpu_only_exact_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            for name, version in write_toolchain_receipt.EXPECTED.items():
                self._dist(site, name, version)
            (site / "payload.py").write_text("x = 1\n", encoding="utf-8")
            receipt = write_toolchain_receipt.build_receipt(site, "a" * 40)
            self.assertEqual(receipt["status"], "BUILT")
            self.assertEqual(receipt["cpu_runtime"]["forbidden_cuda_packages"], [])
            self.assertEqual(receipt["distributions"]["torch"], "2.10.0+cpu")
            self.assertFalse(receipt["acceptance_authority"])

    def test_toolchain_receipt_rejects_cuda_runtime_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            for name, version in write_toolchain_receipt.EXPECTED.items():
                self._dist(site, name, version)
            self._dist(site, "nvidia-cublas-cu12", "12.8.4.1")
            with self.assertRaisesRegex(SystemExit, "forbidden CUDA"):
                write_toolchain_receipt.build_receipt(site, "a" * 40)

if __name__ == "__main__":
    unittest.main()
