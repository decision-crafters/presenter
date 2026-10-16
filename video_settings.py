"""Shared video-export settings, resolved from the brand's DESIGN.md ``video:`` block.

One place for settings that shape the rendered MP4. The closing line (the spoken
repo-deck outro) is the first consumer; #8 (1080p resolution) and #10
(watermark/channel overlay) extend this same block:

    video:
      closingLine: "The repo is linked below. Clone it and run it."
      holdSeconds: 4
      # resolution: "1920x1080"   # issue #8
      # watermark: ...            # issue #10
"""

from dataclasses import dataclass

DEFAULT_HOLD_SECONDS = 4.0

# The pre-configuration repo-deck outro, kept as the fallback when a brand
# declares no closing line.
DEFAULT_CLOSING_LINE = (
    "That wraps up the walkthrough. The code, demos, and documentation are all "
    "linked on screen — grab them from the project's repository."
)


@dataclass
class VideoSettings:
    closing_line: str = DEFAULT_CLOSING_LINE
    hold_seconds: float = DEFAULT_HOLD_SECONDS


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
    )
