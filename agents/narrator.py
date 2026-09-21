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
import subprocess
import tempfile

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000

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
):
    pipeline = _get_pipeline(lang_code)

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
