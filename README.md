# Presenter 🎦

### Introducing **Presenter**: A Multi-Agent AI Tool that can:

- [x] **Create beautiful presentations** for any given topic 🔥
- [x] **Render intuitive & visually appealing diagrams** 🖼️ for slides when needed (using Mermaid)
- [x] **Write scripts** for every slide 📜
- [x] **Render & View interactive presentations in HTML** 💻 (using markdown-slides & reveal.js)
- [x] **Intuitive speaker view with scripts** (reveal.js)
- [x] **Export presentations to PDF** 🖨️ (using DeckTape)
- [x] **Generate audio narrations** from scripts 🎙️ (using Kokoro, fully offline)
- [x] **Render full video presentations** 🎥 with all the slides and voiceover (using FFmpeg)

## Video Demo with overview of the multi-agent setup

[![Presenter](https://img.youtube.com/vi/q8PAD9IS3Ig/maxresdefault.jpg)](https://www.youtube.com/watch?v=q8PAD9IS3Ig)

## Tools Used

- [LlamaIndex](https://www.llamaindex.ai/) Workflows to orchestrate the entire multi-agent setup
- [Ollama](https://ollama.com/) to run the LLM locally (with Ollama Cloud and OpenAI as switchable options)
- [markdown-slides](https://github.com/dadoomer/markdown-slides) and reveal.js for rendering & viewing the presentation
- [Mermaid](https://github.com/mermaid-js/mermaid) to render the diagrams
- [DeckTape](https://github.com/astefanutti/decktape) to export the presentation to PDF
- [Kokoro](https://github.com/hexgrad/kokoro) for fully offline audio narration of the slides
- [FFmpeg](https://www.ffmpeg.org/) to render the full presentation with voiceover

## How to use

- First install the necessary tools

```bash
python -m pip install git+https://gitlab.com/da_doomer/markdown-slides.git
npm install -g @mermaid-js/mermaid-cli
npm install -g decktape
npm install -g puppeteer
puppeteer browsers install chrome
npm install -g repomix   # for building decks from a GitHub repo (--source <url>); or run via npx
```

- Install FFmpeg for your operating system from [here](https://www.ffmpeg.org/download.html)

- Install [Ollama](https://ollama.com/download) and pull a model that supports structured output

```bash
ollama pull qwen2.5:7b   # or llama3.1:8b
```

- Kokoro downloads its voice model (~330 MB) on first run; on some systems it also needs `espeak-ng` installed (e.g. `brew install espeak-ng` / `apt install espeak-ng`)

- Clone the repo

```bash
git clone https://github.com/rsrohan99/presenter.git
cd presenter
```

- Install dependencies

```bash
pip install -r requirements.txt
```

- Copy the example env file (defaults to the local Ollama provider; no keys needed)

```bash
cp .env.example .env
```

- Run the workflow with the topic to create the presentation on

```bash
python run.py "observer design pattern"
```

- Or build a presentation from your own source — a GitHub repo or a local Markdown/PDF file or folder

```bash
python run.py --source https://github.com/owner/repo
python run.py --source ./docs
```

- Choose a different LLM backend or model with `--provider` / `--model`

```bash
python run.py "observer design pattern" --provider ollama-cloud --model qwen2.5:7b
python run.py "observer design pattern" --provider openai --model gpt-4o-mini
```

- Steer the deck with a guidance file (`--guide`). This is a `SKILL.md`/`AGENT.md` in the [Agent Skills format](https://agentskills.io/specification); its Markdown body is injected into the generation prompts. It's optional and additive — great for focusing a broad source on one angle (an example ships in `guides/token-focus/`). If you drop an `AGENT.md` or `SKILL.md` in the project root, it's picked up automatically.

```bash
python run.py --source ./research.md --guide guides/token-focus
```

- Brand the deck with a `DESIGN.md` (`--design`), in the [google-labs-code/design.md](https://github.com/google-labs-code/design.md) format: YAML frontmatter of visual tokens + a Markdown body describing the brand voice. The tokens set the reveal theme, colors, fonts, background, and logo (applied to the HTML **and** the PDF); the voice merges into the content steering. Ready-made themes ship in `designs/`, and a `DESIGN.md` in the project root is picked up automatically (it's gitignored, so keep your personal brand local).

```bash
python run.py "observer design pattern" --design designs/midnight
python run.py "observer design pattern" --design designs/sunrise
```

  Recognized DESIGN.md keys (all optional): `theme` (a reveal base theme: white/black/league/beige/sky/night/serif/simple/solarized/moon/blood), `codeTheme`, `colors` (`background`, `text`|`foreground`, `heading`|`primary`, `accent`|`link`), `typography.heading.fontFamily` / `typography.body.fontFamily` / `typography.body.fontSize`, `fontImports` (a list of Google-Fonts/CSS URLs), `background.image`, `logo` (+ `logoPosition`), `diagramMaxHeight` (cap for diagram images, default `460px`). The Markdown body (Overview / Voice / Do's & Don'ts) steers the wording.

Two rendering niceties apply automatically: a **tall Mermaid diagram is moved onto its own slide** so it isn't cut off (disabled under `--export-video`, which needs one slide per narration), and when a deck is built from `--source`, a **References** slide is appended citing the source repo/file and any reference URLs found in it.

- Presentations are only as good as their source: when a `--source` repo/folder has too little documentation, the run is rejected with a clear message rather than producing a weak deck (add a README/docs and retry).

- Pick a **persona** with `--persona` — a reusable bundle of a narrator voice, tone/style steering, and a **technical-term pronunciation lexicon** so the narration says `kubectl` as "koob control" and `yaml` as "yammel" (the slide text stays unchanged). Ready-made technical personas ship in `personas/` (Cloud Architect, DevOps Engineer, AI Engineer, Researcher, Technical Educator). `--persona auto` picks the best fit for your content; with `--suggest-persona-issue` it offers to file a "new persona needed" GitHub issue when nothing fits. Common terms are pronounced better even without a persona. See [`personas/README.md`](personas/README.md) for the format and how to add your own.

```bash
python run.py "kubernetes operators" --persona personas/devops-engineer --export-video
python run.py --source <repo> --persona auto --export-video
```

- Add `--export-video` argument to generate a full video of the presentation with voiceover (pick a Kokoro voice with `--voice`, or let a `--persona` set it).

```bash
python run.py "observer design pattern" --export-video
```

- After running the workflow, it'll put all the files (slides, video, pdf etc.) inside the `presentations` folder
- There be a folder for each presentation generated
- The interactive HTML for the presentation will be at `presentations/<presentation_folder>/output/index.html`
- The extracted PDF of the presentation will be at `presentations/<presentation_folder>/presentation.pdf`
- The rendered video with voiceover of the presentation will be at `presentations/<presentation_folder>/presentation.mp4`

## Architecture

Presenter is a local, event-driven pipeline built on LlamaIndex Workflows. A topic or a source is turned into a slide structure by the structure agents, each slide is composed in parallel, and the deck is rendered to reveal.js HTML, a PDF, and an optional narrated MP4. It runs local-first (Ollama + Kokoro), with Ollama Cloud and OpenAI as switchable providers.

```mermaid
flowchart LR
  cli[run.py CLI] --> prov[providers.build_llm]
  cli --> ing[ingest: repomix / local]
  cli --> wf[PresenterWorkflow]
  ing --> wf
  wf --> struct[structure + validate + update]
  struct --> slide[slide_maker fan-out]
  slide --> combine[combine_slides]
  combine --> render[mmdc + mdslides + decktape]
  cli -.guide/design.-> wf
  wf -.--export-video.-> vid[Kokoro + ffmpeg -> mp4]
```

Key modules: `run.py` (CLI), `providers.py` (LLM factory), `ingest.py` (repomix + local ingestion), `guide.py` (content steering), `design.py` (DESIGN.md branding), `workflow.py` (`PresenterWorkflow`), `agents/` (structure and slide agents, Kokoro narrator, video workflow), `utils.py` (render fixes, diagram splitting, references slide).

The full design, decisions (ADRs), and diagrams are in [`DESIGN_DOC.md`](DESIGN_DOC.md).
