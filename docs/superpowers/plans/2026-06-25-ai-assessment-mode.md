# AI 使用评估 · ai-assessment mode Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 claude-daily 新增 `ai-assessment` mode：消费 Plan 1 的 `_assessment_context.json` + 现有 `_context.json`，per-session map（subagent fan-out）→ 个人 reduce → 产出 `_ai_assessment.personal.md` / `_ai_assessment.manager.md` / `_ai_assessment.meta.json`，过评估 review gate。**单人 MVP，不接 emit/upload/团队聚合（阶段四）**。

**Architecture:** 评估逻辑全部在 prompt（LLM 驱动），不写打分代码。三类新增产物：①评估契约 `references/ai-assessment-prompts.md` ②评估 review 清单 `references/ai-assessment-review-checklist.md` ③`SKILL.md` 新增 mode 编排。复用 Plan 1 投影层 + 现有 prepare 链路。

**Tech Stack:** Markdown 契约 + SKILL.md 编排；运行期靠 Claude Code 自身的 subagent fan-out 与 review-gate 模式（与现有日报第 4 步同款）。

## Global Constraints

- **不写打分代码**——评分、缺陷根因、reduce 全部由 LLM 按契约执行。代码侧只有 Plan 1 的投影层 + 编排。
- **不接 emit / upload / 团队聚合**——这些是 PRD 阶段四（跨机）。本 mode 只产出 3 个**本机文件**，到此为止。
- **不改日报路径**——`ai-assessment` 是独立 mode，日报 6 步流水线零改动（PRD §12.3）。
- **复用既有契约骨架**：8 维度名 + 自包含评分块骨架直接沿用 `references/report-prompts.md`（DRY，不重新发明）。
- **维度固定为 8 个**（PRD §7 / report-prompts.md 现有）：`目标与上下文`、`约束与验收`、`委派是否合适`、`验证与审查`、`纠错与止损`、`人类关键判断`、`沉淀复用`、`评分置信度`。
- **验证方式**：本 Plan 无 unit test；每个产物的"验证"= 在真实多-session 日上跑 mode + 对照 `ai-assessment-review-checklist.md` 出 PASS/FAIL（与现有 content-review-gate 同机制）。
- **隐私**：manager 产物守 PRD §11 最小披露（不放完整 prompt / 代码 / 敏感路径，Layer 0.5 只摘一句）；personal 产物可深引（本人看）。

---

### Task 1: 评估契约 `references/ai-assessment-prompts.md`

**Files:**
- Create: `skills/claude-daily/references/ai-assessment-prompts.md`

**该文件必须包含以下 6 节（内容要求逐节写明，不留占位）：**

- [ ] **Step 1: 写 §A 输入契约**

> 输入只读两份：`_assessment_context.json`（Plan 1 投影层产物：每 session 的 `commands(含 outcome)`、`edit_events`、`claims(含 prev_verify_outcome)`、`loops`、`danger_ops`、`event_backbone`、`user_prompts`）+ `_context.json`（补 `compact_events` 用于还原叙事）。**AI 回复正文一律不读**（PRD §18.2）。

- [ ] **Step 2: 写 §B 单 session MAP 输出规范**

每个 top-level session 产一份**结构化证据记录**，含：
1. **8 维度评分**：每维度 `0/3|1/3|2/3|3/3|N/A` + 自包含证据链块（**直接套用 `report-prompts.md` 的「输出骨架」**：维度名→分数→紧跟直属证据链，禁止分数堆顶材料堆底）。
2. **Layer 0.5 缺陷根因追踪**：对每个**会上露头的缺陷**（判据：`claims[].prev_verify_outcome=="fail"`，或 `loops` 非空，或 `danger_ops` 非空），按 PRD §18.5 六段写：缺陷 / 怎么暴露[@骨架锚点] / 沟通根因(缺了目标·边界·验证·止损中的哪项) / 行为归因(非人身) / 能力信号(缺口+恢复都写) / 下次护栏。无缺陷写 `本 session 未发现会上露头的缺陷`。
3. **强制极值**：每维度必须挂**最强或最弱**那条证据，禁止写"总体平衡"式总结（PRD §18.8）。
4. **置信度**：本 session 证据覆盖度 `低/中/高` + 一句依据。

- [ ] **Step 3: 写 §C 个人 REDUCE 规范（PRD §9.2/§9.3/§18.7）**

跨该人本批所有 session 聚合成人级画像，**铁律**：
- **不做算术平均**；关键维度（主导/验证/纠错/风险）**取下界 + 标波动**。
- **红线压顶**（§9.3）：任一 session 命中红线（高危改动无验证、架构甩 AI、AI 多次跑偏无止损、生成内容进项目无 diff/test/review）→ 总体等级最高 L1，除非后续 session 明确纠正。
- **置信度随聚合传播**：样本少 / prompts 多空 → 标"低置信，仅供人工复核"。

- [ ] **Step 4: 写 §D 三输出文件契约**

- `_ai_assessment.personal.md`（个人改进版，PRD §10.2 / 形态 B）：做得好的 / 容易埋坑的 / 下次可以这样问(照抄) / 下次必须验证什么 / 可复用 checklist；**深引 Layer 0.5**（本人看，无隐私问题），多引 `user_prompts` 原话。
- `_ai_assessment.manager.md`（管理版，PRD §10.1 / 形态 A）：一句话判断 / 主要证据 / 能力维度表 / 项目风险 / 培训建议 / 不应过度解读；**Layer 0.5 只摘一句 + "详见个人版"指针**，守 §11 最小披露，省略 `人机协作` 式自评细节。
- `_ai_assessment.meta.json`：结构化中间产物——每 session 的 8 维分+证据锚点+命中红线+置信度，加人级 rollup。供未来团队 reduce（阶段四）与 §11.3 复核用。给出明确 JSON 形状示例。

- [ ] **Step 5: 写 §E 行为锚点标尺（治 central tendency，PRD §18.8）**

为 4 个关键维度（主导/验证/纠错/风险）各写 `3/3` vs `1/3` 的**具体行为锚点**（"长这样才算 3，长那样只能 1"），用本仓库已验证的真实例子改写（如：验证 3/3 = "完成 claim 前紧挨真实 test/build 且如实报败"；验证 1/3 = "AI 说完成无 command 证据"）。

- [ ] **Step 6: 提交**

```bash
git add skills/claude-daily/references/ai-assessment-prompts.md
git commit -m "feat(assessment): 评估契约 ai-assessment-prompts.md（map/reduce/Layer0.5/锚点）"
```

---

### Task 2: 评估 review 清单 `references/ai-assessment-review-checklist.md`

**Files:**
- Create: `skills/claude-daily/references/ai-assessment-review-checklist.md`

- [ ] **Step 1: 写清单**

把 PRD §18.9 的 7 个坑写成 PASS/FAIL 检查项（reviewer 子代理读三产物 + `_assessment_context.json` 逐条核）：
1. 是否拿 AI 自述当事实（验证维度高分必须有 command 证据，否则 FAIL）。
2. 证据不足是否硬打分（prompts 空/样本少必须降级低置信）。
3. 是否维度求平均、忽略红线。
4. 是否只用 prompt 打分、漏了行为/命令证据。
5. 是否把任务成败当能力。
6. 是否人身化判断（"不认真"等 → FAIL）。
7. manager 产物是否泄漏完整 prompt/敏感路径，或分数与证据分离。
末尾要求 reviewer 写 `Result: PASS|FAIL` + 命中项。

- [ ] **Step 2: 提交**

```bash
git add skills/claude-daily/references/ai-assessment-review-checklist.md
git commit -m "feat(assessment): 评估 review 清单（7 大坑 PASS/FAIL）"
```

---

### Task 3: `SKILL.md` 新增 `ai-assessment` mode 编排

**Files:**
- Modify: `skills/claude-daily/SKILL.md`（新增一节，不动现有 6-Step Pipeline）

- [ ] **Step 1: 加 Trigger**

在 Trigger 节补：`跑 claude-daily ai-assessment` / `生成 AI 使用能力评估` / `生成管理者版 AI 使用评估` → 走下面的 ai-assessment 流程（默认按最近 N 天 / 指定 `--date`，单人）。

- [ ] **Step 2: 写 ai-assessment 流程（独立小节）**

步骤：
1. **prepare**：`python3 scripts/prepare.py --date <date>`（复用，产 `_context.json`）。
2. **projection**：`python3 scripts/assessment_projection.py --date <date>`（Plan 1，产 `_assessment_context.json`）。
3. **per-session MAP（subagent fan-out）**：对每个 top-level session 起一个 subagent，只喂该 session 的投影记录 + `compact_events`，按 `ai-assessment-prompts.md` §B 产结构化证据记录（控上下文：每 session 独占一个窗口，主线程只收结构化结果）。
4. **个人 REDUCE**：主线程按 §C 聚合成人级画像。
5. **写产物**：按 §D 写 `_ai_assessment.personal.md` / `_ai_assessment.manager.md` / `_ai_assessment.meta.json`。
6. **review gate**：起 fresh subagent 按 `ai-assessment-review-checklist.md` 读三产物 + `_assessment_context.json` 核，写 `_review.assessment.md`（PASS/FAIL）；FAIL 则只重做被点名产物，二次仍 FAIL 停下报告。

- [ ] **Step 3: 提交**

```bash
git add skills/claude-daily/SKILL.md
git commit -m "feat(assessment): SKILL.md 新增 ai-assessment mode 编排"
```

---

### Task 4: 真实多-session 验证（本 Plan 的"测试"）

**Files:** 无（产出在 outbox，不入库）

- [ ] **Step 1: 选一个真实有数据的多-session 日跑全流程**

```bash
cd skills/claude-daily/scripts
python3 prepare.py --date <某有数据的日子>
python3 assessment_projection.py --date <同一天>
```
然后在主会话按 SKILL.md 的 ai-assessment 流程跑 map→reduce→写三产物→review gate。

- [ ] **Step 2: 对照验收（PRD §14.1）**

人工核：(a) 关键判断都能在 `_assessment_context.json` 找到证据；(b) 没把 AI 自述当事实；(c) 没把任务成败当能力；(d) 证据不足处降级而非硬评；(e) manager 产物无隐私泄漏。`_review.assessment.md` = PASS。

- [ ] **Step 3: 按需迭代契约**

若产物薄/糊/越界，改 `ai-assessment-prompts.md` 对应节，重跑 Step 1-2，直到 PASS + 信息密度达到「形态 A/B」水平（我们 brainstorm 时认可的密度）。

## Self-Review

**Spec coverage（对照 PRD §13 MVP 必含项）：** 8 维度评分(Task1 §B)、L0-L4 等级(§C)、证据链(§B 骨架)、置信度(§B/§C)、管理者报告(§D manager)、个人改进(§D personal)、项目风险(§D manager)、培训建议(§D)、证据不足保护(§C + Task2 #2) —— 全部有落点。Layer 0.5 缺陷根因追踪(§B #2)、两端对照靠锚点(§E)。
**Placeholder scan：** 各 Task 的 Step 都写明了具体要产的内容；契约正文在实现时按节填，无 TODO。
**范围一致性：** 全程不接 emit/upload/团队（与 Global Constraints 一致）；维度名与 report-prompts.md 一致。

## 不在本 Plan 范围

- emit/upload 接入、`_ai_assessment.team.md`、跨机/团队 reduce —— PRD 阶段四。
- `_ai_assessment.meta.json` 的 JSON Schema 强校验 —— 视阶段四是否上报再加（MVP 内它是本机中间产物，参照 `_context.json` 同样不带 schema）。
