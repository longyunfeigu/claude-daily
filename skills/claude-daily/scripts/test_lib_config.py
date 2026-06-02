# input: _lib_config module, temp JSON fixtures, env vars
# output: unittest test suite for load() and validate()
# owner: wanhua.gu
# pos: skill test - config loader; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
import json
import os
import tempfile
import unittest
from pathlib import Path

import _lib_config as cfg


class ConfigLoadTest(unittest.TestCase):
    def _write(self, td, body):
        path = Path(td) / "config.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def test_validate_member_id_pattern_rejects_invalid(self):
        for bad in ["", "wanhua", "Wanhua.GU", "1leading-digit", "a"]:
            errors = cfg.validate({"member_id": bad,
                                   "endpoint_base": "http://x",
                                   "endpoint_paths": {"daily_report": "/d", "session_card": "/s"}})
            self.assertTrue(any("member_id" in e for e in errors), msg=f"should reject {bad!r}")

    def test_validate_member_id_accepts_valid(self):
        errors = cfg.validate({"member_id": "wanhua.gu",
                               "endpoint_base": "http://x",
                               "endpoint_paths": {"daily_report": "/d", "session_card": "/s"}})
        self.assertEqual([], errors)

    def test_validate_endpoint_base_requires_scheme(self):
        errors = cfg.validate({"member_id": "wanhua.gu",
                               "endpoint_base": "localhost:8000",
                               "endpoint_paths": {"daily_report": "/d", "session_card": "/s"}})
        self.assertTrue(any("endpoint_base" in e for e in errors))

    def test_validate_requires_endpoint_paths(self):
        errors = cfg.validate({"member_id": "wanhua.gu",
                               "endpoint_base": "http://x",
                               "endpoint_paths": {}})
        self.assertTrue(any("daily_report" in e for e in errors))
        self.assertTrue(any("session_card" in e for e in errors))

    def test_load_reads_json_and_expands_user(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write(td, {
                "member_id": "wanhua.gu",
                "endpoint_base": "http://x",
                "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
                "outbox_dir": "~/.local/state/compound-daily/outbox",
            })
            loaded = cfg.load(path)
            self.assertEqual("wanhua.gu", loaded["member_id"])
            self.assertTrue(loaded["outbox_dir"].startswith(str(Path.home())))

    def test_env_override_member_id(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write(td, {"member_id": "from_file",
                                    "endpoint_base": "http://x",
                                    "endpoint_paths": {"daily_report": "/d", "session_card": "/s"}})
            os.environ["COMPOUND_DAILY_MEMBER_ID"] = "from_env"
            try:
                loaded = cfg.load(path)
                self.assertEqual("from_env", loaded["member_id"])
            finally:
                del os.environ["COMPOUND_DAILY_MEMBER_ID"]


    def test_load_raises_on_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            cfg.load(Path("/nonexistent/path/config.json"))

    def test_load_raises_valueerror_on_invalid_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps({
                "member_id": "X",  # invalid
                "endpoint_base": "http://x",
                "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                cfg.load(path)


if __name__ == "__main__":
    unittest.main()
