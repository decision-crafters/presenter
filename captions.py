"""SRT/VTT captions for a rendered presentation video.

Captions are derived from the per-slide narration text (``slide_<i>/narration.txt``,
the demo walkthroughs in ``demos.json``, and the closing outro in ``closing.json``)
aligned to the actual clip timings in ``clips.txt`` (the same source the YouTube
chapter computation uses). Narration text keeps the correct spelling (TTS
pronunciation tweaks are applied at synthesis time, never saved), so captions
match what a viewer should read.

Writes ``<presentation_dir>/captions.srt`` and ``captions.vtt``. A slide's
narration is split into short, subtitle-sized chunks and spread proportionally
across that slide's clip duration -- accurate enough to follow along, without
needing per-word timestamps from the TTS engine.
"""

import json
import os
import re
import subprocess
from typing import List, Optional, Tuple

MAX_CHARS = 80      # ~2 lines of ~40 chars -- the usual subtitle ceiling
MIN_CUE_SECS = 1.0  # a cue shorter than this would flash; floor it

# A caption event: (start_seconds, end_seconds, text).
Caption = Tuple[float, float, str]


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


def _split_captions(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    """Split narration prose into subtitle-sized chunks (<= max_chars each),
    preferring sentence boundaries and breaking long sentences at word edges."""
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    chunks: List[str] = []
    cur = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # A sentence longer than max_chars is broken into word-groups.
        pieces: List[str] = []
        if len(sentence) <= max_chars:
            pieces = [sentence]
        else:
            buf = ""
            for word in sentence.split():
                if buf and len(buf) + 1 + len(word) > max_chars:
                    pieces.append(buf)
                    buf = word
                else:
                    buf = f"{buf} {word}".strip() if buf else word
            if buf:
                pieces.append(buf)
        for piece in pieces:
            if cur and len(cur) + 1 + len(piece) > max_chars:
                chunks.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip() if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def _timed_chunks(start: float, duration: float, chunks: List[str]) -> List[Caption]:
    """Spread ``chunks`` across ``[start, start+duration]``, each sized by its
    length (longer text -> more screen time), pinned so the last cue ends with
    the clip."""
    if not chunks:
        return []
    total = sum(len(c) for c in chunks) or 1
    end = start + duration
    out: List[Caption] = []
    t = start
    for c in chunks[:-1]:
        d = max(duration * len(c) / total, MIN_CUE_SECS)
        s, e = t, min(t + d, end)
        if e - s >= 0.4:
            out.append((s, e, c))
        t = e
    out.append((t, end, chunks[-1]))
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
