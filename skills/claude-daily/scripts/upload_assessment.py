#!/usr/bin/env python3
# input: outbox/<date>/<member_id>/{_ai_assessment.{manager,personal}.md,_ai_assessment.meta.json,_assessment_context.json} + config.json
# output: outbox/<date>/<member_id>/{ai_assessment.json, ai_assessment.ack.json|ai_assessment.error.json}
# owner: wanhua.gu
# pos: skill ai-assessment upload entry; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""ai-assessment 模式 step 7: 组 payload（含 event_backbone）并上报。

复用 upload.py 的重试 + sha256 ACK 状态机；payload 校验用 _lib_schema。
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _lib_config as cfg
import _lib_paths as paths
import _lib_schema as schema_lib
import upload

DEFAULT_ENDPOINT_PATH = "/api/v1/ingest/ai-assessments"

ARTIFACTS = {
    "manager_md":  "_ai_assessment.manager.md",
    "personal_md": "_ai_assessment.personal.md",
    "meta":        "_ai_assessment.meta.json",
    "context":     "_assessment_context.json",
}


def _now_iso_us() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).isoformat(timespec="microseconds")


def build_payload(outbox: Path, member_id: str, date: str) -> dict:
    """Assemble the ai_assessment payload from the four on-disk artifacts.

    Raises FileNotFoundError with the missing artifact name so the caller can
    tell the user which assessment step to re-run.
    """
    missing = [name for name in ARTIFACTS.values() if not (outbox / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"missing artifacts under {outbox}: {', '.join(missing)}; "
            "run the ai-assessment steps (projection/MAP/REDUCE/review) first"
        )

    manager_md = (outbox / ARTIFACTS["manager_md"]).read_text(encoding="utf-8")
    personal_md = (outbox / ARTIFACTS["personal_md"]).read_text(encoding="utf-8")
    meta = json.loads((outbox / ARTIFACTS["meta"]).read_text(encoding="utf-8"))
    context = json.loads((outbox / ARTIFACTS["context"]).read_text(encoding="utf-8"))

    backbones = []
    for s in context.get("sessions", []):
        backbones.append({
            "session_short": s.get("session_short") or (s.get("session_id") or "")[:8],
            "session_id":    s.get("session_id") or "",
            "project":       s.get("project_dir") or "",
            "events":        s.get("event_backbone") or [],
        })

    return {
        "member_id":    member_id,
        "date_range":   meta.get("date_range") or date,
        "submitted_at": _now_iso_us(),
        "manager_md":   manager_md,
        "personal_md":  personal_md,
        "meta":         meta,
        "backbones":    backbones,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="upload ai-assessment payload")
    ap.add_argument("--date", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true",
                    help="ignore existing ack and re-upload")
    ap.add_argument("--backoff-seconds", default=None,
                    help="override retry backoffs, e.g. '0,0,0' for tests")
    args = ap.parse_args(argv)

    try:
        config = cfg.load(Path(args.config) if args.config else None)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    member_id = config["member_id"]
    outbox = paths.member_outbox(config["outbox_dir"], args.date, member_id)

    try:
        payload = build_payload(outbox, member_id, args.date)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    schema_path = Path(__file__).parent.parent / "schemas" / "ai_assessment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = schema_lib.validate(payload, schema)
    if errors:
        print("ERROR: payload schema validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 4

    payload_path = outbox / "ai_assessment.json"
    if payload_path.exists() and not args.force:
        # Keep the previous submitted_at when nothing else changed, so the
        # sha256-based ack skip in upload._upload_one stays idempotent.
        old = json.loads(payload_path.read_text(encoding="utf-8"))
        probe = dict(payload, submitted_at=old.get("submitted_at", ""))
        if probe == old:
            payload = probe
    paths.atomic_write_json(payload_path, payload)

    if args.backoff_seconds is not None:
        backoffs = [int(x) for x in args.backoff_seconds.split(",") if x]
    else:
        backoffs = upload.DEFAULT_BACKOFFS

    base = config["endpoint_base"].rstrip("/")
    endpoint_path = (config.get("endpoint_paths") or {}).get(
        "ai_assessment", DEFAULT_ENDPOINT_PATH)
    url = base + endpoint_path

    status, info = upload._upload_one(payload_path, url, backoffs, args.force)
    marker = {"ok": "✓", "skipped": "·", "error": "✗"}[status]
    outcome = info.get("outcome") or info.get("reason", "")
    rid = info.get("request_id", "")
    print(f"{marker} {payload_path.name:40s} {status:8s} {outcome:20s} {rid}")
    return 0 if status in ("ok", "skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
