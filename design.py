"""Optional DESIGN.md branding + voice.

A DESIGN.md follows the Agent-friendly design-token format
(https://github.com/google-labs-code/design.md): YAML frontmatter with visual
tokens (``colors``, ``typography``, ``theme``, ``background``, ``logo``) plus a
Markdown body describing the brand voice. We consume a documented subset:

- Visual tokens become a reveal.js base theme + a ``:root { --r-* }`` CSS
  override injected into the rendered deck (so branding also flows into the PDF).
- The Markdown body becomes extra content steering merged into the ``--guide``
  text, so wording/tone matches the brand.

Branding is additive and optional: with no DESIGN.md the deck renders exactly as
before.
"""

import os
import shutil
from dataclasses import dataclass, field
from typing import Optional, Tuple

from guide import _split_frontmatter
from utils import get_presentation_config

DEFAULT_THEME = "white"
DEFAULT_CODE_THEME = "base16/zenburn"

_LOGO_POSITIONS = {
    "top-left": "top:24px;left:24px;",
    "top-right": "top:24px;right:24px;",
    "bottom-left": "bottom:24px;left:24px;",
    "bottom-right": "bottom:24px;right:24px;",
}


@dataclass
class Design:
    tokens: dict = field(default_factory=dict)
    voice: str = ""
    source_dir: Optional[str] = None  # dir of DESIGN.md, for resolving local assets

    @property
    def is_empty(self) -> bool:
        return not self.tokens and not self.voice.strip()


def load_design(path: Optional[str] = None) -> Design:
    """Load a DESIGN.md (file or dir containing one), or auto-discover the root."""
    if path:
        resolved = os.path.join(path, "DESIGN.md") if os.path.isdir(path) else path
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Design file not found: {resolved}")
    else:
        resolved = "DESIGN.md" if os.path.exists("DESIGN.md") else None
        if resolved is None:
            return Design()

    with open(resolved, "r") as f:
        text = f.read()
    frontmatter, body = _split_frontmatter(text)

    tokens = {}
    if frontmatter:
        try:
            import yaml

            tokens = yaml.safe_load(frontmatter) or {}
        except Exception:
            tokens = {}

    name = tokens.get("name") if isinstance(tokens, dict) else None
    print(f"\n> Using design {resolved}" + (f" ({name})" if name else "") + "\n")
    return Design(
        tokens=tokens if isinstance(tokens, dict) else {},
        voice=body,
        source_dir=os.path.dirname(os.path.abspath(resolved)),
    )


# ---- token resolution (brand-arbitrary names -> slide roles, with fallbacks) ----

def _pick(section: dict, *names):
    for n in names:
        if isinstance(section, dict) and section.get(n) not in (None, ""):
            return section[n]
    return None


def _colors(tokens: dict) -> dict:
    c = tokens.get("colors") or {}
    return {
        "background": _pick(c, "background", "bg", "surface"),
        "text": _pick(c, "text", "foreground", "body", "onBackground"),
        "heading": _pick(c, "heading", "primary", "title"),
        "accent": _pick(c, "accent", "link", "secondary"),
    }


def _fonts(tokens: dict) -> dict:
    ty = tokens.get("typography") or {}

    def family(*names):
        for n in names:
            sub = ty.get(n)
            if isinstance(sub, dict) and sub.get("fontFamily"):
                return sub["fontFamily"]
        return None

    body = ty.get("body") or ty.get("main") or {}
    return {
        "heading": family("heading", "display", "title"),
        "body": family("body", "main", "base"),
        "body_size": body.get("fontSize") if isinstance(body, dict) else None,
    }


def _resolve_asset(design: Design, value) -> Tuple[Optional[str], Optional[str]]:
    """Return (href_in_output, local_source_to_copy_or_None)."""
    if not value:
        return None, None
    if str(value).startswith(("http://", "https://", "data:")):
        return value, None
    src = value
    if not os.path.isabs(src) and design.source_dir:
        src = os.path.join(design.source_dir, value)
    return os.path.basename(value), src


# ---- render-side generation ----

def reveal_config_lines(design: Optional[Design]) -> str:
    """The `[comment]: # (...)` reveal config block, from design or defaults."""
    if not design or design.is_empty:
        return get_presentation_config()
    theme = design.tokens.get("theme") or DEFAULT_THEME
    code_theme = (
        design.tokens.get("codeTheme")
        or design.tokens.get("code_theme")
        or DEFAULT_CODE_THEME
    )
    return (
        f"\n[comment]: # (THEME = {theme})\n"
        f"[comment]: # (CODE_THEME = {code_theme})\n"
        "[comment]: # (controls: true)\n"
        "[comment]: # (keyboard: true)\n\n"
    )


def branding_head(design: Design, bg_ref: Optional[str] = None) -> str:
    """`<link>`s for fonts plus a `<style>` overriding reveal CSS variables."""
    tokens = design.tokens
    colors = _colors(tokens)
    fonts = _fonts(tokens)

    rules = []
    if colors["background"]:
        rules.append(f"--r-background-color: {colors['background']};")
    if colors["text"]:
        rules.append(f"--r-main-color: {colors['text']};")
    if colors["heading"]:
        rules.append(f"--r-heading-color: {colors['heading']};")
    if colors["accent"]:
        rules.append(f"--r-link-color: {colors['accent']};")
        rules.append(f"--r-link-color-hover: {colors['accent']};")
    if fonts["body"]:
        rules.append(f"--r-main-font: {fonts['body']};")
    if fonts["heading"]:
        rules.append(f"--r-heading-font: {fonts['heading']};")
    if fonts["body_size"]:
        rules.append(f"--r-main-font-size: {fonts['body_size']};")

    links = "".join(
        f'<link rel="stylesheet" href="{url}">\n'
        for url in (tokens.get("fontImports") or [])
    )

    blocks = []
    if rules:
        blocks.append(":root {\n  " + "\n  ".join(rules) + "\n}")
    if bg_ref:
        blocks.append(
            ".reveal .slide-background { "
            f"background-image: url('{bg_ref}'); "
            "background-size: cover; background-position: center; }"
        )
    style = f"<style>\n{chr(10).join(blocks)}\n</style>\n" if blocks else ""
    return links + style


# reveal.js lays each slide out in a fixed 960x700 coordinate space (then scales
# the whole slide to fit the window), so an absolute px cap in that space is
# reliable, unlike vh which resolves against the un-scaled window.
DEFAULT_DIAGRAM_MAX_HEIGHT = "460px"


def _layout_style(design: Design) -> str:
    """Always-injected CSS that fits diagrams/images inside the slide.

    Mermaid diagrams are embedded as PNGs and can overflow the slide; clamp any
    slide image to the slide box. DESIGN.md may override the height cap via
    ``diagramMaxHeight`` (or ``layout.diagramMaxHeight``).
    """
    layout = design.tokens.get("layout") or {}
    max_h = (
        layout.get("diagramMaxHeight")
        or design.tokens.get("diagramMaxHeight")
        or DEFAULT_DIAGRAM_MAX_HEIGHT
    )
    return (
        "<style>\n"
        ".reveal .slides img { max-width: 100%; max-height: "
        f"{max_h}; width: auto; height: auto; object-fit: contain; }}\n"
        "</style>\n"
    )


def _logo_div(design: Design, logo_ref: Optional[str]) -> str:
    if not logo_ref:
        return ""
    pos = _LOGO_POSITIONS.get(
        design.tokens.get("logoPosition", "top-right"),
        _LOGO_POSITIONS["top-right"],
    )
    return (
        f'<div style="position:fixed;{pos}z-index:40;">'
        f'<img src="{logo_ref}" style="max-height:64px;height:auto;"></div>'
    )


def apply_branding(output_dir: str, design: Optional[Design]) -> None:
    """Fit diagrams to the slide, and (if a design is given) inject brand CSS,
    a logo, and any local assets. Always runs -- the diagram-fit rule applies to
    every deck, branded or not.
    """
    design = design or Design()
    html_file = os.path.join(output_dir, "index.html")
    if not os.path.exists(html_file):
        return

    bg = _pick(design.tokens.get("background") or {}, "image") or design.tokens.get(
        "backgroundImage"
    )
    bg_ref, bg_src = _resolve_asset(design, bg)
    logo_ref, logo_src = _resolve_asset(design, design.tokens.get("logo"))
    for src in (bg_src, logo_src):
        if src and os.path.exists(src):
            shutil.copy(src, os.path.join(output_dir, os.path.basename(src)))

    head = _layout_style(design) + branding_head(design, bg_ref=bg_ref)
    logo_html = _logo_div(design, logo_ref)

    with open(html_file, "r") as f:
        html = f.read()
    if "</head>" in html:
        html = html.replace("</head>", head + "</head>", 1)
    if logo_html and '<div class="reveal">' in html:
        html = html.replace(
            '<div class="reveal">', '<div class="reveal">' + logo_html, 1
        )
    with open(html_file, "w") as f:
        f.write(html)
