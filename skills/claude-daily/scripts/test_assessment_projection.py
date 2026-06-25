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


class DangerOpTest(unittest.TestCase):
    def test_rm_rf_on_tmp_is_benign(self):
        self.assertFalse(ap.is_danger_op("rm -rf /tmp/hb-test"))

    def test_rm_rf_on_real_path_is_danger(self):
        self.assertTrue(ap.is_danger_op("rm -rf ~/project/src"))

    def test_git_reset_hard_is_danger(self):
        self.assertTrue(ap.is_danger_op("git reset --hard origin/main"))

    def test_plain_command_not_danger(self):
        self.assertFalse(ap.is_danger_op("ls -la"))


class ClaimAndLoopTest(unittest.TestCase):
    def test_has_claim(self):
        self.assertTrue(ap.has_claim("好的，已修复了这个问题"))
        self.assertTrue(ap.has_claim("All tests passing — done."))
        self.assertFalse(ap.has_claim("我先看一下这个文件"))

    def test_detect_loops_flags_repeated_verify_failure(self):
        cmds = [
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
        ]
        loops = ap.detect_loops(cmds)
        self.assertEqual(loops[ap.normalize_cmd("uv run python build-data.py")], 3)

    def test_single_failure_is_not_a_loop(self):
        cmds = [{"cmd": "pytest", "kind": "verify", "outcome": "fail"}]
        self.assertEqual(ap.detect_loops(cmds), {})

    def test_explore_failures_ignored(self):
        cmds = [
            {"cmd": "grep x a", "kind": "explore", "outcome": None},
            {"cmd": "grep x a", "kind": "explore", "outcome": None},
        ]
        self.assertEqual(ap.detect_loops(cmds), {})


def _assistant_bash(cmd, tuid):
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Bash", "id": tuid, "input": {"command": cmd}}]}}


def _assistant_edit(path):
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}}


def _assistant_text(text):
    return {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _tool_result(tuid, is_error, text):
    return {"message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tuid, "is_error": is_error,
         "content": text}]}}


def _user(text):
    return {"message": {"role": "user", "content": text}}


class ProjectSessionTest(unittest.TestCase):
    def test_claim_pairs_with_preceding_failed_verify(self):
        rows = [
            _user("帮我修一下"),
            _assistant_bash("uv run python -m pytest -q", "t1"),
            _tool_result("t1", True, "FAILED tests/x.py"),
            _assistant_text("好了，已修复"),
        ]
        out = ap.project_session(rows)
        self.assertEqual(len(out["claims"]), 1)
        self.assertEqual(out["claims"][0]["prev_verify_outcome"], "fail")

    def test_edit_frequency_not_deduped(self):
        rows = [_assistant_edit("/p/walkthrough.md") for _ in range(3)]
        out = ap.project_session(rows)
        self.assertEqual(out["edit_events"][0], {"file": "walkthrough.md", "n": 3})

    def test_explore_nonzero_not_a_failure(self):
        rows = [
            _assistant_bash("grep -n foo bar.py", "g1"),
            _tool_result("g1", True, ""),
        ]
        out = ap.project_session(rows)
        self.assertEqual(out["commands"][0]["outcome"], None)
        self.assertEqual(out["loops"], {})

    def test_backbone_covers_all_rows(self):
        rows = [_user(f"msg {i}") for i in range(50)]
        out = ap.project_session(rows)
        # 全量覆盖：50 条 user 都在骨架里（不砍头尾）
        self.assertEqual(sum(1 for e in out["event_backbone"] if e["type"] == "user"), 50)


if __name__ == "__main__":
    unittest.main()
