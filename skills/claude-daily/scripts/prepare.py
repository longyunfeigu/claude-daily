#!/usr/bin/env python3
# input: ~/.compound-daily/config.json, ~/.claude/projects/**/*.jsonl, ccusage session CLI (npx, 可选;缺失则 token 计 0)
# output: outbox/<date>/<member_id>/_context.json; per-session token 来自 ccusage session 按天切分(已含 subagent)
# owner: wanhua.gu
# pos: skill stage 1 entry; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Stage 1: build context.json from local Claude Code transcripts."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as a script from this directory
sys.path.insert(0, str(Path(__file__).parent))

import _lib_config as cfg
import _lib_paths as paths
import build_report_context as brc


def _today_utc8() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def parse_ccusage_session_tokens(stdout: str) -> dict:
    """Parse `ccusage session --json` stdout into {session_id: total_tokens}.

    ccusage uses each transcript's internal sessionId as `period`; subagent
    transcripts inherit their parent's sessionId, so a parent's totalTokens
    already includes its subagents' tokens. No manual rollup needed.
    """
    data = json.loads(stdout)
    return {s["period"]: s["totalTokens"] for s in data.get("session", [])}


def load_ccusage_session_tokens(date: str):
    """Run ccusage for the given UTC+8 date, return {session_id: total_tokens}.

    Returns None when ccusage is unavailable (not installed / non-zero exit /
    unparseable output): the caller degrades to token=0 and still generates the
    report. Token totals only feed the server-side Token page, not the report
    body, so a missing total does not change report content.

    `--since/--until` slice token usage by day (verified: per-session sums
    equal ccusage daily total), matching the report's strict per-day counting.

    Assumes the host timezone is UTC+8 (same as the report's date boundary).
    ccusage groups days by host timezone; on a non-UTC+8 host the day boundary
    would diverge from the report's UTC+8 `date` and tokens near midnight would
    land on the wrong day.
    """
    try:
        out = subprocess.run(
            ["npx", "ccusage", "session", "--since", date, "--until", date, "--json"],
            capture_output=True, text=True, check=True,
        ).stdout
        return parse_ccusage_session_tokens(out)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"WARN: ccusage 不可用（{type(e).__name__}）；本次报告无 token 数据，token 按 0 计",
              file=sys.stdout)
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="prepare context.json for compound-daily skill")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (UTC+8); default: today")
    ap.add_argument("--config", default=None, help="path to config.json (default: ~/.compound-daily/config.json)")
    args = ap.parse_args(argv)

    try:
        config = cfg.load(Path(args.config) if args.config else None)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    date = args.date or _today_utc8()
    member_id = config["member_id"]
    outbox_dir = config["outbox_dir"]
    projects_root = config["projects_root"]

    # Multi-device collision check (warning only)
    date_dir = Path(outbox_dir) / date
    if date_dir.exists():
        for other in date_dir.iterdir():
            if other.is_dir() and other.name != member_id and not other.name.startswith("_"):
                print(f"WARN: outbox/{date}/ already contains other member_id: {other.name}",
                      file=sys.stdout)

    # Build context using existing brc machinery
    context = brc.build_context(
        projects_root=projects_root,
        date=date,
        timezone_offset="+08:00",
        include_subagent_usage=True,
    )

    # Cross-day filter + warning
    keep_sessions = []
    for sess in context.get("sessions", []):
        started_at = sess.get("started_at")
        if started_at and not started_at.startswith(date):
            print(f"WARN: session {sess['session_id'][:8]} started_at={started_at} != --date={date}; "
                  f"skipped (run with --date {started_at[:10]} to include)", file=sys.stdout)
            continue
        keep_sessions.append(sess)
    context["sessions"] = keep_sessions

    # Override per-session token with ccusage (authoritative, per-day, includes
    # subagent tokens via parent sessionId). Skip when no sessions kept.
    if keep_sessions:
        ccusage_tokens = load_ccusage_session_tokens(date)
        for sess in keep_sessions:
            sess["tokens"] = (ccusage_tokens or {}).get(sess["session_id"], 0)

    # Write context.json
    out_path = paths.member_outbox(outbox_dir, date, member_id) / "_context.json"
    paths.atomic_write_json(out_path, context)
    print(f"wrote {out_path}", file=sys.stdout)
    print(f"sessions: {len(keep_sessions)}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
