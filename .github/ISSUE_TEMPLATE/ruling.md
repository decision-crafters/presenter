---
name: Ruling (agent-buildable change)
about: Decide everything before an agent builds. A human adds `agent-ready` only when this is final.
title: "Ruling: <one-line change>"
labels: []
---

<!-- Constitution: .specify/memory/constitution.md. No `agent-ready` label, no run.
     Small fixes, typos, config and dependency bumps skip this and use a normal PR. -->

## Roles

- **Builder:** <!-- claude-code | opencode | grok-bot -->
- **Grader:** <!-- must differ from the builder; writes acceptance/issue-<N>/ from this issue -->
- **Operator:** <!-- who verifies the builder's push and adds the grader commit -->

## The rule

<!-- What must be true when this is done, in plain words. One behaviour change. -->

## Types and interfaces

<!-- Exact names, signatures, return types, file locations. -->

## What other cases get

<!-- Behaviour for every input this does NOT target (unchanged? default?). -->

## Forbidden files

Always: `acceptance/`, `.specify/memory/`, `.circleci/`, `.github/`.
Also for this change: <!-- list -->

## Existing test edits allowed

<!-- "None", or the exact test IDs and the exact edit. The grader lists any approved
     removal in acceptance/issue-<N>/allowed-missing.txt. -->

## Acceptance checks (given / when / then, exact inputs)

1. **Given** … **when** … **then** …
2.

## Expected Spec Kit trail

`/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.analyze` (fix HIGH findings) → `/speckit.implement`, committed under `specs/<NNN>-<name>/` with the code.

## Limits

- Diff cap: 300 counted lines, tests included.
- Spend: <!-- e.g. $0, free model only -->
- Iterations / time: <!-- e.g. 10 iterations, 90 min -->

## Stop and ask

If anything here conflicts with the code, the constitution, or itself, stop and ask on this issue. Do not guess. Do not report sizes or counts; CI does.

## Grading

CI (`scripts/ci_grade.py`): ruff, mypy, full pytest, `acceptance/issue-<N>/`, every base test ID present, diff summary. A human merges.

## Constitution exceptions

<!-- "None", or the rule and why. -->
