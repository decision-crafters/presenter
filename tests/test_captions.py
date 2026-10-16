import os
import tempfile

import captions
from captions import (
    MAX_CUE_SECS,
    MAX_LINE_CHARS,
    MIN_CUE_SECS,
    _split_captions,
    _timed_chunks,
    _wrap_lines,
    build_captions,
)

NARRATIONS = [
    "Imagine an assistant that can check your calendar, query your database, and send email.",
    "Jev takes typed questions over program state and returns typed, calibrated answers — around a hundred milliseconds, roughly $0.00035 per decision. Per Vercel's launch post, a vendor-reported figure, it reached thirteen percent of paid teams within twenty-four hours.",
    "The type settles the shape — schema risk ends at that boundary. Whether noul is actually true is judgment risk, and types don't touch it.",
    "A threshold of 0.85 tuned on model v1 is a property of the stack, not the task. Change the model, the prompt phrasing, the rubric, or the data distribution, and the score distribution shifts underneath.",
]


def _lines(cue):
    return cue.split("\n")


def test_every_line_within_limit():
    for text in NARRATIONS:
        for cue in _split_captions(text):
            for line in _lines(cue):
                assert len(line) <= MAX_LINE_CHARS, (line, cue)


def test_at_most_two_lines_per_cue():
    for text in NARRATIONS:
        for cue in _split_captions(text):
            assert len(_lines(cue)) <= 2, cue


def test_no_orphan_tail():
    for text in NARRATIONS:
        cues = _split_captions(text)
        if len(cues) >= 2:
            assert len(cues[-1].split()) > 2, cues


def test_number_comma_kept_intact():
    text = "The Astra run shows the rebound: four billion tokens, about $1,200, and 79 commits."
    assert any("1,200" in cue for cue in _split_captions(text))


def test_empty_text():
    assert _split_captions("") == []
    assert _split_captions(None) == []


def test_wrap_lines_pulls_back_orphan():
    # A tail that would otherwise land as a single word gets merged upward.
    lines = _wrap_lines(
        "Imagine an assistant that can check your calendar, query your database, and send email.".split()
    )
    assert len(lines) >= 1
    assert len(lines[-1].split()) > 2, lines


def test_timed_chunks_bounds_and_sum():
    chunks = ["Short cue.", "A somewhat longer cue for timing.", "Final longer cue here with more words."]
    start = 5.0
    duration = 20.0
    caps = _timed_chunks(start, duration, chunks)
    assert len(caps) == 3
    assert caps[0][0] == start
    assert abs(caps[-1][1] - (start + duration)) < 1e-6
    for i in range(1, len(caps)):
        assert abs(caps[i][0] - caps[i - 1][1]) < 1e-6
    for s, e, _ in caps:
        assert e - s >= MIN_CUE_SECS - 1e-6
        assert e - s <= MAX_CUE_SECS + 1e-6


def test_timed_chunks_empty():
    assert _timed_chunks(0.0, 10.0, []) == []


def test_build_captions_end_to_end(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "slide_0"))
        os.makedirs(os.path.join(d, "slide_1"))
        with open(os.path.join(d, "clips.txt"), "w") as f:
            f.write("file 'slide_0/clip.mp4'\nfile 'slide_1/clip.mp4'\n")
        with open(os.path.join(d, "slide_0", "narration.txt"), "w") as f:
            f.write(NARRATIONS[0] + "\n")
        with open(os.path.join(d, "slide_1", "narration.txt"), "w") as f:
            f.write(NARRATIONS[1] + "\n")
        monkeypatch.setattr(captions, "_duration", lambda path: 8.0)
        srt, vtt = build_captions(d)

    assert vtt.startswith("WEBVTT\n")
    blocks = [b for b in srt.split("\n\n") if b.strip()]
    assert len(blocks) >= 2
    cue_texts = []
    for block in blocks:
        lines = block.strip().split("\n")
        assert lines[0].isdigit()
        assert "-->" in lines[1]
        text_lines = lines[2:]
        assert 1 <= len(text_lines) <= 2, text_lines
        for line in text_lines:
            assert len(line) <= MAX_LINE_CHARS, text_lines
        cue_texts.append(" ".join(text_lines))
    # No orphan tail across the whole track.
    assert len(cue_texts[-1].split()) > 2, cue_texts
