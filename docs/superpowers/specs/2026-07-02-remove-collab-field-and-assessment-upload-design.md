# 设计：删除「人机协作」字段 + ai-assessment 上报打通（两仓联动）

日期：2026-07-02　状态：已确认（用户全权委托执行）

## 背景与目标

1. 日报 Session Card 的「人机协作」字段（6 子项 × 两面 × 引原话 × 8 维评分骨架）
   过重，且与 ai-assessment 模式职责重叠。决定**整字段删除**：日报只做工作内容
   复盘，AI 使用分析全部归 ai-assessment 模式。
2. ai-assessment 模式产物目前只落本机，需要与日报一样**上报到 fastapi-base**
   （Compound Daily 服务端）并在前端展示，manager 版报告中的 `@N` 锚点必须
   可点击下钻到原始 event_backbone（契约 §D.2 全透明审计）。
3. 服务端本地运行，数据库用 sqlite3；member_id 用 `wanhua.gu`。

## A. claude-daily：删「人机协作」

personal 卡片从 9 字段 → 8 字段，与 manager 卡片一致。

| 文件 | 改动 |
|---|---|
| `references/report-prompts.md` | 删模板中的字段块、六子项+评分整节、Audience 差异描述、Hallucination Guard 中 4 条相关空句式、顶部脚手架注释里的协作研究引用、"9 fields" → 8 |
| `SKILL.md` | Report Contract 一节删 3 条人机协作规则 |
| `scripts/build_report_context.py` | `session_card_schema` 删 `"人机协作"`；更新相关注释 |
| `references/content-review-checklist.md` | 删对应检查项 |

ai-assessment 模式的 references 不动。回归：`scripts/` 下 pytest 全绿。

## B. 评估上报契约（新增）

### Payload（POST `/api/v1/ingest/ai-assessments`）

```json
{
  "member_id": "wanhua.gu",
  "date_range": "2026-07-01",
  "submitted_at": "<ISO8601>",
  "manager_md": "<_ai_assessment.manager.md 全文>",
  "personal_md": "<_ai_assessment.personal.md 全文>",
  "meta": { "...": "_ai_assessment.meta.json 原样" },
  "backbones": [
    {"session_short": "a8b416f0", "session_id": "<uuid>", "project": "...",
     "events": [{"i": 1, "type": "user", "text": "..."}]}
  ]
}
```

- `backbones` 取自 `_assessment_context.json` 的 `event_backbone`（锚点弹窗数据源，
  不上传则前端锚点是死的）。
- Upsert 键 `(member_id, date_range)`，`submitted_at` 新者胜（与 daily_report 一致）。

### skill 侧

- 新增 `schemas/ai_assessment.schema.json` + `scripts/upload_assessment.py`
  （读三产物 + `_assessment_context.json`，组 payload、schema 校验、POST）。
- `config.json` 的 `endpoint_paths` 新增 `ai_assessment`，缺省回退
  `/api/v1/ingest/ai-assessments`（旧配置不需迁移）。
- `SKILL.md` 评估流程加 step 7：review PASS 后默认 upload，dry-run 词表同日报。

### fastapi-base 后端

按现有 compound_daily DDD 结构镜像：

- 模型 `ai_assessment` 表：`member_id`、`date_range`、`manager_md`、`personal_md`、
  `meta`(Text/JSON)、`backbones`(Text/JSON)、`submitted_at`、`ingested_at`、
  unique(member_id, date_range)。sqlite 兼容类型（String/Text/Integer）。
- routes：`POST /api/v1/ingest/ai-assessments`、`GET /api/v1/ai-assessments`
  （列表，member/date 过滤）、`GET /api/v1/ai-assessments/{id}`（含 backbones）。
- service/repository/domain entity 各一份，测试镜像 test_compound_daily_delete.py 风格。

### fastapi-base 前端

- 新路由「AI 评估」：列表页（member + date_range + 旗标 + 置信度）+ 详情页。
- 详情页渲染 `manager_md`；正文中 `@(\d+)` 解析为可点击 chip，点击弹窗展示该
  session backbone 中锚点附近事件（按报告分节声明的 session 归属匹配 backbones）。
- 已有的「AI 使用评分」解析代码（parseScoreBlock）成为死代码，本次不清理。

## C. 运行与验证

1. `backend/.env`：`DATABASE__URL=sqlite+aiosqlite:///./compound_daily.db`
   （aiosqlite 已在依赖；无 alembic versions，走 create_all 建表）。
2. `./scripts/dev.sh` 起 8000/5173。
3. `~/.compound-daily/config.json`：member_id=wanhua.gu、endpoint_base=http://localhost:8000。
4. 跑 2026-07-01：日报 6 步全流程（含 upload）+ ai-assessment 全流程（含新 upload）。
5. 前端验证：日报/卡片/评估页 + 锚点弹窗。

## 风险与边界

- 评估质量已知病灶（单日样本、投影正则窄、维度证据不均、无 golden 基线）
  **本次不修**——先跑通链路拿真实产出，再定优化顺序。
- 前端旧数据兼容无需考虑：sqlite 全新库。
