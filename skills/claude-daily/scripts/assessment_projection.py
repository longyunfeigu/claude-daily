# input: outbox/<date>/<member_id>/_context.json + raw transcript jsonl
# output: outbox/<date>/<member_id>/_assessment_context.json
# owner: wanhua.gu
# pos: skill ai-assessment projection; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Assessment projection layer (PRD §18.3).

补出 prepare.py 丢弃的 4 个信号：命令成败 / 编辑频次(不去重) / claim↔验证关联 /
全量事件骨架。只读消费 _context.json + raw jsonl，不动日报路径。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _lib_config as cfg  # noqa: E402
import _lib_paths as paths  # noqa: E402

VERIFY_RE = re.compile(
    r"\b(pytest|go test|cargo test|npm (?:run )?(?:test|build)|pnpm|yarn|tsc|"
    r"eslint|ruff|mypy|vitest|jest|playwright|make|uv run|npx\s+tsx)\b", re.I)
EXPLORE_RE = re.compile(
    r"^\s*(cd|ls|cat|head|tail|grep|rg|find|echo|pwd|which|"
    r"git\s+(status|log|diff|branch|show))\b", re.I)
ERR_RE = re.compile(
    r"(Traceback|FAILED|\bFAIL\b|error TS\d|npm ERR|AssertionError|"
    r"SyntaxError|Exception|未找到|No such)", re.I)


def classify_command(cmd):
    """verify | explore | other. verify wins over explore (cd && pytest)."""
    if VERIFY_RE.search(cmd or ""):
        return "verify"
    if EXPLORE_RE.search(cmd or ""):
        return "explore"
    return "other"


def command_outcome(kind, is_error, output):
    """'ok' | 'fail' | None. Only verify commands have a meaningful outcome;
    explore/other nonzero exit is benign (grep no-match) and returns None."""
    if kind != "verify":
        return None
    if is_error or ERR_RE.search(output or ""):
        return "fail"
    return "ok"


DANGER_RE = re.compile(
    r"\brm\s+-rf?\b|\bgit\s+reset\s+--hard\b|\bdrop\s+table\b|\btruncate\b", re.I)
THROWAWAY_RE = re.compile(r"/tmp/|/var/tmp/|/private/tmp/")


def is_danger_op(cmd):
    """Destructive op NOT confined to a throwaway dir (PRD §18.3 path-aware)."""
    if not DANGER_RE.search(cmd or ""):
        return False
    if THROWAWAY_RE.search(cmd or ""):
        return False
    return True


CLAIM_RE = re.compile(
    r"(完成了|搞定|已修复|修好了|done[\.\!\s—-]|fixed|通过了|解决了|"
    r"应该(?:可以|没问题|好)了|implemented)", re.I)


def has_claim(text):
    return bool(CLAIM_RE.search(text or ""))


def normalize_cmd(cmd):
    """归一化键：取最后一段管道、压空白、截断，让"同一条命令"重复可被聚合。"""
    last = (cmd or "").split("&&")[-1].split("|")[-1]
    return re.sub(r"\s+", " ", last).strip()[:60]


def detect_loops(commands):
    """同一归一化命令的验证失败 ≥2 次 = 补丁套补丁（PRD §18.3）。"""
    fails = {}
    for c in commands:
        if c.get("kind") == "verify" and c.get("outcome") == "fail":
            key = normalize_cmd(c.get("cmd", ""))
            fails[key] = fails.get(key, 0) + 1
    return {k: n for k, n in fails.items() if n >= 2}


def _blocks(content):
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _text_of(content):
    return "\n".join(b.get("text", "") for b in _blocks(content)
                     if isinstance(b, dict) and b.get("type") == "text")


def project_session(rows):
    """单 session 投影：4 信号 + 全量事件骨架 + claim↔验证关联。"""
    commands = []            # [{"cmd","kind","outcome"}]
    edit_counts = {}         # file -> n（不去重）
    claims = []
    danger_ops = []
    backbone = []
    pending = {}             # tool_use_id -> commands 下标
    last_verify = None       # (cmd, outcome) 最近一次已解析的验证命令

    for i, r in enumerate(rows):
        msg = r.get("message", {}) or {}
        role = msg.get("role") or r.get("type")
        content = msg.get("content")

        if role == "assistant":
            t = _text_of(content)
            if has_claim(t):
                m = CLAIM_RE.search(t)
                snip = t[max(0, m.start() - 20):m.start() + 40].strip()
                claims.append({
                    "claim": snip,
                    "prev_verify": last_verify[0] if last_verify else None,
                    "prev_verify_outcome": last_verify[1] if last_verify else None,
                })
                backbone.append({"i": i, "type": "claim", "text": snip})
            for b in _blocks(content):
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                nm = b.get("name", "")
                inp = b.get("input", {}) or {}
                if nm == "Bash":
                    cmd = (inp.get("command") or "").strip()
                    kind = classify_command(cmd)
                    commands.append({"cmd": cmd[:200], "kind": kind, "outcome": None})
                    tuid = b.get("id")
                    if tuid:
                        pending[tuid] = len(commands) - 1
                    if is_danger_op(cmd):
                        danger_ops.append({"cmd": cmd[:200]})
                    backbone.append({"i": i,
                                     "type": "verify" if kind == "verify" else "cmd",
                                     "text": cmd[:120]})
                elif nm in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                    fp = inp.get("file_path") or inp.get("notebook_path") or ""
                    name = fp.rsplit("/", 1)[-1]
                    if name:
                        edit_counts[name] = edit_counts.get(name, 0) + 1
                        backbone.append({"i": i, "type": "edit", "text": name})

        elif role == "user":
            for b in _blocks(content):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tuid = b.get("tool_use_id")
                    res = b.get("content", "")
                    rtext = res if isinstance(res, str) else " ".join(
                        x.get("text", "") for x in _blocks(res) if isinstance(x, dict))
                    if tuid in pending:
                        idx = pending[tuid]
                        kind = commands[idx]["kind"]
                        outcome = command_outcome(kind, bool(b.get("is_error")), rtext)
                        commands[idx]["outcome"] = outcome
                        if outcome == "fail":
                            backbone.append({"i": i, "type": "tool_fail",
                                             "text": commands[idx]["cmd"][:80]})
                        if kind == "verify":
                            last_verify = (commands[idx]["cmd"], outcome)
            t = _text_of(content).strip()
            if t and not t.startswith("Caveat") and "<command-" not in t \
                    and "tool_result" not in t and "[Request interrupted" not in t:
                backbone.append({"i": i, "type": "user", "text": t[:200]})

    return {
        "commands": commands,
        "edit_events": [{"file": f, "n": n}
                        for f, n in sorted(edit_counts.items(), key=lambda kv: -kv[1])],
        "claims": claims,
        "loops": detect_loops(commands),
        "danger_ops": danger_ops,
        "event_backbone": backbone,
    }
