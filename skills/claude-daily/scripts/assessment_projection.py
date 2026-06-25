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
