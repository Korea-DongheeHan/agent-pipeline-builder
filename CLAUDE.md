# CLAUDE.md — agent-pipeline-builder

## What this project is

A Claude Code **plugin** (not an app): the `build` skill scaffolds a
self-contained multi-agent development orchestration into a target project
(pipeline skill + agent team + CLAUDE.md trigger), and the `edit` skill
changes and diagnoses installed pipelines. The published artifact of this
repo IS the plugin — every file under `skills/` ships to users.

- Repo/plugin/marketplace name: `agent-pipeline-builder` (renamed from
  graph-builder; old `graph-builder--v0.1~0.3` tags are history — keep them).
- GitHub: https://github.com/Korea-DongheeHan/agent-pipeline-builder (public, Apache-2.0).
- Layout: `.claude-plugin/` manifests · `skills/build/` (scaffolder: SKILL.md,
  `scripts/run_graph.py`, `references/`, `templates/pipeline-dev/` with its
  `agents/`) · `skills/edit/` · `evals/` · trilingual README (`README.md`
  English, `README.ko.md` Korean, `README.zh.md` Simplified Chinese).
  **Whenever README.md changes, apply the same change to README.ko.md and
  README.zh.md in the same commit.**

## Background Claude must know

- **The runner (`skills/build/scripts/run_graph.py`) is stdlib-only Python**
  and is copied verbatim into every scaffolded output. Never add
  dependencies; it must run on a bare `python3` (3.9+). It embeds a mini-YAML
  fallback parser because PyYAML may be absent.
- The `workflow:` DSL (sequence, `parallel`, node-attached `if/goto`, `loop`,
  `branch`, `gate: true`, `type: command`) compiles to edges; the engine only
  knows nodes/edges. Feedback cycles exist only on edges carrying `loop`
  (validated). Fan-in uses sticky arrivals plus wait-while-upstream-busy.
- Agents report `GRAPH_STATUS: SUCCEEDED|FAILED` and optional
  `GRAPH_OUTPUT: {json}`; the runner injects this protocol into prompts and
  evaluates all conditions from it. OUTPUT comparisons are raw string
  comparisons (never coerce `yes`/`no` to booleans — that was a real bug).
- Runner messages are catalogued in `MESSAGES` (en default, ko via
  `settings.lang`); error/validation strings are English. Exit codes:
  0 ok, 1 failed, 2 load/validation, 3 gate pause.
- Templates are the **English source**; the build skill translates output
  docs when the user picks another language. YAML values starting with
  `{{placeholder}}` must be quoted (flow-mapping misparse).
- Trust boundary: `type: command` `run` strings execute as-is; pipeline.yml
  is reviewed like code.

## Development rules

- After any change to the runner, templates, or DSL, run the regression
  before finishing:
  ```bash
  python3 skills/build/scripts/run_graph.py skills/build/templates/pipeline-dev/pipeline.yml --validate
  python3 skills/build/scripts/run_graph.py skills/build/templates/pipeline-dev/pipeline.yml --mock --var requirement=t   # expect exit 3 (gate)
  claude plugin validate .
  rm -rf .graph-runs
  ```
  Cookbook examples in the README are executable claims — re-verify the
  affected pattern when the DSL changes.
- Never commit `.graph-runs/` artifacts (gitignored).
- Release flow: bump `version` in `.claude-plugin/plugin.json` → commit →
  push → `claude plugin tag .` → push the tag → publish the GitHub release
  via device flow (no tokens ever pasted into the conversation). Refresh the
  local install with `claude plugin marketplace update` + `claude plugin update`.
- The scaffolded demo lives in `~/projects/baemin-pay` (`pay-pipeline-dev`);
  sync its `scripts/run_graph.py` copy after runner changes.

## Skill writing rules

Agent-facing documents (SKILL.md files, `references/`, `templates/`) follow
the **skill-style** skill: English, imperative mood, write what to do (not
what the skill is), no scenario enumeration or quoted user phrases in
descriptions, descriptions under 200 characters, lean bodies with details
split into `references/`. Frontmatter descriptions must stay YAML-safe
plain scalars (no `: ` sequences, no leading quotes) — a parse failure
silently drops the skill's metadata.

## Commit convention

Subject line starts with a type prefix, dot, then a space:

```
feat. <what was added>
fix. <what was corrected>
docs. <documentation-only change>
refactor. <behavior-preserving restructure>
build. <manifest, packaging, release plumbing>
test. <tests and evals>
chore. <maintenance that fits nothing above>
```

Example: `feat. add type: command nodes to the runner`. Subject in English or
Korean; keep it under ~70 characters. Bodies stay free-form.
