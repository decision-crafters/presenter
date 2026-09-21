import os
import re

# Slide-break directive that markdown-slides uses (kept in sync with workflow).
SLIDES_SEPARATOR = "\n\n[comment]: # (!!!)\n\n"

PRESENTATION_CONFIG = """
[comment]: # (CODE_THEME = base16/zenburn)
[comment]: # (controls: true)
[comment]: # (keyboard: true)

"""


def get_presentation_config() -> str:
    return PRESENTATION_CONFIG


def get_safe_foldername(topic: str) -> str:
    # return topic.replace(" ", "_").lower()
    return re.sub(r"[^a-zA-Z0-9]", "_", topic).lower()


def sanitize_markdown(text: str) -> str:
    pattern = r"(?s)(```mermaid.*?)(^.*?Note over.*?$)(.*?```)"
    result = re.sub(
        pattern,
        lambda m: m.group(1)
        + re.sub(r"^.*?Note over.*?\n?", "", m.group(2), flags=re.M)
        + m.group(3),
        text,
        flags=re.M,
    )
    pattern2 = r"^(#{1,2})\s"
    result = re.sub(pattern2, r"### ", result, flags=re.M)
    pattern3 = r"!\[.+\]\(\./(.*?\.png)\)"
    result = re.sub(pattern3, r"![diagram](./media/\1)", result, flags=re.M)
    result = result.replace("flowchart TD", "flowchart LR")
    return result + "\n\n"


_IMG_RE = re.compile(r"!\[[^\]]*\]\(\./media/([^)]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)


def _diagram_is_oversized(path: str) -> bool:
    """A diagram earns its own slide when it is tall (would crowd a shared slide)."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return False
    return (h > 300 and h / max(w, 1) > 1.1) or h > 560


def split_oversized_diagrams(markdown: str, media_dir: str) -> str:
    """Move any oversized diagram onto its own slide (keeping the slide title).

    Diagrams are embedded as rendered PNGs; a tall one crowds the slide, so it
    gets a dedicated slide. Only affects the visual deck (HTML/PDF).
    """
    slides = markdown.split(SLIDES_SEPARATOR)
    out = []
    for slide in slides:
        oversized = [
            m.group(0)
            for m in _IMG_RE.finditer(slide)
            if _diagram_is_oversized(os.path.join(media_dir, m.group(1)))
        ]
        if not oversized:
            out.append(slide)
            continue
        heading = _HEADING_RE.search(slide)
        title = heading.group(0) if heading else ""
        body = slide
        for img in oversized:
            body = body.replace(img, "")
        body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
        out.append(body)
        for img in oversized:
            out.append(f"{title}\n\n{img}\n" if title else f"{img}\n")
    return SLIDES_SEPARATOR.join(out)


def references_slide(source, urls) -> str:
    """A trailing 'References' slide citing the source + reference URLs (or '')."""
    lines = ["### References", ""]
    if source:
        lines.append(f"- Source: {source}")
    for url in urls or []:
        lines.append(f"- {url}")
    if len(lines) <= 2:  # nothing to cite
        return ""
    return SLIDES_SEPARATOR + "\n".join(lines) + "\n"
