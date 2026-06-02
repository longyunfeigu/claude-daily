#!/usr/bin/env python3
# input: ~/.claude/projects/**/*.jsonl JSONL transcript files, CLI args (--projects-root, --date, --session, --limit, --timezone-offset)
# output: parse_session_file -> session dict (session_id, user_prompts, tools, deduped token_usage, started_at, duration_seconds, tokens (UTC+8 / int / int)); build_context -> full report context JSON written to --out
# owner: wanhua.gu
# pos: 日报 skill 数据层 - 解析 JSONL 转录文件并生成报告上下文 JSON；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Build compact Claude Code session report context from local JSONL transcripts."""

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


NOISE_MARKERS = (
    "<local-command-caveat>",
    "<command-name>",
    "<local-command-stdout>",
    "<command-message>",
    "Base directory for this skill:",
    "[Request interrupted by user for tool use]",
)

ASSISTANT_KEYPOINT_MARKERS = (
    "关键结论",
    "结论",
    "本质",
    "核心",
    "关键点",
    "所以",
    "推荐",
    "建议",
    "区别",
    "风险",
    "下一步",
    "产出",
    "最终",
    "一句话",
    "总结",
    "注意",
    "未完成",
)

TOKEN_USAGE_KEYS = ("input", "output", "cache_read", "cache_create")
USAGE_FIELD_MAP = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_create": "cache_creation_input_tokens",
}


def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"type": "parse-error", "line": line_no, "raw": line[:500]})
    return rows


def is_noise_text(text):
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    return any(marker in stripped for marker in NOISE_MARKERS)


def text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def compact(text, limit=300):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def split_text_blocks(text):
    blocks = []
    current = []
    for line in (text or "").splitlines():
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks or ([text.strip()] if text and text.strip() else [])


def classify_segment_kind(text):
    stripped = (text or "").strip()
    if stripped.startswith("#"):
        return "heading"
    if stripped.startswith(("- ", "* ", "1. ")):
        return "list_item"
    return "paragraph"


def assistant_segment_signals(text, previous_event_type=None):
    signals = []
    if any(marker in text for marker in ASSISTANT_KEYPOINT_MARKERS):
        signals.append("contains_keyword")
    if previous_event_type == "user_prompt":
        signals.append("after_user_prompt")
    if len(text) > 900:
        signals.append("long")
    if len(text) < 20:
        signals.append("short")
    return signals


def extract_assistant_segments(text, timestamp=None, start_idx=0, previous_event_type=None, limit=24):
    segments = []
    seen = set()
    for block in split_text_blocks(text):
        normalized = compact(block, 1000)
        if not normalized or is_noise_text(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        segments.append(
            {
                "idx": start_idx + len(segments),
                "time": timestamp,
                "kind": classify_segment_kind(normalized),
                "signals": assistant_segment_signals(normalized, previous_event_type),
                "text": normalized,
            }
        )
        if len(segments) >= limit:
            break
    return segments


def add_usage(total, usage):
    if not isinstance(usage, dict):
        return
    for key, field in USAGE_FIELD_MAP.items():
        total[key] += usage.get(field, 0) or 0


def empty_token_usage():
    return {key: 0 for key in TOKEN_USAGE_KEYS}


def merge_token_usage(total, usage):
    if not isinstance(usage, dict):
        return
    for key in TOKEN_USAGE_KEYS:
        total[key] += usage.get(key, 0) or 0


def token_total(usage):
    if not isinstance(usage, dict):
        return None
    if not any(usage.get(key, 0) > 0 for key in TOKEN_USAGE_KEYS):
        return None
    return sum(int(usage.get(key, 0)) for key in TOKEN_USAGE_KEYS)


def usage_request_key(row, message):
    message_id = message.get("id")
    if message_id:
        return ("message_id", message_id)
    return ("row", row.get("uuid"), row.get("timestamp"))


def parse_tool_use(item, evidence, compact_events, timestamp):
    name = item.get("name") or "unknown"
    tool_input = item.get("input") or {}
    evidence["tools"][name] += 1

    file_path = tool_input.get("file_path") or tool_input.get("path")
    if file_path:
        if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            evidence["files_modified"].add(file_path)
        elif name in ("Read", "Glob", "Grep", "LS"):
            evidence["files_read"].add(file_path)
        else:
            evidence["files_referenced"].add(file_path)

    command = tool_input.get("command")
    if name == "Bash" and command:
        evidence["commands"].append(command)

    if name in ("WebSearch", "WebFetch"):
        query = tool_input.get("query") or tool_input.get("url") or tool_input.get("prompt")
        if query:
            evidence["web_sources"].append({"tool": name, "value": compact(query, 220)})

    compact_events.append(
        {
            "type": "tool",
            "time": timestamp,
            "tool": name,
            "file": file_path,
            "command": compact(command, 220) if command else None,
        }
    )


_TZ_UTC8 = timezone(timedelta(hours=8))


def _parse_iso_ts(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, AttributeError):
        return None


def attach_session_metrics(parsed_session: dict) -> None:
    """Mutate parsed_session: replace started_at/ended_at strings with +08:00 ISO,
    add duration_seconds and tokens. Reads existing started_at/ended_at; does
    NOT re-scan transcript. None-vs-zero per spec §4.1.2.
    """
    started_str = parsed_session.get("started_at")
    ended_str = parsed_session.get("ended_at")
    started_dt = _parse_iso_ts(started_str)
    ended_dt = _parse_iso_ts(ended_str)
    if started_dt is not None and started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    if ended_dt is not None and ended_dt.tzinfo is None:
        ended_dt = ended_dt.replace(tzinfo=timezone.utc)

    if started_dt is not None and ended_dt is not None:
        parsed_session["started_at"] = started_dt.astimezone(_TZ_UTC8).isoformat()
        parsed_session["duration_seconds"] = int((ended_dt - started_dt).total_seconds())
    else:
        parsed_session["started_at"] = None
        parsed_session["duration_seconds"] = None

    parsed_session["tokens"] = token_total(parsed_session.get("token_usage"))


def parse_session_file(path, token_date=None, timezone_offset=None):
    rows = read_jsonl(path)
    session_id = None
    cwd = None
    git_branch = None
    timestamps = []
    user_prompts = []
    assistant_samples = []
    assistant_segments = []
    compact_events = []
    evidence = {
        "tools": Counter(),
        "files_read": set(),
        "files_modified": set(),
        "files_referenced": set(),
        "commands": [],
        "web_sources": [],
        "token_usage": empty_token_usage(),
        "request_count": 0,
        "duplicate_usage_rows": 0,
    }
    seen_usage_requests = set()

    for row in rows:
        session_id = session_id or row.get("sessionId")
        cwd = cwd or row.get("cwd")
        git_branch = git_branch or row.get("gitBranch")
        timestamp = row.get("timestamp")
        if timestamp:
            timestamps.append(timestamp)

        message = row.get("message")
        if isinstance(message, dict):
            usage = message.get("usage")
            usage_date_matches = (
                not token_date
                or local_date_for_timestamp(timestamp, timezone_offset or local_timezone_offset()) == token_date
            )
            if isinstance(usage, dict) and usage_date_matches:
                key = usage_request_key(row, message)
                if key in seen_usage_requests:
                    evidence["duplicate_usage_rows"] += 1
                else:
                    seen_usage_requests.add(key)
                    add_usage(evidence["token_usage"], usage)
                    evidence["request_count"] += 1
            content = message.get("content")

            if row.get("type") == "user":
                text = text_from_content(content)
                if text and not is_noise_text(text):
                    user_prompts.append(compact(text, 500))
                    compact_events.append(
                        {
                            "type": "user_prompt",
                            "time": timestamp,
                            "text": compact(text, 280),
                        }
                    )

            if row.get("type") == "assistant":
                text = text_from_content(content)
                if text and not is_noise_text(text):
                    assistant_samples.append(compact(text, 500))
                    previous_event_type = compact_events[-1]["type"] if compact_events else None
                    assistant_segments.extend(
                        extract_assistant_segments(
                            text,
                            timestamp=timestamp,
                            start_idx=len(assistant_segments) + 1,
                            previous_event_type=previous_event_type,
                        )
                    )
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            parse_tool_use(item, evidence, compact_events, timestamp)

        # Claude Code sometimes records tool result metadata outside message.content.
        result = row.get("toolUseResult")
        if isinstance(result, dict):
            if result.get("filePath"):
                evidence["files_referenced"].add(result["filePath"])

    if not session_id:
        session_id = path.stem

    timezone_offset = local_timezone_offset()

    result = {
        "session_id": session_id,
        "session_short": session_id[:8],
        "transcript_path": str(path),
        "project_dir": path.parent.name,
        "project_path": cwd,
        "git_branch": git_branch,
        "started_at": min(timestamps) if timestamps else None,
        "ended_at": max(timestamps) if timestamps else None,
        "active_dates": {
            "utc": sorted(set(parse_iso_date(ts) for ts in timestamps if parse_iso_date(ts))),
            timezone_offset: sorted(set(local_date_for_timestamp(ts, timezone_offset) for ts in timestamps if ts)),
        },
        "message_count": sum(1 for row in rows if isinstance(row.get("message"), dict)),
        "user_prompts": user_prompts,
        "first_prompt": user_prompts[0] if user_prompts else None,
        "last_prompt": user_prompts[-1] if user_prompts else None,
        "assistant_samples": assistant_samples[-3:],
        "assistant_segments": assistant_segments[:80],
        "compact_events": compact_events[:160],
        "tools": dict(evidence["tools"]),
        "files_read": sorted(evidence["files_read"]),
        "files_modified": sorted(evidence["files_modified"]),
        "files_referenced": sorted(evidence["files_referenced"]),
        "commands": evidence["commands"],
        "web_sources": evidence["web_sources"],
        "token_usage": evidence["token_usage"],
        "request_count": evidence["request_count"],
        "duplicate_usage_rows": evidence["duplicate_usage_rows"],
    }
    attach_session_metrics(result)
    return result


def find_session_files(projects_root, session_prefixes, include_subagents=False):
    projects_root = Path(projects_root).expanduser()
    if session_prefixes:
        found = []
        for prefix in session_prefixes:
            matches = sorted(projects_root.glob("* /dummy"))  # never matches; keeps type simple
            matches = sorted(projects_root.glob("*/*{}*.jsonl".format(prefix)))
            matches += sorted(projects_root.glob("*/*/subagents/*{}*.jsonl".format(prefix)))
            found.extend(matches)
        unique = []
        seen = set()
        for path in found:
            if path not in seen and (include_subagents or "/subagents/" not in str(path)):
                unique.append(path)
                seen.add(path)
        return unique

    pattern = "**/*.jsonl" if include_subagents else "*/*.jsonl"
    paths = [p for p in projects_root.glob(pattern) if p.is_file()]
    if not include_subagents:
        paths = [p for p in paths if "/subagents/" not in str(p)]
    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)


def find_subagent_files(projects_root, session_prefixes=None):
    projects_root = Path(projects_root).expanduser()
    prefixes = session_prefixes or []
    if prefixes:
        found = []
        for prefix in prefixes:
            found.extend(projects_root.glob(f"*/*{prefix}*/subagents/*.jsonl"))
            found.extend(projects_root.glob(f"*/*/subagents/*{prefix}*.jsonl"))
        unique = []
        seen = set()
        for path in found:
            if path.is_file() and path not in seen:
                unique.append(path)
                seen.add(path)
        return sorted(unique, key=lambda p: p.stat().st_mtime, reverse=True)
    return sorted(
        [p for p in projects_root.glob("*/*/subagents/*.jsonl") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def parent_session_id_for_subagent_path(path):
    path = Path(path)
    if path.parent.name != "subagents":
        return None
    return path.parent.parent.name


def parse_iso_date(timestamp):
    if not timestamp:
        return None
    return timestamp[:10]


def local_timezone_offset():
    offset = datetime.now().astimezone().utcoffset()
    if offset is None:
        return "+00:00"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return "{}{:02d}:{:02d}".format(sign, total_minutes // 60, total_minutes % 60)


def parse_timezone_offset(offset):
    if not offset:
        return timezone.utc
    sign = 1
    value = offset
    if value[0] == "-":
        sign = -1
        value = value[1:]
    elif value[0] == "+":
        value = value[1:]
    hours, minutes = value.split(":", 1)
    delta = timedelta(hours=int(hours), minutes=int(minutes)) * sign
    return timezone(delta)


def local_date_for_timestamp(timestamp, offset):
    if not timestamp:
        return None
    raw = timestamp.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        # Python 3.7 handles offsets but not all fractional variants; date fallback is better than dropping.
        return parse_iso_date(timestamp)
    return dt.astimezone(parse_timezone_offset(offset)).date().isoformat()


def filter_by_date(sessions, date, timezone_offset=None):
    if not date:
        return sessions
    if timezone_offset:
        return [s for s in sessions if date in s.get("active_dates", {}).get(timezone_offset, [])]
    return [s for s in sessions if parse_iso_date(s.get("ended_at") or s.get("started_at")) == date]


def build_context(projects_root, date=None, session_prefixes=None, include_subagents=False,
                  include_subagent_usage=False, limit=None, timezone_offset=None):
    timezone_offset = timezone_offset or local_timezone_offset()
    paths = find_session_files(projects_root, session_prefixes or [], include_subagents=include_subagents)
    parsed = [parse_session_file(path, token_date=date, timezone_offset=timezone_offset) for path in paths]
    parsed = filter_by_date(parsed, date, timezone_offset)
    if limit:
        parsed = parsed[:limit]

    if include_subagent_usage and not include_subagents:
        by_parent_id = {session.get("session_id"): session for session in parsed}
        subagent_paths = find_subagent_files(projects_root, session_prefixes or [])
        subagents = [
            parse_session_file(path, token_date=date, timezone_offset=timezone_offset)
            for path in subagent_paths
        ]
        subagents = filter_by_date(subagents, date, timezone_offset)
        for subagent in subagents:
            parent_id = parent_session_id_for_subagent_path(subagent.get("transcript_path"))
            parent = by_parent_id.get(parent_id)
            if not parent:
                continue
            merge_token_usage(parent["token_usage"], subagent.get("token_usage"))
            parent["tokens"] = token_total(parent["token_usage"])
            parent["request_count"] = (
                int(parent.get("request_count") or 0)
                + int(subagent.get("request_count") or 0)
            )
            parent["duplicate_usage_rows"] = (
                int(parent.get("duplicate_usage_rows") or 0)
                + int(subagent.get("duplicate_usage_rows") or 0)
            )
            parent["subagent_count"] = int(parent.get("subagent_count") or 0) + 1
            merge_token_usage(parent.setdefault("subagent_token_usage", empty_token_usage()),
                              subagent.get("token_usage"))
            parent["subagent_request_count"] = (
                int(parent.get("subagent_request_count") or 0)
                + int(subagent.get("request_count") or 0)
            )

    totals = {
        "session_count": len(parsed),
        "tools": {},
        "token_usage": empty_token_usage(),
        "request_count": 0,
        "duplicate_usage_rows": 0,
    }
    tool_counter = Counter()
    for session in parsed:
        tool_counter.update(session.get("tools", {}))
        merge_token_usage(totals["token_usage"], session.get("token_usage"))
        totals["request_count"] += int(session.get("request_count") or 0)
        totals["duplicate_usage_rows"] += int(session.get("duplicate_usage_rows") or 0)
    totals["tools"] = dict(tool_counter)

    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "source": str(Path(projects_root).expanduser()),
        "date_filter": date,
        "timezone_offset": timezone_offset,
        "session_prefixes": session_prefixes or [],
        "include_subagents": include_subagents,
        "include_subagent_usage": include_subagent_usage,
        "totals": totals,
        "sessions": parsed,
        "session_card_schema": [
            "主题",
            "目标",
            "主要过程",
            "产出",
            "关键决策",
            "文件/命令证据",
            "未完成事项",
            "可沉淀经验",
        ],
        "instructions_for_llm": {
            "rule": "Use facts and evidence from this JSON only. If evidence is missing, say 未发现明确证据.",
            "pipeline": "Python handled parsing/evidence; LLM should name episodes, write session cards, then synthesize the daily report.",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-root", default=os.path.expanduser("~/.claude/projects"))
    parser.add_argument("--date", help="Filter by session end date, YYYY-MM-DD")
    parser.add_argument("--session", action="append", default=[], help="Session id or prefix; repeatable")
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--include-subagent-usage", action="store_true",
                        help="Roll subagent token usage into parent sessions without adding subagent sessions")
    parser.add_argument("--timezone-offset", default=local_timezone_offset(), help="Local date offset for --date, e.g. +08:00")
    parser.add_argument("--limit", type=int, help="Maximum sessions after filtering")
    parser.add_argument("--out", default="report_context.json", help="Output JSON path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    context = build_context(
        args.projects_root,
        date=args.date,
        session_prefixes=args.session,
        include_subagents=args.include_subagents,
        include_subagent_usage=args.include_subagent_usage,
        limit=args.limit,
        timezone_offset=args.timezone_offset,
    )

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2 if args.pretty else None)
        f.write("\n")

    print(str(out))
    print("sessions={}".format(context["totals"]["session_count"]))


if __name__ == "__main__":
    main()
