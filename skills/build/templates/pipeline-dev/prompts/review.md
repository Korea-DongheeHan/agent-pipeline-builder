# Task input: review

Role and protocol follow the `.claude/agents/{{prefix}}-reviewer` agent
definition. Below is the task input.

## Requirement
{{vars.requirement}}

## Confirmed spec (spec-gate result — overrides assumptions on conflict)
{{vars.decisions}}

## Work
Review this run's change set (`git diff <base branch>...HEAD` or the changed
files). Use the upstream artifacts (context below) to understand intent.

QA already performed execution verification, so do not duplicate it — focus
on **conventions, transactions, and quality**. Always check domain invariants
and dependency direction.

## Verdict criteria
- **APPROVE** (GRAPH_STATUS: SUCCEEDED): no blocker/major findings, and every
  acceptance item confirmed PASS.
- **REQUEST_CHANGES** (GRAPH_STATUS: FAILED): blocker/major findings exist.
  Each finding carries file:line, the problem, the required fix, and the
  acceptance item (`A#`) it maps to. Minors are recorded only and never
  affect the verdict.
