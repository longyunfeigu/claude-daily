---
name: claude-daily
description: Use when the user wants a Claude Code session daily report, session card, work recap, AI coding activity summary, or PRD-compliant Compound Daily ingestion payload. The skill drives the full 6-step pipeline (prepare → generate → emit → upload) end-to-end inside a single Claude Code session.
---

<!--
Schema influences:
- US Army AAR (Intent / Reality / Gap / Adapt)
- Argyris double-loop learning (single-loop action vs double-loop assumption)
- Episodic→semantic memory consolidation (rules over titles, abstraction over recap)
These are scaffolding for the schema, not vocabulary to quote in output.
-->

# Daily Session Report

This skill turns local Claude Code transcripts into PRD-compliant payloads
for the Compound Daily ingestion pipeline. The Session Card schema (8 fields)
and Daily Report schema (9 sections) below define the **content** of each
artifact; this top section defines how Claude Code drives the run end-to-end.

## Trigger

When the user says one of:
- "跑 claude-daily" / "生成今天的日报" / "做今日复盘" / "daily report"
  → Run all 6 steps below (default; includes upload).
- "跑 claude-daily dry-run" / "只看不发" / "preview" / "先看看不发"
  → Run steps 1-5 only; stop after emit shows the summary table.
- "跑昨天的" / explicit "--date YYYY-MM-DD"
  → Use specified date instead of today.
- "重新发一遍" / "force"
  → Pass `--force` to upload (re-uploads regardless of existing acks).

If the user's intent is ambiguous (e.g. "今天看一下"), ask once before
starting. Default the mode slot to dry-run when ambiguous, not auto-upload.

## 6-Step Pipeline

### 1. Prepare context
Run: `python3 scripts/prepare.py --date <date>`

This validates `~/.compound-daily/config.json`, scans
`~/.claude/projects/`, computes per-session duration / started_at,
and writes `outbox/<date>/<member_id>/_context.json`. Per-session token usage
comes from `ccusage session --since/--until` (按天切分，与官方计数口径一致);
because subagent transcripts inherit their parent's sessionId, a parent's
ccusage total already includes its subagents' tokens. Subagent transcripts
remain out of the main session list.

Surface any `WARN:` lines from stdout to the user verbatim (cross-day
sessions, member_id collisions, multi-device conflicts, ccusage unavailable).
A `ccusage unavailable` WARN is non-fatal: token usage degrades to 0 and the
run continues normally. If exit code is non-zero, report the error and stop.

### 2. Read context
Read: `outbox/<date>/<member_id>/_context.json`

### 3. Generate three audience reports

Each round independently re-reads `_context.json` and follows the
Session Card + Daily Report schemas defined below. Do not reuse content
across rounds (acknowledged limitation: in-context priming may blur
audiences; do your best to apply the audience filter matrix for each
round independently).

a. audience=self     → Write `outbox/<date>/<member_id>/_output.personal.md`
b. audience=manager  → Write `outbox/<date>/<member_id>/_output.boss.md`

Each file MUST contain:
- Top-level heading `# Session Cards` containing the 8-field cards
- Top-level heading `# Daily Report` containing the 9-section report

### 4. Generate per-session metadata

Following the rubric in `references/payload-prompts.md`:
- For each top-level session, classify `value_tag` ∈ {valuable, chitchat,
  loop, no_output} using the boundary precedence defined in the rubric.
- Write a `summary` ≤ 80 Unicode characters: single paragraph, plain
  prose, no markdown lists / bold / inline code / file paths / backticks.
  Capture user's original intent + key outcome.

Write `outbox/<date>/<member_id>/_session_meta.json`:

```json
[
  {"session_id": "<full uuid>",
   "summary":    "...",
   "value_tag":  "valuable"}
]
```

Then run the content review gate before emit:

- Start a fresh subagent whose only task is to review the four generated
  artifacts against `references/content-review-checklist.md`.
- The reviewer MUST read artifacts from disk and compare them with
  `_context.json`; do not pass summaries from the generation thread as the
  source of truth.
- The reviewer writes
  `outbox/<date>/<member_id>/_review.content.md` with `Result: PASS` or
  `Result: FAIL`.
- If Claude Code subagents are unavailable, run the same checklist in the main
  thread and set `Mode: main-thread`; do not skip review.
- If the result is `FAIL`, regenerate only the targeted artifact(s) named in
  the review (`step 3a`, `3b`, or `4`), then run the content review gate
  once more.
- If the second review still fails, stop and report the findings to the user.

### 5. Emit payloads
Run: `python3 scripts/emit.py --date <date>`

Run emit only after `_review.content.md` says `Result: PASS`. `emit` validates
the payload structure; semantic and audience-fit validation is handled by the
content review gate.

emit validates the four artifacts, splits Session Cards from
`_output.personal.md`, derives short→full mappings, injects anchors,
runs JSON Schema validation, and writes 11 PRD-compliant payloads.

Show emit's stdout (the summary table) to the user.

If emit's stderr contains `re-run step <N>: <action>`, follow that
directive precisely:
- "re-run step 3a" → regenerate `_output.personal.md` only
- "re-run step 3b" → regenerate `_output.boss.md` only
- "re-run step 4"  → regenerate `_session_meta.json` only

Do not regenerate other artifacts. If the same error repeats after one
fix, stop and report to the user.

### 6. Upload (default)

Skip this step ONLY if the user said dry-run / preview / "只看不发".

Run: `python3 scripts/upload.py --date <date>`

Show upload's stdout to the user (per-line ✓/✗ + final count).

If non-zero exit code, report which payloads failed with the server's
error message; do not retry automatically.

## Required Session Card Schema

Every Session Card must include these fields in this order:

```text
原本想做什么
主要过程
产出
关键决策
差距
走过的弯路
证据
沉淀
  - 下次怎么做
  - 被推翻的想法
```

These eight fields cover three different cognitive functions on purpose:

- **过程** narrates how thinking moved (调研路径、grep 序列、推理拐点)
- **产出** lists what artifacts were created (改了什么文件、给了什么结论)
- **决策** crystallizes why a choice was made (X vs Y 的判断依据)

Do not collapse them into a single narrative; each carries information the others cannot.

Field-level constraints:

- **原本想做什么**: anchor to `user_prompts`; describe the start-of-session goal, not the eventual outcome. Quote a short fragment when it sharpens meaning.
- **主要过程**: bullet or short-paragraph form. Each step ties to tool calls, files read, commands, or web searches. Show the trail, not just the destination.
- **产出**: enumerate concrete deliverables—modified files (with paths), generated tables/snippets, conclusions stated in the conversation. If nothing was produced, write `无产出工件`.
- **关键决策**: each entry framed as "在 X 和 Y 之间为何选 X"; bind to evidence (file, command, web source, benchmark). A choice without a visible alternative is an action, not a decision—belongs to 主要过程.
- **差距**: state intent-vs-reality deviation plainly; if matched, write `无显著偏离`. Do not invent gaps. Unfinished work is a gap (timing or scope reason).
- **走过的弯路**: identify abandoned paths, reverted edits, killed branches, mid-flight reversals; if none, write `今天没走值得记的弯路`.
- **证据**: tool counts (e.g. `Bash×35, Read×23, Edit×16, WebSearch×5`), important files, key commands; if no edits, write `无本地文件修改证据`.
- **沉淀**: split `下次怎么做`（action to repeat/change）and `被推翻的想法`（assumption overturned）; if neither applies, write `今天没什么值得记的`.

If any field lacks evidence, use the explicit "no evidence" phrase from `references/report-prompts.md` instead of inventing content.

## Required Daily Report Schema

Every Daily Report must include these sections in this order:

```text
时间范围 / Audience
今日总览
主题分组
今天学到的
关键决策
被推翻的想法
走过的弯路
验证结果
风险与阻塞
Session 附录
```

Section-level constraints:

- **今日总览**: 2-4 sentences of plain-language recap. Audience: **a colleague who was NOT in your head today**, graspable in 5 seconds. **Must convey the day's shape** (上午/下午/晚上 各自重心 + 高层完成了什么). Hard limits:
  - **No token or cost numbers**—token 用量在服务端 Token 页面单独看，不入正文.
  - **No code symbols**: 类名、函数名、私有方法 (`._execute`)、修饰器 (`@start`)、文件后缀 (`.py`).
  - **No precise timestamps**: 用"上午/下午/晚上"，不写 `10:05`、`14:23`.
  - **No file paths or note IDs**: 不写 `S05B-Agent身份`、`~/.claude/projects/`、绝对路径.
  - Concrete product/topic nouns are encouraged (CrewAI、Agent、向量库). Detail belongs to 主题分组/主要过程/产出/证据—not here.
  - If the day is single-themed, one sentence is fine. Do not pad to fill 4 sentences.
- **主题分组**: 按主题归类（非项目/session），同一主题可跨多个项目，一个 session 也可拆进多个主题.
  - **实质性门槛**: 只有约 10-15 分钟以上的实质工作才单列成主题；零碎修补、小调整一律进 Other.
  - 主题标题可带时段，如 `### 源码精读（上午）`.
  - 每主题 **2-4 条 bullet（封顶）**，每条对应：实质工作 / 关键决策 / 产出工件（路径）.
  - **Other**: 小任务、快修、配置微调一桶带过，简短.
- **今天学到的**: one rule that survives after stripping today's specifics. **Must include an observable trigger condition** (e.g. "下次 SSE 卡顿时…"). Slogans fail this constraint. If no rule emerges, write `今天没学到能带走的`.
- **关键决策**: each formatted as "在 X 和 Y 之间为何选 X". Bare actions without alternatives are not decisions.
- **被推翻的想法**: each item lists 原本以为 / 推翻点 / 证据. Must reference a reversal in the transcript. If none, `今天没遇到被推翻的想法`.
- **走过的弯路**: aggregate session-level reversals; group into 差点合并 / 被否决 / 差点踩. If none, `今天没走值得记的弯路`.
- **验证结果**: bind to concrete evidence (tests run, commands succeeded). If absent, name the session and write `未发现明确验证证据`.
- **风险与阻塞**: per-line blocker + impact + earliest unblock signal.
- **Session 附录**: one line per session with tool counts and key artifacts.

## Evidence Rules

- Treat top-level sessions as the report mainline.
- Treat subagent transcripts as optional evidence only; include them only when the user asks or when debugging.
- Use file paths, commands, tool counts, web searches, token usage, and prompt excerpts from the JSON context as evidence.
- Use `assistant_segments` to infer conclusions and insights Claude produced during the session.
- Treat segment `signals` as mechanical hints only, not importance labels.
- Select or rewrite key points from `assistant_segments` yourself; do not assume Python has already decided what matters.
- Do not treat assistant text as proof of external facts or code completion; bind factual claims to file/command/tool evidence.
- Never claim tests passed, code was deployed, a bug was fixed, or a feature is complete unless evidence exists in the context.
- Clearly mark cross-date reports: selected session reports may span multiple real dates.

### Schema-specific guards

- **今天学到的**: must contain a concrete trigger condition; otherwise the rule is not crystallized.
- **被推翻的想法**: must point to a reversal point in `user_prompts`, `compact_events`, or `assistant_segments` (user correction, benchmark contradiction, rollback). No reversal → no claim.
- **走过的弯路**: extract from `git restore`/`git reset`/`git checkout --`/`git branch -D` commands, reverse-Edit pairs in tools, and user-side mid-flight reversals like 算了/不要/回滚. Without these signals, write the empty phrase, do not invent.
- **差距空允许**: an aligned session is normal; do not manufacture a gap to fill the slot.
- **决策门槛**: a choice qualifies as a decision only if an alternative was visible in the transcript. Otherwise it is just an action and belongs to `主要过程`.

## Audience Modes

Audience changes **which fields appear, how they're worded, and how long the report runs**—not just emphasis or density. Picking the wrong audience is a category error: a self-style reflection sent to a manager reads as self-doubt; a manager-style summary read by oneself loses all the reflection signal.

### 字段保留矩阵

| 字段 | self | manager |
|---|---|---|
| 今日总览 | 个人视角 | 业务影响视角 |
| 主题分组 | ✓ | ✓ 重点（业务化措辞）|
| 今天学到的 | ✓ | 砍 |
| 关键决策 | ✓ | ✓ 仅业务/资源相关 |
| 被推翻的想法 | ✓ | 砍（除非影响进度）|
| 走过的弯路 | ✓ | 砍（除非耗显著时间）|
| 验证结果 | ✓ 详细 | ✓ 高层化 |
| 风险与阻塞 | ✓ | ✓ 重点 |
| Session 附录 | ✓ 完整 | 砍或极简 |

`mixed`（默认）按 self 矩阵执行，但允许在范围内自动收缩：当天没有显著弯路时"走过的弯路"段可以一行带过。

### 风格规则

| 维度 | self | manager |
|---|---|---|
| 人称 | 我 | 我们 / 无主语 |
| 技术密度 | 高（类名、命令、grep）| 低（业务名词为主）|
| 心理活动 | 可以写 | 不写 |
| 字数（中文）| 1500-2500 | 400-800 |

### 硬规则

**manager:**
- 成果优先；技术细节压缩到不影响判断的最小集
- 只保留关键风险与下一步
- **不展示 token、工具调用次数、源码路径，除非用户明确要求**
- 不写"被推翻的想法"和"走过的弯路"——业务读者会读成自我否定

### 范例

**manager 模式（今日总览）：**
> "今天完成了 CrewAI 结构化输出机制的源码级验证，并沉淀到教学文档中。核心风险是结构化输出格式可靠不等于事实可靠，后续会补最小验证案例，避免团队在使用 Agent 工具时误判结果可信度。"

## Script Notes

`scripts/build_report_context.py` supports:

```text
--date YYYY-MM-DD
--session SESSION_PREFIX   repeatable
--projects-root PATH       default ~/.claude/projects
--include-subagents
--include-subagent-usage   roll subagent tokens into parent sessions
--timezone-offset +08:00
--limit N
--out PATH
--pretty
```

Run `python3 scripts/build_report_context.py --help` for exact flags.
