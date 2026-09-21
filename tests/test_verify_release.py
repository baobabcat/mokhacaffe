from pathlib import Path
import stat
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "operations" / "verify-release.sh"


class ReleaseVerificationTests(unittest.TestCase):
    def test_release_verifier_runs_the_complete_non_mutating_gate(self):
        script = SCRIPT.read_text(encoding="utf-8")

        required_commands = [
            "python3 -m unittest discover -s tests -p 'test_*.py'",
            "node --test tests/feed-analytics.test.mjs",
            "python3 -m compileall -q tools tests",
            "python3 tools/gen_feed.py --check",
            "git diff --check",
            "python3 tools/seo_audit.py",
            "python3 tools/check_sources.py",
            'npx --no-install wrangler check startup --outfile "$STARTUP_PROFILE"',
            "npx --no-install wrangler deploy --dry-run",
            "operations/mokhacaffe-health.sh",
        ]
        for command in required_commands:
            with self.subTest(command=command):
                self.assertIn(command, script)

        self.assertIn("set -euo pipefail", script)
        self.assertIn('mktemp -- "${TMPDIR:-/tmp}/mokhacaffe-startup.XXXXXX.cpuprofile"', script)
        self.assertIn('rm -f -- "$STARTUP_PROFILE"', script)
        self.assertNotIn("npx wrangler deploy\n", script)
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
