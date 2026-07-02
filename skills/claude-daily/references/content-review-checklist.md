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
- Every Session Card in `_output.personal.md` contains the 8 required fields in
  order (原本想做什么/主要过程/产出/关键决策/差距/走过的弯路/证据/沉淀).
- No Session Card (personal or manager) contains a `人机协作` field or an
  `AI 使用评分` block; AI 使用分析归 ai-assessment 模式，不进日报。
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
