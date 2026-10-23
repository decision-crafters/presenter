"""Slide layout archetypes: a few story patterns beyond "title + centered bullets".

Each slide may name one layout. The slide writer is told the Markdown *shape*
that layout needs (e.g. a numbered list, not a diagram), the workflow tags the
slide with a Reveal ``<!-- .slide: class="layout-<name>" -->`` comment (which
mdslides passes through and Reveal puts on the slide's ``<section>``), and
``layout_css`` styles it from the brand colors. A slide with no layout renders
exactly as before.

The three patterns (Presenter design determination, Option A at 3 patterns):
- ``boundary``  architecture boundary: numbered parts inside a boundary, feeding one outcome
- ``tradeoff``  a decision between two options, compared side by side
- ``result``    a measured result: one headline number, then before vs. after
"""

import re

LAYOUTS = {
    "boundary": (
        "a system boundary with numbered parts. Markdown shape: the ### title; one "
        "short sentence; a numbered list of 3-8 parts, each 2-6 words; then one "
        "'> ' blockquote line naming what the parts feed into, starting with that "
        "thing in **bold** (e.g. '> **Governor** — providers report state.'). No "
        "diagram on this layout: the list IS the diagram."
    ),
    "tradeoff": (
        "a decision between two options. Markdown shape: the ### title; one short "
        "sentence stating the decision; a 2-column table whose header row names the "
        "two options and whose 2-4 rows compare them in 1-5 words per cell; "
        "optionally one '> ' blockquote line with the verdict. No diagram."
    ),
    "result": (
        "a measured result. Markdown shape: the ### title; one '> ' blockquote line "
        "that starts with the headline number in **bold** (e.g. '> **0 of 5** "
        "actions were authorized'); then a 2-column table with header 'Before | "
        "After' and 1-3 rows of short facts. Only use numbers from the source. No diagram."
    ),
}

LAYOUT_INSTRUCTION = (
    "\nLAYOUT: you may set `layout` to one of these when the slide's idea fits it "
    "naturally, and then the content MUST follow that layout's shape exactly:\n"
    + "\n".join(f"- {name}: {desc}" for name, desc in LAYOUTS.items())
    + "\nOtherwise leave `layout` empty for the default layout. Use a layout only "
    "where it makes the idea clearer, not on every slide, and never on the first slide."
)


def normalize_layout(value: str | None) -> str | None:
    """The layout name if it is a known one, else None (default layout)."""
    name = (value or "").strip().lower()
    return name if name in LAYOUTS else None


def _block_kind(line: str) -> str:
    s = line.lstrip()
    if s.startswith("#"):
        return "heading"
    if s.startswith(">"):
        return "quote"
    if s.startswith("|"):
        return "table"
    if re.match(r"(\d+[.)]|[-*+])\s", s):
        return "list"
    return "text"


def separate_blocks(content: str) -> str:
    """Put a blank line between adjacent blocks of different kinds.

    Models often write a layout slide with no blank lines, and Markdown then
    folds a following '> takeaway' into the last list item (lazy continuation),
    so the layout's parts render inside each other.
    """
    out: list[str] = []
    prev = None
    for line in content.splitlines():
        if not line.strip():
            out.append(line)
            prev = None
            continue
        kind = _block_kind(line)
        if prev is not None and kind != prev:
            out.append("")
        out.append(line)
        prev = kind
    return "\n".join(out)


def tag_slide(content: str, layout: str | None) -> str:
    """Prefix slide Markdown with the Reveal class comment for its layout."""
    name = normalize_layout(layout)
    if not name:
        return content
    return f'<!-- .slide: class="layout-{name}" -->\n{separate_blocks(content)}'


def layouts_enabled(design, flag: bool = True) -> bool:
    """On by default; off with ``--no-layouts`` or ``layouts: false`` in DESIGN.md."""
    if not flag:
        return False
    tokens = getattr(design, "tokens", None) or {}
    return tokens.get("layouts", True) is not False


def layout_css(design=None) -> str:
    """CSS for every layout, colored from the brand (with neutral fallbacks)."""
    from design import _colors, _fonts, _mix

    tokens = getattr(design, "tokens", None) or {}
    c = tokens.get("colors") or {}
    col = _colors(tokens)
    bg = col["background"] or "#191919"
    text = col["text"] or col["heading"] or "#e6edf3"
    accent = col["accent"] or "#42affa"
    edge = c.get("secondary") or accent
    card = c.get("tertiary") or _mix(bg, text, 0.16)
    muted = _mix(text, bg, 0.35)
    head_font = _fonts(tokens)["heading"] or "inherit"

    s = ".reveal .slides section"
    return f"""<style>
/* ---- shared: left-aligned, accent-barred title ---- */
{s}[class*="layout-"]{{text-align:left;width:100%}}
{s}[class*="layout-"] h3{{font-size:1.3em;margin:0 0 .2em;padding-left:.45em;border-left:10px solid {accent};text-align:left}}
{s}[class*="layout-"] > p{{font-size:.62em;color:{muted};margin:0 0 1em .1em}}
{s}[class*="layout-"] > p strong{{color:{accent}}}
{s}[class*="layout-"] blockquote{{width:100%;box-sizing:border-box;margin:24px 0 0;padding:14px 24px;background:{accent};color:{bg};font-style:normal;font-size:.6em;border-radius:12px;box-shadow:none;position:relative}}
{s}[class*="layout-"] blockquote p{{margin:0}}
{s}[class*="layout-"] blockquote strong{{font-family:{head_font};font-weight:800;letter-spacing:.03em}}
{s}[class*="layout-"] table{{width:100%;border-collapse:separate;border-spacing:12px 0;font-size:.58em;margin:0}}
{s}[class*="layout-"] th,{s}[class*="layout-"] td{{border:0;padding:10px 16px;text-align:left}}
{s}[class*="layout-"] td{{background:{card};color:{text}}}
{s}[class*="layout-"] tr:not(:last-child) td{{border-bottom:2px solid {bg}}}
/* ---- boundary: numbered parts inside a dashed boundary, feeding one outcome ---- */
{s}.layout-boundary ol{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;list-style:none;counter-reset:part;margin:0;padding:22px 18px 18px;border:2px dashed {edge};border-radius:16px;width:100%;box-sizing:border-box}}
{s}.layout-boundary ol:has(> li:nth-child(2):last-child){{grid-template-columns:repeat(2,1fr)}}
{s}.layout-boundary ol:has(> li:nth-child(3):last-child),{s}.layout-boundary ol:has(> li:nth-child(5):last-child),{s}.layout-boundary ol:has(> li:nth-child(6):last-child){{grid-template-columns:repeat(3,1fr)}}
{s}.layout-boundary ol li{{counter-increment:part;background:{card};border-radius:10px;padding:14px 14px 16px;font-size:.5em;line-height:1.25;margin:0;color:{text}}}
{s}.layout-boundary ol li::before{{content:counter(part,decimal-leading-zero);display:block;font-family:{head_font};font-weight:800;font-size:1.35em;color:{accent};margin-bottom:.25em}}
{s}.layout-boundary blockquote::before{{content:"\\25BC";position:absolute;top:-28px;left:50%;transform:translateX(-50%);color:{edge};font-size:22px}}
{s}.layout-boundary blockquote strong{{text-transform:uppercase}}
/* ---- tradeoff: two options as side-by-side cards ---- */
{s}.layout-tradeoff th{{font-family:{head_font};font-weight:800;font-size:1.15em;border-radius:12px 12px 0 0;background:{edge};color:{bg}}}
{s}.layout-tradeoff th:last-child{{background:{accent}}}
{s}.layout-tradeoff tr:last-child td{{border-radius:0 0 12px 12px}}
/* ---- result: one headline number, then before vs. after ---- */
{s}.layout-result blockquote{{background:transparent;color:{text};padding:0;margin:0 0 22px;font-size:.9em;border-left:0}}
{s}.layout-result blockquote strong{{display:block;font-size:2.4em;line-height:1.05;color:{accent}}}
{s}.layout-result th{{font-family:{head_font};font-weight:800;font-size:1em;color:{muted};background:transparent}}
{s}.layout-result th:last-child{{color:{accent}}}
{s}.layout-result td:first-child{{color:{muted};text-decoration:line-through;text-decoration-color:{muted}}}
{s}.layout-result td:last-child{{outline:2px solid {accent};outline-offset:-2px}}
</style>
"""
