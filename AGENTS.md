# AGENTS.md

Instructions for any coding agent working in this repository. Project details
live in CLAUDE.md.

## At the start of every session

Run this and, if it prints anything, tell the user which video projects are
still open before starting other work:

```bash
.venv/bin/python series.py status --brief
```

It prints nothing when every planned episode is published. Status is derived
from files on disk, so report it as-is — never mark an episode done by hand.
The only manual step is recording a published video:
`python series.py publish series/<slug>.yaml <episode> <youtube-url>`.

## Before generating a presentation

Ask the user which brand to use (a `designs/` folder — e.g. `midnight`,
`sunrise`, a personal brand, or none) unless the series file already sets `design:`.

## Working agreement (every agent: Claude Code, OpenCode, Grok Bot)

Several agents build this repo. They share no memory, so these rules make the
handoffs safe. Full text: `.specify/memory/constitution.md`; how-to: `docs/sdd.md`.

1. **Read the constitution first.** It overrides this file and prompts where they conflict.
2. **Build only from an `agent-ready` ruling issue** (template: `.github/ISSUE_TEMPLATE/ruling.md`)
   when the change needs a decision. A human adds the label. No label, no run.
   Typos, small fixes, config and dependency bumps use a normal PR.
3. **Commit the trail with the code.** Spec, plan and tasks live under `specs/<NNN>-<name>/`
   (`/speckit.specify` → `clarify` → `plan` → `tasks` → `analyze` → `implement`). A decision
   that isn't committed doesn't exist for the next agent.
4. **Never touch in a build:** `acceptance/`, `.specify/memory/`, `.circleci/`, `.github/`, or
   any file the ruling forbids. The grader owns `acceptance/issue-<N>/`.
5. **The builder never sees its grader.** Don't read the grader's tests or relay reply before
   your work is pushed.
6. **Don't report sizes or counts.** CI (`scripts/ci_grade.py`) reports them.
7. **Stop and ask on the issue** when anything conflicts. Don't guess.
8. **A human merges every PR**, including Dependabot's. No auto-merge.
