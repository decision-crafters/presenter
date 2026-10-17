"""Advisory engine: measure a rendered video, evaluate rules, return advisories.

The check functions are the ones named in ``advisories/rules.yaml``. Each takes
``(facts, params)`` and returns ``None`` (rule passes / not applicable) or a dict
of measured values used to fill the rule's ``{placeholders}``.

Measurement of the final MP4 (duration, loudness, first-audio offset, size,
resolution) is best-effort: any failure yields ``None``, so a rule whose fact is
unknown simply does not fire. Advisories never raise out of a render.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

from advisories import (
    Advisory,
    Rule,
    make_advisory,
)

log = logging.getLogger("advisories")

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


@dataclass
class VideoFacts:
    """Everything a rule can check, measured or declared for one video."""

    content_type: str = "explainer"
    aspect_ratio: str | None = None  # e.g. "16:9", "9:16"
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    filesize_bytes: int | None = None
    chapters: list[dict] = field(default_factory=list)
    title: str = ""
    hook: str = ""
    description: str = ""
    thumbnail_bytes: int | None = None
    captions: bool = False
    outro_hold_seconds: float | None = None
    rights: str = "unknown"
    loudness_lufs: float | None = None
    first_audio_offset: float | None = None
    content: dict = field(default_factory=dict)  # DESIGN.md ``content:`` block
    metadata: dict = field(default_factory=dict)  # the generated kit metadata


# ---- helpers ----

def _fmt_seconds(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _fmt_bytes(num: float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _classify(width: int, height: int) -> str:
    if width < height:
        return "vertical"
    if width > height:
        return "horizontal"
    return "square"


def _aspect_class(facts: VideoFacts) -> str | None:
    if facts.aspect_ratio:
        m = re.fullmatch(r"(\d+):(\d+)", facts.aspect_ratio)
        if m:
            return _classify(int(m.group(1)), int(m.group(2)))
    if facts.width and facts.height:
        return _classify(facts.width, facts.height)
    return None


def is_short(facts: VideoFacts) -> bool:
    return facts.content_type == "short" or _aspect_class(facts) == "vertical"


def rule_applies(rule: Rule, facts: VideoFacts) -> bool:
    applies = rule.applies_to
    if "all" in applies:
        return True
    if facts.content_type in applies:
        return True
    if "short" in applies and is_short(facts):
        return True
    if "long_form" in applies and not is_short(facts):
        return True
    return False


# ---- check functions ----

def _length_type_range(facts: VideoFacts, params: dict) -> dict | None:
    dur = facts.duration_seconds
    if dur is None:
        return None
    lo: float | None = None
    hi: float | None = None
    ranges = params.get("ranges")
    if isinstance(ranges, dict):
        r = ranges.get(facts.content_type)
        if isinstance(r, dict):
            lo, hi = r.get("min_seconds"), r.get("max_seconds")
    else:
        lo, hi = params.get("min_seconds"), params.get("max_seconds")
    if lo is None and hi is None:
        return None
    if (lo is not None and dur < lo) or (hi is not None and dur > hi):
        return {
            "duration": _fmt_seconds(dur),
            "min": _fmt_seconds(lo) if lo is not None else "0:00",
            "max": _fmt_seconds(hi) if hi is not None else "∞",
            "content_type": facts.content_type,
        }
    return None


def _duration_aspect(facts: VideoFacts, params: dict) -> dict | None:
    aspect = params.get("aspect")
    if not aspect or _aspect_class(facts) != aspect:
        return None
    dur = facts.duration_seconds
    if dur is None:
        return None
    lo, hi = params.get("min_seconds"), params.get("max_seconds")
    if (lo is not None and dur < lo) or (hi is not None and dur > hi):
        return {
            "duration": _fmt_seconds(dur),
            "max": _fmt_seconds(hi) if hi is not None else _fmt_seconds(lo or 0),
            "aspect": aspect,
        }
    return None


def _duration_threshold(facts: VideoFacts, params: dict) -> dict | None:
    dur = facts.duration_seconds
    if dur is None:
        return None
    lo, hi = params.get("min_seconds"), params.get("max_seconds")
    if lo is not None and dur < lo:
        return {"duration": _fmt_seconds(dur), "limit": _fmt_seconds(lo)}
    if hi is not None and dur > hi:
        return {"duration": _fmt_seconds(dur), "limit": _fmt_seconds(hi)}
    return None


def _duration_filesize_max(facts: VideoFacts, params: dict) -> dict | None:
    fired = False
    if (
        facts.duration_seconds is not None
        and params.get("max_seconds")
        and facts.duration_seconds > params["max_seconds"]
    ):
        fired = True
    if (
        facts.filesize_bytes is not None
        and params.get("max_bytes")
        and facts.filesize_bytes > params["max_bytes"]
    ):
        fired = True
    if not fired:
        return None
    return {
        "max_duration": _fmt_seconds(params.get("max_seconds", 0)),
        "max_size": _fmt_bytes(params.get("max_bytes", 0)),
    }


def _chapters_valid(facts: VideoFacts, params: dict) -> dict | None:
    chapters = facts.chapters or []
    count = len(chapters)
    min_count = params.get("min_count")
    max_count = params.get("max_count")
    min_seconds = params.get("min_seconds")
    start_zero = params.get("start_at_zero")

    if min_count is not None and count < min_count:
        return {"count": count, "min_count": min_count, "min_seconds": min_seconds or 0}
    if max_count is not None and count > max_count:
        return {"count": count, "max_count": max_count}
    if start_zero and chapters and chapters[0].get("start", 0) > 0:
        return {"count": count, "min_count": min_count or 0, "min_seconds": min_seconds or 0}
    if min_seconds is not None:
        for chapter in chapters:
            if chapter.get("duration") is not None and chapter["duration"] < min_seconds:
                return {
                    "count": count,
                    "min_count": min_count or 0,
                    "min_seconds": min_seconds,
                }
    return None


def _chapters_required_if_long(facts: VideoFacts, params: dict) -> dict | None:
    dur = facts.duration_seconds
    if dur is None or dur < params.get("min_duration_seconds", 0):
        return None
    min_count = params.get("min_count", 0)
    count = len(facts.chapters or [])
    if count < min_count:
        return {"duration": _fmt_seconds(dur), "count": count, "min_count": min_count}
    return None


def _title_length(facts: VideoFacts, params: dict) -> dict | None:
    n = len(facts.title or "")
    lo, hi = params.get("min_chars"), params.get("max_chars")
    if (hi is not None and n > hi) or (lo is not None and n < lo):
        return {"length": n, "min": lo, "max": hi}
    return None


def _keyword_position(facts: VideoFacts, params: dict) -> dict | None:
    keyword = params.get("keyword") or facts.metadata.get("keyword")
    if not keyword:
        return None
    words = re.split(r"\W+", facts.title or "")
    within = int(params.get("within_words", 3))
    if str(keyword).lower() not in [w.lower() for w in words[:within]]:
        return {"keyword": keyword, "within": within}
    return None


def _title_style(facts: VideoFacts, params: dict) -> dict | None:
    title = facts.title or ""
    if not params.get("allow_emoji", False) and _EMOJI_RE.search(title):
        return {"issue": "emoji"}
    letters = [c for c in title if c.isalpha()]
    if letters:
        ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if ratio > float(params.get("max_uppercase_ratio", 0.5)):
            return {"issue": "ALL CAPS", "ratio": f"{ratio:.0%}"}
    return None


def _description_hook(facts: VideoFacts, params: dict) -> dict | None:
    n = len(facts.hook or "")
    max_chars = params.get("max_chars")
    if max_chars is not None and n > max_chars:
        return {"length": n, "max": max_chars}
    return None


def _thumbnail_spec(facts: VideoFacts, params: dict) -> dict | None:
    if (
        facts.thumbnail_bytes is not None
        and params.get("max_bytes")
        and facts.thumbnail_bytes > params["max_bytes"]
    ):
        return {
            "size": _fmt_bytes(facts.thumbnail_bytes),
            "max_size": _fmt_bytes(params["max_bytes"]),
        }
    return None


def _layout_spec(facts: VideoFacts, params: dict) -> dict | None:
    aspect = params.get("aspect")
    if not aspect:
        return None
    if _aspect_class(facts) != aspect:
        return {"aspect": aspect, "found": _aspect_class(facts) or "unknown"}
    max_height = params.get("max_height")
    if max_height is not None and facts.height is not None and facts.height > max_height:
        return {"aspect": aspect, "max_height": max_height, "height": facts.height}
    return None


def _captions_file(facts: VideoFacts, params: dict) -> dict | None:
    if params.get("required") and not facts.captions:
        return {"count": 0}
    return None


def _outro_hold(facts: VideoFacts, params: dict) -> dict | None:
    hold = facts.outro_hold_seconds
    if hold is None:
        return None
    lo, hi = params.get("min_seconds"), params.get("max_seconds")
    if (lo is not None and hold < lo) or (hi is not None and hold > hi):
        return {"hold": hold, "min": lo, "max": hi}
    return None


def _content_rights(facts: VideoFacts, params: dict) -> dict | None:
    allowed = params.get("allowed") or []
    if facts.rights in allowed:
        return None
    return {"rights": facts.rights, "allowed": ", ".join(allowed)}


def _metadata_field(facts: VideoFacts, params: dict) -> dict | None:
    field = params.get("field")
    if not field:
        return None
    content = facts.content or {}
    if field not in content:
        return {"field": field}
    expected = params.get("expected")
    if expected is not None and content[field] != expected:
        return {"field": field, "expected": expected}
    return None


def _integrated_loudness(facts: VideoFacts, params: dict) -> dict | None:
    lufs = facts.loudness_lufs
    if lufs is None:
        return None
    lo, hi = params.get("min_lufs"), params.get("max_lufs")
    if hi is not None and lufs > hi:
        return {"lufs": f"{lufs:.1f}", "max": f"{hi:.1f}"}
    if lo is not None and lufs < lo:
        return {"lufs": f"{lufs:.1f}", "min": f"{lo:.1f}"}
    return None


def _first_audio_offset(facts: VideoFacts, params: dict) -> dict | None:
    offset = facts.first_audio_offset
    if offset is None:
        return None
    max_seconds = params.get("max_seconds")
    if max_seconds is not None and offset > max_seconds:
        return {"offset": f"{offset:.1f}s", "max": f"{max_seconds:.0f}s"}
    return None


_CHECKS: dict[str, Any] = {
    "length_type_range": _length_type_range,
    "duration_aspect": _duration_aspect,
    "duration_threshold": _duration_threshold,
    "duration_filesize_max": _duration_filesize_max,
    "chapters_valid": _chapters_valid,
    "chapters_required_if_long": _chapters_required_if_long,
    "title_length": _title_length,
    "keyword_position": _keyword_position,
    "title_style": _title_style,
    "description_hook": _description_hook,
    "thumbnail_spec": _thumbnail_spec,
    "layout_spec": _layout_spec,
    "captions_file": _captions_file,
    "outro_hold": _outro_hold,
    "content_rights": _content_rights,
    "metadata_field": _metadata_field,
    "integrated_loudness": _integrated_loudness,
    "first_audio_offset": _first_audio_offset,
}


def advise(result: VideoFacts | dict, rules: list[Rule]) -> list[Advisory]:
    """Evaluate every rule against ``result`` and return the advisories that fire.

    ``result`` is a ``VideoFacts`` or a dict of its fields. Unimplemented checks
    (a ``check`` name with no function) are skipped silently at debug level; a
    check that raises is caught and skipped so advisories never block a render."""
    facts = result if isinstance(result, VideoFacts) else VideoFacts(**result)
    advisories: list[Advisory] = []
    for rule in rules:
        if not rule_applies(rule, facts):
            continue
        fn = _CHECKS.get(rule.check)
        if fn is None:
            log.debug("skipping unimplemented check %r for %s", rule.check, rule.id)
            continue
        try:
            ctx = fn(facts, rule.params)
        except Exception:
            log.debug("check %r raised for %s", rule.check, rule.id, exc_info=True)
            continue
        if not ctx:
            continue
        advisories.append(make_advisory(rule, ctx))
    return advisories


# ---- measurement (best-effort, never raises) ----

def _ffprobe_duration(path: str) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _ffprobe_resolution(path: str) -> tuple[int | None, int | None]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60,
        )
        width, height = out.stdout.strip().split(",")[:2]
        return int(width), int(height)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, None


def _ffmpeg_ebur128(path: str) -> float | None:
    """Integrated loudness in LUFS (measure only; never normalize)."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-nostats", "-i", path, "-map", "0:a:0",
             "-af", "ebur128", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
        for line in out.stderr.splitlines():
            m = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", line)
            if m:
                return float(m.group(1))
        return None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _ffmpeg_first_audio(path: str) -> float | None:
    """Seconds until the first audio above the noise floor (best-effort)."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-i", path, "-af", "silencedetect=noise=-40dB:d=0.1",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
        for line in out.stderr.splitlines():
            m = re.search(r"silence_end:\s*(-?\d+(?:\.\d+)?)", line)
            if m:
                return float(m.group(1))
        return None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _aspect_from_dims(width: int, height: int) -> str:
    if width and height:
        g = _gcd(width, height)
        return f"{width // g}:{height // g}"
    return "16:9"


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def build_facts(
    presentation_dir: str,
    *,
    meta: dict | None = None,
    chapters: list[dict] | None = None,
    content_type: str = "explainer",
    rights: str = "unknown",
    content: dict | None = None,
    duration_seconds: float | None = None,
    filesize_bytes: int | None = None,
    outro_hold_seconds: float | None = None,
    aspect_ratio: str | None = None,
    width: int | None = None,
    height: int | None = None,
    loudness_lufs: float | None = None,
    first_audio_offset: float | None = None,
) -> VideoFacts:
    """Measure a rendered deck (best-effort) into a ``VideoFacts``. Explicitly
    passed values win over disk measurement, which is handy for tests."""
    meta = meta or {}
    mp4 = os.path.join(presentation_dir, "presentation.mp4")
    has_mp4 = os.path.exists(mp4)

    if duration_seconds is None and has_mp4:
        duration_seconds = _ffprobe_duration(mp4)
    if filesize_bytes is None and has_mp4:
        try:
            filesize_bytes = os.path.getsize(mp4)
        except OSError:
            filesize_bytes = None
    if (width is None or height is None) and has_mp4:
        w, h = _ffprobe_resolution(mp4)
        width = width if width is not None else w
        height = height if height is not None else h
    if aspect_ratio is None and width and height:
        aspect_ratio = _aspect_from_dims(width, height)
    if loudness_lufs is None and has_mp4:
        loudness_lufs = _ffmpeg_ebur128(mp4)
    if first_audio_offset is None and has_mp4:
        first_audio_offset = _ffmpeg_first_audio(mp4)

    thumb = os.path.join(presentation_dir, "youtube", "thumbnail.jpg")
    thumbnail_bytes = os.path.getsize(thumb) if os.path.exists(thumb) else None
    captions = any(
        os.path.exists(os.path.join(presentation_dir, f"captions.{ext}"))
        for ext in ("srt", "vtt")
    )

    return VideoFacts(
        content_type=content_type,
        aspect_ratio=aspect_ratio,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        filesize_bytes=filesize_bytes,
        chapters=list(chapters or []),
        title=meta.get("title", ""),
        hook=meta.get("hook", ""),
        description=meta.get("description", ""),
        thumbnail_bytes=thumbnail_bytes,
        captions=captions,
        outro_hold_seconds=outro_hold_seconds,
        rights=rights,
        loudness_lufs=loudness_lufs,
        first_audio_offset=first_audio_offset,
        content=dict(content or {}),
        metadata=dict(meta),
    )
