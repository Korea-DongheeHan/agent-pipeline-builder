# Task input: test authoring

Role and protocol follow the `.claude/agents/{{prefix}}-test-engineer` agent
definition. Below is the task input.

## Requirement
{{vars.requirement}}

## Confirmed spec (spec-gate result — overrides assumptions on conflict)
{{vars.decisions}}

## Work
Write unit tests against the interfaces and acceptance criteria the `analyst`
froze (in the context below). You run in parallel with the implementation
(implement node), so do not wait for it — the downstream qa node performs the
combined execution.

- Map at least one test to every acceptance item (`A1, A2, ...`).
- Never edit implementation code.

## Verdict
SUCCEEDED when every acceptance item has mapped tests written;
FAILED when authoring is blocked (e.g. interfaces not frozen).
