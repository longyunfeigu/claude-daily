# Report Output Contract

Use this contract after reading `report_context.json` produced by `scripts/build_report_context.py`.

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

Write one card per top-level session, in chronological order:

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

人机协作：（仅 personal 卡片；manager 卡片省略本字段）
- 协作方式：
- 怎么提问：
- 怎么驾驭：
- 哪些做得好 / 可复用：

沉淀：
- 下次怎么做：
- 被推翻的想法：
```

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

**人机协作**

仅在 self/personal 卡片写本字段；manager 卡片省略（业务读者会把"我怎么驾驭 AI"读成自我评价）。

<!-- 下面四条子项的判断标尺来自人机协作研究，仅作 LLM 内部分析脚手架，名词不进正文：
     加速/探索双模 (Grounded Copilot, arxiv 2206.15000)；code-with/code-for (arxiv 2507.08149)；
     提问手法 (Prompt Pattern Catalog, arxiv 2302.11382)；提问缺陷类目 (arxiv 2504.20196)；
     依赖姿态 over/under-reliance + 纠错恢复 (arxiv 2603.18895)；选择性采纳 (arxiv 2506.10051)。 -->


通用规则：
- **全程大白话，禁止学术黑话**——不要出现 acceleration mode / delegation / Dependency Ratio / interactive steering 这类词。用"加速/探索""替我写/陪我写"这类中文，或直接描述行为。这些框架只是 schema 的脚手架，不是正文词汇。
- **每条实例必须直接引用 `user_prompts` 里的真实原话**（带引号的 verbatim 片段，可截断但不得改写措辞），让读者看到用户当时到底怎么说的，而不是转述。
  - ✅ `约束前置——「fastapi-base里的内容不做改动」「这两个我不需要了，你写在README.md 中吧」`
  - ❌ `你要求别动 fastapi-base、把功能写进 README`（转述，无原话）
  - **只能引用 `user_prompts` 里真实出现的句子**；不要把 CLAUDE.md 规则、AI 自己的话、或推测当成用户原话（强制引用正是为了挡住这种张冠李戴）。
- 每条子项给多个这样的带原话实例，不是一句概括。
- 全部绑 transcript 证据；子项无证据时写空句式（见 Hallucination Guard），不编。

四条子项：

- **协作方式**：这次偏"你定方向、AI 执行 + 紧驾驭"，还是"整包委派给 agent 自己跑"？以加速（知道要干嘛、让 AI 更快到达）为主还是探索（不确定、用 AI 列选项摸路）为主，或两者在不同阶段交替。依据：`user_prompts` 语气（指令式 vs 提问式）+ 委派粒度（大段交给 agent vs 多次小步引导）+ `compact_events` 的回合密度。

- **怎么提问**：用下面两把标尺分析（**标尺只用于判断，这些名词不许进正文；正文翻成大白话 + 引用户原话佐证**）：
  - 提问手法（识别用户用了哪几手 → 引原话）：①给上下文/指明范围 ②写死约束与反例（"不要…""只要…不要…"）③限定产出形态（要表格/要 diff/要先出方案）④先要 AI 给方案或讲权衡再拍板，而非直接下令 ⑤要求验证/核查、不轻信 ⑥赋角色或给标准。
  - 提问缺陷（识别哪轮漏了什么 → 导致什么）：漏目标 / 漏约束边界 / 漏上下文（哪个文件、在哪） / 漏示例或期望输出 / 漏验收标准。指出因哪类缺失导致 AI 跑偏、返工或被追加澄清（依据 `compact_events` 里需求漂移、AI 先做后被否的回合）。

- **怎么驾驭**：用下面三组信号判断（**输出大白话，不写信号名**）：
  - 依赖姿态：盲接受/不验证就用（过度依赖）↔ 该交给 AI 的硬自己扛、不放手（依赖不足）↔ 校准得当（该放手放手、该验证验证）。
  - 纠错恢复：AI 出错或越界时，**多快被抓到、怎么纠、有没有防止扩散**——抓得早、止损快是强信号。
  - 选择性：整块照单全收 ↔ 细粒度挑着用、只采纳对的部分。
  具体动作：纠正/否决/砍范围/拦截风险动作；引原话佐证（不对/重来/换一种/算了/不要/回滚等）+ 回退命令（git restore/reset）+ 几轮收敛。

- **哪些做得好 / 可复用**：按下方标尺，点出本 session 里**最强的几个人类动作 + 为什么有用**（必须绑具体动作和它带来的效果，如"避免了一轮返工""及时拦住了越界"，**不许空夸**如"提问很清晰"）。可附 1 条【可更好】指出哪一步本可做得更好。
  评判标尺（"人比 AI 更该主导"的动作）：① 给明确约束/边界/示例 → 减少返工；② 决策前先让 AI 调研/给方案再拍板 → 不盲接受；③ 及时发现并纠正 AI 错误/越界 → 错误恢复快；④ 主动砍范围、否决过度设计 → 防止 AI 跑偏膨胀；⑤ 要求验证、不轻信 AI 自述；⑥ 选择性采纳而非整块照单全收。
  每条形如 `【好】<具体动作>——<为什么有用/带来的效果>`。

**沉淀**
- `下次怎么做`：a concrete action to repeat or change next time the same task appears.
- `被推翻的想法`：a belief that was overturned by today's evidence. Must reference a reversal point in the transcript.
- If neither applies, write `今天没什么值得记的` rather than padding.

## Daily Report

Use this structure exactly:

```markdown
时间范围：<start> → <end>（timezone）
Audience：<self|manager|mixed>

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

## Hallucination Guard

Only write claims supported by `report_context.json`.

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
- `这次基本一遍过，没怎么纠偏`
- `这次协作方式不明显`
- `这次提问没有明显模式`

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
