# input: emit module via direct import + minimal markdown fixtures inline
# output: unittest test suite for split / resolve / inject helpers
# owner: wanhua.gu
# pos: skill test - emit.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Direct-import tests for emit helper functions."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import emit


FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "sample_minimal"


class SplitSessionCardsTest(unittest.TestCase):
    def test_split_three_blocks(self):
        md = """# Session Cards

## Session `aaa11111`：A title

content A

## Session `bbb22222`：B title

content B

## Session `ccc33333`：C title

content C

# Daily Report

stuff
"""
        blocks = emit.split_session_cards(md)
        self.assertEqual(3, len(blocks))
        self.assertEqual("aaa11111", blocks[0]["short"])
        self.assertEqual("A title", blocks[0]["title"])

    def test_split_no_session_cards_section(self):
        md = "# Daily Report\nonly daily"
        self.assertEqual([], emit.split_session_cards(md))


class ResolveShortTest(unittest.TestCase):
    def setUp(self):
        self.context = {"sessions": [
            {"session_id": "f66e2252-9cef-4d50-b8f2-000000000001"},
            {"session_id": "55e3ff9b-3a4c-0000-0000-000000000002"},
        ]}

    def test_unique_match(self):
        m = emit.resolve_short_to_full(["f66e2252"], self.context)
        self.assertEqual("f66e2252-9cef-4d50-b8f2-000000000001", m["f66e2252"])

    def test_collision_returns_none_for_expansion(self):
        ctx = {"sessions": [
            {"session_id": "f66e2252-aaaa-..."},
            {"session_id": "f66e2252-bbbb-..."},
        ]}
        m = emit.resolve_short_to_full(["f66e2252"], ctx)
        self.assertIsNone(m["f66e2252"])

    def test_unknown_short_raises(self):
        with self.assertRaises(ValueError):
            emit.resolve_short_to_full(["deadbeef"], self.context)


class InjectAnchorsTest(unittest.TestCase):
    def test_injects_backtick_short(self):
        md = "see `f66e2252` for details"
        out = emit.inject_session_links(md, "wanhua.gu",
                                        {"f66e2252": "f66e2252-9cef-4d50-b8f2-001"})
        self.assertIn("[`f66e2252`](/sessions/wanhua.gu/f66e2252-9cef-4d50-b8f2-001)", out)

    def test_idempotent(self):
        md = "see `f66e2252` for details"
        once = emit.inject_session_links(md, "wanhua.gu",
                                         {"f66e2252": "f66e2252-9cef-4d50-b8f2-001"})
        twice = emit.inject_session_links(once, "wanhua.gu",
                                          {"f66e2252": "f66e2252-9cef-4d50-b8f2-001"})
        self.assertEqual(once, twice)

    def test_does_not_match_bare_hex(self):
        md = "commit a1b2c3d4 was reverted"  # no backticks
        out = emit.inject_session_links(md, "wanhua.gu",
                                        {"a1b2c3d4": "a1b2c3d4-aaaa-bbbb-cccc-001"})
        self.assertEqual(md, out)

    def test_unknown_short_left_alone(self):
        md = "see `deadbeef` here"
        out = emit.inject_session_links(md, "wanhua.gu", {})
        self.assertEqual(md, out)


class TolerantMetaParseTest(unittest.TestCase):
    def setUp(self):
        self.context = {"sessions": [
            {"session_id": "f66e2252-9cef-4d50-b8f2-000000000001"},
            {"session_id": "55e3ff9b-3a4c-0000-0000-000000000002"},
        ]}

    def test_camelcase_keys_normalized(self):
        meta = [{"sessionId": "f66e2252-9cef-4d50-b8f2-000000000001",
                 "valueTag": "valuable",
                 "summary": "x"}]
        normalized, fixes = emit.normalize_meta(meta, self.context)
        self.assertEqual("f66e2252-9cef-4d50-b8f2-000000000001",
                         normalized[0]["session_id"])
        self.assertEqual("valuable", normalized[0]["value_tag"])
        self.assertTrue(any("sessionId" in f for f in fixes))

    def test_enum_typo_corrected(self):
        meta = [{"session_id": "f66e2252-9cef-4d50-b8f2-000000000001",
                 "value_tag": "valueable",
                 "summary": "x"}]
        normalized, fixes = emit.normalize_meta(meta, self.context)
        self.assertEqual("valuable", normalized[0]["value_tag"])
        self.assertTrue(any("valueable" in f for f in fixes))

    def test_dict_wrapped_list_unwrapped(self):
        meta = {"sessions": [{"session_id": "f66e2252-9cef-4d50-b8f2-000000000001",
                              "value_tag": "valuable", "summary": "x"}]}
        normalized, fixes = emit.normalize_meta(meta, self.context)
        self.assertEqual(1, len(normalized))

    def test_short_session_id_recovered_to_full(self):
        meta = [{"session_id": "f66e2252",
                 "value_tag": "valuable", "summary": "x"}]
        normalized, fixes = emit.normalize_meta(meta, self.context)
        self.assertEqual("f66e2252-9cef-4d50-b8f2-000000000001",
                         normalized[0]["session_id"])


class EmitEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / "outbox" / "2026-05-10" / "wanhua.gu"
        self.outbox.mkdir(parents=True)
        for name in ("_output.personal.md", "_output.boss.md",
                     "_session_meta.json"):
            shutil.copy(FIXTURE / "llm_output" / name, self.outbox / name)
        ctx = {"sessions": [{
            "session_id": "f66e2252-9cef-4d50-b8f2-000000000001",
            "started_at": "2026-05-10T09:42:11+08:00",
            "duration_seconds": 814,
            "tokens": 5800,
        }]}
        (self.outbox / "_context.json").write_text(json.dumps(ctx), encoding="utf-8")
        self.config_path = Path(self.tmp.name) / "config.json"
        self.config_path.write_text(json.dumps({
            "member_id": "wanhua.gu",
            "endpoint_base": "http://x",
            "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
            "outbox_dir": str(Path(self.tmp.name) / "outbox"),
            "projects_root": str(self.tmp.name),
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_emit_writes_3_payloads(self):
        rc = emit.main(["--config", str(self.config_path), "--date", "2026-05-10"])
        self.assertEqual(0, rc)
        self.assertTrue((self.outbox / "daily_report.personal.json").exists())
        self.assertTrue((self.outbox / "daily_report.boss.json").exists())
        self.assertTrue((self.outbox / "session_card.f66e2252.json").exists())

    def test_session_card_contains_full_8field_markdown(self):
        emit.main(["--config", str(self.config_path), "--date", "2026-05-10"])
        sc = json.loads((self.outbox / "session_card.f66e2252.json").read_text())
        self.assertIn("原本想做什么", sc["content"])
        self.assertIn("主要过程", sc["content"])
        self.assertIn("沉淀", sc["content"])
        self.assertEqual("valuable", sc["value_tag"])
        self.assertEqual(5800, sc["token"])
        self.assertEqual(814, sc["duration"])

    def test_daily_report_anchors_injected(self):
        emit.main(["--config", str(self.config_path), "--date", "2026-05-10"])
        dr = json.loads((self.outbox / "daily_report.personal.json").read_text())
        self.assertIn("[`f66e2252`](/sessions/wanhua.gu/f66e2252-9cef-4d50-b8f2-000000000001)",
                      dr["content"])

    def test_emit_missing_artifact_fails(self):
        (self.outbox / "_output.boss.md").unlink()
        rc = emit.main(["--config", str(self.config_path), "--date", "2026-05-10"])
        self.assertNotEqual(0, rc)

    def test_token_null_omits_field(self):
        ctx_path = self.outbox / "_context.json"
        ctx = json.loads(ctx_path.read_text())
        ctx["sessions"][0]["tokens"] = None
        ctx["sessions"][0]["duration_seconds"] = None
        ctx_path.write_text(json.dumps(ctx), encoding="utf-8")
        emit.main(["--config", str(self.config_path), "--date", "2026-05-10"])
        sc = json.loads((self.outbox / "session_card.f66e2252.json").read_text())
        self.assertNotIn("token", sc)
        self.assertNotIn("duration", sc)


if __name__ == "__main__":
    unittest.main()
