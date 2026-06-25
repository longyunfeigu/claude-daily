# AI 使用评估 Review 清单

ai-assessment mode 的产物 review gate。**fresh subagent** 执行：从磁盘读
`_ai_assessment.personal.md`、`_ai_assessment.manager.md`、`_ai_assessment.meta.json`
与 `_assessment_context.json`，逐条核对，**不得**把生成线程的结论当真相来源。

输出写到 `_review.assessment.md`，首行 `Result: PASS` 或 `Result: FAIL`；
若无 subagent，在主线程跑同一清单并标 `Mode: main-thread`，不得跳过。
任一项 FAIL 即整体 FAIL，并指明命中项 + 对应产物（personal / manager / meta）。

## 检查项（对应 PRD §18.9 七大坑）

1. **拿 AI 自述当事实** —— 任何「验证意识」高分（2/3 或 3/3）必须在 `_assessment_context.json` 的 `commands[].outcome` 或 `claims[].prev_verify_outcome` 有对应证据。AI 说「完成 / 通过」但无 verify 命令证据却给了高分 → FAIL。

2. **证据不足硬打分** —— `user_prompts` 为空 / 只有闲聊 / 样本极少时，对应维度必须是 `N/A（证据不足）` 或低置信，而不是给一个干净的 2/3。出现「无证据的中庸分」→ FAIL。

3. **维度求平均、忽略红线** —— 人级等级若由维度算术平均得出 → FAIL。关键维度（主导 / 验证 / 纠错 / 风险）必须取下界 + 标波动；任一 session 命中红线而总体等级 > L1 且无「后续纠正」说明 → FAIL。

4. **只用 prompt 打分** —— 验证 / 纠错 / 风险等维度的判断必须引用行为证据（`commands` / `loops` / `danger_ops` / `edit_events`），不能只凭 `user_prompts` 措辞。只读 prompt 就给关键维度定分 → FAIL。

5. **把任务成败当能力** —— 出现「任务失败 → 低分」或「任务成功 → 高分」的直接挂钩、而未看是否设边界 / 验证 / 抓偏 / 留人工判断 → FAIL（PRD §6.4）。

6. **人身化判断** —— 任一产物出现「这个人不认真 / 能力差 / 不靠谱」等人格化措辞 → FAIL。只允许行为描述（「未发现验证命令」「关键取舍由 AI 给出且未见确认」）。

7. **隐私泄漏 / 证据糊成一团** ——
   - `_ai_assessment.manager.md` 出现完整 prompt / 大段代码 / 敏感文件路径 / token 数 → FAIL（守 §11 最小披露）。
   - 任一产物里分数与证据分离（分数堆一处、材料堆另一处，无法逐条复核）→ FAIL。

## 额外结构核对

- 三产物齐全；`personal` 含 §10.2 五节、`manager` 含 §10.1 六节、`meta.json` 可解析且含 `sessions` + `person`。
- Layer 0.5 缺陷根因追踪：凡 `_assessment_context.json` 中有 `prev_verify_outcome=="fail"` / `loops` 非空 / `danger_ops` 非空的 session，对应产物必须有一段缺陷根因追踪；否则 FAIL。
- `manager` 的 Layer 0.5 只摘一句 + 指针（不深引）。
