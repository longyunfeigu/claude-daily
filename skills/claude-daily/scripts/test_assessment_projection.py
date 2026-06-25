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


class CliTest(unittest.TestCase):
    def _config(self, td):
        cfg_path = Path(td) / "config.json"
        cfg_path.write_text(json.dumps({
            "member_id": "wanhua.gu",
            "endpoint_base": "http://x",
            "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
            "outbox_dir": str(Path(td) / "outbox"),
            "projects_root": str(Path(td) / "projects"),
        }), encoding="utf-8")
        return cfg_path

    def test_writes_assessment_context(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = self._config(td)
            # 1) 造一个真实 transcript jsonl
            tx = Path(td) / "sess.jsonl"
            rows = [
                {"message": {"role": "user", "content": "修一下"}},
                {"message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Bash", "id": "t1",
                     "input": {"command": "uv run python -m pytest -q"}}]}},
                {"message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1",
                     "is_error": True, "content": "FAILED"}]}},
                {"message": {"role": "assistant", "content": [
                    {"type": "text", "text": "已修复"}]}},
            ]
            tx.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            # 2) 造一个指向它的 _context.json
            outbox = Path(td) / "outbox" / "2026-06-25" / "wanhua.gu"
            outbox.mkdir(parents=True)
            (outbox / "_context.json").write_text(json.dumps({
                "generated_at": "2026-06-25T00:00:00Z",
                "sessions": [{
                    "session_id": "sess-0001", "session_short": "sess",
                    "project_dir": "demo", "transcript_path": str(tx),
                    "user_prompts": ["修一下"],
                }],
            }), encoding="utf-8")
            # 3) 跑 CLI
            p = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(cfg_path),
                 "--date", "2026-06-25"],
                capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr)
            out = json.loads((outbox / "_assessment_context.json").read_text())
            self.assertEqual(out["member_id"], "wanhua.gu")
            sess = out["sessions"][0]
            self.assertEqual(sess["claims"][0]["prev_verify_outcome"], "fail")
            self.assertEqual(sess["user_prompts"], ["修一下"])

    def test_missing_context_errors(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = self._config(td)
            p = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(cfg_path),
                 "--date", "2026-06-25"],
                capture_output=True, text=True)
            self.assertNotEqual(0, p.returncode)
            self.assertIn("_context.json", p.stderr)


if __name__ == "__main__":
    unittest.main()
