# input: upload module + mock socketserver HTTP fixtures
# output: unittest test suite for Stage 4 upload state machine
# owner: wanhua.gu
# pos: skill test - upload.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Mock-server-driven tests for upload.py state machine."""
import hashlib
import http.server
import json
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import upload


class MockHandler(http.server.BaseHTTPRequestHandler):
    response_code = 200
    response_body = {"outcome": "ok", "request_id": "req_test_001"}
    request_count = 0

    def do_POST(self):
        type(self).request_count += 1
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(self.response_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.response_body).encode("utf-8"))

    def log_message(self, *args, **kwargs):
        pass


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class _ServerCtx:
    def __init__(self):
        self.httpd = _ReusableTCPServer(("127.0.0.1", 0), MockHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class UploadStateMachineTest(unittest.TestCase):
    def setUp(self):
        MockHandler.response_code = 200
        MockHandler.response_body = {"outcome": "ok", "request_id": "req_test_001"}
        MockHandler.request_count = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / "outbox" / "2026-05-10" / "wanhua.gu"
        self.outbox.mkdir(parents=True)
        self.payload_path = self.outbox / "daily_report.personal.json"
        self.payload = {
            "member_id": "wanhua.gu", "date": "2026-05-10", "type": "personal",
            "content": "x", "submitted_at": "2026-05-10T22:31:04.123456+08:00",
        }
        self.payload_path.write_text(json.dumps(self.payload), encoding="utf-8")
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
        return upload.main([
            "--config", str(self.config_path),
            "--date", "2026-05-10",
            "--backoff-seconds", "0,0,0",
            *extra,
        ])

    def test_success_writes_ack_with_sha256(self):
        rc = self._run()
        self.assertEqual(0, rc)
        ack_path = self.outbox / "daily_report.personal.ack.json"
        self.assertTrue(ack_path.exists())
        ack = json.loads(ack_path.read_text())
        self.assertEqual("ok", ack["outcome"])
        canonical = json.dumps(self.payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), ack["payload_sha256"])

    def test_skips_when_sha256_matches(self):
        self._run()
        before = MockHandler.request_count
        self._run()
        self.assertEqual(before, MockHandler.request_count)

    def test_resends_when_payload_changed(self):
        self._run()
        before = MockHandler.request_count
        self.payload["content"] = "modified"
        self.payload_path.write_text(json.dumps(self.payload), encoding="utf-8")
        self._run()
        self.assertEqual(before + 1, MockHandler.request_count)

    def test_force_ignores_ack(self):
        self._run()
        before = MockHandler.request_count
        self._run("--force")
        self.assertEqual(before + 1, MockHandler.request_count)

    def test_422_writes_error_no_retry(self):
        MockHandler.response_code = 422
        MockHandler.response_body = {"errors": ["content too short"]}
        rc = self._run()
        self.assertNotEqual(0, rc)
        self.assertEqual(1, MockHandler.request_count)
        self.assertTrue((self.outbox / "daily_report.personal.error.json").exists())

    def test_5xx_retries_three_times_then_error(self):
        MockHandler.response_code = 500
        MockHandler.response_body = {}
        rc = self._run()
        self.assertNotEqual(0, rc)
        self.assertEqual(4, MockHandler.request_count)
        self.assertTrue((self.outbox / "daily_report.personal.error.json").exists())

    def test_outcome_ignored_stale_treated_as_ok(self):
        MockHandler.response_body = {"outcome": "ignored_stale", "request_id": "x"}
        rc = self._run()
        self.assertEqual(0, rc)
        self.assertTrue((self.outbox / "daily_report.personal.ack.json").exists())

    def test_outcome_unknown_writes_error(self):
        MockHandler.response_body = {"outcome": "duplicate", "request_id": "x"}
        rc = self._run()
        self.assertNotEqual(0, rc)
        self.assertTrue((self.outbox / "daily_report.personal.error.json").exists())


if __name__ == "__main__":
    unittest.main()
