# Node prompt authoring guide

In the default output structure, **roles and expertise live in
`.claude/agents/` definitions** (rules: `agent-guide.md`), and node prompts
define only the **task input and verdict criteria** — what comes in, what to
do, what counts as success.
The status report syntax (GRAPH_STATUS/GRAPH_OUTPUT) is injected by the
runner automatically; never repeat it. Write only the **verdict criteria and
key contract**.
(A node used without an agent definition carries its role section in the
prompt instead.)

## Common structure (all kinds)

```markdown
# Role/Task: <name>

## Requirement / input
{{vars.requirement}}          ← use variable substitution

## Work
1. ...concrete steps...
   (Upstream outputs are auto-injected as context below — state which
    node's artifact is used and how.)

## Deliverable
What must appear in the response body.

## Verdict
- SUCCEEDED when: ...
- FAILED when: ... (knowing which edge consumes FAILED helps)
- If there is a routing key: which GRAPH_OUTPUT keys carry which values.
  e.g. GRAPH_OUTPUT: {"route": "heavy"}  /  {"failed_items": "A3,A5"}
```

## kind: development — dev-team prompts

Role-separated. Each node is one role on a development team. Must include:

| Node role | Core contract |
|---|---|
| Design (architect/analyst) | Work split + **freeze the interfaces (signatures, types) between parallel branches** + verifiable **acceptance criteria (`A1, A2…` ids)** + undecided items recorded as assumptions (headless nodes cannot ask) |
| Implementation (implement) | Follow the frozen interfaces (parallel nodes build against them) + never work around design-code mismatches silently — record them + **on rerun (feedback), fix only the FAIL items** (no full rewrites — prevents regressions) |
| Test/QA | Compile gate first + **per-acceptance-item PASS/FAIL table** + FAIL items carry reproduction and cause location (the implement node fixes from this report alone) + never edit implementation code + never report unexecuted checks as passed |
| Review (review) | State the APPROVE=SUCCEEDED / REQUEST_CHANGES=FAILED mapping + findings carry file:line and the required fix + minors are recorded, not verdict-affecting + no duplicate verification with QA |
| Escalation (escalate) | On loop exhaustion, a report presenting both sides' evidence — `exhausted:` target nodes auto-fail the run after finishing |

Feedback-loop contract: verdict nodes (test/QA/review) report failures as
`GRAPH_OUTPUT: {"failed_items": "A3,A5"}`, and implement-node prompts carry a
"fix only FAIL items on rerun" section.

## kind: workflow — task-chain prompts

Procedural. Each node is one batch job/task. Must include:

- **Procedure**: numbered steps; state inputs (upstream artifacts) and outputs.
- **Idempotency**: reruns (resume, feedback) must not double-process.
- **Failure verdict**: what counts as FAILED (including partial-failure
  policy — fail when downstream must not run on incomplete data).
- **Routing keys**: nodes with conditional branches list their GRAPH_OUTPUT
  keys and values.

## Converting an existing harness skill to a graph

Mapping when converting an orchestrator-style harness skill:

- Phases/subagents → nodes. If dedicated agent definitions exist, reuse them
  via the node `agent:` field and keep the prompt to **task input only**
  (the role lives in the agent definition).
- Parallel teams → `parallel` blocks (fan-out + fan-in at the next step).
- Convergence loops / "stop after N consecutive failures" →
  `max: N` + `exhausted: <report node>` (auto-fails after it runs).
- Interactive gates (spec confirmation via AskUserQuestion) → `gate: true`
  nodes (pause → confirm → `--resume` + `--var` injection; see
  templates/pipeline-dev).
- Commits and merges stay out of the graph (manual, after END).
