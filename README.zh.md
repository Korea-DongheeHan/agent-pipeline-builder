# agent-pipeline-builder

**用一句话，为你的项目构建一套多智能体开发编排。**

[English](README.md) · [한국어](README.ko.md) · 中文

![agent-pipeline-builder: pipeline.yml 被编译为确定性的多智能体图](docs/hero.svg)

agent-pipeline-builder 是一个 Claude Code 插件，它把一套由 YAML 驱动、
可独立运行的智能体流水线脚手架到你的仓库中。只需描述一次你的领域，插件就会
生成编排技能、专属智能体团队以及触发配置。此后的功能需求会沿着一张确定性的
图流转：分析、确认规格、并行实现与测试、验证、评审，并循环收敛直到验收通过。

```
agent-pipeline-builder 插件
  ├─ agent-pipeline-builder:build   # 构建编排（6 个阶段）
  └─ agent-pipeline-builder:edit    # 修改与诊断已安装的流水线
        │
        ▼  “为这个项目搭建一套开发编排”
<你的项目>/
  CLAUDE.md                              # 触发规则（自动注册）
  .claude/
    skills/<domain>-pipeline-dev/        # 编排技能（独立运行）
      SKILL.md · pipeline.yml · prompts/ · scripts/run_graph.py
    agents/<prefix>-analyst.md ···       # 智能体团队（角色、模型、工具）
```

产物自成一体。脚手架完成后，流水线只依赖 Python 3 和 `claude` CLI，
不再需要本插件。

## 为什么选择 agent-pipeline-builder

- **确定性编排。** 调度图的是脚本而不是 LLM：相同输入，相同流程。分支、
  扇出/扇入、反馈循环和循环上限都被机械地强制执行。
- **流水线的所有权在 YAML。** 整个流程都在一份 `pipeline.yml` 里。调整阶段
  顺序、收紧循环、增加安全评审节点，都不需要碰任何代码。
- **默认规格驱动。** 内置流水线在分析之后停在规格门。在写下任何一行实现
  之前，由你确认范围与验收标准。
- **上下文隔离。** 每个节点都是全新的 claude 会话。节点之间只传递摘要加
  文件路径的有界交接，不会累积上下文污染。
- **续跑而不是重跑。** 运行失败？修复原因后 `--resume`。成功的节点直接用
  缓存，只有失败路径重新执行。
- **成本透明。** 一次节点执行等于一个 claude 会话。技能在运行前先告诉你
  预计的会话数量。

## 安装

```
/plugin marketplace add Korea-DongheeHan/agent-pipeline-builder
/plugin install agent-pipeline-builder@agent-pipeline-builder-marketplace
```

## 可以这样说

按目的选择触发表达：

- **构建新编排**（`agent-pipeline-builder:build`）：“搭建一套开发编排”、
  “为这个仓库构建智能体流水线”、“创建一个 harness”、
  “把我们的编排技能转换成图”。
- **修改或诊断已安装的流水线**（`agent-pipeline-builder:edit`）：
  “给流水线加一个安全扫描步骤”、“把收敛循环上限改成 3”、
  “把 qa 换成 command 节点”、“昨天的流水线为什么失败了”。
- **运行脚手架出的流水线**（由项目的 CLAUDE.md 触发，而不是本插件）：
  任何普通的功能需求，例如“增加部分退款支持”，以及后续请求如
  “接着上次的运行继续”、“把评审意见改完再跑一次”、
  “用会话模式跑，我想看过程”。

普通的代码提问、一行改错和构建诊断，刻意不触发任何东西。

## 构建一套编排

在任意项目里说“搭建一套开发编排”。`build` 技能会走完六个阶段，并在关键处
征求你的确认：

1. **审计。** 检测已有的流水线、智能体和 CLAUDE.md 标记。维护类请求会被
   路由到 `agent-pipeline-builder:edit`，绝不重复生成。
2. **分析。** 读取你的技术栈、真实的构建/测试命令和约定文档，绝不猜测。
3. **设计（你来确认）。** 给出节点/智能体表和流程的 mermaid 图，以及流水线
   名称（默认 `<domain>-pipeline-dev`）、智能体前缀、默认执行模式与产物语言。
4. **生成智能体。** 把你的真实命令和约定出处写进
   `.claude/agents/<prefix>-*.md`。已有的智能体会被复用，绝不重复。
5. **生成流水线技能并注册触发。** 脚手架技能目录，并在 CLAUDE.md 追加标记块。
6. **验证。** 校验图结构，mock 跑通规格门与收敛循环，确认没有残留占位符。

## 会生成什么

以名为 `order-service`、前缀为 `order` 的项目为例：

```
order-service/
  CLAUDE.md                            # + 触发块（标记分隔，可替换）
  .claude/
    skills/order-pipeline-dev/
      SKILL.md                         # 运行方式：模式、规格门、续跑、演进
      pipeline.yml                     # 流程定义。改编排就改这个文件
      prompts/                         # 每个节点的任务输入与判定标准
        analyst.md · implement.md · test.md · qa.md · review.md · escalate.md
      scripts/run_graph.py             # 执行引擎（纯标准库 Python）
      references/session-mode.md       # 可观测会话模式的解释规则
    agents/
      order-analyst.md                 # 角色、工作方式、项目事实
      order-implementer.md
      order-test-engineer.md
      order-qa.md
      order-reviewer.md
```

生成的智能体自带让它第一天就有用的事实：

```markdown
---
name: order-implementer
description: order-service implementation specialist for the implement node.
---
## Project context
- Stack: Kotlin + Spring Boot multi-module Gradle
- Build: ./gradlew classes testClasses --parallel
- Conventions: AGENTS.md is the single source; domain rules live in .claude/skills/<domain>/
```

## 示例：一个功能需求的完整旅程

```bash
$ PL=.claude/skills/order-pipeline-dev
$ python3 $PL/scripts/run_graph.py $PL/pipeline.yml \
    --var requirement="Add partial-refund support to the order API"

[10:02:11] ▶ analyst started (iter 1)
[10:03:24] ✔ analyst SUCCEEDED (iter 1)
[10:03:24] ⏸ gate spec-gate reached — paused        # exit code 3
```

analyst 产出了规格草案和值得确认的问题。Claude 读取后，通过一轮
AskUserQuestion 与你确认规格，然后携带决策续跑：

```bash
$ python3 $PL/scripts/run_graph.py $PL/pipeline.yml --resume 20260731-100211-ab12 \
    --var requirement="..." \
    --var decisions="scope: refunds after settlement excluded; API: extend existing endpoint"

[10:07:02] ⏩ analyst reused from cache
[10:07:02] ⏩ gate spec-gate passed (confirmed in a previous run)
[10:07:02] ▶ implement started (iter 1)     # runs in parallel
[10:07:02] ▶ test started (iter 1)          # with implement
[10:14:40] ▶ qa started (iter 1)
[10:18:03] ✘ qa FAILED (iter 1)             # acceptance A3 failed
[10:18:03] ↻ feedback qa → implement (1/2)
[10:21:47] ✔ qa SUCCEEDED (iter 2)
[10:24:12] ✔ review SUCCEEDED (iter 1)
[10:24:12] ● END reached
[10:24:12] ✔ pipeline SUCCEEDED — artifacts: .graph-runs/20260731-100211-ab12
```

每个节点的完整提示词与输出都保留在 `.graph-runs/<run-id>/` 下备查。
提交始终由你掌控。

## 默认流水线

```yaml
workflow:
  - analyst                          # 分析、SDD 规格草案、待确认问题
  - spec-gate                        # ⏸ 暂停 → AskUserQuestion 确认规格 → 续跑
  - parallel: [implement, test]      # 实现 ‖ 测试编写（扇出）
  - qa:                              # 扇入：构建、运行、判定验收项
      if: FAILED                     # 收敛循环：只返工失败的部分
      goto: implement
      max: 2
      exhausted: escalate            # 反复失败 → 出报告，然后让运行失败
  - review:                          # 静态评审（通过 → 结束；提交归人）
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate
```

每个节点都用 `.claude/agents/` 里的项目专属智能体定义运行，携带真实的
构建命令、测试命令与约定指引。

## 图工程手册

默认流水线只是通用图语言的一个实例。用下面这些可自由嵌套的模式组合出
你自己的流程：

**顺序链** — 批处理任务、迁移：

```yaml
workflow:
  - extract
  - transform
  - load
```

**条件路由（分类后执行）** — 分诊节点通过 `GRAPH_OUTPUT` 上报路由键，
每个分支走自己的子流程：

```yaml
workflow:
  - triage                    # GRAPH_OUTPUT: {"kind": "bug" | "feature" | "docs"}
  - branch:
      on: kind
      cases:
        bug: [reproduce, fix]
        feature: [design, implement]
        docs: update-docs
  - verify                    # 汇合点，先到先行
```

**质量门链** — 快速失败并显式终止：

```yaml
nodes:
  - {id: build-check, type: command, run: "./gradlew classes testClasses --parallel"}
  - {id: security-scan, type: command, run: "./gradlew dependencyCheckAnalyze"}
  - {id: deploy-ready, prompt: prompts/deploy-ready.md}
  - {id: report-failure, prompt: prompts/report-failure.md}
workflow:
  - build-check:
      if: FAILED
      goto: [report-failure, FAIL]   # 先跑报告节点，然后让运行失败
  - security-scan:
      if: FAILED
      goto: [report-failure, FAIL]
  - deploy-ready
```

**人工检查点** — 在任何需要人来决定的地方暂停：

```yaml
nodes:
  - id: approve-plan
    gate: true
workflow:
  - plan
  - approve-plan              # 暂停；续跑时注入确认的值
  - execute
```

**扇出与综合** — 把工作拆进相互隔离的上下文，再在屏障处合并：

```yaml
workflow:
  - plan-slices                                     # 每个分片写一份简报
  - parallel: [audit-api, audit-batch, audit-web]   # 各自独立会话
  - synthesize                                      # 等齐所有分支后合并
```

**对抗性验证** — 给每个生产者配一个独立的反驳者，只保留幸存的结果：

```yaml
workflow:
  - parallel:
      - [draft-a, refute-a]    # 反驳者上报 GRAPH_OUTPUT {"refuted": "yes|no"}
      - [draft-b, refute-b]
  - synthesize                 # 在该节点上加 context: [draft-a, draft-b]
```

**生成后过滤** — 多个不同视角的生成器，加一个过滤器:

```yaml
workflow:
  - parallel: [ideate-risk, ideate-ux, ideate-cost]
  - filter                     # 去重、按标准打分、只返回最优
```

**循环直到完成** — 只要节点报告还有剩余工作，就在有上限的自环里重复：

```yaml
workflow:
  - sweep:                     # 每批一次；GRAPH_OUTPUT {"remaining": "yes"|"no"}
      if: remaining == yes
      goto: sweep              # 自环：再跑一批
      max: 20                  # 设计上的硬上限 — 成本有界
  - report
```

这些图是静态的：节点集合在编写 YAML 时就固定了。运行时决定智能体数量的
动态扇出、无上限循环、两两对决的锦标赛都刻意不在范围内。用固定宽度的
扇出、有上限的自环，以及一个对并行尝试统一裁决的评审节点来近似它们。

## YAML 能表达什么

| 能力 | 语法 |
|---|---|
| 顺序 / 并行阶段 | 列表顺序 / `parallel: [a, b]` |
| 状态驱动的跳转或循环 | 在节点上附加 `{if: FAILED, goto: ...}`（向后 goto = 反馈循环） |
| 多分支路由 | `branch: {on: <输出键>, cases: ...}` |
| 有作用域的循环块 | `loop: {body, redo, max, exhausted}` |
| 人工检查点 | `gate: true` 节点 — 暂停（exit 3），确认后携带值续跑 |
| 确定性 shell 步骤 | `type: command` 节点 — 无智能体会话；exit code 即判定，stdout 的 `GRAPH_OUTPUT` 参与路由 |
| 低层边 | `edges:`，支持 `route == heavy` 这类 when 表达式，`to: FAIL` 终止 |
| 状态与续跑 | `.graph-runs/<run-id>/state.json`，`--resume` 复用成功节点缓存 |
| 干跑验证 | `--validate`、`--dry-run`、`--mermaid`、可编排状态/输出脚本的 `--mock` |
| 日志语言 | `settings.lang: en \| ko` — 运行日志与注入协议本地化；标记保持语言中立 |

智能体在最后一行上报 `GRAPH_STATUS: SUCCEEDED|FAILED`，路由值通过
`GRAPH_OUTPUT: {"key": "value"}` 传递（协议由运行器自动注入）。运行器仅依赖
Python 3 标准库（有 PyYAML 就用，没有则回退到内置解析器）。

## 两种执行模式

| | Runner（默认） | Session |
|---|---|---|
| 编排者 | `run_graph.py` 脚本 | 通过 Agent 工具的 Claude |
| 保证 | 确定性、可续跑、零编排成本 | 解释执行同一份 YAML |
| 可观测性 | 控制台日志 + `run.log` + 各节点输出文件 | Claude Code UI 的实时子智能体树 |
| 适用 | 无人值守、大型或重复运行 | 观察、调试、干预 |

默认值由 `pipeline.yml` 的 `settings.mode` 决定，单次运行时开口即可覆盖
（“用会话模式跑”）。

## 运行模型 — 发布前必须了解

- **成本上限。** 最大会话数 ≈ 节点数 +（反馈节点数 × 循环上限）。注册的
  触发规则默认排除单文件的轻量修改。
- **上下文隔离。** 每个节点都是从空上下文启动的独立会话。节点间只传递
  “上游输出（默认截断 8000 字符）+ 完整输出文件路径”（有界交接）。
  编排者是脚本，不存在上下文污染。
- **可观测性。** Runner 模式看控制台日志（▶/✔/↻/●）与 `.graph-runs/`
  产物；Session 模式看 Claude Code 子智能体树。Runner 模式下节点内部的
  工具调用不会实时显示（完整输出落盘）。
- **权限。** 节点会话的 permission-mode 由 `settings.claude_args` 决定
  （默认 `acceptEdits`）。
- **人工确认走门。** headless 节点无法提问 — 需要人确认的地方（如规格
  确认）放 `gate: true` 节点（暂停 → AskUserQuestion → 续跑）。提交与
  合并在运行之后由人完成。

## 评估套件

技能层在 `evals/` 下自带评估用例 — 脚手架完整性、就地修改（禁止重复
生成流水线）、触发克制（普通代码提问不得生成任何东西）：

```
claude plugin eval agent-pipeline-builder@agent-pipeline-builder-marketplace --scaffold --runs 1
```

`plugin eval` 尚在抢先体验阶段；确定性的图引擎另由 `--validate` 与
`--mock` 回归覆盖（每次发布 22 项检查）。

## 插件结构

```
.claude-plugin/
  plugin.json / marketplace.json    # 清单 · 自托管市场
skills/
  build/                            # agent-pipeline-builder:build — 脚手架
    SKILL.md                        # 6 阶段流程
    scripts/run_graph.py            # 执行引擎（会复制进每个产物）
    templates/pipeline-dev/         # 产物骨架（SKILL.md、yml、prompts，
                                    # agents/ 内含 5 个角色定义骨架）
    references/team-patterns.md     # 团队架构模式 ↔ 图 DSL
    references/agent-guide.md       # 智能体编写与替换规则
    references/yml-spec.md          # pipeline.yml 完整规格
    references/prompt-guide.md      # 提示词规则 + harness 转换映射
    references/session-mode.md      # 会话（树视图）模式解释规则
  edit/                             # agent-pipeline-builder:edit — 修改与诊断
    SKILL.md
evals/                              # 技能层评估用例（build / edit / 触发）
```
