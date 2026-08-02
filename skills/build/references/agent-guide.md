# Agent definition (.claude/agents) authoring guide

Every pipeline node runs with a project agent definition
(`nodes[].agent` → `claude --agent`; `subagent_type` in session mode).
Skeletons: `templates/pipeline-dev/agents/*.md`.

## Division of labor (strict)

| Location | Contents | Change frequency |
|---|---|---|
| `.claude/agents/<prefix>-*.md` | **Role and expertise**: system prompt (working style, prohibitions), project facts (build/test commands, conventions), model/tool limits | Low (project traits) |
| `prompts/*.md` | **Task input and verdict criteria**: what comes in, what counts as success, GRAPH_OUTPUT key contract | Medium (pipeline design) |
| `pipeline.yml` | **Flow**: order, parallelism, branches, loops | High (operational tuning) |

Never write the same content in two places — a role duplicated into a prompt
drifts on the first edit.

## Frontmatter

```markdown
---
name: {{prefix}}-analyst          # required; must match the yml agent: value
description: ...                  # required; when to use this agent (drives auto-delegation)
model: sonnet                     # optional; omitted = inherit the session model
tools: Read, Grep, Glob, Bash     # optional; omitted = all tools
---
(body = the system prompt)
```

## Placeholder substitution (mandatory at scaffold time)

Fill every placeholder with Phase 1 facts. None may remain:

| Placeholder | Value |
|---|---|
| `{{prefix}}` | agent prefix (project slug, e.g. `pay`) |
| `{{project_name}}` | project name |
| `{{tech_stack}}` | language and framework (e.g. Kotlin + Spring Boot multi-module) |
| `{{build_command}}` / `{{test_command}}` | the real commands (e.g. `./gradlew build`) |
| `{{conventions}}` | key conventions: layer rules, dependency direction, naming |
| `{{test_conventions}}` | test framework and placement rules |

## Convention references (priority: auto-load > lazy-read pointers > full import — forbidden)

Node sessions start at the project root, so **the project CLAUDE.md (with its
@refs), `.claude/rules/`, and domain skills auto-load already** — never copy
conventions in that scope into agent definitions (double loading = token waste
× node count, plus drift). A one-line SSOT pointer is enough.

Only when conventions live in large docs **outside auto-load scope** (e.g.
`docs/conventions/*.md`), add **per-role lazy-read pointers** instead of
copying:

```markdown
## Reference docs (Read only the relevant entries when starting work)
- Review criteria, dependency direction: docs/conventions/architecture.md
- Transaction and cache rules: docs/conventions/transaction.md
```

Map only the docs relevant to the role (reviewer = architecture and review
criteria; test-engineer = test rules). The source stays the SSOT and updates
apply from the next run.

## Model assignment guidance

- analyst / reviewer: judgment quality dominates the outcome — keep a strong
  model (omitted = inherit).
- test-engineer / qa: procedural — `model: sonnet` or similar saves cost.
- When unsure, omit (inherit) — it is the safe default.

## Projects with existing agents

If `.claude/agents/` already has definitions with overlapping roles, **reuse
them instead of creating new ones** — just align the pipeline.yml `agent:`
values to the existing names. Fill only the missing roles from the templates.
