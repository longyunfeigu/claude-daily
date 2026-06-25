# AI 使用评估 · 投影层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `scripts/assessment_projection.py`，消费现有 `_context.json` 并重读原始 transcript jsonl，补出 prepare 丢弃的 4 个评估信号，写出 `_assessment_context.json`。

**Architecture:** 投影层是一个独立的只读消费者：从 `_context.json` 拿到 session 列表与每个 session 的 `transcript_path`，重新解析 raw jsonl，提取「命令成败 / 编辑频次（不去重）/ claim↔验证关联 / 全量事件骨架」，并内置两条去误判规则（验证命令 vs 探索命令、danger 看路径）。**完全不修改 `build_report_context.py` / `prepare.py`，日报路径零影响**（PRD §18.3）。

**Tech Stack:** Python 3 标准库（`json`/`re`/`argparse`/`pathlib`），复用 `_lib_config`、`_lib_paths`；测试用 `unittest`（与 `test_prepare.py` 同风格）。

## Global Constraints

- **只用 Python 3 标准库**，不引入第三方依赖（与现有 scripts 一致）。
- **不改动 `build_report_context.py`、`prepare.py`、`emit.py`、`upload.py`**——投影层是新增旁路，日报 6 步流水线不动（PRD §12.3 / §18.3）。
- 每个新 `.py` 文件开头必须有 header 注释块，格式照抄现有脚本：`# input:` / `# output:` / `# owner: wanhua.gu` / `# pos: ...; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md`。
- 测试用 `unittest.TestCase`；CLI 测试用 `subprocess`，单元测试直接 `import assessment_projection`；测试 fixture 的 `member_id` 用 `wanhua.gu`（与 `test_prepare.py` 一致）。
- 复用 `_lib_config.load()`、`_lib_paths.member_outbox()`、`_lib_paths.atomic_write_json()`，不重新实现配置/路径逻辑。
- **去误判规则是硬约束**（PRD §18.3，已在阶段一验证踩到）：`exit≠0 ≠ 失败`——只有验证命令的失败才算失败，探索命令（grep/find/cd/echo）的非零退出是良性；danger 判定看路径上下文（`/tmp` 使い捨て不算）。
- KISS：投影层只产**结构化信号**，不产散文、不打分、不调用 LLM。打分是 Plan 2 的事。

---

### Task 1: 模块骨架 + 命令分类与成败判定

**Files:**
- Create: `skills/claude-daily/scripts/assessment_projection.py`
- Test: `skills/claude-daily/scripts/test_assessment_projection.py`

**Interfaces:**
- Produces:
  - `classify_command(cmd: str) -> str` 返回 `"verify"` | `"explore"` | `"other"`
  - `command_outcome(kind: str, is_error: bool, output: str) -> str | None` 返回 `"ok"` | `"fail"` | `None`（非验证命令一律 `None`）

- [ ] **Step 1: 写失败测试**

创建 `skills/claude-daily/scripts/test_assessment_projection.py`：

```python
# input: assessment_projection.py functions + temp config/fixtures
# output: unittest suite for the AI-assessment projection layer
# owner: wanhua.gu
# pos: skill test - assessment_projection.py; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Tests for the assessment projection layer."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "assessment_projection.py"
sys.path.insert(0, str(Path(__file__).parent))
import assessment_projection as ap  # noqa: E402


class ClassifyCommandTest(unittest.TestCase):
    def test_verify_commands(self):
        self.assertEqual(ap.classify_command("uv run python -m pytest -q"), "verify")
        self.assertEqual(ap.classify_command("npm run build"), "verify")
        self.assertEqual(ap.classify_command("cd app && pytest"), "verify")

    def test_explore_commands(self):
        self.assertEqual(ap.classify_command("grep -n foo bar.py"), "explore")
        self.assertEqual(ap.classify_command("find . -name '*.py'"), "explore")
        self.assertEqual(ap.classify_command("git status --short"), "explore")

    def test_other(self):
        self.assertEqual(ap.classify_command("mkdir -p /tmp/x"), "other")


class CommandOutcomeTest(unittest.TestCase):
    def test_verify_pass(self):
        self.assertEqual(ap.command_outcome("verify", False, "5 passed"), "ok")

    def test_verify_fail_via_is_error(self):
        self.assertEqual(ap.command_outcome("verify", True, ""), "fail")

    def test_verify_fail_via_text(self):
        self.assertEqual(ap.command_outcome("verify", False, "FAILED tests/x.py"), "fail")

    def test_explore_nonzero_is_not_failure(self):
        # grep no-match returns exit 1 — benign, must NOT be a failure
        self.assertIsNone(ap.command_outcome("explore", True, ""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'assessment_projection'`

- [ ] **Step 3: 写最小实现**

创建 `skills/claude-daily/scripts/assessment_projection.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: PASS（`ClassifyCommandTest`、`CommandOutcomeTest` 全绿）

- [ ] **Step 5: Commit**

```bash
git add skills/claude-daily/scripts/assessment_projection.py skills/claude-daily/scripts/test_assessment_projection.py
git commit -m "feat(assessment): 投影层命令分类与成败判定（verify/explore 去误判）"
```

---

### Task 2: danger 操作识别（看路径上下文）

**Files:**
- Modify: `skills/claude-daily/scripts/assessment_projection.py`
- Test: `skills/claude-daily/scripts/test_assessment_projection.py`

**Interfaces:**
- Produces: `is_danger_op(cmd: str) -> bool` —— 命令含破坏性动词且**不限于** throwaway 目录时为 True。

- [ ] **Step 1: 写失败测试**

在 `test_assessment_projection.py` 末尾（`if __name__` 之前）追加：

```python
class DangerOpTest(unittest.TestCase):
    def test_rm_rf_on_tmp_is_benign(self):
        self.assertFalse(ap.is_danger_op("rm -rf /tmp/hb-test"))

    def test_rm_rf_on_real_path_is_danger(self):
        self.assertTrue(ap.is_danger_op("rm -rf ~/project/src"))

    def test_git_reset_hard_is_danger(self):
        self.assertTrue(ap.is_danger_op("git reset --hard origin/main"))

    def test_plain_command_not_danger(self):
        self.assertFalse(ap.is_danger_op("ls -la"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection.DangerOpTest -v`
Expected: FAIL — `AttributeError: module 'assessment_projection' has no attribute 'is_danger_op'`

- [ ] **Step 3: 写最小实现**

在 `assessment_projection.py` 的 `command_outcome` 之后追加：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: PASS（含 `DangerOpTest`）

- [ ] **Step 5: Commit**

```bash
git add skills/claude-daily/scripts/assessment_projection.py skills/claude-daily/scripts/test_assessment_projection.py
git commit -m "feat(assessment): danger 操作识别（/tmp 使い捨て不误报）"
```

---

### Task 3: claim 识别 + 循环检测

**Files:**
- Modify: `skills/claude-daily/scripts/assessment_projection.py`
- Test: `skills/claude-daily/scripts/test_assessment_projection.py`

**Interfaces:**
- Produces:
  - `has_claim(text: str) -> bool` —— AI 是否声称"完成/修好/通过"
  - `normalize_cmd(cmd: str) -> str` —— 命令归一化键（用于循环检测）
  - `detect_loops(commands: list[dict]) -> dict` —— 同一归一化命令的验证失败 ≥2 次 → `{key: n}`

- [ ] **Step 1: 写失败测试**

在 `test_assessment_projection.py` 追加：

```python
class ClaimAndLoopTest(unittest.TestCase):
    def test_has_claim(self):
        self.assertTrue(ap.has_claim("好的，已修复了这个问题"))
        self.assertTrue(ap.has_claim("All tests passing — done."))
        self.assertFalse(ap.has_claim("我先看一下这个文件"))

    def test_detect_loops_flags_repeated_verify_failure(self):
        cmds = [
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
            {"cmd": "uv run python build-data.py", "kind": "verify", "outcome": "fail"},
        ]
        loops = ap.detect_loops(cmds)
        self.assertEqual(loops[ap.normalize_cmd("uv run python build-data.py")], 3)

    def test_single_failure_is_not_a_loop(self):
        cmds = [{"cmd": "pytest", "kind": "verify", "outcome": "fail"}]
        self.assertEqual(ap.detect_loops(cmds), {})

    def test_explore_failures_ignored(self):
        cmds = [
            {"cmd": "grep x a", "kind": "explore", "outcome": None},
            {"cmd": "grep x a", "kind": "explore", "outcome": None},
        ]
        self.assertEqual(ap.detect_loops(cmds), {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection.ClaimAndLoopTest -v`
Expected: FAIL — `AttributeError: ... has no attribute 'has_claim'`

- [ ] **Step 3: 写最小实现**

在 `assessment_projection.py` 追加：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: PASS（含 `ClaimAndLoopTest`）

- [ ] **Step 5: Commit**

```bash
git add skills/claude-daily/scripts/assessment_projection.py skills/claude-daily/scripts/test_assessment_projection.py
git commit -m "feat(assessment): claim 识别与失败循环检测"
```

---

### Task 4: 单 session 投影（4 信号 + 事件骨架 + claim↔验证关联）

**Files:**
- Modify: `skills/claude-daily/scripts/assessment_projection.py`
- Test: `skills/claude-daily/scripts/test_assessment_projection.py`

**Interfaces:**
- Consumes: `classify_command`, `command_outcome`, `is_danger_op`, `has_claim`, `detect_loops`（Task 1-3）
- Produces: `project_session(rows: list[dict]) -> dict`，返回：
  ```python
  {"commands": [{"cmd","kind","outcome"}],
   "edit_events": [{"file","n"}],          # 不去重，按 n 降序
   "claims": [{"claim","prev_verify","prev_verify_outcome"}],
   "loops": {key: n},
   "danger_ops": [{"cmd"}],
   "event_backbone": [{"i","type","text"}]}  # 全量，不砍头尾
  ```
  `rows` 是单个 session 的 jsonl 逐行解析对象，按时间顺序。

- [ ] **Step 1: 写失败测试**

在 `test_assessment_projection.py` 追加（用合成 rows 覆盖关键行为：验证失败后的 claim 应配上"fail"、同文件多次编辑不去重、探索命令非零不算失败）：

```python
def _assistant_bash(cmd, tuid):
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Bash", "id": tuid, "input": {"command": cmd}}]}}

def _assistant_edit(path):
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}}

def _assistant_text(text):
    return {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}

def _tool_result(tuid, is_error, text):
    return {"message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tuid, "is_error": is_error,
         "content": text}]}}

def _user(text):
    return {"message": {"role": "user", "content": text}}


class ProjectSessionTest(unittest.TestCase):
    def test_claim_pairs_with_preceding_failed_verify(self):
        rows = [
            _user("帮我修一下"),
            _assistant_bash("uv run python -m pytest -q", "t1"),
            _tool_result("t1", True, "FAILED tests/x.py"),
            _assistant_text("好了，已修复"),
        ]
        out = ap.project_session(rows)
        self.assertEqual(len(out["claims"]), 1)
        self.assertEqual(out["claims"][0]["prev_verify_outcome"], "fail")

    def test_edit_frequency_not_deduped(self):
        rows = [_assistant_edit("/p/walkthrough.md") for _ in range(3)]
        out = ap.project_session(rows)
        self.assertEqual(out["edit_events"][0], {"file": "walkthrough.md", "n": 3})

    def test_explore_nonzero_not_a_failure(self):
        rows = [
            _assistant_bash("grep -n foo bar.py", "g1"),
            _tool_result("g1", True, ""),
        ]
        out = ap.project_session(rows)
        self.assertEqual(out["commands"][0]["outcome"], None)
        self.assertEqual(out["loops"], {})

    def test_backbone_covers_all_rows(self):
        rows = [_user(f"msg {i}") for i in range(50)]
        out = ap.project_session(rows)
        # 全量覆盖：50 条 user 都在骨架里（不砍头尾）
        self.assertEqual(sum(1 for e in out["event_backbone"] if e["type"] == "user"), 50)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection.ProjectSessionTest -v`
Expected: FAIL — `AttributeError: ... has no attribute 'project_session'`

- [ ] **Step 3: 写最小实现**

在 `assessment_projection.py` 追加：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: PASS（含 `ProjectSessionTest` 全部 4 条）

- [ ] **Step 5: Commit**

```bash
git add skills/claude-daily/scripts/assessment_projection.py skills/claude-daily/scripts/test_assessment_projection.py
git commit -m "feat(assessment): 单 session 投影（4 信号 + 全量骨架 + claim↔验证关联）"
```

---

### Task 5: CLI 入口 —— 读 `_context.json`、重解析 transcript、写 `_assessment_context.json`

**Files:**
- Modify: `skills/claude-daily/scripts/assessment_projection.py`
- Test: `skills/claude-daily/scripts/test_assessment_projection.py`

**Interfaces:**
- Consumes: `project_session`（Task 4）；`_lib_config.load`、`_lib_paths.member_outbox`、`_lib_paths.atomic_write_json`
- Produces:
  - `load_session_rows(path: str) -> list[dict]`
  - `main(argv=None) -> int`（CLI：`--date`（必填）、`--config`）
  - 副作用：把 `_assessment_context.json` 写到 `outbox/<date>/<member_id>/`

- [ ] **Step 1: 写失败测试**

在 `test_assessment_projection.py` 追加（subprocess 跑 CLI：造一个临时 transcript + 一个指向它的 `_context.json`，断言产物含预期信号）：

```python
class CliTest(unittest.TestCase):
    def _config(self, td):
        cfg_path = Path(td) / "config.json"
        cfg_path.write_text(json.dumps({
            "member_id": "wanhua.gu",
            "endpoint_base": "http://x",
            "endpoint_paths": {"daily_report": "/d", "session_card": "/s"},
            "outbox_dir": str(Path(td) / "outbox"),
            "projects_root": str(Path(td) / "projects"),
        }), encoding="utf-8")
        return cfg_path

    def test_writes_assessment_context(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = self._config(td)
            # 1) 造一个真实 transcript jsonl
            tx = Path(td) / "sess.jsonl"
            rows = [
                {"message": {"role": "user", "content": "修一下"}},
                {"message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Bash", "id": "t1",
                     "input": {"command": "uv run python -m pytest -q"}}]}},
                {"message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1",
                     "is_error": True, "content": "FAILED"}]}},
                {"message": {"role": "assistant", "content": [
                    {"type": "text", "text": "已修复"}]}},
            ]
            tx.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            # 2) 造一个指向它的 _context.json
            outbox = Path(td) / "outbox" / "2026-06-25" / "wanhua.gu"
            outbox.mkdir(parents=True)
            (outbox / "_context.json").write_text(json.dumps({
                "generated_at": "2026-06-25T00:00:00Z",
                "sessions": [{
                    "session_id": "sess-0001", "session_short": "sess",
                    "project_dir": "demo", "transcript_path": str(tx),
                    "user_prompts": ["修一下"],
                }],
            }), encoding="utf-8")
            # 3) 跑 CLI
            p = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(cfg_path),
                 "--date", "2026-06-25"],
                capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr)
            out = json.loads((outbox / "_assessment_context.json").read_text())
            self.assertEqual(out["member_id"], "wanhua.gu")
            sess = out["sessions"][0]
            self.assertEqual(sess["claims"][0]["prev_verify_outcome"], "fail")
            self.assertEqual(sess["user_prompts"], ["修一下"])

    def test_missing_context_errors(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = self._config(td)
            p = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(cfg_path),
                 "--date", "2026-06-25"],
                capture_output=True, text=True)
            self.assertNotEqual(0, p.returncode)
            self.assertIn("_context.json", p.stderr)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection.CliTest -v`
Expected: FAIL —— CLI 无 `main`/无 `--date` 处理，subprocess 非零退出或产物缺失

- [ ] **Step 3: 写最小实现**

在 `assessment_projection.py` 末尾追加：

```python
def load_session_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main(argv=None):
    ap_ = argparse.ArgumentParser(description="AI assessment projection layer")
    ap_.add_argument("--date", required=True)
    ap_.add_argument("--config", default=None)
    args = ap_.parse_args(argv)

    try:
        config = cfg.load(Path(args.config) if args.config else None)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    member_id = config["member_id"]
    outbox = paths.member_outbox(config["outbox_dir"], args.date, member_id)
    ctx_path = outbox / "_context.json"
    if not ctx_path.exists():
        print(f"ERROR: {ctx_path} not found; run prepare.py first", file=sys.stderr)
        return 3

    context = json.loads(ctx_path.read_text(encoding="utf-8"))
    out_sessions = []
    for s in context.get("sessions", []):
        tp = s.get("transcript_path")
        signals = (project_session(load_session_rows(tp))
                   if tp and Path(tp).exists() else {})
        out_sessions.append({
            "session_id": s.get("session_id"),
            "session_short": s.get("session_short"),
            "project_dir": s.get("project_dir"),
            "user_prompts": s.get("user_prompts", []),
            **signals,
        })

    out = {
        "generated_at": context.get("generated_at"),
        "date_filter": args.date,
        "member_id": member_id,
        "sessions": out_sessions,
    }
    paths.atomic_write_json(outbox / "_assessment_context.json", out)
    print(f"✓ _assessment_context.json written ({len(out_sessions)} sessions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skills/claude-daily/scripts && python3 -m unittest test_assessment_projection -v`
Expected: PASS（全部 task 1-5 的测试类全绿）

- [ ] **Step 5: 跑一遍真实数据冒烟（可选但推荐）**

Run（确保当天已有 `_context.json`，否则先 `python3 prepare.py --date <date>`）：
```bash
cd skills/claude-daily/scripts
python3 assessment_projection.py --date <你有数据的某天>
python3 -c "import json,glob; f=sorted(glob.glob('$HOME/.local/state/compound-daily/outbox/*/*/_assessment_context.json'))[-1]; d=json.load(open(f)); s=d['sessions'][0]; print('signals keys:', sorted(s.keys())); print('loops sample:', [x.get('loops') for x in d['sessions'] if x.get('loops')][:3])"
```
Expected: 打印出含 `commands/edit_events/claims/loops/danger_ops/event_backbone` 的 keys；若某 session 有补丁循环，`loops` 非空。

- [ ] **Step 6: Commit**

```bash
git add skills/claude-daily/scripts/assessment_projection.py skills/claude-daily/scripts/test_assessment_projection.py
git commit -m "feat(assessment): 投影层 CLI（读 _context.json、写 _assessment_context.json）"
```

---

## Self-Review

**Spec coverage（对照 PRD §18.3 四信号 + 两去误判规则）：**

| 设计要求 | 落点 |
|---|---|
| 命令成败/退出码 | Task 1 `command_outcome` + Task 4 tool_result 配对 |
| 编辑频次（不去重） | Task 4 `edit_counts` / `edit_events` |
| claim↔验证关联 | Task 4 `claims[].prev_verify_outcome` |
| 中段覆盖（不砍头尾） | Task 4 `event_backbone` 遍历全量 rows（测试 `test_backbone_covers_all_rows`） |
| 去误判①：验证 vs 探索 | Task 1 `classify_command` + `command_outcome`（探索非零→None） |
| 去误判②：danger 看路径 | Task 2 `is_danger_op`（/tmp 不报） |
| 补丁循环检测 | Task 3 `detect_loops` |
| 不动日报路径 | 全程新增独立脚本，未列任何对 `build_report_context.py`/`prepare.py` 的修改 |

**Placeholder scan：** 无 TBD/TODO；每个 code step 都是完整可运行代码。
**Type consistency：** `project_session` 返回的键（`commands/edit_events/claims/loops/danger_ops/event_backbone`）在 Task 4 测试与 Task 5 CLI 中引用一致；`command_outcome` 的 `"ok"/"fail"/None` 三态在 Task 1/4 一致；`detect_loops` 在 Task 3/4 签名一致。

## 不在本 Plan 范围（Plan 2 再做）

- `references/ai-assessment-prompts.md`（8 维度行为锚点标尺 + Layer 0/0.5/1 + reduce 不平均规则 + 强制极值）
- `references/ai-assessment-review-checklist.md`（PRD §18.9 七大坑）
- SKILL.md 新增 `ai-assessment` mode 编排（prepare → projection → per-session map fan-out → 个人 reduce → 输出 → review gate）
- 三输出文件 `_ai_assessment.personal.md` / `_ai_assessment.manager.md` / `_ai_assessment.meta.json`
