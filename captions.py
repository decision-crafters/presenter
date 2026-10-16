"""SRT/VTT captions for a rendered presentation video.

Captions are derived from the per-slide narration text (``slide_<i>/narration.txt``,
the demo walkthroughs in ``demos.json``, and the closing outro in ``closing.json``)
aligned to the actual clip timings in ``clips.txt`` (the same source the YouTube
chapter computation uses). Narration text keeps the correct spelling (TTS
pronunciation tweaks are applied at synthesis time, never saved), so captions
match what a viewer should read.

Writes ``<presentation_dir>/captions.srt`` and ``captions.vtt``. A slide's
narration is wrapped into caption cues of at most two lines of at most
``MAX_LINE_CHARS`` characters, broken at word and clause boundaries, and spread
proportionally across that slide's clip duration -- accurate enough to follow
along, without needing per-word timestamps from the TTS engine. The trailing cue
is never a one/two-word orphan.

Because clip durations are derived from the actual narration audio (plus a small
pad), spreading cues proportionally to character count keeps reading speed at the
TTS speaking pace -- well under the ~17-20 chars/sec subtitle ceiling.
"""

import json
import os
import re
import subprocess
from typing import List, Optional, Tuple

MAX_LINE_CHARS = 42   # characters per caption line (subtitle ceiling)
MIN_CUE_SECS = 1.0    # a cue shorter than this would flash; floor it
MAX_CUE_SECS = 7.0    # a cue longer than this overstays on a still frame
ORPHAN_WORDS = 2      # a trailing line of <= this many words is merged upward

# A caption event: (start_seconds, end_seconds, text).
Caption = Tuple[float, float, str]

# Punctuation a caption line may end on (kept with the fragment it closes).
_CLAUSE_END = re.compile(r"[,;:—–.!?]$")


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return 0.0
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _wrap_lines(words: List[str], max_line: int = MAX_LINE_CHARS) -> List[str]:
    """Word-wrap ``words`` into lines of ``<= max_line`` characters.

    Breaks at word boundaries, preferring a break right after clause punctuation
    once a line is about half full, and guarantees the final line holds more than
    ``ORPHAN_WORDS`` words by pulling words back from the previous line."""
    lines: List[str] = []
    line = ""
    for word in words:
        if not line:
            line = word
        elif len(line) + 1 + len(word) > max_line:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}"
            # Break after a clause boundary once the line is reasonably full.
            if len(line) >= max_line // 2 and _CLAUSE_END.search(line):
                lines.append(line)
                line = ""
    if line:
        lines.append(line)

    # Fix a too-short final line by pulling words from the previous line so the
    # caption never ends on a one/two-word leftover.
    while len(lines) > 1 and len(lines[-1].split()) <= ORPHAN_WORDS:
        prev_words = lines[-2].split()
        if len(prev_words) <= 1:
            break
        moved = prev_words[-1]
        new_last = f"{moved} {lines[-1]}"
        if len(new_last) > max_line:
            break
        lines[-2] = " ".join(prev_words[:-1])
        lines[-1] = new_last
    return lines


def _split_captions(text: str) -> List[str]:
    """Split narration prose into caption cues (at most two lines of at most
    ``MAX_LINE_CHARS`` characters each), breaking at clause/word boundaries and
    merging any orphan one/two-word tail into the previous line."""
    words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
    lines = _wrap_lines(words)

    cues: List[str] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            cues.append(f"{lines[i]}\n{lines[i + 1]}")
            i += 2
        else:
            cues.append(lines[i])
            i += 1
    return cues


def _reconcile_durations(durations: List[float], total: float) -> List[float]:
    """Clamp each cue to ``[MIN_CUE_SECS, MAX_CUE_SECS]`` and nudge values so they
    still sum to ``total`` (bounded passes; converges on realistic inputs)."""
    lo, hi = MIN_CUE_SECS, MAX_CUE_SECS
    ds = [max(lo, min(hi, d)) for d in durations]
    for _ in range(64):
        diff = total - sum(ds)
        if abs(diff) < 1e-6:
            break
        if diff > 0:
            movable = [i for i, d in enumerate(ds) if d < hi - 1e-9]
        else:
            movable = [i for i, d in enumerate(ds) if d > lo + 1e-9]
        if not movable:
            break
        step = diff / len(movable)
        for i in movable:
            ds[i] = max(lo, min(hi, ds[i] + step))
    return ds


def _timed_chunks(start: float, duration: float, chunks: List[str]) -> List[Caption]:
    """Spread ``chunks`` across ``[start, start+duration]``, each sized by its
    character count (longer text -> more screen time), floored at MIN_CUE_SECS and
    capped at MAX_CUE_SECS, pinned so the last cue ends with the clip."""
    if not chunks:
        return []
    end = start + duration
    lengths = [len(c.replace("\n", "")) for c in chunks]
    total = sum(lengths) or 1
    durations = _reconcile_durations(
        [duration * n / total for n in lengths], duration
    )
    out: List[Caption] = []
    t = start
    for text, d in zip(chunks, durations):
        out.append((t, t + d, text))
        t += d
    # Pin the last cue to the clip end exactly (a no-op when durations already
    # sum to the clip length, but guards against float drift and negative
    # durations when a clip is shorter than MIN_CUE_SECS * len(chunks)).
    if out:
        s, _, text = out[-1]
        out[-1] = (min(s, end), end, text)
    return out


def _clip_narration(presentation_dir: str, rel: str, demos: List[dict],
                    closing: Optional[dict]) -> Optional[str]:
    """The spoken text for one entry in clips.txt, or None."""
    m = re.match(r"slide_(\d+)/clip\.mp4$", rel)
    if m:
        path = os.path.join(presentation_dir, f"slide_{m.group(1)}", "narration.txt")
        if os.path.exists(path):
            return open(path).read().strip()
        return None
    m = re.match(r"demo_(\d+)\.mp4$", rel)
    if m:
        idx = int(m.group(1))
        if idx < len(demos):
            demo = demos[idx]
            return (demo.get("narration") or demo.get("title") or "").strip() or None
        return None
    if rel.startswith("closing"):
        return (closing or {}).get("narration") or None
    return None


def _fmt_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(seconds: float) -> str:
    return _fmt_srt(seconds).replace(",", ".")


def _to_srt(captions: List[Caption]) -> str:
    blocks = []
    for i, (s, e, text) in enumerate(captions, start=1):
        blocks.append(f"{i}\n{_fmt_srt(s)} --> {_fmt_srt(e)}\n{text}\n")
    return "\n".join(blocks)


def _to_vtt(captions: List[Caption]) -> str:
    blocks = [f"{_fmt_vtt(s)} --> {_fmt_vtt(e)}\n{text}" for s, e, text in captions]
    return "\n\n".join(blocks) + "\n"


def build_captions(presentation_dir: str) -> Tuple[str, str]:
    """Return (srt, vtt) caption text for the rendered video."""
    clips_file = os.path.join(presentation_dir, "clips.txt")
    if not os.path.exists(clips_file):
        raise SystemExit(
            f"No clips.txt in {presentation_dir}: render the video first (--export-video)."
        )
    demos = []
    demos_file = os.path.join(presentation_dir, "demos.json")
    if os.path.exists(demos_file):
        try:
            demos = json.load(open(demos_file)) or []
        except Exception:
            demos = []
    closing = None
    closing_file = os.path.join(presentation_dir, "closing.json")
    if os.path.exists(closing_file):
        try:
            closing = json.load(open(closing_file))
        except Exception:
            closing = None

    rels = re.findall(r"file '([^']+)'", open(clips_file).read())
    captions: List[Caption] = []
    t = 0.0
    for rel in rels:
        dur = _duration(os.path.join(presentation_dir, rel))
        text = _clip_narration(presentation_dir, rel, demos, closing)
        if text:
            captions.extend(_timed_chunks(t, dur, _split_captions(text)))
        t += dur

    return _to_srt(captions), "WEBVTT\n\n" + _to_vtt(captions)


def write_captions(presentation_dir: str) -> List[str]:
    """Write captions.srt and captions.vtt; returns the written paths."""
    srt, vtt = build_captions(presentation_dir)
    paths = []
    for name, content in (("captions.srt", srt), ("captions.vtt", vtt)):
        path = os.path.join(presentation_dir, name)
        with open(path, "w") as f:
            f.write(content)
        paths.append(path)
    return paths


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Generate SRT/VTT captions for a rendered deck.")
    p.add_argument("presentation_dir")
    args = p.parse_args()
    for path in write_captions(args.presentation_dir):
        print(f"> Wrote {path}")
