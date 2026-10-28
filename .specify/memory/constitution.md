# Presenter Constitution

Presenter is built by several agents (Claude Code, OpenCode, Grok Bot) and one human who
decides and merges. These rules bind every agent equally. Each rule cites the code that already
follows it; new code follows the same pattern. Spec Kit: `specify` 1.2.0 (pinned; upgrade as its
own PR).

## Core Principles

### I. Additive and empty-safe

An optional feature must leave output unchanged when it is not used. With no `--guide`,
`--design`, `--persona`, `--images`, or slide layout, a deck renders exactly as it did before the
feature existed. Opt-outs are explicit flags or tokens, never removals.

Follows it today: `design.load_design` (empty `Design()`), `persona.load_persona(None)`,
`layouts.layouts_enabled` (`--no-layouts`, `layouts: false`), `images.fetch_slide_image` (off
unless `--images`).

### II. Compute facts; generate only wording

Anything that can be computed or checked is computed in code, never asked of a model, and model
output is clamped to hard limits in code. The model writes prose; code owns numbers, timings,
counts, and status.

Follows it today: chapters from `ffprobe` clip durations (`youtube.compute_chapters`); episode
status derived from files on disk (`series.episode_status`); YouTube tag and hashtag limits
enforced after generation (`youtube._clean_tags`).

### III. Fix model mistakes in code, not prompts

A model failure seen more than once gets a deterministic guard in code. Prompts may also steer,
but a prompt alone is not a fix.

Follows it today: `utils.sanitize_markdown` (heading demotion, image paths, Mermaid fixes),
`utils.repair_mermaid` (missing edge arrow), `layouts.separate_blocks` (missing blank lines), and
the slide-0 layout gate in `workflow.compose_one_slide` (`slide_index > 0`).

### IV. Resumable cache contract

Every expensive step checks for its output file and returns early when it exists, so reruns are
incremental. New per-slide state is a file in the slide folder that a rerun reads back.

Follows it today: `structure.json`, `slide_<i>/content.md` and `narration.txt`,
`slide_<i>/image_query.txt`, `slide_<i>/layout.txt`, `narration.mp3`, `clip.mp4`
(`workflow.compose_one_slide`, `agents/video_creator.py`).

### V. Source fidelity

Slides, narration, and metadata use only facts from the source. Never present an invented
incident, figure, price, quote, commit, or file name as real. A scenario that is not in the
source is framed as an example ("say your agent…"), never as something that happened.

### VI. Builder-written tests alone never mean done

A ruled change is done when acceptance tests written by someone other than the builder (another
agent or a human, from the ruling issue) pass, CI is green (ruff, mypy, pytest, acceptance, base
test IDs present), and a human merges. The builder never edits its grader.

## Working Agreement (multi-agent)

- **Only what is committed crosses a handoff.** Agents share no memory. A decision that is not in
  the ruling issue, spec, plan, or tasks does not exist for the next agent.
- **Rulings first.** Work that needs a decision starts as a GitHub issue from the `ruling`
  template. A human adds `agent-ready` when it is final. No label, no run.
- **Builder and grader differ.** The issue names both. The grader writes
  `acceptance/issue-<N>/` from the issue and hands it to the operator, never to the builder. It
  lands as one separate commit after the builder's work is pushed.
- **Forbidden in a build:** `acceptance/`, `.specify/memory/`, `.circleci/`, `.github/`, and any
  file the issue lists.
- **Numbers come from CI**, not from an agent's own report.
- **Stop and ask** on the issue when anything conflicts. Do not guess.
- Small fixes, typos, config changes, and dependency bumps skip the ruling and use a normal PR,
  still CI-graded and human-merged.

## Governance

This constitution overrides informal guidance in `CLAUDE.md`, `AGENTS.md`, and prompts where they
conflict. Amendments change this file in their own PR with a version bump: MAJOR when a rule is
removed or redefined, MINOR when a rule is added, PATCH for wording. A human merges every PR,
including Dependabot's. The baseline test IDs are recorded in
`.specify/memory/test-baseline.txt`.

**Version**: 1.0.0 | **Ratified**: 2026-10-28 | **Last Amended**: 2026-10-28
