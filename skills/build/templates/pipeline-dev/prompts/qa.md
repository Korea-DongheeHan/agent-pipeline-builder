# Task input: integration QA

Role and protocol follow the `.claude/agents/{{prefix}}-qa` agent definition.
Below is the task input.

## Requirement
{{vars.requirement}}

## Confirmed spec (spec-gate result — overrides assumptions on conflict)
{{vars.decisions}}

## Work
Verify the combined artifacts of `implement` (code) and `test` (tests) from
the context below. Execute in stages — **compile gate → unit → integration**
— and verify only the affected modules.

1. Produce the verdict table per acceptance item (`A1, A2, ...`) from the
   `analyst` spec: `A1: PASS/FAIL/N-A — one-line evidence`.
2. For FAIL items, include an error excerpt and the cause location
   (file:line) — the implement node fixes from this report alone.
3. On build failure, isolate the cause; never fix code yourself.

## Rules
- Never report an unexecuted check as passed.
- If the test environment is unavailable (Docker etc.), perform static
  verification only and state "dynamic verification not performed".

## Verdict
SUCCEEDED when every acceptance item passes; FAILED when any item fails.
Report the failures via GRAPH_OUTPUT, e.g. GRAPH_OUTPUT: {"failed_items": "A3"}
