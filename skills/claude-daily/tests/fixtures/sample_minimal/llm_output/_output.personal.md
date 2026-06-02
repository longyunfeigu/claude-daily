# Session Cards

## Session `f66e2252`：精读 CrewAI 结构化输出

原本想做什么：
用户希望搞清 CrewAI 结构化输出与 Agent 委托机制的关系，并把结论沉淀。

主要过程：
- 用户从结构化输出问题切入，要求联网验证 response_model 的副作用
- Claude 沿源码调研 internal_instructor 与 lite_agent

产出：
- 确认 response_model 在 non-streaming 路径会绕开真实工具调用

关键决策：
- 在 response_model 与 output_pydantic 之间为何选 output_pydantic：需要查真实数据时优先 output_pydantic

差距：
无显著偏离

走过的弯路：
今天没走值得记的弯路

证据：
Bash×8, Read×12, Edit×0；关键文件：CrewAI/internal_instructor.py

沉淀：
- 下次怎么做：再选结构化输出库时先跑一个最小工具调用 demo
- 被推翻的想法：今天没遇到被推翻的想法

# Daily Report

时间范围：2026-05-10 09:42 → 09:55（+08:00）
Audience：self

## 今日总览

上午精读 CrewAI 源码，搞清结构化输出与 Agent 委托机制的边界。

## 主题分组

### CrewAI 源码精读（上午）
- 厘清结构化输出与 Agent 委托机制边界（`f66e2252`）

## 今天学到的

下次再选结构化输出库时，先跑最小工具调用 demo 验证副作用。

## 关键决策

`f66e2252`：在 response_model 与 output_pydantic 之间为何选 output_pydantic — 需要查真实数据。

## 被推翻的想法

今天没遇到被推翻的想法

## 走过的弯路

今天没走值得记的弯路

## 验证结果

未发现明确验证证据

## 风险与阻塞

无

## Session 附录

`f66e2252` 精读 CrewAI 结构化输出 → Bash×8, Read×12；关键文件：CrewAI/internal_instructor.py
