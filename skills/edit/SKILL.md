---
name: edit
description: Changes and diagnoses installed graph pipelines. Use for adding or removing nodes and agents, adjusting branches, loops, or pass/fail criteria, and analyzing why a pipeline run failed. Building a new orchestration belongs to agent-pipeline-builder:build.
---

# agent-pipeline-builder:edit — change and diagnose a pipeline

Change the yml, prompts, and agents of an installed orchestration **safely**.
Principles: keep the three layers in sync (flow = yml, task input = prompts,
roles = agents), and never finish a change without a mock verification.

## Procedure

### 1. Locate the target

Find `.claude/skills/*/pipeline.yml`. If there are several, confirm with the
user. When DSL syntax is needed, read `../build/references/yml-spec.md`
relative to this skill. Inspect the current structure with `--mermaid` and
keep it as the before-state.

### 2. Design the change — per-type checklist

| Request | What to change |
|---|---|
| Add a node (stage) | ① a `nodes` entry plus its position in `workflow` ② create `prompts/<node>.md` ③ if a dedicated role is needed, add `.claude/agents/<prefix>-*.md` (see the build skill's `templates/pipeline-dev/agents/`) |
| Remove a node | Remove the node and its step from the yml, confirm no goto/branch still points at it (`--validate` catches this), delete the orphaned prompt |
| Adjust a loop | The node's `max` / `exhausted` values (attached if/goto or a loop block) |
| Add or change a branch | Status checks via node-attached `{if, goto}`; multi-case via `branch:` — define every case (an unmatched case deadlocks) and check the merge point's `join: any` |
| Parallelize | Wrap sequential nodes in `parallel: [...]` and move the interface-freezing duty into the upstream node's prompt |
| Change pass/fail criteria | The verdict section of `prompts/<node>.md`, plus any edge conditions using its GRAPH_OUTPUT keys |
| Change an agent | `.claude/agents/<name>.md` (model, tools, role) — keep `name` matching the yml `agent:` value |
| Diagnose a failure | `.graph-runs/<run-id>/state.json` for the failed node and reason → the full text in `outputs/<node>.iterN.md` → decide whether the cause is the prompt, the agent, or the flow |

### 3. Apply and verify (mandatory)

```bash
PL=.claude/skills/<pipeline-name>
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --validate
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mermaid    # show the new structure to the user
# Drive the changed path through a mock (prove the branch/loop actually takes it):
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock --mock-status <node>=FAILED,SUCCEEDED
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock --mock-output '<node>={"key": "value"}'
```

### 4. Record the change (mandatory)

Append one row to `CHANGELOG.md` in the pipeline directory (create it if missing):

```markdown
| Date | Request | Files changed |
|---|---|---|
| 2026-07-31 | add security-scan node | pipeline.yml, prompts/security.md |
```

When the same kind of change request repeats (2+ times), identify the root
cause (prompt criteria, agent role, or flow design) and propose a structural
fix.

### 5. Report

Report the before/after mermaid comparison, the changed file list, the mock
verification results, and whether the CLAUDE.md marker block needs a wording
update.

## Cautions

- Never modify `scripts/run_graph.py` — engine bugs and feature requests
  belong to the agent-pipeline-builder plugin.
- A node failure with no edge handling it fails the pipeline immediately —
  that is the **default behavior**. Judge whether that is correct before
  reflexively adding a failure branch.
- Never finish a change without verification. A change without a mock run is
  incomplete.
