# claude-daily

一个 Claude Code skill，把本地会话记录（`~/.claude/projects/**/*.jsonl`）整理成一份可追溯的每日工作报告。

整个 skill 分成两段：先用 Python 做确定性处理，再让 LLM 做语义合成。

```text
原始 JSONL 记录
  → Python 解析（scripts/build_report_context.py）
  → 压缩后的证据 JSON（工具调用、文件、命令、用户提问、助手段落）
  → LLM Session Card（8 个字段）
  → LLM Daily Report（9 个部分）
  → 独立内容审查（subagent / main-thread fallback）
  → emit JSON payload + upload
```

Python 负责解析、降噪、提取证据；LLM 负责命名片段、做差距分析、把当天的经验沉淀成可复用的规则。emit 只做 payload 结构校验；日报内容是否符合受众、证据和字段规则，由独立内容审查 gate 检查。

## 使用指南（在 Claude Code 里调用）

下面的「快速开始」是直接跑 Python 脚本、调试用的。日常使用更简单：在 Claude Code 里用自然语言触发本 skill，它会把 6 步管线（prepare → 读取上下文 → 生成两份受众报告 → 元数据 + 内容审查 → emit → upload）一次跑完。

### 一、输入是什么

这个 skill 不需要你手动准备数据，输入只有两样，且都已固定：

| 输入 | 位置 | 说明 |
|---|---|---|
| 配置文件 | `~/.compound-daily/config.json` | 一次性配好即可；缺失时 prepare 会报错提示。可参考 `config.example.json` |
| Claude Code 历史记录 | `~/.claude/projects/` | skill 自动扫描，就是你平时跑 Claude Code 留下的 transcript |

配置文件长这样：

```json
{
  "member_id": "your.username",                          // 你是谁，决定上报归属
  "endpoint_base": "https://your-compound-daily-host",   // 上报到哪（改成你的服务地址）
  "outbox_dir": "~/.local/state/compound-daily/outbox",  // 中间产物落盘处
  "projects_root": "~/.claude/projects"                  // 从哪读历史
}
```

所以你真正要给的"输入"其实只有一个：**日期**（不给就是今天）。token 用量由 `ccusage` 自动按本地自然日切，不用你管。

### 二、怎么触发（直接用自然语言说）

不用敲命令，用自然语言说就行：

| 你想干嘛 | 说这句 | 行为 |
|---|---|---|
| 跑今天 + 上报（默认） | `跑 claude-daily` / `生成今天的日报` | 6 步全跑，含上传 |
| 只看不发（建议先用这个） | `跑 claude-daily dry-run` / `只看不发` | 跑 1–5 步，生成报告但不上传 |
| 跑某一天 | `跑 2026-05-28 的` / `--date 2026-05-28` | 换日期 |
| 重发 | `重新发一遍` / `force` | 无视已上报记录强制重传 |

> ⚠️ 一个坑：日期按 session **起始时间**算。昨天开始、跨到今天的 session，跑"今天"时会被跳过并 WARN 提示——要补就单独跑那天的日期。

### 三、跑完产出什么

中间产物落在 `~/.local/state/compound-daily/outbox/<日期>/<member_id>/`：

- `_output.personal.md` —— 给自己看的详细复盘（含弯路、被推翻的想法、完整 Session 附录，约 1500–2500 字）
- `_output.boss.md` —— 给老板看的业务版（砍掉技术细节和自我否定，约 400–800 字）
- 最终 emit 出 11 个 payload（9 张 session 卡 + 2 份日报），upload 推到服务端

最简单的用法就是直接说 `跑 claude-daily`；想先确认内容再决定发不发，就说 `跑 claude-daily，先看看不发`。

## 为什么是这种结构

这套 schema 是把每日报告当成"认知工具"来设计的，而不是一张待填写的表格。三个核心承诺：

- **意图 vs 现实是一等公民。** 每个 Session Card 和整份 Daily Report 都要明确给出"原本想做什么"和"实际发生了什么"之间的差距。
- **单环学习和双环学习分开。** 动作层的改进（`下次怎么做`）和信念层的改变（`被推翻的想法`）各占一栏，不混在一起。
- **情景记忆和语义沉淀同时保留。** `今日总览` 是时间序的叙事快照，便于快速回忆；`今天学到的` 是脱离当天具体情境后仍然成立的规则。前者给后者喂料，不要合并。

## 目录结构

```text
.
├── SKILL.md                          # Skill 主规格，是事实源
├── references/
│   ├── report-prompts.md             # LLM 输出契约
│   └── content-review-checklist.md   # emit 前内容审查清单
└── scripts/
    ├── build_report_context.py       # JSONL → 压缩 JSON 的解析器
    └── test_build_report_context.py  # 单元测试
```

## 快速开始

按本地日期生成上下文 JSON：

```bash
python3 scripts/build_report_context.py --date 2026-05-07 --pretty --out /tmp/claude-report-context.json
```

按 session id 前缀挑选会话：

```bash
python3 scripts/build_report_context.py --session f66e2252 --session 55e3ff9b --pretty --out /tmp/claude-report-context.json
```

之后把生成的 JSON 喂给 Claude（或在 Claude Code 里直接调用本 skill），按照 `references/report-prompts.md` 的契约输出两段内容：

```text
Session Cards
Daily Report
```

不要用自由发挥的总结、纯表格或纯时间线替代 Daily Report；缺少 `# Daily Report` 段的报告视为不完整。

## 命令行参数

```text
--date YYYY-MM-DD          按本地日期过滤
--session PREFIX           session id 或前缀，可重复
--projects-root PATH       默认 ~/.claude/projects
--include-subagents        把 subagent 记录也纳入证据
--timezone-offset +08:00   --date 的时区偏移
--limit N                  过滤后限制会话数量
--out PATH                 输出 JSON 路径
--pretty                   美化 JSON 输出
```

完整参数以 `python3 scripts/build_report_context.py --help` 为准。

## Schema

**Session Card** — 8 个必填字段，顺序固定：

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

**Daily Report** — 9 个必填部分，顺序固定：

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

每个字段的硬约束、证据规则、以及三种受众模式（`self` / `manager` / `mixed`）写在 `SKILL.md` 里。LLM 必须逐行对齐的输出契约写在 `references/report-prompts.md` 里。

emit 前必须先跑 `references/content-review-checklist.md`：优先启动独立 subagent 自检；如果当前运行环境没有 subagent，就在 main thread 按同一清单审查并写 `_review.content.md`。只有 `Result: PASS` 才能继续 emit / upload。

## 几条关键证据规则

- 顶层会话作为报告主线，subagent 记录默认仅作辅助证据。
- 字段缺乏证据时，写明确的"未发现明确证据"句式，不要编造内容。
- 不能仅凭助手文本就声称测试通过、代码已部署、bug 已修复，必须有文件、命令或工具调用作为证据。
- "决策"必须有可见的备选项；没有备选项的选择只是动作，归到 `主要过程`。
- "走过的弯路"必须能从 `git restore` / `git reset` / 反向 Edit / 用户的"算了/回滚"等信号中找到证据，否则就写空句式。

## 运行测试

```bash
cd scripts
python3 -m unittest test_build_report_context.py
```

## 环境要求

- Python 3.7 及以上
- 本地存在 `~/.claude/projects/` 下的 Claude Code 会话记录
