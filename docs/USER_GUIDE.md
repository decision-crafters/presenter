# Presenter User Guide

**Version**: 0.3.0
**Last Updated**: 2026-09-21
**Maintainers**: Presenter project

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Features](#features)
4. [Troubleshooting](#troubleshooting)
5. [FAQ](#faq)
6. [Support](#support)
7. [Appendix](#appendix)

---

## Introduction

### What is Presenter?

Presenter is a command line tool that turns a topic, a GitHub repository, or a
research document into a narrated slide deck. Each run produces a reveal.js HTML
deck and a PDF. An optional step produces a narrated MP4. Presenter runs local
first: the default language model is a local Ollama model, and narration uses the
offline Kokoro voice, so you can build a full deck without a paid cloud service.

### Who should use this guide?

This guide is for people who are comfortable running commands in a terminal and
want to convert a topic or existing work into a talk.

### Scope

This guide covers:

- ✅ Installation and setup.
- ✅ The three ways to build a deck.
- ✅ Provider selection, length, steering, branding, images, and video.
- ✅ Personas, technical-term pronunciation, and demo embedding.
- ✅ Finding and opening the output.
- ❌ Internal architecture and design decisions. Those live in `DESIGN_DOC.md`.

---

## Getting Started

### Prerequisites

Before you begin, confirm each item:

- [ ] **Python 3.11**. The narration package does not support Python 3.13 or later.
- [ ] **One language model provider**, one of:
  - A local **Ollama** daemon with a structured-output model pulled, for example `qwen2.5:7b`.
  - An **Ollama Cloud** API key.
  - An **OpenAI** API key.
- [ ] **Command line tools on PATH**: `mmdc`, `mdslides`, `decktape`, `ffmpeg`, `ffprobe`, `repomix`, `git`.
- [ ] **`espeak-ng`** is optional. Kokoro narrates English without it. Install it only for better pronunciation of rare, out-of-dictionary words.

### First-time setup

#### Step 1: Create a virtual environment

1. Open a terminal in the project folder.
2. Run `python3.11 -m venv .venv`.
3. Run `source .venv/bin/activate`.

**✅ Verification**: `python --version` reports a 3.11 version.

#### Step 2: Install the dependencies

1. Run `pip install -r requirements.txt`.
2. Run `pip install "git+https://gitlab.com/da_doomer/markdown-slides.git"` to install `mdslides`.
3. Run `npm install -g @mermaid-js/mermaid-cli decktape repomix`.
4. Install `ffmpeg` from the FFmpeg website.

#### Step 3: Configure a provider

1. Run `cp .env.example .env`.
2. For a local model, install Ollama and run `ollama pull qwen2.5:7b`.
3. For a cloud model, set `OLLAMA_CLOUD_API_KEY` or `OPENAI_API_KEY` in `.env`.

**✅ Verification**: `.env` contains the key for your chosen provider.

### Quick start (a few minutes)

1. Run `python run.py "the observer design pattern"`.
2. Wait for the run to finish.
3. Open `presentations/observer_design_pattern/output/index.html` in a browser.
4. Open `presentations/observer_design_pattern/presentation.pdf` to read the PDF.

The last line of a successful run starts with `PRESENTER_RESULT` and lists the
output paths.

---

## Features

### Build from a topic

#### Overview

Give Presenter a short topic. Presenter writes the structure, the slides, and the
narration for that topic.

#### How to use

1. Run `python run.py "your topic here"`.
2. Wait for the deck to render.

**✅ Verification**: a new folder appears under `presentations/`.

💡 **Tip**: Keep the topic focused. A narrow topic produces a sharper deck.

### Build from a GitHub repo or a research file

#### Overview

Point Presenter at a repository or a document. Presenter reads the source and
derives the title and the slide structure. You do not supply a topic.

#### How to use

1. For a repository, run `python run.py --source https://github.com/owner/repo`.
2. For a local file or folder, run `python run.py --source ./research.md`.

**✅ Verification**: the run prints the ingested document count, then builds the deck.

💡 **Tip**: A repository must contain real documentation. Presenter reads Markdown,
not source code.

### Choose the language model provider and model

#### Overview

Presenter supports a local Ollama model, Ollama Cloud, and OpenAI. The default is
the local Ollama provider.

#### How to use

1. For local Ollama, run `python run.py "your topic"`.
2. For Ollama Cloud, run `python run.py "your topic" --provider ollama-cloud --model gpt-oss:120b`.
3. For OpenAI, run `python run.py "your topic" --provider openai --model gpt-4o-mini`.

💡 **Tip**: The model must support structured output. Weak models can fail to return
valid slide data.

### Set the length

#### Overview

The default target is 15 slides, about 15 minutes of narrated content.

#### How to use

1. Run `python run.py "your topic" --slides 20` to request a longer deck.

💡 **Tip**: Presenter treats the number as a target. A rich topic can produce more.

### Focus the angle with a guide file

#### Overview

A guide file steers the content. Use it to focus a broad source on one angle. The
guide follows the Agent Skills format (`SKILL.md` or `AGENT.md`).

#### How to use

1. Run `python run.py --source ./research.md --guide guides/token-focus`.

💡 **Tip**: A `SKILL.md` or `AGENT.md` in the project root is picked up automatically.

### Brand the deck with a DESIGN.md

#### Overview

A `DESIGN.md` file sets the theme, colors, fonts, background, and logo. The
branding applies to the HTML and the PDF. The two shipped themes are `midnight`
and `sunrise`.

#### How to use

1. Run `python run.py "your topic" --design designs/midnight`.
2. To brand every deck, save your own `DESIGN.md` in the project root.

💡 **Tip**: The Markdown body of a `DESIGN.md` also steers the wording toward the
brand voice.

### Add inline images

#### Overview

Presenter can add a photo to slides that have no diagram. Images are off by
default.

#### How to use

1. For no-key images, run `python run.py "your topic" --images pollinations`.
2. For real stock photos, set `PEXELS_API_KEY` in `.env` and run `python run.py "your topic" --images pexels`.

⚠️ **Warning**: Pollinations is slow. Each image takes about 20 to 40 seconds.

### Export a narrated video

#### Overview

Presenter can render an MP4 with narration for every slide.

#### How to use

1. Run `python run.py "your topic" --export-video`.
2. To pick a narration voice, add `--voice af_heart`.

**✅ Verification**: `presentations/<slug>/presentation.mp4` exists.

### Choose a persona

#### Overview

A persona is a reusable bundle of a narrator voice, a tone and style, and a
pronunciation lexicon for technical terms. A persona keeps the narration
consistent and makes the audio say hard words correctly. Five personas ship with
Presenter: Cloud Architect, DevOps Engineer, AI Engineer, Researcher, and
Technical Educator.

#### How to use

1. Run `python run.py "kubernetes operators" --persona personas/devops-engineer --export-video`.
2. To let Presenter pick the best fit, run `python run.py --source https://github.com/owner/repo --persona auto --export-video`.

**✅ Verification**: the run prints a line that starts with `> Using persona`.

💡 **Tip**: An explicit `--voice` or `--lang` flag overrides the persona, and the
persona overrides the built-in default. To add your own persona, follow
`personas/README.md`.

### Pronounce technical terms correctly

#### Overview

Presenter rewrites technical terms to a spoken form at narration time only. The
audio says "koob control" for `kubectl`, "yammel" for `yaml`, and "Jupiter" for
`Jupyter`. The slide text and the speaker notes keep the real spelling. About 30
common terms are always corrected. A persona adds terms for its field and can
override the built-in forms.

#### How to use

1. Run any `--export-video` command. The built-in terms apply with no flag.
2. Add `--persona personas/ai-engineer` to apply a domain lexicon.

💡 **Tip**: To fix a term Presenter still gets wrong, add it to a persona under
`pronunciations`. See `personas/README.md`.

### Match the narrator voice to a gender

#### Overview

A persona declares a gender, and each Kokoro voice carries a gender. When a
persona sets a voice that does not match its gender, Presenter switches to a
matching default voice and prints a note. The narrator never speaks in the wrong
gender.

#### How to use

1. Set `gender` and `voice` in a `PERSONA.md`.
2. Run the deck.

**✅ Verification**: the console prints an auto-correct note only when the voice and
gender disagree.

### Auto-select a persona and report a gap

#### Overview

The `--persona auto` option matches the content to the closest persona. When no
persona fits, Presenter can open a GitHub issue that requests a new persona for
the detected domain.

#### How to use

1. Run `python run.py --source https://github.com/owner/repo --persona auto`.
2. To file a gap issue, add `--suggest-persona-issue`.
3. To choose the target repository, add `--persona-issue-repo owner/name`.

⚠️ **Warning**: Filing an issue is opt-in. In an interactive terminal, Presenter
asks for confirmation first.

### Show a demo recording from a source repo

#### Overview

When a source repository embeds a demo recording in its README, Presenter uses
it. Presenter downloads the recording, adds a Demo slide, and, for a video,
splices the demo in as an animated clip with a spoken walkthrough. The
walkthrough follows the repository's VHS tape commands when Presenter can fetch
them, and it runs for the length of the demo. Supported formats are GIF, MP4,
and WebM.

#### How to use

1. Run `python run.py --source https://github.com/owner/repo --export-video`.
2. Open the deck or the video to see the demo.

**✅ Verification**: a `demos.json` file appears in the deck folder, and the `media`
folder holds the downloaded recording.

💡 **Tip**: The demo animates in the HTML deck and in the video. The PDF shows one
still frame.

### Cite the source and close with a call to action

#### Overview

For a source based deck, Presenter adds a small footer with the repository on
every slide. Presenter ends the deck with a "Get the Code" slide that lists the
repository and the demo links. The exported video ends on that same closing
slide.

#### How to use

1. Run `python run.py --source https://github.com/owner/repo --export-video`.
2. Open the last slide of the deck, or the end of the video, to see the links.

### Find and open the output

#### Overview

Every run writes to a folder named after the deck under `presentations/`.

#### How to use

1. Open `presentations/<slug>/output/index.html` for the interactive deck.
2. Open `presentations/<slug>/presentation.pdf` for the PDF.
3. Read the `PRESENTER_RESULT` line for the exact paths.

---

## Troubleshooting

### Common issues

#### Issue: The install fails on the narration package

**Symptoms**: `pip install` reports that no matching version of `kokoro` was found.
**Cause**: The Python version is 3.13 or later.
**Solution**:
1. Create the virtual environment with Python 3.11.
2. Reinstall the dependencies.

**Prevention**: Always create the environment with `python3.11 -m venv .venv`.

#### Issue: The run stops with a provider error

**Symptoms**: The run reports a missing key or a refused connection.
**Cause**: The selected provider is not configured.
**Solution**:
1. For local Ollama, start the Ollama daemon and pull a model.
2. For Ollama Cloud, set `OLLAMA_CLOUD_API_KEY` in `.env`.
3. For OpenAI, set `OPENAI_API_KEY` in `.env`.

#### Issue: The render step fails

**Symptoms**: The run reports that `mmdc`, `mdslides`, or `decktape` produced no output.
**Cause**: A render tool is missing from PATH.
**Solution**:
1. Confirm the tool is installed.
2. Confirm the tool is on PATH.
3. Run the command again.

#### Issue: A source is rejected

**Symptoms**: The run reports insufficient documentation.
**Cause**: The source contains too little readable text.
**Solution**:
1. Add a README or documentation to the source.
2. Run the command again.

#### Issue: The video export fails

**Symptoms**: Narration does not render.
**Cause**: A required tool is missing from PATH, or the virtual environment is not active, so `mdslides`, `ffmpeg`, or Kokoro cannot run.
**Solution**:
1. Activate the virtual environment so `mdslides` and Kokoro are on PATH.
2. Confirm `ffmpeg` and `ffprobe` are installed.
3. Run the command with `--export-video` again.

### Error messages

| Message | Meaning | Solution |
|---------|---------|----------|
| `Render failed: mdslides did not produce ...` | The HTML render tool did not run or failed. | Install `markdown-slides` and confirm `mdslides` is on PATH. |
| `PDF export failed: decktape did not produce ...` | The PDF export tool did not run or failed. | Install `decktape` and its Chrome, and confirm it is on PATH. |
| `Diagram render failed: mmdc did not produce ...` | The diagram tool did not run. | Install `@mermaid-js/mermaid-cli` and confirm `mmdc` is on PATH. |
| `Insufficient documentation in <source> ...` | The source has too little text for a deck. | Add a README or docs, then retry. |
| `OLLAMA_CLOUD_API_KEY is required ...` | The cloud provider has no key. | Set `OLLAMA_CLOUD_API_KEY` in `.env`. |
| `No ingestible files ... found in <source>` | The source folder has no Markdown or text. | Point at a documented source. |

### System requirements

**Minimum**:

- Python 3.11.
- A configured language model provider.
- The render command line tools on PATH.

**Recommended**:

- A capable structured-output model, for example `qwen2.5:7b` or a strong cloud model.
- `espeak-ng` is optional. It improves pronunciation of rare, out-of-dictionary words only.

---

## FAQ

**Q: Does Presenter need an internet connection?**
A: A local Ollama model needs no internet. Ollama Cloud, OpenAI, a repository
source, and the image feature all need internet.

**Q: Is Presenter free to run?**
A: Yes, when you use a local Ollama model and the offline Kokoro voice.

**Q: How long is a deck?**
A: The default target is 15 slides. Use `--slides` to change the target.

**Q: Can I customize the branding?**
A: Yes. Use a `DESIGN.md` file with `--design`, or save one in the project root.

**Q: Where does the output go?**
A: Into `presentations/<slug>/`. The interactive deck is `output/index.html`. The
PDF is `presentation.pdf`.

**Q: Can Presenter run fully offline?**
A: Yes, for a topic-based deck with a local Ollama model. A repository source or
the image feature requires internet.

---

## Support

Presenter is an open source project.

- **Source and issues**: the project GitHub repository.
- **Reference documentation**: `README.md` for setup, `DESIGN_DOC.md` for the design.

Report a problem by opening an issue on the repository. Include the command you
ran and the full output.

---

## Appendix

### Command reference

| Flag | Meaning | Default |
|------|---------|---------|
| `topic` | The presentation topic. Omit it when you use `--source`. | none |
| `--source` | A GitHub repo URL or a local Markdown or PDF file or folder. The title and structure are derived from the source. | none |
| `--provider` | The language model provider: `ollama`, `ollama-cloud`, or `openai`. | `ollama` |
| `--model` | The model name. | `qwen2.5:7b` |
| `--slides` | The target number of slides. | `15` |
| `--guide` | A `SKILL.md` or `AGENT.md` guide file that steers content. | auto-discover |
| `--design` | A `DESIGN.md` file that brands the deck. | auto-discover |
| `--images` | Add inline photos: `pollinations`, `pexels`, or `picsum`. | off |
| `--voice` | The Kokoro narration voice. | persona voice, then `af_heart` |
| `--lang` | The Kokoro language code. | persona lang, then `a` |
| `--persona` | A `PERSONA.md` file or directory, or `auto` to pick the best fit. Sets the voice, tone, and pronunciation. | none |
| `--suggest-persona-issue` | With `--persona auto`, offer to file a GitHub issue when no persona fits. | off |
| `--persona-issue-repo` | The target repository for a persona gap issue. | current repo |
| `--export-video` | Export a narrated MP4. | off |

### Glossary

- **Deck**: A set of slides. Presenter produces an HTML deck and a PDF.
- **reveal.js**: The HTML presentation framework used for the deck.
- **Mermaid**: A text format for diagrams. Presenter renders it to images.
- **Provider**: The service that runs the language model. Local Ollama, Ollama Cloud, or OpenAI.
- **Ollama**: A local server for language models, with an optional cloud tier.
- **Kokoro**: An offline text to speech model used for narration.
- **repomix**: A tool that packs a repository into one text file for ingestion.
- **DESIGN.md**: A brand and voice file for a deck.
- **Guide**: A `SKILL.md` or `AGENT.md` file that focuses the content.
- **Persona**: A `PERSONA.md` bundle of a narrator voice, a tone and style, and a pronunciation lexicon.
- **Pronunciation lexicon**: A map from a technical term to its spoken form, applied to the narration audio only.
- **VHS tape**: A `.tape` script that records a terminal demo. Presenter reads its commands to narrate the demo.
- **Get the Code**: The closing call-to-action slide that lists the repository and demo links.
- **PRESENTER_RESULT**: The final machine-readable line that lists the output paths.

### Version history

| Version | Date | Changes |
|---------|------|---------|
| 0.2.0 | 2026-09-21 | First user guide. |
| 0.3.0 | 2026-09-21 | Added personas, technical-term pronunciation, voice and gender matching, persona auto-select with a gap issue, demo embedding with a narrated walkthrough, a source footer, and a closing call-to-action. |
