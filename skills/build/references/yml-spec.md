# pipeline.yml specification

Full schema of the graph pipeline definition file. The runner is
`scripts/run_graph.py`.

## Top level

```yaml
name: my-pipeline        # pipeline name (defaults to the file name)
kind: development        # development | workflow — sets the prompt style at scaffold time (documentation only)
vars:                    # pipeline inputs, substituted as {{vars.KEY}}; --var KEY=VALUE overrides.
                         # Merged values persist in <run-dir>/vars.json and are restored on --resume
  requirement: "..."
settings: { ... }        # see below
nodes: [ ... ]           # node (agent) definitions
workflow: [ ... ]        # recommended — nested block DSL (see below)
edges: [ ... ]           # low level — direct edge definitions (can be mixed with workflow)
```

## workflow — nested block DSL (recommended)

Write the flow as a **nested structure that reads top to bottom**. The runner
compiles it to edges internally. START/END are wired automatically (START
before the first step, END after the last step's SUCCEEDED).

```yaml
workflow:
  - analyst                            # string = run the node in sequence (when upstream SUCCEEDED)
  - parallel: [implement, test]        # fan-out; items = node | sequence | nested block
  - qa:                                # fan-in — waits for every parallel branch
      if: FAILED                       # node-attached routing: check THIS node's status/output, then jump
      goto: implement                  # goto to an already-placed node = feedback loop (detected automatically)
      max: 2                           # loop cap (backward goto defaults to 3)
      exhausted: escalate              # on exhaustion: FAIL (default, fail immediately) | a node id
  - review
  - branch:                            # multi-case branch (only right after a single node)
      on: route                        # a GRAPH_OUTPUT key; omit it and case keys become
      cases:                           # SUCCEEDED|FAILED|ALWAYS (STATUS branching)
        heavy: process-heavy           # case value = node | sequence (END/FAIL terminals allowed)
        light: [process-light]
  - finalize                           # branch merge point — automatically join: any
```

Block semantics:

- **Sequence**: list order. Each connection's default condition is upstream
  SUCCEEDED.
- **parallel**: run branches concurrently. The next step waits for all
  branches (join: all). Branches may contain sequences and nested blocks.
- **if/goto** (recommended for status checks and loops): attach routing rules
  to a node. Check its status (`if: FAILED`) or output
  (`if: route == heavy`) and jump.
  ```yaml
  - qa:                          # multiple rules as a list:
      if: FAILED                 #   - qa:
      goto: implement            #       - {if: FAILED, goto: implement, max: 2}
      max: 2                     #       - {if: risk == high, goto: security}
  ```
  - **Backward goto** (to an already-placed node) = feedback loop. Beyond
    `max` (default 3) it delegates to the `exhausted` path. A list target
    reworks several nodes.
  - **Forward/sideways/END/FAIL goto** = conditional branch. Target nodes get
    `join: any` automatically.
  - Omitting `if` makes it an unconditional jump and cuts the sequential flow.
  - With an OUTPUT condition (`==`/`!=`), the negated condition is injected
    into the next step's default edge so the two are mutually exclusive
    (`in` has no auto-exclusion — use branch instead).
  - `goto: [report-node, FAIL]` means "run the report node, then fail the
    pipeline" — the runner fails the run automatically after that node
    finishes (fail-after semantics).
- **loop**: for an explicitly scoped loop. Inside `body`, any node **after
  the redo step** reporting FAILED feeds back to the redo node. A FAILED at
  or before the redo step fails the pipeline. Beyond `max` it delegates to
  `exhausted`.
  ```yaml
  - loop:
      max: 2
      exhausted: escalate
      redo: implement                  # defaults to the first body node
      body:
        - parallel: [implement, test]
        - qa
        - review
  ```
- **branch**: pick a case from the upstream node's GRAPH_OUTPUT (`on` key) or
  STATUS. An unmatched case deadlocks the pipeline — define every case. The
  merge point (next step) becomes `join: any` automatically (an explicit
  `join` on the node is respected).
- **Merge-point caveat**: if manual `edges:` also feed a node that only some
  paths reach, set `join: any` on the node explicitly.

## settings

| Key | Default | Description |
|---|---|---|
| `lang` | `en` | Language of runner logs and injected prompt protocol (`en` \| `ko`). Status markers and exit codes are language-neutral |
| `mode` | `session` | Declared default execution mode. `session` = Claude interprets the YAML with the Agent tool (observable, inherits MCP); `runner` = run_graph.py (deterministic, resumable, unattended, but MCP is unreliable — see "Runner mode and MCP"). The output SKILL.md follows this value; users can override per run |
| `parallelism` | 4 | Maximum concurrently running nodes |
| `state_dir` | `.graph-runs` | Where run state and artifacts are stored |
| `node_timeout` | 3600 | Per-execution limit for a node (seconds) |
| `max_total_steps` | 100 | Cap on total node activations (runaway guard) |
| `context_max_chars` | 40000 | Per-node cap when injecting upstream output into a prompt. Truncated content keeps the full output file path — tell the prompt to read that file |
| `claude_args` | `[]` | Extra claude CLI args for every node, e.g. `["--permission-mode", "acceptEdits"]` |
| `model` | (none) | Default model for nodes **without** `agent:`. An agent node keeps its agent definition's model; only a node-level `model` overrides that |
| `claude_bin` | `claude` | Path to the claude binary (env `CLAUDE_BIN` also works) |

## nodes

```yaml
nodes:
  - id: spec-gate
    gate: true                 # gate node: pauses the pipeline on arrival (PAUSED, exit 3).
                               # The orchestrator gets human confirmation (e.g. spec
                               # via AskUserQuestion), then --resume passes it
                               # (inject confirmed values with --var). No prompt, no agent run
  - id: build-check
    type: command              # agent (default) | command. A command node runs a shell
    run: ./gradlew build       # command with no agent session — exit 0 = SUCCEEDED,
                               # anything else FAILED. A GRAPH_OUTPUT line on stdout is
                               # parsed for routing, and {{vars.*}} substitution applies
                               # to run. Trust boundary: run executes as-is —
                               # review pipeline.yml like code
    timeout: 900               # optional per-node timeout (seconds); defaults to settings.node_timeout
  - id: review                 # required, unique. START/END/FAIL are reserved
    prompt: prompts/review.md  # required (except gate/command). Relative to the cwd where
                               # the script runs; falls back to the pipeline.yml directory
    model: opus                # optional per-node model. Precedence: node model >
                               # agent definition's model > settings.model
                               # (settings.model never overrides an agent definition)
    agent: my-reviewer         # optional; claude --agent — uses the repo's
                               # .claude/agents/<name> definition (model, tools, system prompt)
    join: all                  # all (default) | any — fan-in policy (the workflow DSL sets this automatically)
    retry: 1                   # optional immediate retries on FAILED (default 0)
    allowed_tools: "Read Bash" # optional; passed as --allowedTools. Required for MCP
                               # tools in runner mode — see "Runner mode and MCP" below
    persist: true              # optional; session mode only — keep the subagent alive
                               # across loop iterations and send feedback via SendMessage
                               # instead of respawning. Runner mode ignores it
    context: [architect]       # optional; inject these nodes' outputs even if not direct
                               # upstream. Needed whenever the prompt reads a node that sits
                               # further back than one hop — --validate warns when it is missing
    append_prompt: |           # optional inline instructions appended after the prompt file
      extra instructions...
```

- `model` — the value is passed to `claude --model` as-is: an alias (`opus`,
  `sonnet`, `haiku`) or a full model id. The runner does not validate it; a
  wrong name fails only when the node executes, so verify unusual names with
  `claude -p --model <name> "ok"` before wiring them in.
- `join: all` — every non-loop inbound edge must arrive before the node runs
  (fan-in synchronization).
- `join: any` — the first arrival runs it (branch merge points).
- `persist: true` — session-mode execution detail (see
  `references/session-mode.md`, "Persistent nodes"). It changes how a loop
  re-entry executes the node, never the graph semantics: loop caps, iterN
  artifacts, and fan-in behave identically. Put it on builder-type nodes
  (implementer) only; judgment nodes (QA, reviewer) benefit from a fresh
  isolated session each iteration. The runner ignores the key.
- **Sticky arrivals**: a satisfied precondition stays satisfied. In a feedback
  loop where only the failed path re-runs, a fan-in node re-triggers with
  (previous arrivals + the new one) — but if an upstream node is still
  running or pending, it waits and re-runs exactly once.

## edges — low-level definitions

Use these for topologies the workflow DSL cannot express. When mixed with
workflow, they are appended to the compiled edges.

```yaml
edges:
  - from: review               # node id | START | list (a list expands to multiple edges)
    to: [impl-a, impl-b]       # node id | END | FAIL | list (a list = fan-out)
    when: FAILED               # condition; omitted = STATUS==SUCCEEDED
    loop:                      # declares this edge as a feedback (cyclic) edge
      max: 3
      on_exhausted: escalate   # FAIL (default) | a node id to delegate to
```

### when conditions

A list means AND. String shorthands and expressions are supported:

```yaml
when: FAILED                   # STATUS shorthand: SUCCEEDED | FAILED | ALWAYS
when: route == heavy           # GRAPH_OUTPUT expression: == | != | in [a, b]
when:
  - type: STATUS               # explicit form
    status: SUCCEEDED
  - type: OUTPUT
    key: route
    equals: heavy              # equals | not_equals | in: [a, b]
```

OUTPUT comparisons are raw string comparisons — expression values are never
coerced (`yes` stays the string "yes").

### Graph rules

- The graph without `loop` edges must be a DAG. Cycles (feedback) are allowed
  only through edges carrying `loop` — `--validate` enforces this.
- Reaching `to: END` = pipeline success. New activations stop; running nodes
  finish.
- Reaching `to: FAIL` = the pipeline ends as an intentional failure (e.g.
  after an escalation report).
- A node that reports FAILED with no matching edge fails the pipeline
  immediately.
- No runnable node while END is unreached = deadlock; the run fails with a
  diagnosis of what was waiting.

## Agent status protocol

The runner injects this at the end of every prompt automatically (do not
repeat it in prompt files):

```
GRAPH_OUTPUT: {"key": "value"}   # optional — input for branch/OUTPUT conditions
GRAPH_STATUS: SUCCEEDED          # required — SUCCEEDED | FAILED
```

No marker with exit 0 counts as SUCCEEDED (with a warning). Prompt files
carry only the **pass/fail criteria** and the **GRAPH_OUTPUT key contract**.

## Prompt variable substitution

`{{vars.KEY}}`, `{{run.id}}`, `{{node.id}}`, `{{node.iteration}}`

## Context injection

When a node runs, the latest outputs of its **context predecessors** are
injected as an "upstream outputs" section. Content beyond
`context_max_chars` is truncated, with the full output file path provided
alongside — state in the prompt that the node reads that file when the
section is truncated.

Context predecessors are the direct upstream nodes, with two corrections:

- A `gate: true` node produces no output, so it is transparent: the gate's
  own predecessors pass through to the node below it. Without this, one gate
  erases the whole upstream from everything downstream of it.
- A `type: command` node's own output is a build log. It is additive: the
  node's output is injected **and** its own predecessors pass through, so
  dropping a shell step into a chain never hides the work above it.
- A node reached only through `exhausted:` has no inbound edge. It receives
  both ends of the exhausted loop plus their predecessors, so an escalation
  report can name what failed and why.

Anything further back is not injected. Declare it in `context:`.

`--validate` reads every prompt file and warns when the prompt names another
node in backticks (`` `analyst` ``) whose output never reaches it. That
warning is the flow/prompt mismatch: fix it by adding the node to `context:`,
not by rewording the prompt.

## Runner mode and MCP

Runner mode starts each node as a headless `claude -p` session. MCP servers
do **not** carry over the way they do in an interactive session: a server can
time out before its tools load, and a loaded tool can be refused for lack of
a granted permission. A node that writes to Jira, Confluence, or a similar
MCP-backed service fails there while working fine in session mode.

For a pipeline with MCP-dependent nodes, set `settings.mode: session` and say
so in the generated SKILL.md. When runner mode is required anyway, name the
tools per node:

```yaml
  - id: analyst
    allowed_tools: "mcp__<server>__*"
```

Verify the grant before wiring it in — each node session reconnects MCP from
scratch:

```bash
claude -p --allowedTools "mcp__<server>__*" "call one tool and report the result or the exact error"
```

## CLI

```
python3 scripts/run_graph.py pipeline.yml            # run
  --validate                                         # checks only (schema, reachability, cycles,
                                                     #   prompt/graph mismatch warnings)
  --dry-run                                          # parallel-wave execution plan
  --mermaid                                          # mermaid diagram
  --mock                                             # simulated run without claude calls
  --mock-status NODE=FAILED,SUCCEEDED                # scripted statuses per iteration (last value repeats)
  --mock-output 'NODE={"route": "light"}'            # scripted GRAPH_OUTPUT
  --resume RUN_ID                                    # resume; SUCCEEDED nodes served from cache,
                                                     #   vars restored from <run-dir>/vars.json
  --var KEY=VALUE                                    # inject prompt variables (persisted to vars.json)
```

Exit codes: 0 success, 1 failure, 2 load/validation error, **3 gate pause**
(PAUSED — review upstream artifacts, confirm, then `--resume`, optionally
injecting confirmed values with `--var`).

## Run artifacts

```
<state_dir>/<run-id>/
  state.json                  # node statuses, outputs, loop counters (resume input)
  vars.json                   # merged vars (yml defaults < saved < --var); --resume restores
                              #   these, and editing the file injects values without --var
  run.log                     # automatic run log (same as console — no redirection needed)
  prompts/<node>.iterN.prompt.md   # the exact injected prompt (debugging)
  outputs/<node>.iterN.md          # full node output
```
