# Task input: implementation

Role and protocol follow the `.claude/agents/{{prefix}}-implementer` agent
definition. Below is the task input.

## Requirement
{{vars.requirement}}

## Confirmed spec (spec-gate result — overrides assumptions on conflict)
{{vars.decisions}}

## Work
Implement per the `analyst` plan and spec (in the context below), in layer
order (domain → core/persistence → application → deployment modules).
Follow the interfaces the analysis froze exactly — the test node is working
against the same interfaces in parallel. When the analysis and the code
disagree, never work around it silently; record the mismatch and your choice
in the deliverable.

## On rerun (feedback)
If the context contains a failure report from `qa` or `review`, fix **only
the FAIL items (`A#`)**. Touching passing parts creates regressions. If you
edit a file, re-check the other acceptance items pinned to that file.

## Verdict
SUCCEEDED when the implementation compiles and is complete; FAILED when
blocked.
