# Presenter personas

A **persona** bundles three things a presentation needs, so "who is narrating and
how they speak" is one declared, reusable artifact instead of three scattered flags:

1. **Voice** — the Kokoro TTS voice (`voice`) + language (`lang`).
2. **Tone / style** — the Markdown body, injected as STEERING GUIDANCE into
   structure, slide, and narration generation (same mechanism as `--guide`).
3. **Pronunciation** — a `pronunciations` lexicon applied *deterministically right
   before TTS*, so Kokoro says `kubectl` as "koob control" and `yaml` as "yammel"
   while the on-screen speaker notes keep the correct spelling.

This is the OpenPersona idea applied to presenting: declare it once, and it travels
with every deck. It is additive and empty-safe — with no `--persona`, decks render
as before, except common technical terms already sound better (see built-ins below).

## Using a persona

```bash
python run.py "kubernetes operators" --persona personas/devops-engineer --export-video
python run.py --source <repo> --persona auto --export-video   # auto-pick best fit
```

Precedence (highest first): explicit CLI flag (`--voice`, `--lang`, `--design`) →
the persona's value → built-in default. So a persona sets the voice/tone/pronunciation,
and any explicit flag still wins for a one-off override.

`--persona auto` matches the topic/source to the best persona in this directory. If
nothing fits and you pass `--suggest-persona-issue`, presenter offers to file a
"new persona needed" GitHub issue (via `gh`) for the detected domain, with a ready
`PERSONA.md` stub — so the library grows from real gaps.

## The `PERSONA.md` format

YAML frontmatter + a Markdown body (mirrors `guides/*/SKILL.md` and `designs/*/DESIGN.md`):

```yaml
---
name: Cloud Architect                 # shown in logs and used by --persona auto
description: One line; used by auto-selection.
voice: am_michael                     # Kokoro voice (see kokoro voices)
gender: male                          # female|male — kept consistent with voice
lang: a                               # Kokoro language code (a = US English)
design: designs/midnight              # optional: link a brand pack
domains: [cloud, aws, kubernetes]     # hints for --persona auto matching
pronunciations:                       # term -> how it should SOUND
  EC2: E C two
  IAM: I am
  Terraform: terra form
---
Narrate as a senior cloud architect. Frame ideas at the system level: tradeoffs,
blast radius, cost, operability...   # <- this body becomes STEERING GUIDANCE
```

- `voice` here is the **Kokoro TTS voice**, distinct from a DESIGN.md `voice` (which
  is brand-voice prose). A persona can `design:`-link a brand pack to pair a look
  with the voice.
- **Voice / gender stay matched.** Kokoro encodes gender in the voice name:
  `af_`/`bf_` = female, `am_`/`bm_` = male (the 2nd letter). Declare `gender:` and
  the loader checks it against the `voice`; on a mismatch it **auto-corrects** to a
  matching default (`af_heart` for female, `am_michael` for male) and prints a note,
  so a persona never narrates in the wrong gender. American voices: female
  `af_heart/af_bella/af_nicole/af_sarah`, male `am_michael/am_adam/am_liam/am_echo`.
- `pronunciations` values are **respellings a general-English TTS says correctly**
  (`CUDA → "kooda"`), not IPA. Matching is case-insensitive and word-boundary-anchored,
  so `env → envy` won't touch `envelope`.

## Built-in pronunciations (always on)

`persona.py` ships `BUILTIN_PRONUNCIATIONS` — ~30 cross-cutting terms (`kubectl`,
`kubernetes`, `yaml`, `json`, `k8s`, `nginx`, `PostgreSQL`, `.ipynb`, `CLI`…). These
apply to every run so common jargon sounds right by default. A persona's own
`pronunciations` **override** the built-ins for its domain.

## Adding / maintaining a persona (this directory is a small, maintained wiki)

1. Create `personas/<name>/PERSONA.md` from the format above (copy the closest
   existing persona and edit).
2. Add its domain jargon to `pronunciations` — only terms Kokoro gets wrong; test with
   a quick `narrate(...)` clip and add fixes as you hear them.
3. Add a one-line row to [`index.md`](./index.md).
4. Run once with `--persona personas/<name> --export-video` and listen.

Think of it like the LLM-Wiki pattern: **this README is the schema**, `index.md` is
the **catalog**, and each `PERSONA.md` is a **page**. An LLM can maintain the library
— adding pages, refining lexicons as new mispronunciations surface, and keeping the
index current — because the bookkeeping is near-zero.
