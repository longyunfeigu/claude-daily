#!/usr/bin/env python3
# input: outbox/<date>/<member_id>/{_context.json, _output.*.md, _session_meta.json}
# output: outbox/<date>/<member_id>/{daily_report,session_card}.*.json
# owner: wanhua.gu
# pos: skill stage 3 entry; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Stage 3: assemble PRD-compliant payloads from 4 LLM artifacts + context.json."""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import _lib_config as cfg
import _lib_paths as paths
import _lib_schema as sv


SESSION_CARDS_HEADING = re.compile(r"^#\s+Session\s+Cards\s*$", re.MULTILINE)
DAILY_REPORT_HEADING  = re.compile(r"^#\s+Daily\s+Report\s*$",  re.MULTILINE)
SESSION_HEADING       = re.compile(r"^##\s+Session\s+`([^`]+)`[：:]?\s*(.*)$", re.MULTILINE)
ANCHOR                = re.compile(r"(?<!\[)`([0-9a-f]{8,12})`")
AUDIENCE_TYPE         = {"personal": "personal", "boss": "boss"}
AUDIENCE_FILE         = {"personal": "_output.personal.md",
                         "boss":     "_output.boss.md"}


def split_session_cards(md: str) -> list:
    """Slice # Session Cards section, return list of {short, title, content_md}."""
    cards_start = SESSION_CARDS_HEADING.search(md)
    daily_start = DAILY_REPORT_HEADING.search(md)
    if not cards_start or not daily_start:
        return []
    cards_section = md[cards_start.end():daily_start.start()]
    matches = list(SESSION_HEADING.finditer(cards_section))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cards_section)
        blocks.append({
            "short": m.group(1).strip(),
            "title": m.group(2).strip(),
            "content_md": cards_section[start:end].rstrip(),
        })
    return blocks


def resolve_short_to_full(shorts, context: dict) -> dict:
    """Return {short: full_uuid_or_None_if_collision}; raises on unknown."""
    all_ids = [s["session_id"] for s in context.get("sessions", [])]
    mapping = {}
    for short in shorts:
        candidates = [sid for sid in all_ids if sid.startswith(short)]
        if not candidates:
            raise ValueError(f"short {short!r} not in context")
        if len(candidates) == 1:
            mapping[short] = candidates[0]
        else:
            mapping[short] = None
    return mapping


def inject_session_links(md: str, member_id: str, short_to_full: dict) -> str:
    """Replace `<short>` markdown spans with [`<short>`](/sessions/<mid>/<full>).

    Idempotent: once wrapped, the resulting markdown link does not contain a
    bare `<short>` span, so re-running is a no-op.
    """
    def repl(m):
        short = m.group(1)
        full = short_to_full.get(short)
        if not full:
            return m.group(0)
        return f"[`{short}`](/sessions/{member_id}/{full})"
    return ANCHOR.sub(repl, md)


_KEY_ALIASES = {
    "sessionId":  "session_id",
    "session-id": "session_id",
    "id":         "session_id",
    "valueTag":   "value_tag",
    "value-tag":  "value_tag",
    "tag":        "value_tag",
}
_VALID_TAGS = {"valuable", "chitchat", "loop", "no_output"}
_TAG_ALIASES = {
    "valueable":    "valuable",
    "worthwhile":   "valuable",
    "chit-chat":    "chitchat",
    "chitchatting": "chitchat",
    "looped":       "loop",
    "looping":      "loop",
    "no-output":    "no_output",
    "nooutput":     "no_output",
}


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 99
    if a == b:
        return 0
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[n][m]


def _normalize_tag(tag: str, fixes: list) -> str:
    if tag in _VALID_TAGS:
        return tag
    if tag in _TAG_ALIASES:
        fixed = _TAG_ALIASES[tag]
        fixes.append(f"value_tag {tag!r} → {fixed!r}")
        return fixed
    for valid in _VALID_TAGS:
        if _edit_distance(tag, valid) <= 1:
            fixes.append(f"value_tag {tag!r} → {valid!r} (edit-distance fix)")
            return valid
    fixes.append(f"value_tag {tag!r} unrecognized; left as-is for schema to reject")
    return tag


def normalize_meta(meta, context: dict):
    """Return (normalized_list, fixes_list).

    Accepts list or {sessions:[...]} or {data:[...]} or {items:[...]}.
    Normalizes camelCase keys, enum typos, short→full session_id.
    """
    fixes = []

    if isinstance(meta, dict):
        for wrap_key in ("sessions", "data", "items"):
            if isinstance(meta.get(wrap_key), list):
                fixes.append(f"unwrapped dict.{wrap_key} → list")
                meta = meta[wrap_key]
                break

    if not isinstance(meta, list):
        raise ValueError(
            f"_session_meta.json: expected list, got {type(meta).__name__}"
        )

    all_ids = [s["session_id"] for s in context.get("sessions", [])]
    normalized = []
    for entry in meta:
        if not isinstance(entry, dict):
            fixes.append(f"skipping non-dict meta entry: {entry!r}")
            continue
        new_entry = {}
        for k, v in entry.items():
            new_key = _KEY_ALIASES.get(k, k)
            if new_key != k:
                fixes.append(f"key {k!r} → {new_key!r}")
            new_entry[new_key] = v

        sid = new_entry.get("session_id", "")
        if isinstance(sid, str) and len(sid) < 36 and sid:
            candidates = [x for x in all_ids if x.startswith(sid)]
            if len(candidates) == 1:
                fixes.append(f"session_id short {sid!r} → {candidates[0]!r}")
                new_entry["session_id"] = candidates[0]
            elif len(candidates) > 1:
                fixes.append(f"session_id short {sid!r} ambiguous; left as-is")

        if "value_tag" in new_entry and isinstance(new_entry["value_tag"], str):
            new_entry["value_tag"] = _normalize_tag(new_entry["value_tag"], fixes)

        normalized.append(new_entry)

    return normalized, fixes


def _now_iso_us() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).isoformat(timespec="microseconds")


def _slice_daily_report(md: str) -> str:
    daily_start = DAILY_REPORT_HEADING.search(md)
    if not daily_start:
        return ""
    return md[daily_start.start():].rstrip() + "\n"


def _build_short_to_full(blocks, context: dict) -> dict:
    """Resolve all shorts in blocks to full uuids; fail fast on collision (L15)."""
    shorts = [b["short"] for b in blocks]
    mapping = resolve_short_to_full(shorts, context)
    collisions = [s for s, f in mapping.items() if f is None]
    if collisions:
        raise ValueError(
            f"short prefix collision: {collisions} match multiple sessions. "
            f"Edit _output.personal.md to use 12-char shorts (e.g. 'f66e2252-9cef') "
            f"and re-run emit. (Auto-expansion deferred — L15.)"
        )
    return mapping


def _print_summary_table(payloads_meta):
    print()
    print("┌─ Today's summary ─────────────────────────────────────────────")
    valuable   = sum(1 for m in payloads_meta if m.get("value_tag") == "valuable")
    loop_count = sum(1 for m in payloads_meta if m.get("value_tag") == "loop")
    chit       = sum(1 for m in payloads_meta if m.get("value_tag") == "chitchat")
    nout       = sum(1 for m in payloads_meta if m.get("value_tag") == "no_output")
    total_tokens = sum(m.get("token") or 0 for m in payloads_meta)
    total_dur    = sum(m.get("duration") or 0 for m in payloads_meta)
    print(f"│ sessions: {len(payloads_meta)}  "
          f"(valuable={valuable} / loop={loop_count} / chitchat={chit} / no_output={nout})")
    print(f"│ total token: {total_tokens}  total duration: {total_dur}s")
    for m in payloads_meta:
        token_s = f"{m.get('token')}" if m.get("token") is not None else "n/a"
        dur_s = f"{m.get('duration')}s" if m.get("duration") is not None else "n/a"
        print(f"│   {m['session_id'][:8]}  {m.get('value_tag','?'):10s}  {dur_s:>8s}  {token_s:>8s}")
    print("└───────────────────────────────────────────────────────────────")


_STEP_HINT = {
    "_output.personal.md": "3a (audience=self)",
    "_output.boss.md":     "3b (audience=manager)",
    "_session_meta.json":  "4 (value_tag + summary)",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="emit PRD payloads from LLM artifacts")
    ap.add_argument("--date", default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    try:
        config = cfg.load(Path(args.config) if args.config else None)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not args.date:
        print("ERROR: --date is required (UTC+8 YYYY-MM-DD)", file=sys.stderr)
        return 2

    member_id = config["member_id"]
    outbox = paths.member_outbox(config["outbox_dir"], args.date, member_id)

    schema_dir = Path(__file__).parent.parent / "schemas"
    daily_schema = json.loads((schema_dir / "daily_report.schema.json").read_text())
    session_schema = json.loads((schema_dir / "session_card.schema.json").read_text())

    required_files = ["_output.personal.md", "_output.boss.md",
                      "_session_meta.json"]
    missing = [f for f in required_files if not (outbox / f).exists()]
    if missing:
        print(f"ERROR: {len(missing)} LLM artifact(s) missing in {outbox}:",
              file=sys.stderr)
        for f in missing:
            print(f"  - {f}: re-run step {_STEP_HINT[f]}: Write {f}", file=sys.stderr)
        return 3

    context = json.loads((outbox / "_context.json").read_text(encoding="utf-8"))

    raw_meta = json.loads((outbox / "_session_meta.json").read_text(encoding="utf-8"))
    meta, fixes = normalize_meta(raw_meta, context)
    if fixes:
        for f in fixes:
            print(f"INFO: meta fix: {f}", file=sys.stdout)
        paths.atomic_write_json(outbox / "_session_meta.json", meta)
    meta_by_id = {m["session_id"]: m for m in meta if m.get("session_id")}

    personal_md = (outbox / "_output.personal.md").read_text(encoding="utf-8")
    blocks = split_session_cards(personal_md)
    short_to_full = _build_short_to_full(blocks, context)

    submitted_at = _now_iso_us()
    sessions_by_id = {s["session_id"]: s for s in context.get("sessions", [])}

    payloads_meta = []
    for block in blocks:
        full = short_to_full[block["short"]]
        ctx_sess = sessions_by_id.get(full, {})
        m = meta_by_id.get(full)
        if m is None:
            print(f"ERROR: _session_meta.json missing entry for session {full[:8]}: "
                  f"re-run step 4: Write _session_meta.json with all sessions",
                  file=sys.stderr)
            return 4
        if not ctx_sess.get("started_at"):
            print(f"WARN: session {full[:8]} skipped: no timestamps in transcript",
                  file=sys.stdout)
            continue
        card = {
            "member_id":    member_id,
            "session_id":   full,
            "started_at":   ctx_sess["started_at"],
            "submitted_at": submitted_at,
            "content":      block["content_md"],
            "summary":      m.get("summary", ""),
            "value_tag":    m.get("value_tag", ""),
        }
        if ctx_sess.get("duration_seconds") is not None:
            card["duration"] = ctx_sess["duration_seconds"]
        if ctx_sess.get("tokens") is not None:
            card["token"] = ctx_sess["tokens"]
        errors = sv.validate(card, session_schema)
        if errors:
            print(f"ERROR: session_card.{block['short']}.json schema validation failed:",
                  file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            print(f"  re-run step 4: Write _session_meta.json with corrected entries",
                  file=sys.stderr)
            return 5
        paths.atomic_write_json(outbox / f"session_card.{block['short']}.json", card)
        payloads_meta.append({
            "session_id": full,
            "value_tag":  card["value_tag"],
            "token":      card.get("token"),
            "duration":   card.get("duration"),
        })

    for audience in ("personal", "boss"):
        md = (outbox / AUDIENCE_FILE[audience]).read_text(encoding="utf-8")
        daily_md = _slice_daily_report(md)
        if not daily_md:
            print(f"ERROR: _output.{audience}.md missing # Daily Report section: "
                  f"re-run step 3: Write _output.{audience}.md",
                  file=sys.stderr)
            return 6
        injected = inject_session_links(daily_md, member_id, short_to_full)
        report = {
            "member_id":    member_id,
            "date":         args.date,
            "type":         AUDIENCE_TYPE[audience],
            "content":      injected,
            "submitted_at": submitted_at,
        }
        errors = sv.validate(report, daily_schema)
        if errors:
            print(f"ERROR: daily_report.{audience}.json schema failed:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 7
        paths.atomic_write_json(outbox / f"daily_report.{audience}.json", report)

    _print_summary_table(payloads_meta)
    print(f"OK: wrote {len(payloads_meta) + 2} payloads under {outbox}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
