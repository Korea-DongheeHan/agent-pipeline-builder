# Session orchestration mode — rules for observable execution

Instead of the runner (run_graph.py), **Claude in the main session interprets
pipeline.yml and executes nodes with the Agent tool**. Each node appears as a
subagent in the Claude Code tree view, so progress is observable live. The
pipeline.yml remains the single source of truth.

## Choosing a mode

| | Session mode (default) | Runner mode |
|---|---|---|
| Execution guarantee | Depends on the model following these rules | Deterministic, enforced by the script |
| Observability | **Live tree view** | Console log + state.json |
| Resume | None | Cached reuse of succeeded nodes |
| Context | Node summaries accumulate in the main session | Nodes fully isolated; main session untouched |
| MCP tools | Inherited from the main session | Unreliable — each node is a headless `claude -p` session, so servers may time out before their tools load and loaded tools may lack a granted permission |
| Best for | Interactive runs that need watching, and any pipeline whose nodes call MCP tools | Unattended, batch, large runs with no MCP |

## Interpretation rules (Claude MUST follow)

1. **Understand the structure first** — run `--validate`, then `--dry-run`
   for the wave order, branches, and loops. Never reinterpret the graph.
2. **One node execution = one Agent tool call.** Compose the prompt from:
   - the prompt file content (substitute `{{vars.*}}` with real values)
   - context predecessors' results: a summary plus the output file path
     (never inline the full text — bounded handoff). Context predecessors are
     the direct upstream nodes, with two corrections the runner also applies:
     a `gate: true` node has no output, so pass its own predecessors through
     instead; a `type: command` node is additive, so pass its output *and* its
     predecessors; a node reached only via `exhausted:` has no inbound edge, so
     give it both ends of the exhausted loop plus their predecessors. Add
     every node listed in the node's `context:` key
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
6-2. **Persistent nodes (`persist: true`)** — the node's subagent survives
   loop iterations instead of being respawned.
   - **First execution**: a normal Agent call; record the returned agent
     name for later messaging.
   - **Loop re-entry** (a backward goto reaches the node again): do not
     spawn. SendMessage the recorded agent with the feedback summary from
     the verdict node (QA/review), the artifact paths, and the same
     GRAPH_STATUS / GRAPH_OUTPUT instruction. The agent already holds the
     full working context, so never re-inline its own prior output.
   - **Fallback**: if SendMessage fails or ListAgents no longer shows the
     agent, spawn fresh per rule 2 with the prior output path plus the
     feedback injected, and note the fallback in the final report.
   - All other rules stay in force: loop caps (rule 6), per-iteration
     `<node>.iterN.md` artifacts (rule 7), fan-in and condition verdicts.
     `persist` changes how the node executes, never what the graph means.
7. **Preserve artifacts** — write each node's full result to
   `.graph-runs/session-<YYYYMMDD-HHMMSS>/outputs/<node>.iterN.md` and keep
   only summaries in the session context.
8. **Termination** — END reached = report success with the per-node verdict
   table. FAIL terminal, deadlock, or loop exhaustion = report failure with
   the cause and evidence. Never report an unexecuted node as executed.
