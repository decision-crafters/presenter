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
