# input: upload_assessment module + mock socketserver HTTP fixtures
# output: unittest test suite for ai-assessment upload
# owner: wanhua.gu
# pos: skill test - upload_assessment.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Mock-server-driven tests for upload_assessment.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import upload_assessment
from test_upload import MockHandler, _ServerCtx


META = {
    "member_id": "wanhua.gu",
    "date_range": "2026-07-01",
    "session_count": 1,
    "sessions": [{"session_short": "a8b416f0", "project": "demo",
                  "dims": {"目标与上下文": "强"}, "flags": [], "confidence": "中",
                  "defects": []}],
    "person": {"judgment": "保持主导", "flags": ["本期无明显风险"],
               "strength_themes": [], "risk_themes": [], "training_themes": [],
               "confidence": "中", "do_not_overinterpret": "样本少"},
}

CONTEXT = {
    "sessions": [{
        "session_id": "a8b416f0-0000-0000-0000-000000000001",
        "session_short": "a8b416f0",
        "project_dir": "demo",
        "user_prompts": ["帮我修个 bug"],
        "event_backbone": [{"i": 0, "type": "user", "text": "帮我修个 bug"},
                           {"i": 3, "type": "verify", "text": "pytest -q"}],
    }],
}


class UploadAssessmentTest(unittest.TestCase):
    def setUp(self):
        MockHandler.response_code = 200
        MockHandler.response_body = {"outcome": "ok", "request_id": "req_asmt_001"}
        MockHandler.request_count = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / "outbox" / "2026-07-01" / "wanhua.gu"
        self.outbox.mkdir(parents=True)
        (self.outbox / "_ai_assessment.manager.md").write_text("# 评估\n@3 锚点", encoding="utf-8")
        (self.outbox / "_ai_assessment.personal.md").write_text("# 复盘", encoding="utf-8")
        (self.outbox / "_ai_assessment.meta.json").write_text(
            json.dumps(META, ensure_ascii=False), encoding="utf-8")
        (self.outbox / "_assessment_context.json").write_text(
            json.dumps(CONTEXT, ensure_ascii=False), encoding="utf-8")
        self.server = _ServerCtx()
        self.config_path = Path(self.tmp.name) / "config.json"
        self.config_path.write_text(json.dumps({
            "member_id": "wanhua.gu",
            "endpoint_base": f"http://127.0.0.1:{self.server.port}",
            "endpoint_paths": {
                "daily_report": "/api/v1/ingest/daily-reports",
                "session_card": "/api/v1/ingest/session-cards"},
            "outbox_dir": str(Path(self.tmp.name) / "outbox"),
            "projects_root": str(self.tmp.name),
        }), encoding="utf-8")

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def _run(self, *extra):
        return upload_assessment.main([
            "--config", str(self.config_path),
            "--date", "2026-07-01",
            "--backoff-seconds", "0,0,0",
            *extra,
        ])

    def test_uploads_and_writes_ack(self):
        rc = self._run()
        self.assertEqual(0, rc)
        self.assertEqual(1, MockHandler.request_count)
        payload = json.loads((self.outbox / "ai_assessment.json").read_text(encoding="utf-8"))
        self.assertEqual("wanhua.gu", payload["member_id"])
        self.assertEqual("2026-07-01", payload["date_range"])
        self.assertEqual(1, len(payload["backbones"]))
        self.assertEqual("a8b416f0", payload["backbones"][0]["session_short"])
        self.assertEqual(2, len(payload["backbones"][0]["events"]))
        ack = json.loads((self.outbox / "ai_assessment.ack.json").read_text(encoding="utf-8"))
        self.assertEqual("ok", ack["outcome"])

    def test_second_run_skips_via_ack(self):
        self.assertEqual(0, self._run())
        self.assertEqual(0, self._run())
        self.assertEqual(1, MockHandler.request_count)

    def test_force_reuploads(self):
        self.assertEqual(0, self._run())
        self.assertEqual(0, self._run("--force"))
        self.assertEqual(2, MockHandler.request_count)

    def test_missing_artifact_errors(self):
        (self.outbox / "_ai_assessment.meta.json").unlink()
        self.assertEqual(3, self._run())
        self.assertEqual(0, MockHandler.request_count)

    def test_endpoint_default_path_used(self):
        # config has no ai_assessment path -> default kicks in; assert via ack endpoint
        self.assertEqual(0, self._run())
        ack = json.loads((self.outbox / "ai_assessment.ack.json").read_text(encoding="utf-8"))
        self.assertTrue(ack["endpoint"].endswith("/api/v1/ingest/ai-assessments"))


if __name__ == "__main__":
    unittest.main()
