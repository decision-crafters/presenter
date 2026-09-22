"""Offline narration with Kokoro TTS.

Replaces the ElevenLabs cloud call. Kokoro runs fully locally (Apache-2.0) and
emits raw audio, so we synthesize to WAV and encode to MP3 with ffmpeg (already
a dependency of the video pipeline). The output contract is unchanged: a valid
MP3 is written at ``output_file`` so ``ffprobe``/``ffmpeg`` downstream need no
changes.

First run downloads the Kokoro model (~330 MB). Phonemization may also require
the system package ``espeak-ng``.

``voice`` is a Kokoro voice name (e.g. ``af_heart``); ``lang_code`` is Kokoro's
single-letter language code (``a`` = American English). The old ElevenLabs
``model`` id is no longer used.
"""

import os
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000


def apply_pronunciations(text: str, lexicon: dict) -> str:
    """Rewrite hard-to-say technical tokens to a spoken form before TTS.

    Kokoro phonemizes English literally, so ``kubectl``/``yaml`` come out wrong.
    A persona's pronunciation lexicon maps a term to how it should *sound*
    (``kubectl`` -> ``koob control``); we substitute here, on the TTS input only,
    so the on-screen speaker notes keep the correct spelling. Matching is
    case-insensitive and anchored on non-word boundaries (longest key first) so a
    term isn't matched inside a larger word.
    """
    if not text or not lexicon:
        return text
    keys = sorted((k for k in lexicon if k), key=len, reverse=True)
    if not keys:
        return text
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)",
        re.IGNORECASE,
    )
    lower = {k.lower(): v for k, v in lexicon.items()}
    return pattern.sub(lambda m: lower[m.group(1).lower()], text)

# Lazily-initialized singleton pipeline, keyed by language code, so the model is
# loaded once per process rather than per slide.
_PIPELINES = {}


def _get_pipeline(lang_code: str):
    if lang_code not in _PIPELINES:
        from kokoro import KPipeline

        _PIPELINES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPELINES[lang_code]


async def narrate(
    text: str,
    voice: str,
    output_file: str,
    lang_code: str = "a",
    pronunciations: dict = None,
):
    pipeline = _get_pipeline(lang_code)

    # Fix technical-term pronunciation on the TTS input only (never the saved
    # narration.txt), so the spoken audio is right while the notes stay readable.
    if pronunciations:
        text = apply_pronunciations(text, pronunciations)

    # Kokoro yields audio in chunks (one per sentence-ish segment); concatenate
    # them into a single clip before encoding.
    segments = [audio for _, _, audio in pipeline(text, voice=voice)]
    if not segments:
        raise ValueError("Kokoro produced no audio for the given narration text.")
    audio = np.concatenate(segments)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        sf.write(wav_path, audio, SAMPLE_RATE)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, output_file],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
