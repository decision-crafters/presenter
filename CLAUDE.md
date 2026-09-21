# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Presenter is a multi-agent AI tool that turns a topic (or a folder of source documents) into a full presentation: reveal.js HTML slides, a PDF, per-slide narration audio, and a rendered narrated video. Orchestration is built on **LlamaIndex Workflows** (event-driven, step-based).

## Commands

```bash
# Install Python deps
pip install -r requirements.txt

# Generate a presentation from a topic
python run.py "observer design pattern"

# Generate and also render the narrated video
python run.py "observer design pattern" --export-video
```

There is no test suite, linter, or build step. Copy `.env.example` to `.env`; the default `ollama` provider needs no API keys (just a running Ollama daemon with a pulled model). Keys are only needed for `--provider ollama-cloud` (`OLLAMA_CLOUD_API_KEY`) or `--provider openai` (`OPENAI_API_KEY`).

Common flags: `--source <path|github-url>` (build from a repo or Markdown/PDF instead of a topic), `--provider ollama|ollama-cloud|openai`, `--model <name>`, `--slides <n>` (target count, default 15 ≈ 15 min), `--guide <path>` (content steering file), `--design <path>` (DESIGN.md branding + voice), `--voice <kokoro-voice>`, `--export-video`.

### External CLI tools (must be installed and on PATH)

The workflows shell out via `subprocess`; missing tools fail at runtime, not import time:
- `ollama` — the LLM daemon for the default provider (`ollama pull qwen2.5:7b` first)
- `mmdc` (`@mermaid-js/mermaid-cli`) — renders Mermaid blocks to PNG
- `mdslides` (markdown-slides, installed from GitLab) — renders markdown to reveal.js HTML
- `decktape` — exports the HTML deck to PDF
- `ffmpeg` / `ffprobe` — builds/concatenates video clips, and encodes Kokoro WAV → mp3 (video path)
- `repomix` (Node CLI; `npm i -g repomix`, or run via `npx`) — packs a `--source` GitHub repo's docs into one blob for `ingest.py` (honors .gitignore, secret-scans)
- Kokoro may also need the system package `espeak-ng` for phonemization

See README.md for the exact install incantations.

## Architecture

### Two workflows, one entrypoint

`run.py` runs two LlamaIndex `Workflow` classes in sequence:
1. **`PresenterWorkflow`** (`workflow.py`) — produces slides, HTML, and PDF. Returns the presentation folder path.
2. **`PresenterVideoCreaterWorkflow`** (`agents/video_creator.py`) — only runs with `--export-video`; consumes that folder to produce narration audio and the final `presentation.mp4`.

Both use the fan-out/fan-in pattern: a step emits N `ctx.send_event(...)` events, a `num_workers`-parallel step processes each, and a final step uses `ctx.collect_events(ev, [Event] * N)` to join (returns `None` until all N have arrived). Workflow state uses the llama-index 0.14 API: `await ctx.store.get(...)` / `await ctx.store.set(...)`.

### LLM provider factory

The LLM is built in one place — `build_llm(provider, model)` in `providers.py` — and injected into the workflow, so every agent only sees the abstract `LLM` type. Providers: `ollama` (local, default), `ollama-cloud` (via its OpenAI-compatible endpoint using `OpenAILike`), `openai`. Selection comes from `--provider`/`--model` or the `LLM_PROVIDER`/`LLM_MODEL` env vars. Every LLM call relies on structured output, so a chosen model must support tool/JSON-schema output (e.g. `qwen2.5:7b`, `llama3.1:8b`). Both the topic and `--source` paths use a single `structured_predict` for the structure (the source text is injected into the prompt), so the source is capped small enough to fit one call.

### Optional steering guide (`guide.py`)

`load_guide(path)` reads a guidance file — a `SKILL.md`/skill dir or plain `AGENT.md` in the [agentskills.io](https://agentskills.io/specification) format (YAML frontmatter + Markdown body; only the body is used) — and `format_steering` wraps its body as a `STEERING GUIDANCE` block that is injected into all three generation prompts. It is **additive and optional**: with no `--guide` and no auto-discovered `AGENT.md`/`SKILL.md`, the prompts render exactly as their baked-in defaults. The threading is `run.py` → `PresenterWorkflow(guide=...)` → `create_presentation_structure` / `create_presentation_structure_from_data` / `compose_slide`. The marquee use is focusing a broad source on one thesis (see `guides/token-focus/`).

### Optional branding (`design.py`)

`load_design(path)` reads a `DESIGN.md` ([google-labs-code/design.md](https://github.com/google-labs-code/design.md) format: YAML visual tokens + a Markdown voice body; auto-discovers a gitignored root `DESIGN.md`). It splits into two effects, both **additive/empty-safe**:
- **Visual**: `reveal_config_lines` picks the reveal base theme/`CODE_THEME` (prepended before `mdslides`), and `apply_branding` post-processes `output/index.html` — injecting a `<style>:root{--r-*}</style>` (brand colors → `--r-background/main/heading/link-color`, fonts → `--r-*-font` + Google-Fonts `<link>`s), an optional background image and logo `<div>`, and copying local assets. This runs in `combine_slides` **after `mdslides` and before `decktape`**, so the PDF inherits the theme.
- **Voice**: the DESIGN.md Markdown body is merged (in `run.py`) with the `--guide` body into the single steering string fed to the prompts — no agent changes.

mdslides itself has no custom-CSS hook, so branding is applied by HTML post-processing rather than by forking mdslides (a deliberate, documented choice). Example themes live in `designs/`.

### Optional persona (`persona.py`)

`load_persona(path)` reads a `PERSONA.md` (YAML frontmatter + Markdown body, same convention as guide/design) and returns a `Persona` that **unifies the three existing steering seams** so "who narrates and how they speak" is one declared artifact: the body becomes STEERING GUIDANCE (like `--guide`), `voice`/`lang` pick the Kokoro voice (like `--voice`/`--lang`), and `pronunciations` is a term→spoken-form lexicon. `run.py` resolves precedence **explicit CLI flag > persona > built-in default** and threads the pieces in (`steering` → `PresenterWorkflow`; `voice`/`lang`/`pronunciations` → `PresenterVideoCreaterWorkflow`). The lexicon is applied in `agents/narrator.apply_pronunciations` **inside `narrate()` right before Kokoro** (a word-boundary, case-insensitive substitution) — it fixes the *spoken* audio only, never the saved `narration.txt`, so on-screen notes keep the correct spelling. `BUILTIN_PRONUNCIATIONS` (~30 common terms: kubectl, yaml, k8s, json…) always applies even with no persona; a persona's entries override it per domain. All **additive/empty-safe**: no `--persona` → built-ins only, nothing else changes. `--persona auto` runs `select_persona` (one structured LLM call over the `personas/` catalog) and, on no fit with `--suggest-persona-issue`, `open_persona_gap_issue` files a `gh` issue (opt-in + confirmed). The library (`personas/`) is a small maintainable KB: `README.md` (schema/how-to), `index.md` (catalog), one `PERSONA.md` per persona. Ships Cloud Architect / DevOps Engineer / AI Engineer / Researcher / Technical Educator.

### Two input paths (decided in `PresenterWorkflow.start`)

- **Source-driven**: when `--source` is passed, `ingest.py`'s `load_source_documents` builds documents and `create_presentation_structure_from_data` derives both the title and slide structure. A **GitHub repo** is packed by `repomix` (`_pack_repo`, restricted to doc globs, secret-scanned) and capped to `MAX_TOTAL_BYTES`. A **local folder** goes through `_collect_files`, which prioritizes README → spec/`references/`/`schemas/` files → `docs/` → rest, truncates any single oversized file (`MAX_FILE_BYTES`), and caps total size. Either way, a source with less than `MIN_DOC_CHARS` of extractable text is **rejected** (which also catches image-only PDFs) rather than made into a weak deck.
- **Topic-driven** (default): the structure is generated from the topic, then run through a validate → update loop (`structure_validator` decides `is_perfect`; if not, `structure_updater` splits over-dense slides).

### `agents/` — mostly stateless prompt functions

Each file (except `video_creator.py` and `narrator.py`) exports a plain function that wraps an LLM call, typically `llm.(a)structured_predict(SomeModel, prompt=...)` returning a Pydantic model from `models.py`. Prompts are large inline string constants encoding the presentation "rules" (one atomic idea per slide, ≤6–8 words per line, ~40–60s narration). `narrator.py` is the TTS integration (Kokoro, offline — synthesizes WAV then encodes to mp3 via ffmpeg); `video_creator.py` is a full sub-workflow.

### Resumption via on-disk caching (important)

Every expensive step checks for its output file and returns early if present. This makes reruns incremental and is the intended way to iterate:
- `presentations/<safe_topic>/structure.pkl` — pickled `PresentationStructure`; if present, structure generation is skipped entirely.
- `presentations/<safe_topic>/slide_<i>/content.md` + `narration.txt` — skip slide composition.
- `slide_<i>/narration.mp3` and `slide_<i>/clip.mp4` — skip TTS and clip rendering.

To force regeneration, delete the relevant cached file(s). `get_safe_foldername` (`utils.py`) maps a topic to its folder by lowercasing and replacing non-alphanumerics with `_`.

### Output layout

Everything lands in `presentations/<safe_topic>/` (gitignored): `output/index.html` (interactive deck), `presentation.pdf`, `presentation.mp4`, plus `presentation_template.md` / `presentation.md` intermediates, a `media/` folder of rendered diagram PNGs, and one `slide_<i>/` subfolder per slide.

### Markdown post-processing (`utils.py`)

`sanitize_markdown` runs between LLM output and the renderers and encodes hard-won rendering fixes — stripping `Note over` from Mermaid sequence diagrams, demoting `#`/`##` headings to `###`, rewriting image paths to `./media/`, and forcing `flowchart TD` → `flowchart LR`. Adjust here when diagrams or slides render wrong, rather than in prompts. Slides are joined with the `[comment]: # (!!!)` separator (`utils.SLIDES_SEPARATOR`) that markdown-slides uses for slide breaks.

Two more `utils` steps run in `combine_slides` after diagrams are rendered to `media/`, before `mdslides`: `split_oversized_diagrams` measures each diagram PNG (Pillow) and moves a **tall** one onto its own slide (carrying the title) so it doesn't crowd the slide — gated off by `split_diagrams=False` when `--export-video`, since extra slides would desync the per-slide narration; and `references_slide` appends a trailing **References** slide citing the `--source` and up to 8 URLs found in the source (via `ingest.extract_reference_urls`), skipped for topic decks. `design.apply_branding` also always injects a diagram-fit CSS cap (`diagramMaxHeight`, default 460px in reveal's 960×700 slide space).
