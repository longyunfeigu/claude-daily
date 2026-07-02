#!/usr/bin/env python3
# input: outbox/<date>/<member_id>/{daily_report,session_card}.*.json + config.json
# output: outbox/<date>/<member_id>/{*.ack.json, *.error.json}
# owner: wanhua.gu
# pos: skill stage 4 entry; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Stage 4: HTTP upload payloads with retry + sha256 ACK."""
import argparse
import hashlib
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _lib_config as cfg
import _lib_paths as paths

DEFAULT_TIMEOUT = 10
DEFAULT_BACKOFFS = [1, 4, 16]
OK_OUTCOMES = {"ok", "ignored_stale"}
USER_AGENT = "compound-daily-skill/0.2"


def _now_iso_us() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).isoformat(timespec="microseconds")


def _payload_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _opener_for(url: str):
    """Loopback endpoints must not go through HTTP(S)_PROXY (corp proxy
    would intercept localhost and return 5xx)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _post(url: str, payload: dict, timeout: int = DEFAULT_TIMEOUT):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent":   USER_AGENT},
    )
    try:
        with _opener_for(url).open(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(data)
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            data = {}
        return e.code, data


def _classify(status_or_exc):
    if isinstance(status_or_exc, int):
        if status_or_exc == 422:
            return "validation"
        if 400 <= status_or_exc < 500:
            return "client_error"
        if 500 <= status_or_exc < 600:
            return "retryable_server"
        if 200 <= status_or_exc < 300:
            return "ok_check_outcome"
    if isinstance(status_or_exc, (urllib.error.URLError, socket.timeout)):
        return "retryable_network"
    return "unknown"


def _upload_one(payload_path: Path, url: str, backoffs, force: bool):
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    sha = _payload_sha256(payload)
    ack_path = payload_path.with_suffix("").with_suffix(".ack.json")
    err_path = payload_path.with_suffix("").with_suffix(".error.json")
    # with_suffix(".ack.json") on .json strips .json then adds .ack.json — but
    # double-call ensures correctness when name is daily_report.personal.json
    # Result: daily_report.personal.ack.json and .error.json siblings.
    ack_path = payload_path.parent / (payload_path.stem + ".ack.json")
    err_path = payload_path.parent / (payload_path.stem + ".error.json")

    if ack_path.exists() and not force:
        existing = json.loads(ack_path.read_text(encoding="utf-8"))
        if existing.get("payload_sha256") == sha:
            return ("skipped", existing)

    def _record_error(reason, extra):
        err = {"reason": reason, **extra}
        paths.atomic_write_json(err_path, err)
        if ack_path.exists():
            try:
                ack_path.unlink()
            except OSError:
                pass
        return ("error", err)

    attempts = [None] + list(backoffs)
    is_last = lambda i: i >= len(attempts) - 1

    for i, backoff in enumerate(attempts):
        if backoff is not None and backoff > 0:
            time.sleep(backoff)
        try:
            status, body = _post(url, payload)
        except (urllib.error.URLError, socket.timeout) as e:
            if not is_last(i):
                continue
            return _record_error("network_error", {"exception": str(e)})

        kind = _classify(status)
        if kind in ("validation", "client_error"):
            return _record_error(f"http_{status}", {"body": body})
        if kind == "retryable_server":
            if not is_last(i):
                continue
            return _record_error(f"http_{status}_after_retries", {"body": body})
        if kind == "ok_check_outcome":
            outcome = (body or {}).get("outcome")
            if outcome in OK_OUTCOMES:
                ack = {
                    "uploaded_at":    _now_iso_us(),
                    "endpoint":       url,
                    "outcome":        outcome,
                    "request_id":     (body or {}).get("request_id", ""),
                    "payload_sha256": sha,
                }
                paths.atomic_write_json(ack_path, ack)
                if err_path.exists():
                    try:
                        err_path.unlink()
                    except OSError:
                        pass
                return ("ok", ack)
            return _record_error("unknown_outcome", {"body": body})

    return _record_error("loop_exhausted_unexpected", {})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="upload PRD payloads")
    ap.add_argument("--date", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true",
                    help="ignore existing acks and re-upload")
    ap.add_argument("--backoff-seconds", default=None,
                    help="override DEFAULT_BACKOFFS, e.g. '0,0,0' for tests")
    args = ap.parse_args(argv)

    try:
        config = cfg.load(Path(args.config) if args.config else None)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.backoff_seconds is not None:
        backoffs = [int(x) for x in args.backoff_seconds.split(",") if x]
    else:
        backoffs = DEFAULT_BACKOFFS

    member_id = config["member_id"]
    outbox = paths.member_outbox(config["outbox_dir"], args.date, member_id)
    base = config["endpoint_base"].rstrip("/")
    paths_cfg = config["endpoint_paths"]

    sc_files = sorted(outbox.glob("session_card.*.json"))
    sc_files = [p for p in sc_files
                if not (p.name.endswith(".ack.json") or p.name.endswith(".error.json"))]
    dr_files = [outbox / f"daily_report.{a}.json" for a in ("personal", "boss")]
    dr_files = [p for p in dr_files if p.exists()]

    plan = [(p, base + paths_cfg["session_card"]) for p in sc_files] + \
           [(p, base + paths_cfg["daily_report"]) for p in dr_files]

    if not plan:
        print(f"ERROR: no payloads under {outbox}", file=sys.stderr)
        return 3

    n_ok = n_err = n_skip = 0
    for payload_path, url in plan:
        status, info = _upload_one(payload_path, url, backoffs, args.force)
        marker = {"ok": "✓", "skipped": "·", "error": "✗"}[status]
        outcome = info.get("outcome") or info.get("reason", "")
        rid = info.get("request_id", "")
        print(f"{marker} {payload_path.name:40s} {status:8s} {outcome:20s} {rid}")
        if status == "ok":
            n_ok += 1
        elif status == "skipped":
            n_skip += 1
        else:
            n_err += 1

    print("───────────────────────────────────")
    print(f"{n_ok}/{len(plan)} uploaded, {n_skip} skipped, {n_err} failed")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
