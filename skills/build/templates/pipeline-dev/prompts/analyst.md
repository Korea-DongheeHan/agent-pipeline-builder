# Task input: analysis + SDD spec draft

Role and protocol follow the `.claude/agents/{{prefix}}-analyst` agent
definition. Below is the task input.

## Requirement
{{vars.requirement}}

## Work
1. Analyze the modules the requirement touches and draft the implementation plan.
2. Write the **SDD spec draft**:
   - scope (in / out)
   - scenarios (GWT)
   - invariants and contracts
   - **acceptance criteria** (`A1, A2, ...` ids — the verdict units for QA and review)
   - assumptions (decide from code and conventions instead of asking, and record here)
3. Split the work into two branches and freeze the interfaces (signatures,
   types) between them:
   - implementation branch (implement node) / test branch (test node)

## Questions to confirm (important — this pipeline has a spec gate)
When this node finishes, the pipeline **pauses at the spec gate** and the
orchestrator asks the user your questions, grounded in your output. End your
deliverable with a `## Questions to confirm` section:

- Raise **only the axes where the user's answer changes the deliverable** —
  at most 4. If there are two axes, ask two. Anything decidable from code,
  conventions, or existing patterns is an assumption, not a question.
- Axis priority: ① scope boundary ② architecture decisions (layers, ports,
  dependency direction) ③ contracts and edge cases ④ done criteria (test
  scope, documentation).
- Give each question 2–4 options and a **recommendation with a one-line
  reason** — the orchestrator forwards them into AskUserQuestion as-is.
- If no question is needed, write "Questions to confirm: none (assumptions suffice)".

## Verdict
SUCCEEDED when the analysis, spec draft, and questions are complete;
FAILED when the requirement is contradictory or infeasible.
Report the question count via GRAPH_OUTPUT, e.g. GRAPH_OUTPUT: {"questions": "3"}
