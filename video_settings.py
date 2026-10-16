"""Shared video-export settings, resolved from the brand's DESIGN.md ``video:`` block.

One place for settings that shape the rendered MP4. The closing line (the spoken
repo-deck outro), the end-screen hold, and the video resolution live here; #10
(watermark/channel overlay) extends this same block:

    video:
      closingLine: "The repo is linked below. Clone it and run it."
      holdSeconds: 4
      resolution: 1080p        # 480p | 720p | 1080p | 1440p | 2160p | WxH
      # watermark: ...         # issue #10
"""

import re
from dataclasses import dataclass
from typing import Tuple

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


def parse_resolution(value, default: Tuple[int, int] = DEFAULT_RESOLUTION) -> Tuple[int, int]:
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
    resolution: Tuple[int, int] = DEFAULT_RESOLUTION


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
    return VideoSettings(
        closing_line=closing or DEFAULT_CLOSING_LINE,
        hold_seconds=max(0.0, hold),
        resolution=parse_resolution(v.get("resolution")),
    )
