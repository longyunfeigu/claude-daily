import json
import tempfile
import unittest
from pathlib import Path

import build_report_context as brc


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class BuildReportContextTest(unittest.TestCase):
    def test_parse_session_filters_noise_and_extracts_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            session = root / "-tmp-project" / "abc12345-0000.jsonl"
            write_jsonl(
                session,
                [
                    {"type": "last-prompt", "lastPrompt": "duplicate", "sessionId": "abc12345-0000"},
                    {
                        "type": "user",
                        "timestamp": "2026-05-06T01:00:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "abc12345-0000",
                        "message": {
                            "content": "<local-command-caveat>noise</local-command-caveat>",
                        },
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-05-06T01:01:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "abc12345-0000",
                        "message": {"content": "Base directory for this skill: /tmp/skill\n# Some Skill"},
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-05-06T01:01:30.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "abc12345-0000",
                        "message": {"content": "[Request interrupted by user for tool use]"},
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-05-06T01:02:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "abc12345-0000",
                        "message": {"content": "帮我解释 sandbox 是什么"},
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-05-06T01:02:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "abc12345-0000",
                        "message": {
                            "usage": {
                                "input_tokens": 10,
                                "output_tokens": 20,
                                "cache_read_input_tokens": 30,
                                "cache_creation_input_tokens": 40,
                            },
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Read",
                                    "input": {"file_path": "/tmp/project/src/sandbox.ts"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "Bash",
                                    "input": {"command": "rg sandbox /tmp/project"},
                                },
                            ],
                        },
                    },
                ],
            )

            parsed = brc.parse_session_file(session)

            self.assertEqual(parsed["session_id"], "abc12345-0000")
            self.assertEqual(parsed["project_path"], "/tmp/project")
            self.assertEqual(parsed["user_prompts"], ["帮我解释 sandbox 是什么"])
            self.assertEqual(parsed["tools"]["Read"], 1)
            self.assertEqual(parsed["tools"]["Bash"], 1)
            self.assertEqual(parsed["files_read"], ["/tmp/project/src/sandbox.ts"])
            self.assertEqual(parsed["commands"], ["rg sandbox /tmp/project"])
            self.assertEqual(parsed["token_usage"]["output"], 20)

    def test_find_sessions_uses_top_level_sessions_only_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            top = root / "-tmp-project" / "top123.jsonl"
            sub = root / "-tmp-project" / "top123" / "subagents" / "agent-a.jsonl"
            write_jsonl(top, [{"type": "user", "message": {"content": "top"}}])
            write_jsonl(sub, [{"type": "user", "message": {"content": "sub"}}])

            found = brc.find_session_files(root, [], include_subagents=False)

            self.assertEqual(found, [top])

    def test_date_filter_uses_local_offset_and_any_activity(self):
        sessions = [
            {
                "session_id": "late-utc",
                "active_dates": {
                    "+08:00": ["2026-05-06"],
                },
            },
            {
                "session_id": "other-day",
                "active_dates": {
                    "+08:00": ["2026-05-07"],
                },
            },
        ]

        filtered = brc.filter_by_date(sessions, "2026-05-06", "+08:00")

        self.assertEqual([s["session_id"] for s in filtered], ["late-utc"])

    def test_extracts_assistant_segments_with_mechanical_signals(self):
        with tempfile.TemporaryDirectory() as td:
            session = Path(td) / "projects" / "-tmp-project" / "key123.jsonl"
            write_jsonl(
                session,
                [
                    {
                        "type": "user",
                        "timestamp": "2026-05-06T01:00:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "key123",
                        "message": {"content": "这个系统的本质是什么"},
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-05-06T01:01:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "key123",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "关键结论：这个系统的本质是先抽事实，再做语义总结。",
                                }
                            ]
                        },
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-05-06T01:02:00.000Z",
                        "cwd": "/tmp/project",
                        "sessionId": "key123",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "我现在继续看下一个文件。",
                                }
                            ]
                        },
                    },
                ],
            )

            parsed = brc.parse_session_file(session)

            self.assertNotIn("assistant_key_points", parsed)
            self.assertEqual(len(parsed["assistant_segments"]), 2)
            self.assertEqual(parsed["assistant_segments"][0]["kind"], "paragraph")
            self.assertIn("contains_keyword", parsed["assistant_segments"][0]["signals"])
            self.assertNotIn("contains_keyword", parsed["assistant_segments"][1]["signals"])

    def test_compact_events_interleave_assistant_voice(self):
        with tempfile.TemporaryDirectory() as td:
            session = Path(td) / "projects" / "-tmp-project" / "arc12345.jsonl"
            write_jsonl(
                session,
                [
                    {"type": "user", "timestamp": "2026-05-06T01:00:00.000Z",
                     "cwd": "/tmp/project", "sessionId": "arc12345",
                     "message": {"content": "把 X 改成 Y"}},
                    {"type": "assistant", "timestamp": "2026-05-06T01:00:10.000Z",
                     "cwd": "/tmp/project", "sessionId": "arc12345",
                     "message": {"content": [
                         {"type": "text", "text": "好的，我先读一下相关文件再改。"},
                         {"type": "tool_use", "name": "Read",
                          "input": {"file_path": "/tmp/project/x.py"}},
                     ]}},
                ],
            )

            parsed = brc.parse_session_file(session)

            # timeline now reads 用户问 -> AI 答 -> 工具, so the dialogue arc is reconstructable
            kinds = [e["type"] for e in parsed["compact_events"]]
            self.assertEqual(kinds, ["user_prompt", "assistant", "tool"])
            self.assertIn("好的", parsed["compact_events"][1]["text"])


class AttachSessionMetricsTest(unittest.TestCase):
    def _session(self, rows):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            session = root / "-tmp-project" / "f66e2252-0001.jsonl"
            write_jsonl(session, rows)
            paths = brc.find_session_files(root, session_prefixes=None)
            self.assertEqual(1, len(paths))
            return brc.parse_session_file(paths[0])

    def test_metrics_basic_token_sum(self):
        sess = self._session([
            {"type": "user",      "timestamp": "2026-05-10T01:00:00.000Z",
             "sessionId": "f66e2252-0001", "cwd": "/tmp",
             "message": {"content": "hi"}},
            {"type": "assistant", "timestamp": "2026-05-10T01:00:30.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"content": "ok", "usage": {
                 "input_tokens": 10, "output_tokens": 20,
                 "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3}}},
        ])
        self.assertEqual(38, sess["tokens"])
        self.assertEqual(30, sess["duration_seconds"])
        self.assertTrue(sess["started_at"].startswith("2026-05-10T09:00:00"))

    def test_metrics_deduplicates_repeated_usage_by_message_id(self):
        sess = self._session([
            {"type": "assistant", "timestamp": "2026-05-10T01:00:00.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"id": "msg_01same", "content": "ok", "usage": {
                 "input_tokens": 10, "output_tokens": 20,
                 "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3}}},
            {"type": "assistant", "timestamp": "2026-05-10T01:00:01.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"id": "msg_01same", "content": "ok", "usage": {
                 "input_tokens": 10, "output_tokens": 20,
                 "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3}}},
        ])
        self.assertEqual(38, sess["tokens"])
        self.assertEqual(1, sess["request_count"])
        self.assertEqual(1, sess["duplicate_usage_rows"])

    def test_metrics_no_timestamps_returns_none(self):
        sess = self._session([
            {"type": "user", "sessionId": "f66e2252-0001", "cwd": "/tmp",
             "message": {"content": "hi"}},
        ])
        self.assertIsNone(sess["started_at"])
        self.assertIsNone(sess["duration_seconds"])

    def test_metrics_no_usage_returns_null_tokens(self):
        sess = self._session([
            {"type": "user",      "timestamp": "2026-05-10T01:00:00.000Z",
             "sessionId": "f66e2252-0001", "cwd": "/tmp",
             "message": {"content": "hi"}},
            {"type": "assistant", "timestamp": "2026-05-10T01:00:30.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"content": "ok"}},
        ])
        self.assertIsNone(sess["tokens"])

    def test_metrics_partial_usage_sums_only_present(self):
        sess = self._session([
            {"type": "assistant", "timestamp": "2026-05-10T01:00:00.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"content": "x", "usage": {"input_tokens": 100}}},
            {"type": "assistant", "timestamp": "2026-05-10T01:00:10.000Z",
             "sessionId": "f66e2252-0001",
             "message": {"content": "y"}},
        ])
        self.assertEqual(100, sess["tokens"])


class BuildContextSubagentUsageTest(unittest.TestCase):
    def test_subagent_usage_rolls_up_to_parent_without_adding_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            top = root / "-tmp-project" / "parent1234-0000.jsonl"
            sub = root / "-tmp-project" / "parent1234-0000" / "subagents" / "agent-a.jsonl"
            write_jsonl(top, [
                {"type": "assistant", "timestamp": "2026-05-10T01:00:00.000Z",
                 "sessionId": "parent1234-0000", "message": {
                     "id": "msg_top", "content": "top", "usage": {
                         "input_tokens": 10, "output_tokens": 20,
                         "cache_read_input_tokens": 30,
                         "cache_creation_input_tokens": 40}}},
            ])
            write_jsonl(sub, [
                {"type": "assistant", "timestamp": "2026-05-10T01:01:00.000Z",
                 "sessionId": "agent-a", "message": {
                     "id": "msg_sub", "content": "sub", "usage": {
                         "input_tokens": 1, "output_tokens": 2,
                         "cache_read_input_tokens": 3,
                         "cache_creation_input_tokens": 4}}},
                {"type": "assistant", "timestamp": "2026-05-10T01:01:01.000Z",
                 "sessionId": "agent-a", "message": {
                     "id": "msg_sub", "content": "sub duplicate", "usage": {
                         "input_tokens": 1, "output_tokens": 2,
                         "cache_read_input_tokens": 3,
                         "cache_creation_input_tokens": 4}}},
            ])

            context = brc.build_context(
                root,
                date="2026-05-10",
                timezone_offset="+08:00",
                include_subagent_usage=True,
            )

            self.assertEqual(1, context["totals"]["session_count"])
            self.assertEqual(["parent1234-0000"], [s["session_id"] for s in context["sessions"]])
            self.assertEqual(110, context["sessions"][0]["tokens"])
            self.assertEqual(2, context["sessions"][0]["request_count"])
            self.assertEqual({"input": 11, "output": 22, "cache_read": 33, "cache_create": 44},
                             context["totals"]["token_usage"])
            self.assertEqual(1, context["sessions"][0]["subagent_count"])


if __name__ == "__main__":
    unittest.main()
