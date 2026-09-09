from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "indexnow_ping.py"


class IndexNowCliTests(unittest.TestCase):
    def test_help_exits_without_submitting(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("--dry-run", result.stdout)
        self.assertNotIn("HTTP 200", result.stdout)
        self.assertNotIn("HTTP 202", result.stdout)

    def test_unknown_option_is_rejected_without_submitting(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--not-a-real-option"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertNotIn("HTTP 200", result.stdout)
        self.assertNotIn("HTTP 202", result.stdout)


if __name__ == "__main__":
    unittest.main()
