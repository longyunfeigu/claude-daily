# AI 使用评估 Review 清单

ai-assessment mode 的产物 review gate。**fresh subagent** 执行：从磁盘读
`_ai_assessment.personal.md`、`_ai_assessment.manager.md`、`_ai_assessment.meta.json`
与 `_assessment_context.json`，逐条核对，**不得**把生成线程的结论当真相来源。

输出写到 `_review.assessment.md`，首行 `Result: PASS` 或 `Result: FAIL`；
无 subagent 时在主线程跑并标 `Mode: main-thread`，不得跳过。任一项 FAIL 即整体 FAIL，
并指明命中项 + 对应产物（personal / manager / meta）。

## 检查项（对应 PRD §18.9 七大坑）

1. **拿 AI 自述当事实** —— 任何把「验证意识」判为 `强` 或 `到位` 的，必须在 `_assessment_context.json` 的 `commands[].outcome` 或 `claims[].prev_verify_outcome` 有对应证据。AI 说「完成 / 通过」但无 verify 证据却判「强/到位」→ FAIL。

2. **证据不足硬判** —— `user_prompts` 为空 / 只有闲聊 / 全是 explore 命令（outcome=null）时，对应维度必须是 `证据不足`，而不是给一个 `到位`。出现「无证据的中庸判断」→ FAIL。

3. **数字分 / 等级混入** —— 三产物任一出现 `0/3`、`2/3` 这类数字分，或 `L0-L4` 能力等级 → FAIL（本评估已去数字、去等级，只用定性 + 旗标 + 主题）。

4. **红线未驱动旗标** —— 若某 session 命中红线（高危改动无验证/确认、关键取舍交 AI、AI 多次跑偏无止损、生成内容进项目无 diff/test/review），而 `person.flags` 缺 `红线命中` → FAIL。反之无红线却标了 → FAIL。

5. **只用 prompt 判关键维度** —— 验证 / 纠错 / 风险维度的判断必须引用行为证据（`commands` / `loops` / `danger_ops` / `edit_events`），不能只凭 `user_prompts` 措辞。只读 prompt 就判关键维度 → FAIL。

6. **把任务成败当能力** —— 出现「任务失败 → 判弱」或「任务成功 → 判强」的直接挂钩、未看是否设边界/验证/抓偏/留人工判断 → FAIL（PRD §6.4）。

7. **人身化判断** —— 任一产物出现「这个人不认真 / 能力差 / 不靠谱」等人格化措辞 → FAIL。只允许行为描述。

8. **隐私 / 证据糊一团** ——
   - `_ai_assessment.manager.md` 出现完整 prompt / 大段代码 / 敏感文件路径 / token 数 → FAIL（守 §11 最小披露）。
   - 评分块/判断与证据分离（判断堆一处、材料堆另一处，无法逐条复核）→ FAIL。

## 额外结构核对

- 三产物齐全；`personal` 叙事优先（每 session 有执行叙事 §B.1，不是只有结论 bullet）；`manager` 含旗标 + 定性维度表 + 风险 + 培训；`meta.json` 可 `json.load`，含 `dims`(定性) + `flags` + `risk_themes`，**无 `level`、无数字 `scores`**。
- 叙事深度：实质 session（多 prompt + 工具证据）的执行叙事必须覆盖主要回合，不能压成三五条干 bullet（否则退化成总结 → FAIL）。
- Layer 0.5：凡 `_assessment_context.json` 中有 `prev_verify_outcome=="fail"` / `loops` 非空 / `danger_ops` 非空的 session，对应产物必须有一段缺陷根因追踪；否则 FAIL。
- `manager` 的 Layer 0.5 只摘一句 + 指针（不深引）。
