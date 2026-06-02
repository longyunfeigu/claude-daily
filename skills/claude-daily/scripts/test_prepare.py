# input: prepare.py via subprocess, temp config + projects fixtures
# output: unittest test suite for Stage 1 CLI behavior
# owner: wanhua.gu
# pos: skill test - prepare.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Subprocess-driven tests for prepare.py CLI."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "prepare.py"

sys.path.insert(0, str(Path(__file__).parent))
import prepare  # noqa: E402


def run(args, env_extra=None, expect_zero=True):
    env = {**os.environ, **(env_extra or {})}
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )
    if expect_zero and p.returncode != 0:
        raise AssertionError(f"prepare.py failed: rc={p.returncode}\nSTDOUT: {p.stdout}\nSTDERR: {p.stderr}")
    return p


class PrepareCliTest(unittest.TestCase):
    def _setup(self, td):
        cfg = Path(td) / "config.json"
        cfg.write_text(json.dumps({
            "member_id": "wanhua.gu",
            "endpoint_base": "http://x",
            "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
            "outbox_dir": str(Path(td) / "outbox"),
            "projects_root": str(Path(td) / "projects"),
        }), encoding="utf-8")
        return cfg

    def test_invalid_member_id_fails(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = self._setup(td)
            cfg.write_text(json.dumps({
                "member_id": "X",
                "endpoint_base": "http://x",
                "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
                "outbox_dir": str(Path(td)),
                "projects_root": str(Path(td)),
            }), encoding="utf-8")
            p = run(["--config", str(cfg), "--date", "2026-05-10"], expect_zero=False)
            self.assertNotEqual(0, p.returncode)
            self.assertIn("member_id", (p.stderr + p.stdout).lower())

    def test_writes_context_json(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = self._setup(td)
            (Path(td) / "projects").mkdir()
            run(["--config", str(cfg), "--date", "2026-05-10"])
            ctx = Path(td) / "outbox" / "2026-05-10" / "wanhua.gu" / "_context.json"
            self.assertTrue(ctx.exists())

    def test_multi_device_warning_emitted(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = self._setup(td)
            (Path(td) / "projects").mkdir()
            other = Path(td) / "outbox" / "2026-05-10" / "other.user"
            other.mkdir(parents=True)
            (other / "_context.json").write_text("{}")
            p = run(["--config", str(cfg), "--date", "2026-05-10"])
            self.assertIn("WARN", p.stdout + p.stderr)
            self.assertIn("other.user", p.stdout + p.stderr)


class ParseCcusageTokensTest(unittest.TestCase):
    def test_maps_period_to_total_tokens(self):
        stdout = json.dumps({"session": [
            {"period": "aaaa1111-...", "totalTokens": 123},
            {"period": "bbbb2222-...", "totalTokens": 456},
        ], "totals": {"totalTokens": 579}})
        m = prepare.parse_ccusage_session_tokens(stdout)
        self.assertEqual(m["aaaa1111-..."], 123)
        self.assertEqual(m["bbbb2222-..."], 456)
        # missing session_id resolves to 0 via .get default (apply step behavior)
        self.assertEqual(m.get("unknown", 0), 0)

    def test_empty_session_list(self):
        self.assertEqual(prepare.parse_ccusage_session_tokens('{"session": []}'), {})


if __name__ == "__main__":
    unittest.main()
