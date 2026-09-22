import html
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
    result = _fix_timeline_periods(result)
    return result + "\n\n"


def _fix_timeline_periods(text: str) -> str:
    """Mermaid ``timeline`` uses ``<period> : <event>`` syntax, so a colon inside
    the period token breaks the parser. Models love to use ``HH:MM`` timestamps as
    periods (e.g. ``14:31 : Snapshot saved``), whose colon collides with the
    separator and aborts ``mmdc`` for the whole deck. Rewrite ``HH:MM`` -> ``HH.MM``
    inside timeline blocks only, leaving the ``:`` event separators untouched."""

    def _fix_block(m: "re.Match") -> str:
        body = m.group(1)
        if not re.match(r"\s*timeline\b", body):
            return m.group(0)
        body = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1.\2", body)
        return "```mermaid" + body + "```"

    return re.sub(r"(?s)```mermaid(.*?)```", _fix_block, text)


# Only Mermaid diagram PNGs are eligible for the own-slide split; fetched photos
# (.jpg) and demo GIFs stay with their own slide.
_IMG_RE = re.compile(r"!\[[^\]]*\]\(\./media/([^)]+\.png)\)")
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


def sources_slide(citations, urls=None) -> str:
    """Closing 'Sources' slide for a research/document deck: the works the
    source itself cites, then any URLs found in it. Rendered as a compact HTML
    list (research write-ups often cite 10+ works, which overflow at the deck's
    normal bullet size). Returns '' when empty."""
    items = list(citations or []) + [u for u in (urls or []) if u not in (citations or [])]
    if not items:
        return ""
    lis = "\n".join(f"<li>{html.escape(item)}</li>" for item in items)
    size = "0.6em" if len(items) > 8 else "0.8em"
    body = f'<ul style="font-size:{size}; line-height:1.35">\n{lis}\n</ul>'
    return SLIDES_SEPARATOR + "### Sources\n\n" + body + "\n"


def demo_slides(items) -> str:
    """One 'Demo' slide per detected recording. ``items`` is a list of
    ``{"title", "file"}`` where ``file`` is a basename already copied into
    ``media/``. GIFs animate in the HTML deck (static frame in the PDF). Empty
    input yields '' so nothing is appended."""
    out = []
    for item in items or []:
        title = (item.get("title") or "Demo").strip()
        media_file = item.get("file")
        if not media_file:
            continue
        out.append(f"### Demo — {title}\n\n![](./media/{media_file})")
    if not out:
        return ""
    return SLIDES_SEPARATOR + SLIDES_SEPARATOR.join(out) + "\n"


def cta_slide(source, demo_urls=None) -> str:
    """A closing 'Get the Code' call-to-action citing the repo/source and any
    demo links. Returns '' when there is no source to point at."""
    if not source:
        return ""
    lines = ["### Get the Code", "", f"- Repo: {source}"]
    for url in demo_urls or []:
        lines.append(f"- Demo: {url}")
    return SLIDES_SEPARATOR + "\n".join(lines) + "\n"
