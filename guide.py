"""Optional guidance-file steering.

Reads a guidance file that steers presentation generation -- a marquee use is
focusing a broad source ("make this deck about cutting the token bill") or
setting a house style. The file follows the Agent Skills spec
(https://agentskills.io/specification): a ``SKILL.md`` with optional YAML
frontmatter (``name``/``description``/...) plus a free-form Markdown body, or a
plain ``AGENT.md`` with no frontmatter. Only the Markdown body is used as
steering text; it is injected into the generation prompts.

Steering is additive and optional: with no guide (the default) the prompts
render exactly as they do today.
"""

import os
from typing import Optional

# Files auto-discovered in the project root when --guide is not given.
AUTO_DISCOVERY_NAMES = ("AGENT.md", "SKILL.md")


def _split_frontmatter(text: str) -> tuple[Optional[str], str]:
    """Return (frontmatter_yaml_or_None, body). Handles a leading ``---`` fence."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].strip() == "---":
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == "---":
                fm = "\n".join(lines[i + 1 : j])
                body = "\n".join(lines[j + 1 :])
                return fm, body.strip()
    return None, text.strip()


def _guide_name(frontmatter: Optional[str]) -> Optional[str]:
    if not frontmatter:
        return None
    try:
        import yaml

        data = yaml.safe_load(frontmatter) or {}
        name = data.get("name")
        return str(name) if name else None
    except Exception:
        return None


def format_steering(guide: str) -> str:
    """Wrap the guide body as a prompt block, or "" when there is no guide."""
    if not guide or not guide.strip():
        return ""
    return (
        "\n\nSTEERING GUIDANCE (follow strictly; overrides conflicting "
        "defaults above):\n" + guide.strip() + "\n"
    )


def _resolve_file(path: str) -> str:
    """A SKILL.md/AGENT.md file, or a skill directory containing SKILL.md."""
    if os.path.isdir(path):
        return os.path.join(path, "SKILL.md")
    return path


def load_guide(path: Optional[str] = None) -> str:
    """Load the steering body from a guide file.

    ``path`` explicit -> must exist (fail loudly). ``path`` None -> auto-discover
    ``AGENT.md``/``SKILL.md`` in the project root; return "" if none is found.
    """
    if path:
        resolved = _resolve_file(path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Guide file not found: {resolved}")
    else:
        resolved = next(
            (n for n in AUTO_DISCOVERY_NAMES if os.path.exists(n)), None
        )
        if resolved is None:
            return ""

    with open(resolved, "r") as f:
        text = f.read()

    frontmatter, body = _split_frontmatter(text)
    if body:
        name = _guide_name(frontmatter)
        label = f" ({name})" if name else ""
        print(f"\n> Using guidance from {resolved}{label}\n")
    return body
