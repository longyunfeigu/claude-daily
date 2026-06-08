# Daily Report Content Review Checklist

Use this checklist for the independent content review gate after the LLM has
written `_output.personal.md`, `_output.boss.md`, and `_session_meta.json`,
before `emit.py` runs.

## Reviewer Role

You are a skeptical report reviewer, not a co-writer. Read the artifacts from
disk and compare them with `_context.json`, `SKILL.md`, `report-prompts.md`, and
`payload-prompts.md`. Do not rely on the generation thread's memory.

Your job is to decide whether the artifacts are safe to emit and upload. Do not
rewrite the reports. Return a compact PASS/FAIL report with precise fixes.

## Inputs

- `outbox/<date>/<member_id>/_context.json`
- `outbox/<date>/<member_id>/_output.personal.md`
- `outbox/<date>/<member_id>/_output.boss.md`
- `outbox/<date>/<member_id>/_session_meta.json`
- `SKILL.md`
- `references/report-prompts.md`
- `references/payload-prompts.md`

## Hard Fail Checks

Fail the review if any item below is violated.

### Artifact Shape

- Each `_output.*.md` has top-level `# Session Cards` and `# Daily Report`.
- Daily Report sections use markdown `##` headings for the required sections
  that are kept for the target audience.
- Personal report keeps all 9 required Daily Report sections.
- Manager report omits `今天学到的`, `被推翻的想法`, `走过的弯路`, and usually
  `Session 附录`, unless a removed section directly affects schedule or risk.
- Every Session Card in `_output.personal.md` contains the 9 required fields in
  order (原本想做什么/主要过程/产出/关键决策/差距/走过的弯路/证据/人机协作/沉淀).
- `主要过程` 按回合/阶段叙事并覆盖到主要回合；不应被压成三五条干 bullet（10+ 回合的 session 尤其）。
- `_session_meta.json` has one entry per top-level session and each `summary`
  is at most 80 Unicode characters.

### 今日总览 / 主题分组

- `今日总览` is prose (not a bullet list) and conveys the day's shape (上午/下午/晚上 重心).
- `今日总览` contains no token/cost numbers, precise clock times, file paths, note IDs,
  markdown code spans, class/function/private method names, decorators, or file suffixes.
- `今日总览` is understandable to someone who was not in the session.
- `主题分组` groups by theme, not by project/session; trivial work (under ~10-15 min)
  is bucketed under Other rather than given its own theme.
- Each theme carries at most 4 bullets.

### Evidence Discipline

- No report claims tests passed, deployment happened, a bug was fixed, or a
  feature is complete unless `_context.json` has command/file/tool evidence.
- `关键决策` entries use the shape "在 X 和 Y 之间为何选 X" and the alternative is
  visible in the transcript or assistant segments.
- `被推翻的想法` points to a visible reversal; otherwise the report uses the empty
  phrase.
- `走过的弯路` points to revert/reset/abandoned-path/user-reversal evidence;
  otherwise the report uses the empty phrase.
- `验证结果` names missing verification explicitly with `未发现明确验证证据`.

### 人机协作（仅 personal）

- personal 卡片每张都有 `人机协作`，含六子项：协作方式 / 怎么提问 / 怎么驾驭 / 哪些做得好 / 哪些用得不好 / AI 使用评分；manager 卡片不应出现该字段。
- 正文无学术黑话（acceleration / delegation / Dependency Ratio / interactive steering 等）。
- 每个子项都写**有效做法 + 缺口 / 可更好**；只夸不指出缺口，或无证据地批评，判为不合格。
- 当 `_context.json` 的 `user_prompts` 非空时，真人动作实例必须直接引用其中真实原话（带引号 verbatim 片段），不是泛泛转述；引文必须能逐字找到，把 CLAUDE.md 规则、AI 自己的话或推测当成用户原话的，判为不合格（张冠李戴）。
- 当 `user_prompts` 为空时，报告不得硬评真人提问手法、不得编造引文；必须写明 `user_prompts 为空 / 无真人提问可评`，并指出下一次委派应补的目标、边界、验收标准、验证方式、停手/确认点中的具体缺口。
- `哪些做得好` 每条都绑**具体动作 + 带来的效果**，空夸（如"提问很清晰"而无具体动作/原话）判为不合格；没有真人动作时，可以评价可复用的 AI 工作方式，但必须附【可更好】。
- `哪些用得不好 / 风险信号` 必须扫描坏味道：糊需求整包委派、盲收 AI 输出、不读 diff/不跑测试、依赖不查、补丁 loop、把架构/安全/产品取舍外包、没有沉淀、缺少验证或独立 review；有证据则必须写成 `【风险】<证据>——<为什么不好>——<下次怎么拦>`，无证据则写 `这次未发现明显的 AI 使用坏味道`。
- `哪些用得不好 / 风险信号` 不得写成泛泛建议（如"可以更清晰"），必须是 transcript 中可定位的坏信号；如果没有坏信号，不能硬凑批评。
- `AI 使用评分` 必须包含固定维度：目标与上下文 / 约束与验收 / 委派是否合适 / 验证与审查 / 纠错与止损 / 人类关键判断 / 沉淀复用 / 评分置信度；不得出现总分。
- 每个评分维度必须是 `0/3`、`1/3`、`2/3`、`3/3` 或 `N/A`，并跟一句具体证据；没有证据必须写 `N/A`，不能凭印象扣分或加分。
- `评分置信度` 只能为低/中/高，并说明证据覆盖情况；如果 `user_prompts`、`commands`、`files_modified` 等关键证据不足，置信度不得写高。
- 标尺真落地：`怎么提问` 要落到具体手法或缺陷类目（如"写死约束""漏验收标准导致返工"）；`怎么驾驭` 要给出依赖姿态判断（过度/不足/校准）+ 至少一处纠错恢复、选择性采纳、人工验收缺失或待确认决策点观察。但**标尺名词不得出现在正文**（出现 Prompt Pattern/Dependency Ratio 等即不合格）。

### Audience Fit

- Personal can be reflective and technical.
- Manager starts from outcome, risk, and next decision; it does not expose token
  counts, tool call counts, raw source paths, grep trails, or implementation
  minutiae unless the user explicitly asked for them.

## Output Protocol

Write `outbox/<date>/<member_id>/_review.content.md` exactly in this shape:

```markdown
# Content Review

Result: PASS|FAIL
Mode: subagent|main-thread

## Findings

- [step 3a|3b|4] <artifact>: <specific violation> -> <specific fix>

## Notes

- <optional non-blocking observation>
```

If there are no blocking findings, write `Result: PASS` and `- none` under
Findings.

When returning FAIL, assign each finding to exactly one regeneration target:

- `step 3a` for `_output.personal.md`
- `step 3b` for `_output.boss.md`
- `step 4` for `_session_meta.json`

Do not ask for broad rewrites. Point to the smallest artifact that must be
regenerated.
