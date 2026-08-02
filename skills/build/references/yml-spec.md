# pipeline.yml specification

Full schema of the graph pipeline definition file. The runner is
`scripts/run_graph.py`.

## Top level

```yaml
name: my-pipeline        # pipeline name (defaults to the file name)
kind: development        # development | workflow — sets the prompt style at scaffold time (documentation only)
vars:                    # prompt variables, substituted as {{vars.KEY}}; --var KEY=VALUE overrides
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
| `mode` | `runner` | Declared default execution mode. `runner` = run_graph.py (deterministic, resume); `session` = Claude interprets the same YAML with the Agent tool (observable). The output SKILL.md follows this value; users can override per run |
| `parallelism` | 4 | Maximum concurrently running nodes |
| `state_dir` | `.graph-runs` | Where run state and artifacts are stored |
| `node_timeout` | 3600 | Per-execution limit for a node (seconds) |
| `max_total_steps` | 100 | Cap on total node activations (runaway guard) |
| `context_max_chars` | 8000 | Per-node cap when injecting upstream output into a prompt |
| `claude_args` | `[]` | Extra claude CLI args for every node, e.g. `["--permission-mode", "acceptEdits"]` |
| `model` | (none) | Default model; per-node `model` wins |
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
    model: opus                # optional per-node model
    agent: my-reviewer         # optional; claude --agent — uses the repo's
                               # .claude/agents/<name> definition (model, tools, system prompt)
    join: all                  # all (default) | any — fan-in policy (the workflow DSL sets this automatically)
    retry: 1                   # optional immediate retries on FAILED (default 0)
    allowed_tools: "Read Bash" # optional; passed as --allowedTools
    context: [architect]       # optional; inject these nodes' outputs even if not direct upstream
    append_prompt: |           # optional inline instructions appended after the prompt file
      extra instructions...
```

- `join: all` — every non-loop inbound edge must arrive before the node runs
  (fan-in synchronization).
- `join: any` — the first arrival runs it (branch merge points).
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

When a node runs, the latest outputs of its direct upstream nodes (plus any
nodes listed in `context`) are injected as an "upstream outputs" section.
Content beyond `context_max_chars` is truncated, with the full output file
path provided alongside.

## CLI

```
python3 scripts/run_graph.py pipeline.yml            # run
  --validate                                         # checks only (schema, reachability, cycles)
  --dry-run                                          # parallel-wave execution plan
  --mermaid                                          # mermaid diagram
  --mock                                             # simulated run without claude calls
  --mock-status NODE=FAILED,SUCCEEDED                # scripted statuses per iteration (last value repeats)
  --mock-output 'NODE={"route": "light"}'            # scripted GRAPH_OUTPUT
  --resume RUN_ID                                    # resume; SUCCEEDED nodes served from cache
  --var KEY=VALUE                                    # inject prompt variables
```

Exit codes: 0 success, 1 failure, 2 load/validation error, **3 gate pause**
(PAUSED — review upstream artifacts, confirm, then `--resume`, optionally
injecting confirmed values with `--var`).

## Run artifacts

```
<state_dir>/<run-id>/
  state.json                  # node statuses, outputs, loop counters (resume input)
  run.log                     # automatic run log (same as console — no redirection needed)
  prompts/<node>.iterN.prompt.md   # the exact injected prompt (debugging)
  outputs/<node>.iterN.md          # full node output
```
