# Team architecture patterns — mapped to the graph DSL

Start from these patterns when choosing a team structure for a request. Every
pattern is expressed in the pipeline.yml workflow DSL and they compose freely.

## 1. Pipeline (sequential chain)

Work connected only by order: batch job chains, migration steps.

```yaml
workflow:
  - extract
  - transform
  - load
```

## 2. Fan-Out / Fan-In (parallel division)

Independent work runs concurrently and synchronizes at a merge point:
multi-branch implementation, multi-dimension inspection.

```yaml
workflow:
  - plan
  - parallel: [impl-api, impl-batch, impl-admin]
  - integrate            # join: all (default) — waits for every branch
```

## 3. Producer–Reviewer (produce → judge + convergence loop)

Produce, let an independent judge verdict, rework on failure. **The backbone
of development orchestration** — templates/pipeline-dev is this pattern plus
fan-out.

```yaml
workflow:
  - implement
  - review:
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate            # repeated failure → run the report node, then auto-fail
```

## 4. Expert Pool (conditional routing)

Delegate by input kind. A triage node reports the routing key via
GRAPH_OUTPUT.

```yaml
workflow:
  - triage                          # GRAPH_OUTPUT: {"kind": "bug"|"feature"|"docs"}
  - branch:
      on: kind
      cases:
        bug: [reproduce, fix]
        feature: [design, implement]
        docs: update-docs
  - verify                          # merge point — automatically join: any
```

## 5. Gate (quality gate chain)

Each stage passes or fails, and a failure exits immediately.
Verification-heavy pipelines. Make deterministic stages (build, scan)
`type: command` nodes — they verdict by exit code with no agent-session cost.

```yaml
workflow:
  - build-check:
      if: FAILED
      goto: [report-failure, FAIL]  # run the report node, then fail the run
  - security-scan:
      if: FAILED
      goto: [report-failure, FAIL]
  - deploy-ready
```

## 6. Fan-out & Synthesize (split, then merge)

Split the work into context-isolated branches, run them in parallel, and
merge at a barrier. Fits audits and investigations where branches must not
contaminate each other.

```yaml
workflow:
  - plan-slices                                     # writes one brief per branch
  - parallel: [audit-api, audit-batch, audit-web]   # each in its own session
  - synthesize                                      # join: all barrier — merges all branches
```

## 7. Adversarial Verification

Pair every producer with an independent refuter and synthesize only what
survives. Session isolation structurally blocks self-preference bias.

```yaml
workflow:
  - parallel:
      - [draft-a, refute-a]     # refuters report GRAPH_OUTPUT {"refuted": "yes|no"}
      - [draft-b, refute-b]
  - synthesize                  # set context: [draft-a, draft-b] on this node so it
                                # receives the originals alongside the verdicts
```

Swap the refuters for scorers and the same skeleton becomes
**Generate-and-Filter**: `parallel: [ideate-a, ideate-b, ideate-c]` followed
by one filter node.

## 8. Loop until Done

When the amount of work is unknown, self-loop while the node reports work
remaining. `max` is a cost ceiling, not an iteration target — beyond it the
run delegates to the exhausted path.

```yaml
workflow:
  - sweep:                      # one batch of work; GRAPH_OUTPUT {"remaining": "yes|no"}
      if: remaining == yes
      goto: sweep               # self-loop
      max: 20
  - report                      # proceeds once remaining is no
```

## Unsupported patterns (say so honestly)

- **Dynamic fan-out / Supervisor**: nodes are declared statically in the yml.
  The agent count cannot grow at runtime — fix the branch width up front, or
  work around it in session mode where Claude spawns agents directly.
- **Pairwise tournament**: winner-advances brackets are dynamic flow.
  Approximate with N parallel attempts judged at once by a single node (same
  skeleton as 7).
- **Unbounded loops**: every loop requires `max` — it prevents unbounded cost
  when the stop condition never arrives.
- **Real-time team chat**: nodes do not message each other. Defects circulate
  through feedback edges — deterministic and reproducible, at the cost of
  slower round trips.

## Selection guide

| Request | Pattern |
|---|---|
| "a feature development pipeline" | 3 + 2 (the default template as-is) |
| "automate batch/sequential jobs" | 1 (+ the failure branch of 5) |
| "handle request types differently (classify-and-act)" | 4 |
| "automate pre-merge quality checks" | 5 |
| "divide a large audit/investigation" | 6 |
| "filter results through refutation/scoring" | 7 |
| "repeat until no work remains" | 8 |
