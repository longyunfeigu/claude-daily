# value_tag Classification Rubric + summary Constraints

This file is loaded by Claude Code in step 4 of the 6-step pipeline
(see SKILL.md). It governs only the `_session_meta.json` output, not
Session Cards or Daily Reports.

## value_tag

For each top-level session, choose exactly one tag.

### Boundary precedence

When multiple tags apply, pick the **leftmost**:

  valuable > loop > chitchat > no_output

This eliminates ambiguity for borderline sessions.

### Per-tag criteria

| value_tag   | Choose when                                                            |
|-------------|------------------------------------------------------------------------|
| valuable    | At least one concrete artifact in 产出 (file path / successful command  |
|             | / doc landing) AND no significant 走过的弯路.                           |
| loop        | 走过的弯路 contains repeated reverts / git restore-reset-checkout--, or |
|             | 差距 indicates the session got stuck cycling.                           |
| chitchat    | 主要过程 is research / Q&A only; no artifacts, no decisions.            |
| no_output   | Tool calls happened but 产出 = "无产出工件" AND no verification.        |

### Worked examples

**Example 1**: Session 改了 3 个 .py 文件 + git restore 一次 + 测试通过
→ `valuable` (有产出 + 一次反复但收敛 → 不算 loop)

**Example 2**: Session 反复 git reset --hard 三次，最终 abandon
→ `loop` (反复未收敛)

**Example 3**: Session 全程 web 调研，没产出文件
→ `chitchat` (research only, no artifact)

**Example 4**: Session 跑了 ls / pytest，但代码没改、测试没过
→ `no_output`

## summary

For each session, write a one-sentence summary in `_session_meta.json`:

- ≤ 80 Unicode characters
- Single paragraph (no `\n`)
- Plain prose: no markdown lists, no bold, no inline code, no file paths,
  no class names, no backticks
- Capture: user's original intent + key outcome (or block)

**Bad** (uses markdown list):
> "- 调研 CrewAI\n- 修改 S04 笔记"

**Good**:
> "用户希望搞清 CrewAI 结构化输出与真实工具调用的边界，最终确认结论并落到学习笔记"

**Bad** (file path + class name + backticks):
> "改了 \`crew_agent_executor.py\` 里 \`_execute\` 方法"

**Good**:
> "调整 Agent 执行流程的内部方法，验证后续工具调用走真实路径"
