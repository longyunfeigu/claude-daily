# input: assessment_projection.py functions + temp config/fixtures
# output: unittest suite for the AI-assessment projection layer
# owner: wanhua.gu
# pos: skill test - assessment_projection.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Tests for the assessment projection layer."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "assessment_projection.py"
sys.path.insert(0, str(Path(__file__).parent))
import assessment_projection as ap  # noqa: E402


class ClassifyCommandTest(unittest.TestCase):
    def test_verify_commands(self):
        self.assertEqual(ap.classify_command("uv run python -m pytest -q"), "verify")
        self.assertEqual(ap.classify_command("npm run build"), "verify")
        self.assertEqual(ap.classify_command("cd app && pytest"), "verify")

    def test_explore_commands(self):
        self.assertEqual(ap.classify_command("grep -n foo bar.py"), "explore")
        self.assertEqual(ap.classify_command("find . -name '*.py'"), "explore")
        self.assertEqual(ap.classify_command("git status --short"), "explore")

    def test_other(self):
        self.assertEqual(ap.classify_command("mkdir -p /tmp/x"), "other")


class CommandOutcomeTest(unittest.TestCase):
    def test_verify_pass(self):
        self.assertEqual(ap.command_outcome("verify", False, "5 passed"), "ok")

    def test_verify_fail_via_is_error(self):
        self.assertEqual(ap.command_outcome("verify", True, ""), "fail")

    def test_verify_fail_via_text(self):
        self.assertEqual(ap.command_outcome("verify", False, "FAILED tests/x.py"), "fail")

    def test_explore_nonzero_is_not_failure(self):
        # grep no-match returns exit 1 — benign, must NOT be a failure
        self.assertIsNone(ap.command_outcome("explore", True, ""))


if __name__ == "__main__":
    unittest.main()
