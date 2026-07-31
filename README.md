# graph-builder

**Build a multi-agent development orchestration for your project from a single sentence.**

![graph-builder: pipeline.yml compiled into a deterministic multi-agent graph](docs/hero.svg)

graph-builder is a Claude Code plugin that scaffolds a self-contained, YAML-driven
agent pipeline into your repository. Describe your domain once, and the plugin
generates an orchestration skill, a specialized agent team, and the trigger wiring.
From then on, feature requests run through a deterministic graph:
analyze, confirm the spec, implement and test in parallel, verify, review,
and loop until acceptance passes.

```
graph-builder plugin
  ├─ graph-builder:build   # scaffold an orchestration (6 phases)
  └─ graph-builder:edit    # modify and diagnose an installed pipeline
        │
        ▼  "Set up a dev orchestration for this project"
<your-project>/
  CLAUDE.md                              # trigger rule (auto-registered)
  .claude/
    skills/<domain>-pipeline-dev/        # the orchestration skill (self-contained)
      SKILL.md · pipeline.yml · prompts/ · scripts/run_graph.py
    agents/<prefix>-analyst.md ···       # the agent team (role, model, tools)
```

The output runs on its own. Once scaffolded, the pipeline needs neither this
plugin nor any dependency beyond Python 3 and the `claude` CLI.

## Why graph-builder

- **Deterministic orchestration.** A script, not an LLM, schedules the graph:
  same input, same flow. Branching, fan-out/fan-in, feedback loops, and loop
  caps are enforced mechanically.
- **You own the pipeline in YAML.** The whole flow lives in one `pipeline.yml`.
  Reorder stages, tighten loops, or add a security-review node without touching
  any code.
- **Spec-driven by default.** The built-in pipeline pauses at a spec gate after
  analysis. You confirm scope and acceptance criteria before a single line of
  implementation runs.
- **Context isolation.** Every node starts as a fresh claude session. Nodes
  exchange only bounded handoffs, a summary plus a file path, so no context
  pollution accumulates.
- **Resume, don't redo.** Failed run? Fix the cause and `--resume`. Succeeded
  nodes are served from cache; only the failed path re-executes.
- **Transparent cost.** One node execution equals one claude session. The skill
  tells you the expected session count before it runs anything.

## Install

```
/plugin marketplace add <this-repo-url>
/plugin install graph-builder@graph-builder-marketplace
```

Then, in any project: *"Set up a development orchestration"*. The `build` skill
audits existing setup, analyzes your stack and conventions, proposes the team
design with a mermaid diagram, scaffolds everything, registers the CLAUDE.md
trigger, and verifies the graph with a mock run before handing it over.

## The default pipeline

```yaml
workflow:
  - analyst                          # analysis, SDD spec draft, questions to confirm
  - spec-gate                        # ⏸ pause → confirm spec via AskUserQuestion → resume
  - parallel: [implement, test]      # implementation ‖ test authoring (fan-out)
  - qa:                              # fan-in: build, run, judge acceptance items
      if: FAILED                     # convergence loop: rework only what failed
      goto: implement
      max: 2
      exhausted: escalate            # repeated failure → report, then fail the run
  - review:                          # static review (approve → done; commits stay human)
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate
```

Each node runs with a project-specific agent definition from `.claude/agents/`,
carrying your real build commands, test commands, and convention pointers.

## What the YAML can express

| Capability | Syntax |
|---|---|
| Sequential / parallel stages | list order / `parallel: [a, b]` |
| Status-driven jump or loop | attach `{if: FAILED, goto: ...}` to a node (backward goto = feedback loop) |
| Multi-case routing | `branch: {on: <output-key>, cases: ...}` |
| Scoped loop block | `loop: {body, redo, max, exhausted}` |
| Human checkpoint | `gate: true` node — pauses (exit 3), resume with confirmed values |
| Low-level edges | `edges:` with `when` expressions such as `route == heavy`, `to: FAIL` termination |
| State and resume | `.graph-runs/<run-id>/state.json`, `--resume` with cached successes |
| Dry verification | `--validate`, `--dry-run`, `--mermaid`, `--mock` with scripted statuses and outputs |

Agents report `GRAPH_STATUS: SUCCEEDED|FAILED` and optional
`GRAPH_OUTPUT: {"key": "value"}` on their last lines; the runner injects the
protocol automatically and evaluates every conditional edge from it.

## Two execution modes

| | Runner (default) | Session |
|---|---|---|
| Orchestrated by | `run_graph.py` script | Claude, via the Agent tool |
| Guarantees | Deterministic, resumable, zero orchestration cost | Follows the same YAML, interpreted |
| Observability | Console log + `run.log` + per-node output files | Live subagent tree in the Claude Code UI |
| Best for | Unattended, large, or repeated runs | Watching, debugging, intervening |

Set the default with `settings.mode` in `pipeline.yml`, and override it per run
by simply asking ("run it in session mode").

## Operating notes

- **Cost ceiling.** Maximum sessions ≈ node count + (feedback nodes × loop max).
  The registered trigger excludes thin single-file changes by default.
- **Human gates.** Headless nodes cannot ask questions. Spec confirmation
  happens at the gate; commits and merges happen after the run, by you.
- **Evolution loop.** Feedback maps to a concrete fix target (prompts, agents,
  or YAML), and `graph-builder:edit` applies changes with validation and a
  changelog entry.

## Plugin layout

```
.claude-plugin/                     # manifest + self-hosted marketplace
skills/
  build/                            # graph-builder:build — the scaffolder
    SKILL.md                        # 6-phase procedure
    scripts/run_graph.py            # the engine (copied into every output)
    templates/pipeline-dev/         # output skill skeleton (SKILL.md, yml, prompts)
    templates/agents/               # agent definition skeletons (5 roles)
    references/                     # yml spec, team patterns, agent guide,
                                    # prompt guide, session-mode rules
  edit/                             # graph-builder:edit — change & diagnose
```
