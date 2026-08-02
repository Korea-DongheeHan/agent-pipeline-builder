# Session orchestration mode — rules for observable execution

Instead of the runner (run_graph.py), **Claude in the main session interprets
pipeline.yml and executes nodes with the Agent tool**. Each node appears as a
subagent in the Claude Code tree view, so progress is observable live. The
pipeline.yml remains the single source of truth.

## Choosing a mode

| | Runner mode | Session mode |
|---|---|---|
| Execution guarantee | Deterministic, enforced by the script | Depends on the model following these rules |
| Observability | Console log + state.json | **Live tree view** |
| Resume | Cached reuse of succeeded nodes | None |
| Context | Nodes fully isolated; main session untouched | Node summaries accumulate in the main session |
| Best for | Unattended, batch, large runs | Interactive runs that need watching |

## Interpretation rules (Claude MUST follow)

1. **Understand the structure first** — run `--validate`, then `--dry-run`
   for the wave order, branches, and loops. Never reinterpret the graph.
2. **One node execution = one Agent tool call.** Compose the prompt from:
   - the prompt file content (substitute `{{vars.*}}` with real values)
   - upstream results: a summary plus the output file path (never inline the
     full text — bounded handoff)
   - the status instruction: "when done, end with `GRAPH_STATUS: SUCCEEDED`
     or `FAILED` on the last line, and `GRAPH_OUTPUT: {json}` right above it
     if routing values are needed"
   - if the node declares `agent:`, pass that name as `subagent_type`
3. **Parallel steps (same wave)** — call Agent multiple times in a single
   response (they display in parallel in the tree view).
4. **Fan-in** — a `join: all` node (default) runs only after every non-loop
   upstream finishes; `join: any` runs on the first arrival.
5. **Condition verdicts** — evaluate edge conditions (when / if / branch
   cases) from the GRAPH_STATUS / GRAPH_OUTPUT the subagent reported. A
   missing marker counts as SUCCEEDED, but say so in the report.
6. **Respect loop caps** — feedback loops (loop / backward goto) never exceed
   `max`. On exhaustion follow the exhausted path (FAIL = stop and report to
   the user; a node = delegate to it).
6-1. **Gate nodes (`gate: true`)** — spawn no agent. Run **AskUserQuestion on
   the spot**, grounded in the upstream artifact (e.g. the analyst's
   questions-to-confirm section), inject the confirmed decisions into
   downstream prompts, then continue. Never run downstream nodes before the
   user answers.
7. **Preserve artifacts** — write each node's full result to
   `.graph-runs/session-<YYYYMMDD-HHMMSS>/outputs/<node>.iterN.md` and keep
   only summaries in the session context.
8. **Termination** — END reached = report success with the per-node verdict
   table. FAIL terminal, deadlock, or loop exhaustion = report failure with
   the cause and evidence. Never report an unexecuted node as executed.
