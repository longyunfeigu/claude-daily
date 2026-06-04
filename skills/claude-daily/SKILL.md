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
for the Compound Daily ingestion pipeline. This file defines how Claude Code
drives the run end-to-end; `references/report-prompts.md` is the source of
truth for Session Card, Daily Report, evidence, and audience rules.

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

### 3. Generate two audience reports

Each round independently re-reads `_context.json` and
`references/report-prompts.md`. Do not reuse content across rounds
(acknowledged limitation: in-context priming may blur audiences; do your
best to apply the audience rules for each round independently).

a. audience=self     → Write `outbox/<date>/<member_id>/_output.personal.md`
b. audience=manager  → Write `outbox/<date>/<member_id>/_output.boss.md`

Each file MUST contain:
- Top-level heading `# Session Cards` containing the per-session cards
- Top-level heading `# Daily Report` containing the audience-specific report

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

- Start a fresh subagent whose only task is to review the three generated
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

emit validates `_context.json` plus the three generated artifacts, splits
Session Cards from `_output.personal.md`, derives short→full mappings,
injects anchors, runs JSON Schema validation, and writes one Session Card
payload per top-level session plus two Daily Report payloads
(`session_count + 2` total).

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

## Report Contract

`references/report-prompts.md` is the single source of truth for report
content. Load it during step 3 and follow it exactly for:

- Session Card shape: personal cards include 9 fields; manager cards omit
  `人机协作`.
- Daily Report shape: personal keeps the full 9 sections; manager applies the
  audience-specific removals and compression rules.
- Evidence rules, hallucination guards, audience modes, and empty evidence
  phrases.

`references/payload-prompts.md` governs only `_session_meta.json`.
`references/content-review-checklist.md` governs the review gate before emit.

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
