"""Shared video-export settings, resolved from the brand's DESIGN.md ``video:`` block.

One place for settings that shape the rendered MP4. The closing line (the spoken
repo-deck outro), the end-screen hold, and the video resolution live here; #10
(watermark/channel overlay) extends this same block:

    video:
      closingLine: "The repo is linked below. Clone it and run it."
      holdSeconds: 4
      resolution: 1080p        # 480p | 720p | 1080p | 1440p | 2160p | WxH
      watermark:               # corner bug overlaid on the exported video (#10)
        image: logo.png        # optional; defaults to the design's `logo`
        position: bottom-right # top-left | top-right | bottom-left | bottom-right
        height: 64             # px at 1080p, scaled to the render resolution
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

DEFAULT_HOLD_SECONDS = 4.0

# Named video sizes (16:9). ``resolution`` accepts a name or an explicit
# ``WIDTHxHEIGHT`` string; both normalize to an even (width, height) pair.
RESOLUTIONS = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
    "4k": (3840, 2160),
}
DEFAULT_RESOLUTION = RESOLUTIONS["1080p"]  # 1920x1080 (issue #8)

# The pre-configuration repo-deck outro, kept as the fallback when a brand
# declares no closing line.
DEFAULT_CLOSING_LINE = (
    "That wraps up the walkthrough. The code, demos, and documentation are all "
    "linked on screen — grab them from the project's repository."
)


def parse_resolution(value, default: tuple[int, int] = DEFAULT_RESOLUTION) -> tuple[int, int]:
    """Normalize a size to an even ``(width, height)`` pair.

    Accepts a name (``"1080p"``), a ``"WIDTHxHEIGHT"`` string, or a
    ``[width, height]`` sequence. Anything unset/malformed falls back to
    ``default`` (so a bad value can never break the render).
    """
    if value is None:
        return default
    if isinstance(value, str):
        key = value.strip().lower().replace(" ", "")
        if key in RESOLUTIONS:
            return RESOLUTIONS[key]
        m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", key)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if w % 2 == 0 and h % 2 == 0:
                return (w, h)
        return default
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            w, h = int(value[0]), int(value[1])
            if w % 2 == 0 and h % 2 == 0:
                return (w, h)
        except (TypeError, ValueError):
            pass
    return default


@dataclass
class VideoSettings:
    closing_line: str = DEFAULT_CLOSING_LINE
    hold_seconds: float = DEFAULT_HOLD_SECONDS
    resolution: tuple[int, int] = DEFAULT_RESOLUTION
    watermark: Optional["WatermarkSettings"] = None


@dataclass
class WatermarkSettings:
    """A corner bug overlaid on the exported video (issue #10).

    ``image`` is a resolved local path to a PNG (a URL or SVG is skipped with a
    warning). ``height`` is in pixels at the 1080p reference and scales with the
    render resolution.
    """
    image: str | None = None
    position: str = "bottom-right"
    height: int = 64


# ffmpeg ``overlay`` expressions for each corner, in the filter_complex
# coordinate space (W/H = main video, w/h = the scaled watermark).
_WATERMARK_POSITIONS = {
    "top-left": "24:24",
    "top-right": "W-w-24:24",
    "bottom-left": "24:H-h-24",
    "bottom-right": "W-w-24:H-h-24",
}


def watermark_filter(watermark: WatermarkSettings, video_height: int) -> str:
    """The ffmpeg ``-filter_complex`` that scales the bug and overlays it in its
    corner. ``video_height`` is the render height (e.g. 1080)."""
    h = max(16, round(watermark.height * video_height / 1080))
    pos = _WATERMARK_POSITIONS.get(watermark.position, _WATERMARK_POSITIONS["bottom-right"])
    return f"[1:v]scale=-1:{h}[wm];[0:v][wm]overlay={pos}"


def video_settings(design) -> VideoSettings:
    """Resolve the brand's ``video:`` tokens (or defaults) into VideoSettings."""
    tokens = getattr(design, "tokens", None) or {}
    v = tokens.get("video") if isinstance(tokens, dict) else None
    if not isinstance(v, dict):
        v = {}
    closing = (v.get("closingLine") or v.get("closing_line") or "").strip()
    hold = v.get("holdSeconds", v.get("hold_seconds", DEFAULT_HOLD_SECONDS))
    try:
        hold = float(hold)
    except (TypeError, ValueError):
        hold = DEFAULT_HOLD_SECONDS

    watermark = _resolve_watermark(design, v.get("watermark"))
    return VideoSettings(
        closing_line=closing or DEFAULT_CLOSING_LINE,
        hold_seconds=max(0.0, hold),
        resolution=parse_resolution(v.get("resolution")),
        watermark=watermark,
    )


def _resolve_watermark(design, raw) -> WatermarkSettings | None:
    """Build a WatermarkSettings from ``video.watermark`` (or None when disabled).

    The bug image defaults to the design's ``logo`` token (the same asset used on
    the slides and thumbnail), resolved relative to the DESIGN.md directory.
    """
    if raw is None or raw is False:
        return None
    cfg = raw if isinstance(raw, dict) else {}
    # Presence enables it; `enabled: false` opts out (and `enabled: true` is the
    # explicit form of the default).
    if cfg.get("enabled", True) is False:
        return None
    tokens = getattr(design, "tokens", None) or {}
    image = cfg.get("image") or (tokens.get("logo") if isinstance(tokens, dict) else None)
    if image and not str(image).startswith(("http://", "https://", "data:")):
        src = image
        if not os.path.isabs(src) and getattr(design, "source_dir", None):
            src = os.path.join(design.source_dir, src)
        image = src
    try:
        height = int(cfg.get("height", 64))
    except (TypeError, ValueError):
        height = 64
    return WatermarkSettings(
        image=str(image) if image else None,
        position=str(cfg.get("position", "bottom-right")),
        height=height,
    )


def watermark_issue(watermark: WatermarkSettings | None) -> str | None:
    """Why a *configured* watermark can't be overlaid, or None.

    Returns None both for "no watermark configured" (nothing to warn about) and
    for a usable watermark; a configured-but-unusable image yields a message.
    """
    if not watermark or not watermark.image:
        return None
    img = watermark.image
    if img.lower().startswith(("http://", "https://", "data:")):
        return "remote image URLs aren't fetched; use a local PNG"
    if img.lower().endswith(".svg"):
        return "SVG isn't supported by the overlay; use a PNG"
    if not os.path.exists(img):
        return f"image not found: {img}"
    return None
