# Report Output Contract

Use this contract after reading `_context.json` produced by `scripts/prepare.py`.

## Contents

- [Required Final Shape](#required-final-shape)
- [Session Cards](#session-cards)
- [Daily Report](#daily-report)
- [Audience Modes](#audience-modes)
- [Hallucination Guard](#hallucination-guard)
- [Episode Guidance](#episode-guidance)
- [Input Priority](#input-priority)

## Required Final Shape

The final answer must contain both sections, in this order:

```markdown
# Session Cards

[one card per top-level session]

# Daily Report

[daily synthesis]
```

Do not output only a table, only a timeline, or only a free-form reflection. A report missing the `# Daily Report` section is incomplete.

## Session Cards

Write one card per top-level session, in chronological order. Personal and
manager cards share the same 8 fields.

```markdown
## Session `<session_short>`：<short title>

原本想做什么：

主要过程：
-

产出：
-

关键决策：
-

差距：

走过的弯路：

证据：

沉淀：
- 下次怎么做：
- 被推翻的想法：
```

These fields cover different cognitive functions:
- **过程** narrates how thinking moved (调研路径、grep 序列、推理拐点).
- **产出** lists what artifacts were created (改了什么文件、给了什么结论).
- **决策** crystallizes why a choice was made (X vs Y 的判断依据).

Do not collapse them into a single narrative; each carries information the
others cannot.

### Field rules

**原本想做什么**
- Anchor to actual `user_prompts`; quote a short fragment when useful.
- Describe what the user wanted at the start, not what was eventually built.
- If the session shifted intent mid-way, note both the original and shifted goal.

**主要过程**
- Bullet form, narrate the session **逐回合/逐阶段**——把对话弧线一段段写出来，不要压成三五条干 bullet。每个实质回合/阶段一条。
- Reconstruct the arc from the interleaved `compact_events` timeline, which now carries `user_prompt → assistant → tool` 顺序事件；用它还原"用户问什么 → AI 怎么回/提了什么 → 这一轮落了什么"。
- Each bullet = 用户这一轮的诉求 + AI 的回应或方案 + 该回合的落地（tool calls, files read/modified, commands, web searches）+ 命名的用户 pushback（如有）。
- 详细度下限：覆盖到当天的主要回合；一个有 10+ 回合的 session 不应只剩 4 条过程。This field shows the trail, not the destination. Do not skip to results here.
- Example bullet shape: "用户抛出 X vs Y 两个候选 → Claude 先读 a.py/b.py 摸清现状、指出 Y 是伪命题并给推荐 → 用户认可并定下方向 Z"; "Claude 沿着 a.py、b.py 一路 grep，定位 X、Y、Z 字段的实际行为，用户随后要求联网验证是不是幻觉".

**产出**
- Enumerate concrete artifacts created in the session:
  - Modified files (cite full paths from `files_modified`).
  - Tables, schemas, decision matrices, code snippets given in the conversation.
  - Documents updated, branches created, ADRs written.
- If nothing was produced, write `无产出工件`. Do not pad with conclusions.
- 产出 is what exists after the session; conclusions/insights belong to `沉淀`.

**关键决策**
- Each entry framed as "在 X 和 Y 之间为何选 X"; if no alternative was visible, the choice is an action—move it to 主要过程.
- Bind each decision to evidence: a file change, command result, benchmark, web source, or user statement.
- Capture the rule, not just the choice. Example: "选型规则：需要查真实数据 → 用 output_pydantic；输入已含全部信息 → 用 response_model。"
- If no decisions were made, write `无关键决策`.

**差距**
- Compare 原本想做什么 vs 实际做了什么. State the deviation plainly and the reason.
- If they match, write `无显著偏离`. Do not invent gaps.
- Treat unfinished work as a gap (timing reason or scope reason).

**走过的弯路**
- Capture what almost happened but did not. Sources to scan:
  - `git restore`, reverted Edits, deleted branches in `commands` / `tools`.
  - User mid-session reversals like "算了"、"不要这个了"、"回滚" in `user_prompts`.
  - Paths considered then rejected in `assistant_segments`.
- If no such evidence, write `今天没走值得记的弯路`. Do not fabricate alternatives.

**证据**
- Tool counts, e.g. `Bash×28, Read×24, Edit×3`.
- Important modified files first; truncate noisy paths.
- Commands only when they explain the work.
- If there are no file edits, write `无本地文件修改证据`.

**沉淀**
- `下次怎么做`：a concrete action to repeat or change next time the same task appears.
- `被推翻的想法`：a belief that was overturned by today's evidence. Must reference a reversal point in the transcript.
- If neither applies, write `今天没什么值得记的` rather than padding.

## Daily Report

Use this structure exactly:

```markdown
时间范围：<start> → <end>（timezone）
Audience：<self|manager>

## 今日总览

## 主题分组

## 今天学到的

## 关键决策

## 被推翻的想法

## 走过的弯路

## 验证结果

## 风险与阻塞

## Session 附录
```

### Section rules

**今日总览**

This is a *briefing*, not a *log*. Imagine a colleague who was NOT in your head today reading it cold. They should grasp roughly what you did in 5 seconds.

Hard limits:
- 2-4 sentences of prose. **Must convey the shape of the day**: 上午/下午/晚上 各自的重心，以及高层上完成了什么.
- **No token or cost numbers** here. Token 用量在服务端 Token 页面单独呈现，不写进报告正文.
- **No code symbols** anywhere: 类名、函数名、私有方法（`._execute`）、修饰器（`@start`）、文件后缀（`.py`）.
- **No precise timestamps**: 用"上午/下午/晚上"，不写 `10:05`、`14:23`.
- **No file paths or note IDs**: 不写 `S05B-Agent身份`、`~/.claude/projects/` 这类只有作者认得的标识.
- **No insider jargon verbs**: 避免"顺手摸了 X 为 Y 攒证据"这种黑话.
- Concrete product/topic nouns ARE encouraged: CrewAI、Agent、向量库、黑客松、源码 are good; specific symbols inside those products are not.
- Single-themed day → one sentence. Do not pad to fill 4 sentences.
- Avoid bullet lists; this section is prose.

If you find yourself writing class names, file paths, timestamps, or token counts, **stop and move that detail to 主题分组 / 主要过程 / 产出 / 证据 or the Token 页面**.

✅ Good example:
> "上午到下午精读 CrewAI 源码、搞清结构化输出与 Agent 委托/规划机制；晚上帮老板设计了 AI Builder 黑客松方案，并调研了用 session 日志自动出日报的方法论。"

**主题分组**

把当天工作按**主题**归类，不按项目或 session——同一主题可横跨多个项目，一个 session 也可拆进多个主题。

- **实质性门槛**：只有约 10-15 分钟以上的实质工作才单列成一个主题；零碎修补、小调整一律进 Other，不单独成段.
- 主题标题可带时段，例如 `### 源码精读机制（上午）`、`### 黑客松方案设计（晚上）`.
- 每个主题 **2-4 条 bullet（封顶）**，每条对应其一：实质工作 / 关键决策 / 产出工件（含文件路径）.
- 这是主题级摘要，不是流水账；不要罗列每一步.
- **Other**：剩余小任务、快修、配置微调一桶带过，保持简短.

The 越界 example below applies to 今日总览 specifically:

❌ Bad example (越界进入 log 而非 briefing):
> "上午 10:05 在 Obsidian Vault 打开 CrewAI 学习笔记 S04，先精读 internal_instructor / lite_agent / crew_agent_executor，把 response_model 副作用从'教学版幻觉'质疑里救回来并写进 S05B-Agent身份；约 10:53 平行起了一个非源码会话…"

What's wrong with the bad example: 时间精确到分钟、笔记编号外露、类名修饰器堆叠、单段超 200 字。同等信息在新 schema 中应这样分配：

| 内容片段 | 应去字段 |
|---|---|
| `10:05`、`10:53`、`14:23` | Session 附录的时间范围 |
| `internal_instructor`、`lite_agent`、`crew_agent_executor`、`@start/@router/@listen` | 主要过程的 grep 路径 |
| `S04`、`S05B-Agent身份`、`S11-规划系统` | 产出的修改文件清单 |
| "把 response_model 副作用从'教学版幻觉'救回来" | 关键决策 或 被推翻的想法 |

**今天学到的**
- One sentence (or two short ones) carrying a rule that survives after stripping today's specifics.
- **Hard constraint**: must include an observable trigger condition, e.g. "下次 SSE 卡顿时…", "再选向量库时…".
- Vague slogans like "持续学习"、"注意细节"、"沟通很重要" fail this constraint. If no rule emerges, write `今天没学到能带走的` and explain why in one line.

**关键决策**
- Format each decision as "在 X 和 Y 之间为何选 X". A bare action without an alternative is not a decision; omit it.
- Bind to evidence: which file/command/web source informed the choice.

**被推翻的想法**
- Each item: "原本以为：X。被推翻的点：Y。证据：Z。"
- Must reference a reversal in the transcript: user correction, benchmark result, rollback, or a `compact_events` shift.
- If none, write `今天没遇到被推翻的想法`. Do not fabricate beliefs to fit the slot.

**走过的弯路**
- Aggregate all session-level reversals worth carrying forward.
- Group into: 差点合并的改动 / 被否决的路径 / 差点踩的坑.
- If no session produced reversals, write `今天没走值得记的弯路`.

**验证结果**
- Bind to concrete evidence: tests run, commands succeeded, files reviewed, deploys observed.
- If a session had no verification, name the session and write `未发现明确验证证据`.

**风险与阻塞**
- One risk per line. Each risk states: blocker + impact + earliest unblock signal.

**Session 附录**
- One line per session: `<short> <title> → tool counts；关键文件；分支/产出工件`.

## Audience Modes

Audience changes which fields appear, how they are worded, and how long the
report runs. It is not just an emphasis change.

| 字段 | self | manager |
|---|---|---|
| 今日总览 | 个人视角 | 业务影响视角 |
| 主题分组 | ✓ | ✓ 重点（业务化措辞） |
| 今天学到的 | ✓ | 砍 |
| 关键决策 | ✓ | ✓ 仅业务/资源相关 |
| 被推翻的想法 | ✓ | 砍（除非影响进度） |
| 走过的弯路 | ✓ | 砍（除非耗显著时间） |
| 验证结果 | ✓ 详细 | ✓ 高层化 |
| 风险与阻塞 | ✓ | ✓ 重点 |
| Session 附录 | ✓ 完整 | 砍或极简 |

| 维度 | self | manager |
|---|---|---|
| 人称 | 我 | 我们 / 无主语 |
| 技术密度 | 高（类名、命令、grep） | 低（业务名词为主） |
| 心理活动 | 可以写 | 不写 |
| 字数（中文） | 1500-2500 | 400-800 |

Manager hard rules:
- 成果优先；技术细节压缩到不影响判断的最小集.
- 只保留关键风险与下一步.
- 不展示 token、工具调用次数、源码路径，除非用户明确要求.
- 不写"被推翻的想法"和"走过的弯路"，除非它们直接影响进度或风险判断.

Manager 今日总览 example:
> "今天完成了 CrewAI 结构化输出机制的源码级验证，并沉淀到教学文档中。核心风险是结构化输出格式可靠不等于事实可靠，后续会补最小验证案例，避免团队在使用 Agent 工具时误判结果可信度。"

## Hallucination Guard

Only write claims supported by `_context.json`.

Evidence discipline:
- Treat top-level sessions as the report mainline.
- Treat subagent transcripts as optional evidence only; include them only when
  the user asks or when debugging.
- Use file paths, commands, tool counts, web searches, token usage, and prompt
  excerpts from `_context.json` as evidence.
- Use `assistant_segments` to infer conclusions and insights Claude produced
  during the session, but do not treat assistant text as proof of external
  facts or code completion.
- Treat segment `signals` as mechanical hints only, not importance labels.
- Select or rewrite key points from `assistant_segments` yourself; do not
  assume Python has already decided what matters.
- Clearly mark cross-date reports: selected session reports may span multiple
  real dates.

Use these phrases when evidence is absent:

- `未发现明确验证证据`
- `无本地文件修改证据`
- `未从 transcript 中发现后续计划`
- `该结论来自用户讨论和工具调用摘要，未绑定代码变更`
- `今天没遇到被推翻的想法`
- `今天没走值得记的弯路`
- `做的和原本想的一致`
- `今天没学到能带走的`
- `今天没什么值得记的`
- `无产出工件`
- `无关键决策`
- `无显著偏离`

Do **not**:

- Claim tests passed without a test command in `commands`.
- Claim a feature shipped, deployed, or merged without a corresponding command/branch signal.
- Claim a bug was fixed because the assistant said so; the fix must show up in `files_modified` plus a verification command.
- Invent an alternative path for `走过的弯路` just to fill the slot.
- Manufacture a "被推翻的想法" item when the transcript only shows action-level changes.

## Episode Guidance

The script emits `compact_events`. Use them to infer semantic episodes; Python finds candidate events, the LLM decides meaning:

- Merge follow-up questions that refine the same topic.
- Split when the user changes product/problem/domain.
- Name episodes with concrete nouns, not generic labels like `讨论` or `分析`.
- Episodes can summarize into a card's `主要过程` field; do not expose internals unless useful.

## 怎么从 transcript 里挖出走过的弯路

To populate `走过的弯路` reliably, scan the context for these signals:

| Signal | Source field | Meaning |
|---|---|---|
| `git restore`, `git reset`, `git checkout --` | `commands` | reverted local work |
| Edit followed by reverse Edit on same file | `tools` ordered by ts | tried then undone |
| `git branch -D <name>` | `commands` | abandoned branch |
| `user_prompts` containing `算了`、`不要`、`回滚`、`撤销`、`换一种` | `user_prompts` | mid-flight reversal |
| Web search hits not reflected in any later code change | `web_sources` vs `files_modified` | path investigated then dropped |

A reversal that is then re-attempted and succeeded is a `差距` story, not a `走过的弯路`. A reversal that ended in abandonment is a `走过的弯路`.

## Input Priority

Use report context fields in this order:

1. `user_prompts` and `compact_events` for intent and flow.
2. `tools`, `files_modified`, `files_read`, `commands`, `web_sources` for evidence.
3. `assistant_segments` for conclusions and reusable insights; select useful points yourself, do not assume Python decided importance.
4. `assistant_samples` only as fallback context.
