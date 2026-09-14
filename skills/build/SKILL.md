---
name: build
description: Meta-skill that builds a multi-agent development orchestration into a project. Use when composing a new agent team, graph pipeline, or development harness, or when converting an existing orchestrator harness skill into a graph. Changes to an installed pipeline belong to agent-pipeline-builder:edit.
---

# agent-pipeline-builder:build — compose a development orchestration

Turn a one-sentence domain description into a development orchestration that
runs on its own inside the project. This skill is used only at composition
time; the output runs without the plugin.

## Output structure (complete ALL of this)

```
<project>/
  CLAUDE.md                              # ① trigger rule for dev requests
  .claude/
    skills/<pipeline-name>/              # ② main orchestration skill (default name: <domain>-pipeline-dev)
      SKILL.md                           #    run procedure (runner/session modes)
      pipeline.yml                       #    flow SSOT — users add and change it in YAML
      prompts/*.md                       #    per-node task input and pass/fail criteria
      scripts/run_graph.py               #    execution engine (copy)
      references/session-mode.md         #    interpretation rules for the observable mode (copy)
    agents/<prefix>-*.md                 # ③ agent team (role, model, tools)
```

Division of labor: **flow = yml, roles = agents, task input = prompts**.
Details in `references/agent-guide.md`. Never write the same content in two places.

## Phase 0: audit (decide the run mode)

Before creating anything, audit what already exists:

- Check `.claude/skills/*/pipeline.yml` (installed pipelines), `.claude/agents/`,
  and `agent-pipeline-builder:*` marker blocks in CLAUDE.md.
- **Drift check** — if the artifacts disagree with each other (a yml `agent:`
  points to a missing agent, a marker exists without a skill directory, and so
  on), report it first.

| State | Mode |
|---|---|
| No artifacts | **New build** — proceed from Phase 1 |
| Pipeline exists + request adds a new pipeline/node/agent | **Extend** — proceed from Phase 1 without colliding with existing names or agents (no duplicates) |
| Pipeline exists + request changes, fixes, or diagnoses it | **Maintenance — do not use this skill; route to `agent-pipeline-builder:edit`** |

## Phase 1: project analysis

Collect project facts before scaffolding (they feed the agent placeholders):

- Tech stack and the real build/test commands (confirm in README and build
  files; never guess).
- Layer structure, dependency direction, and conventions (CLAUDE.md,
  convention docs, code samples).
- **Determine the load scope of convention docs** — anything inside
  CLAUDE.md (@refs), `.claude/rules/`, or domain skills auto-loads into node
  sessions, so no action is needed. Docs outside auto-load scope (e.g. docs/)
  get per-role lazy-read pointers in Phase 3 (see the convention reference
  rule in `references/agent-guide.md`).
- **Check existing `.claude/agents/`** — reuse definitions whose roles overlap.

## Phase 2: team design (user confirmation gate)

Start from the patterns in `references/team-patterns.md`.
**For a standard feature-development request, the default template as-is is
the default choice** — analysis → **SDD spec gate (⏸ confirmed via
AskUserQuestion)** → implement ‖ test → QA → review, with convergence loops.
Deviate only when the request differs, and place a `gate: true` node wherever
a human must confirm.

Prefer **3–8 nodes** — beyond that, split the pipeline (one per stage) or
merge nodes. More nodes mean more session cost and wider loops.

Confirm with the user: ① the node/agent table (roles, models) ② the flow as a
mermaid diagram (generate with `--mermaid` from the draft pipeline.yml)
③ the pipeline name (default `<domain>-pipeline-dev`, with the domain slug
matching the agent prefix) ④ the **default execution mode** — session
(recommended: live subagent view and mid-run intervention; no resume,
main-session overhead) vs runner (unattended, deterministic, resume, zero
orchestration cost). The choice is recorded in `settings.mode` of the output
pipeline.yml and can be overridden verbally per run. ⑤ the **output
language** — detect the project's primary documentation language and propose
it as the default (en | ko). `settings.lang` switches the runner logs, and the
SKILL.md, prompts, and agent definitions are generated in this language.

## Phase 3: generate agent definitions (`.claude/agents/`)

Copy `templates/pipeline-dev/agents/*.md` into the project as
`.claude/agents/<prefix>-<role>.md` and **substitute every
placeholder** with Phase 1 facts (rules: `references/agent-guide.md`).
When existing agents cover a role, reuse them instead of generating — only
align the `agent:` values in the yml.

## Phase 4: generate the orchestration skill (`.claude/skills/<pipeline-name>/`)

Copy `templates/pipeline-dev/` in full **except its `agents/` directory**
(that was consumed by Phase 3 and must not land inside the skill), then:

1. Substitute the placeholders (`{{pipeline_name}}`, `{{prefix}}`,
   `{{project_name}}`, `{{build_command}}`) in `SKILL.md`, `pipeline.yml`, and
   `prompts/*.md`, and
   set `settings.lang` in pipeline.yml to the language chosen in Phase 2.
   When the output language is not English, translate the template bodies
   (SKILL.md, prompts, agent definitions — the templates are the English
   source) into the chosen language.
   The output SKILL.md description must include **concrete trigger situations
   plus follow-up keywords (rerun, revise, refine, apply feedback)** — adapt
   the template default to the project's vocabulary.
1-1. `{{build_command}}` is the `build-check` node's shell command — the
   project's cheapest command that fails on a broken build (`./gradlew
   compileKotlin compileTestKotlin`, `npm run build`, `cargo check`). When the
   project has no such command, delete the `build-check` node and its workflow
   step instead of inventing one; `--validate` catches a dangling step.
2. Set `settings.mode`. `session` is the default and stays the default
   whenever any node calls MCP tools (Jira, Confluence, GitLab, a wiki):
   runner mode starts each node as a headless `claude -p` session where MCP
   servers may fail to load (`references/yml-spec.md`, "Runner mode and
   MCP"). Choose `runner` only for a pipeline that runs unattended and calls
   no MCP tool. State the chosen default and the reason in the output
   SKILL.md; for runner mode with MCP, set `allowed_tools` per node and
   verify the grant first.
3. Wire the context the prompts assume. A prompt that reads an output more
   than one hop upstream needs that node in the reader's `context:` — the
   template does this for `qa` and `review`. Gates and `exhausted:` targets
   need no declaration; the runner corrects those two itself.
4. If the Phase 2 design differs from the default template, adjust workflow,
   nodes, and prompts (DSL spec: `references/yml-spec.md`; prompt rules:
   `references/prompt-guide.md`).
5. Copy this skill's `scripts/run_graph.py` and
   `references/session-mode.md` verbatim (never modify the runner — it
   guarantees standalone execution).

## Phase 5: register in CLAUDE.md (mandatory)

Append a trigger block to the project ROOT CLAUDE.md (create the file if
missing; replace the block if the same marker exists):

```markdown
<!-- agent-pipeline-builder:<pipeline-name> start -->
## Development orchestration: <pipeline-name>
For development, feature-change, test-hardening, and review requests, use the
`.claude/skills/<pipeline-name>` skill (development orchestration).
Perform thin single-file changes directly instead.
<!-- agent-pipeline-builder:<pipeline-name> end -->
```

## Phase 6: verify and hand over (mandatory — do not skip)

```bash
PL=.claude/skills/<pipeline-name>
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --validate
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock          # expect spec gate PAUSED (exit 3)
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock \
  --resume <RUN_ID> --mock-status qa=FAILED,SUCCEEDED             # gate pass + convergence loop
# Leftover scaffold placeholders = incomplete ({{vars.*}} etc. are runtime variables, excluded)
grep -rn "{{" $PL .claude/agents/<prefix>-*.md | grep -v "{{vars\.\|{{run\.\|{{node\."
```

Every `warning:` line `--validate` prints is a defect, not a note. A
`prompt mentions X but that output never reaches it` warning means the prompt
asks for something the graph cannot deliver — add `X` to that node's
`context:` and validate again. Hand over only with zero warnings.

Read one `.graph-runs/<run-id>/prompts/*.prompt.md` from the mock run and
confirm the `upstream node outputs` section holds what the prompt asks for.

**Trigger validation** — reason through the output SKILL.md description:

- 5 should-trigger phrases: real development requests this project would see
  (e.g. "add feature X", "apply the review feedback and rerun").
- 5 should-NOT-trigger phrases, centered on **near-misses** — "what does this
  function do" (a question), "fix this one typo" (a thin change), "why is the
  build broken" (a diagnosis).
- If either set misfires, revise the description (state trigger and exclusion
  conditions).

Include in the handover report: the generated file tree, the CLAUDE.md
registration, the **cost profile** (one node execution = one claude session;
estimate the maximum session count), the two execution modes (runner =
deterministic + resume / session = live subagent view), the context-isolation
property, the permission-mode setting, the MCP limitation of runner mode when
it applies, and that future changes go through `agent-pipeline-builder:edit`.

## References

- `references/team-patterns.md` — team architecture patterns mapped to the graph DSL
- `references/agent-guide.md` — agent authoring and substitution rules
- `references/yml-spec.md` — full pipeline.yml schema, DSL, CLI
- `references/prompt-guide.md` — prompt rules and harness-conversion mapping
- `references/session-mode.md` — interpretation rules for session (tree-view) orchestration
- `templates/pipeline-dev/` — output skill skeleton (its `agents/` holds the agent skeletons)
