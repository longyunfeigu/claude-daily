# claude-daily

把本地 Claude Code 会话记录（`~/.claude/projects/**/*.jsonl`）整理成一份可追溯的每日工作报告的 Claude Code skill。先用 Python 做确定性解析、降噪、抽取证据，再让 LLM 做语义合成（Session Card + Daily Report），最后按 PRD 上报到 Compound Daily ingestion 服务。

## 输出长这样（脱敏示例）

以下三张图是 skill 产出、在配套 Web 端里渲染的效果；内容已脱敏，仅用于展示格式与信息结构。

**个人版报告** —— 给自己看的详细复盘：今日总览、主题分组、今天学到的、关键决策、被推翻的想法、走过的弯路、验证结果、风险与阻塞、Session 附录。

![个人版报告](assets/personal-report.png)

**老板版报告** —— 给老板看的业务摘要：今日总览、主题分组、关键决策、验证结果、风险与阻塞。

![老板版报告](assets/boss-report.png)

**Session Card** —— 单个会话的复盘卡片：原本想做什么 / 主要过程 / 产出 / 关键决策 / 差距 / 走过的弯路 / 证据 / 人机协作 / 沉淀。personal 卡片会在 `人机协作` 里评价 AI 使用：协作方式、怎么提问、怎么驾驭、哪些做得好、哪些用得不好 / 风险信号，以及证据绑定的维度评分；manager 卡片会省略这部分自我复盘。

AI 使用评分不算总分，只按 `目标与上下文`、`约束与验收`、`委派是否合适`、`验证与审查`、`纠错与止损`、`人类关键判断`、`沉淀复用` 给 `0/3`、`1/3`、`2/3`、`3/3` 或 `N/A`。每个分数都必须绑定 transcript 证据；证据不足或本 session 不适用时写 `N/A`，不能凭印象打分。

![Session Card](assets/session-card.png)

## 让 AI 工具替你部署

懒得照着下面手动装，可以把仓库地址丢给 Claude Code / Codex 这类 AI 编码工具，让它读 README 自己装。开个新会话，把下面这段贴进去：

```text
帮我部署这个 Claude Code skill：https://github.com/longyunfeigu/claude-daily
请读它的 README，按「安装」一节做：
1. 添加 marketplace 并安装 claude-daily 插件；
2. 把技能目录里的 config.example.json 复制成 ~/.compound-daily/config.json，填好 member_id（如 your.name）和 endpoint_base；
3. 检查 Python 3.7+，可选装 ccusage（npm i -g ccusage）。
装完跑一次 dry-run（只看不发）验证。
```

> `/plugin marketplace add`、`/plugin install` 是 Claude Code 的交互命令，要你在会话里确认执行；`~/.compound-daily/config.json` 和依赖检查 AI 能直接帮你跑完。下面「安装」一节是这套步骤的完整说明，手动装也照它来。

## 安装

### 1. 添加 marketplace 并安装插件

在 Claude Code 里：

```text
/plugin marketplace add git@github.com:longyunfeigu/claude-daily.git
/plugin install claude-daily
```

本地调试也可以直接添加本地路径：

```text
/plugin marketplace add /path/to/claude-daily   # 换成你 clone 仓库的本地路径
/plugin install claude-daily
```

装完后在任意项目里都能触发，不用再往每个项目复制。更新用 `/plugin marketplace update`。

### 2. 一次性配置

skill 首次运行需要 `~/.compound-daily/config.json`。把技能目录里的 `config.example.json` 复制过去，改两个字段即可（其余字段有默认值）：

```bash
mkdir -p ~/.compound-daily
cp skills/claude-daily/config.example.json ~/.compound-daily/config.json
# 然后编辑 ~/.compound-daily/config.json
```

要改的字段：

| 字段 | 说明 |
|---|---|
| `member_id` | 你的标识，小写、需含分隔符（如 `wanhua.gu`） |
| `endpoint_base` | 上报服务地址 |

> 缺配置时 skill 会报错并提示去哪复制 example —— 照提示做一次即可，之后不用再管。

### 3. 依赖

- **Python 3.7+**（必需）
- **[ccusage](https://github.com/ryoppippi/ccusage)**（npm CLI，**可选**）：用于按本地自然日统计每个会话的 token。

```bash
npm i -g ccusage
```

> ccusage 缺失（未安装 / 调用失败 / 输出异常）时，`prepare` 只会打印一行 `WARN`、把 token 计 0，**报告照常生成**。token 仅用于服务端 Token 页，不进报告正文，所以缺了不影响日报内容。

## 使用

在 Claude Code 里用自然语言触发，不用敲命令：

| 想干嘛 | 说这句 | 行为 |
|---|---|---|
| 跑今天 + 上报（默认） | `跑 claude-daily` / `生成今天的日报` | 6 步全跑，含上传 |
| 只看不发（建议先用） | `跑 claude-daily dry-run` / `只看不发` | 跑 1–5 步，生成报告但不上传 |
| 跑某一天 | `跑 2026-05-28 的` / `--date 2026-05-28` | 换日期 |
| 重发 | `重新发一遍` / `force` | 无视已上报记录强制重传 |

> 日期按 session **起始时间**算；跨天的 session 跑「今天」时会被跳过并 WARN 提示，要补就单独跑那天。

产出落在 `~/.local/state/compound-daily/outbox/<日期>/<member_id>/`：给自己看的详细复盘 `_output.personal.md`、给老板看的业务版 `_output.boss.md`，以及 emit 出的 PRD payload。

## 定时执行（cron）

不想每天手动开 session，可以让 cron 在第二天早上自动生成并上报前一天的日报——「第二天跑前一天」正好避开「跨天 session 被跳过」的坑。

> ⚠️ 关键：报告生成依赖 LLM（不是纯脚本），所以 cron 要用**无头模式调起 Claude Code**（`claude -p`）来触发本 skill，**不能**直接跑 `prepare.py`。

**前置条件**

- 已 `/plugin install claude-daily`，且 `~/.compound-daily/config.json` 配好。
- cron 以**你本人这个用户**运行（这样 `~/.claude` 的登录凭证可用；若用 API key，在脚本里 `export ANTHROPIC_API_KEY=...`）。
- `claude`（以及可选的 `node`/`npx` 供 ccusage 用）在脚本的 `PATH` 里。

**推荐：用一个小包装脚本**（省去 cron 的 PATH 精简和 `%` 转义问题）。存成 `~/run-claude-daily.sh`：

```bash
#!/usr/bin/env bash
# 生成并上报前一天的 claude-daily 日报
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"   # 改成你的 claude/node 所在目录（用 which claude / which node 查）
YESTERDAY="$(date -d 'yesterday' +%F)"                        # Linux GNU date；macOS 用：date -v-1d +%F
claude -p "跑 claude-daily --date $YESTERDAY（正式上报，不要 dry-run）" \
  --dangerously-skip-permissions \
  >> "$HOME/.compound-daily/cron.log" 2>&1
```

```bash
chmod +x ~/run-claude-daily.sh
```

再 `crontab -e` 加一行（每天 09:30 跑前一天）：

```cron
30 9 * * * /home/<you>/run-claude-daily.sh
```

**几个要点**

- **权限**：cron 无人值守、弹不了权限确认，所以加了 `--dangerously-skip-permissions`——它跳过**所有**权限检查，仅在你信任这个 skill、跑在自己机器上时用。想收窄就换成 `--allowedTools "Bash Read Write Edit Task"`（仍偏宽，因为 Bash 在内）。
- **日志**：输出都进 `~/.compound-daily/cron.log`，失败去那看。
- **只生成不上报**：把 prompt 换成 `跑 claude-daily dry-run --date $YESTERDAY` 即可。
- **nvm 用户注意 ccusage**：nvm 装的 `node`/`npx` 不在上面默认 `PATH` 里，要把 `~/.config/nvm/versions/node/<版本>/bin` 也加进 `export PATH=`，否则 ccusage 取不到 token（只 WARN、计 0，报告正文照常）。
- **直接写 crontab（不用包装脚本）也行**，但要在 crontab 顶部设 `PATH=`，且 `date` 的 `%` 必须转义成 `\%`。

## 更多

权威流程见 [`skills/claude-daily/SKILL.md`](../fastapi-base/.agents/skills/claude-daily/SKILL.md)；
Session Card / Daily Report 输出契约、证据规则、受众模式见
[`skills/claude-daily/references/report-prompts.md`](../fastapi-base/.agents/skills/claude-daily/references/report-prompts.md)。
