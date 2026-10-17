import json
import os
import subprocess
from typing import Any

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from llama_index.core.workflow.retry_policy import ConstantDelayRetryPolicy

from agents.narrator import narrate
from models import PresentationStructure, load_structure, structure_cache_path
from video_settings import (
    DEFAULT_RESOLUTION,
    WatermarkSettings,
    watermark_filter,
    watermark_issue,
)

# Playback speed for the narration in the exported video. 1.0 = Kokoro's
# natural speaking pace. Values > 1.0 speed it up (1.4 was the old hardcoded
# default, which sounded rushed). The per-slide clip duration is derived from
# this same constant so audio and video stay in sync — change it in one place.
NARRATION_TEMPO = 1.0

# Watermark re-encode settings. The overlay has to re-encode the already-h264
# video, so we pin a low CRF (near-transparent second generation) instead of
# ffmpeg's default CRF 23. Tune here to trade quality against encode time.
WATERMARK_CRF = "18"
WATERMARK_PRESET = "medium"


def _demo_vf(width: int, height: int) -> str:
    """Scale/pad a demo recording to the target frame so the final
    `concat -c copy` can stitch it without a re-encode (h264/yuv420p, 25fps)."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p,fps=25"
    )


def _media_duration(path: str) -> float:
    """Duration (seconds) of a media file via ffprobe, or 0.0 if unknown."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return 0.0
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _build_demo_clip(media_path, caption_mp3, duration: float, out_file: str, vf: str) -> bool:
    """Render one demo recording as a clip matching the narrated clips.
    The demo animates (looped to fill ``duration``); audio is the spoken caption
    (padded with silence) or a silent stereo track. Returns True on success."""
    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", media_path]
    if caption_mp3:
        cmd += ["-i", caption_mp3, "-af", "apad"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += [
        "-t", f"{duration:.3f}", "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        out_file,
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and os.path.exists(out_file)


class NarrationRequestReceived(Event):
    slide_index: int


class SlideNarrated(Event):
    slide_index: int


class SlideClipCreated(Event):
    slide_index: int
    clip_file: str


class PresenterVideoCreaterWorkflow(Workflow):
    def __init__(
        self,
        *args: Any,
        voice: str,
        lang_code: str = "a",
        pronunciations: dict = None,
        resolution: tuple = DEFAULT_RESOLUTION,
        watermark: WatermarkSettings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.voice = voice
        self.lang_code = lang_code
        # Persona pronunciation lexicon applied to narration/captions before TTS.
        self.pronunciations = pronunciations or {}
        self.watermark = watermark
        # Target frame size; the deck's screenshots and demo clips are rendered
        # to match so the final `concat -c copy` needs no re-encode.
        self.width, self.height = resolution

    @step
    async def start(
        self, ctx: Context, ev: StartEvent
    ) -> NarrationRequestReceived | StopEvent | None:
        presentation_dir = ev.presentation_dir
        await ctx.store.set("presentation_dir", presentation_dir)
        if not structure_cache_path(presentation_dir):
            return StopEvent(result="No structure found")
        structure: PresentationStructure = load_structure(presentation_dir)
        await ctx.store.set("structure", structure)
        slides = structure.slides
        await ctx.store.set("num_slides", len(slides))
        for i in range(len(slides)):
            ctx.send_event(NarrationRequestReceived(slide_index=i))
        return None

    @step(num_workers=5, retry_policy=ConstantDelayRetryPolicy())
    async def narrate_slide(
        self, ctx: Context, ev: NarrationRequestReceived
    ) -> SlideNarrated:
        slide_index = ev.slide_index
        presentation_dir = await ctx.store.get("presentation_dir")
        slide_dir = os.path.join(presentation_dir, f"slide_{slide_index}")
        narration_file = os.path.join(slide_dir, "narration.txt")
        narration_audio_file = os.path.join(slide_dir, "narration.mp3")
        print(f"\n> Narrating slide_{slide_index}\n")
        if os.path.exists(narration_audio_file):
            return SlideNarrated(slide_index=slide_index)
        with open(narration_file) as f:
            narration = f.read()
        await narrate(
            narration, self.voice, narration_audio_file,
            lang_code=self.lang_code, pronunciations=self.pronunciations,
        )
        return SlideNarrated(slide_index=slide_index)

    @step(num_workers=5, retry_policy=ConstantDelayRetryPolicy())
    async def create_slide_clip(
        self, ctx: Context, ev: SlideNarrated
    ) -> SlideClipCreated:
        slide_index = ev.slide_index
        presentation_dir = await ctx.store.get("presentation_dir")
        slide_dir = os.path.join(presentation_dir, f"slide_{slide_index}")
        slide_clip_file = os.path.join(slide_dir, "clip.mp4")
        print(f"\n> Creating clip for slide_{slide_index}\n")
        if os.path.exists(slide_clip_file):
            return SlideClipCreated(slide_index=slide_index, clip_file=slide_clip_file)
        slide_ss_file = os.path.join(
            presentation_dir,
            f"presentation_{slide_index+1}_{self.width}x{self.height}.png",
        )
        slide_audio_file = os.path.join(slide_dir, "narration.mp3")
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                slide_audio_file,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed for {slide_audio_file}: "
                f"{result.stderr.strip()[-300:]}"
            )
        output = json.loads(result.stdout)
        duration = float(output["format"]["duration"]) / NARRATION_TEMPO + 0.5
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", slide_ss_file,
                "-i", slide_audio_file,
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000", "-ac", "2", "-shortest", "-t", f"{duration:.3f}",
                "-vf", "format=yuv420p",
                "-filter:a", f"atempo={NARRATION_TEMPO}",
                slide_clip_file,
            ],
            capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(slide_clip_file):
            raise RuntimeError(
                f"ffmpeg failed to build {slide_clip_file}: "
                f"{(r.stderr or b'').decode(errors='ignore').strip()[-300:]}"
            )
        print(f"\n> Created clip for slide_{slide_index}\n")
        return SlideClipCreated(slide_index=slide_index, clip_file=slide_clip_file)

    async def _build_demo_clips(self, presentation_dir: str):
        """Render an animated clip per detected demo (from demos.json), appended
        after the narrated slides so the video actually plays the demos. Returns
        clip paths relative to ``presentation_dir`` for the concat list."""
        demos_file = os.path.join(presentation_dir, "demos.json")
        if not os.path.exists(demos_file):
            return []
        try:
            with open(demos_file) as f:
                demos = json.load(f)
        except Exception:
            return []
        media_dir = os.path.join(presentation_dir, "media")
        rels = []
        for idx, demo in enumerate(demos):
            media_path = os.path.join(media_dir, demo.get("file", ""))
            if not demo.get("file") or not os.path.exists(media_path):
                continue
            clip_file = os.path.join(presentation_dir, f"demo_{idx}.mp4")
            if not os.path.exists(clip_file):
                print(f"\n> Creating demo clip {idx}: {demo.get('title')}\n")
                # Prefer the runtime-sized walkthrough written at deck build; fall
                # back to a short title caption if none is present.
                script = demo.get("narration") or f"Demo: {demo.get('title') or 'demo'}"
                caption_path = os.path.join(presentation_dir, f"demo_{idx}_caption.mp3")
                caption_mp3: str | None = caption_path
                try:
                    await narrate(
                        script, self.voice, caption_path, lang_code=self.lang_code,
                        pronunciations=self.pronunciations,
                    )
                except Exception:
                    caption_mp3 = None
                if caption_mp3 and not os.path.exists(caption_mp3):
                    caption_mp3 = None
                # Clip length = whichever is longer, so the walkthrough is never
                # cut off and the demo GIF loops to fill any remainder.
                duration = max(
                    _media_duration(media_path),
                    _media_duration(caption_mp3) if caption_mp3 else 0.0,
                    2.0,
                )
                if not _build_demo_clip(
                    media_path, caption_mp3, duration, clip_file,
                    _demo_vf(self.width, self.height),
                ):
                    continue
            rels.append(os.path.relpath(clip_file, presentation_dir))
        return rels

    async def _build_closing_clip(self, presentation_dir: str):
        """Append a closing 'Get the Code' clip so every recording ends on the CTA
        and its links. Reuses the branded CTA slide screenshot + a spoken outro.
        Returns the clip path relative to ``presentation_dir``, or None."""
        closing_file = os.path.join(presentation_dir, "closing.json")
        if not os.path.exists(closing_file):
            return None
        try:
            with open(closing_file) as f:
                closing = json.load(f)
        except Exception:
            return None
        idx = closing.get("screenshot_index")
        shot = os.path.join(
            presentation_dir, f"presentation_{idx}_{self.width}x{self.height}.png"
        )
        if not idx or not os.path.exists(shot):
            print(f"\n> Closing CTA screenshot not found ({shot}); skipping.\n")
            return None
        clip_file = os.path.join(presentation_dir, "closing.mp4")
        if not os.path.exists(clip_file):
            print("\n> Creating closing CTA clip\n")
            caption_path = os.path.join(presentation_dir, "closing_caption.mp3")
            caption_mp3: str | None = caption_path
            try:
                await narrate(
                    closing.get("narration") or "Get the code linked on screen.",
                    self.voice, caption_path, lang_code=self.lang_code,
                    pronunciations=self.pronunciations,
                )
            except Exception:
                caption_mp3 = None
            if caption_mp3 and not os.path.exists(caption_mp3):
                caption_mp3 = None
            # The CTA frame holds on screen for hold_seconds after the outro
            # finishes, so the links stay readable (the shared `video:` setting).
            try:
                hold_seconds = max(0.0, float(closing.get("hold_seconds", 4.0)))
            except (TypeError, ValueError):
                hold_seconds = 4.0
            duration = (
                _media_duration(caption_mp3) if caption_mp3 else 0.0
            ) + hold_seconds
            if not _build_demo_clip(
                shot, caption_mp3, duration, clip_file,
                _demo_vf(self.width, self.height),
            ):
                return None
        return os.path.relpath(clip_file, presentation_dir)

    @step
    async def combine_clips(self, ctx: Context, ev: SlideClipCreated) -> StopEvent | None:
        num_slides = await ctx.store.get("num_slides")
        presentation_dir = await ctx.store.get("presentation_dir")
        events = ctx.collect_events(ev, [SlideClipCreated] * num_slides)
        if not events:
            return None
        all_clips_file = os.path.join(presentation_dir, "clips.txt")
        clips = []
        for i in range(num_slides):
            clip_file = os.path.join(f"slide_{i}", "clip.mp4")
            clips.append(f"file '{clip_file}'")
        # Append animated demo clips (if any) after the narrated slides.
        for demo_rel in await self._build_demo_clips(presentation_dir):
            clips.append(f"file '{demo_rel}'")
        # End every recording on the closing 'Get the Code' CTA clip.
        closing_rel = await self._build_closing_clip(presentation_dir)
        if closing_rel:
            clips.append(f"file '{closing_rel}'")
        with open(all_clips_file, "w") as f:
            f.write("\n".join(clips))
        presentation_video_file = os.path.join(presentation_dir, "presentation.mp4")
        print("\n> Rendering full presentation video...\n")
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", all_clips_file, "-c", "copy", presentation_video_file,
            ],
            capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(presentation_video_file):
            raise RuntimeError(
                f"ffmpeg concat failed: "
                f"{(r.stderr or b'').decode(errors='ignore').strip()[-300:]}"
            )
        if self._apply_watermark(presentation_video_file):
            print("\n> Watermark overlay applied.\n")
        print(f'\n> Presentation video created: "open {presentation_video_file}"\n')
        return StopEvent(result="Presentation video created")

    def _apply_watermark(self, video_file: str) -> bool:
        """Overlay the configured corner bug onto ``video_file`` in place.

        A no-op when no watermark is configured; warns and skips when the
        configured image is missing, remote, or unsupported. Returns True on
        success.
        """
        issue = watermark_issue(self.watermark)
        if issue is not None:
            print(f"\n! Watermark skipped: {issue}\n")
            return False
        if not self.watermark or not self.watermark.image:
            return False
        filt = watermark_filter(self.watermark, self.height)
        tmp = video_file + ".wm.mp4"
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_file, "-i", self.watermark.image,
                "-filter_complex", filt, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", WATERMARK_CRF, "-preset", WATERMARK_PRESET,
                "-c:a", "copy", tmp,
            ],
            capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(tmp):
            print(
                "\n! Watermark overlay failed; leaving the video un-watermarked.\n"
            )
            return False
        os.replace(tmp, video_file)
        return True
