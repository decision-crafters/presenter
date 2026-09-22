from typing import Any
import subprocess
import shlex
import os
import json
import pickle

from llama_index.core.workflow import (
    step,
    Context,
    Workflow,
    Event,
    StartEvent,
    StopEvent,
)
from llama_index.core.workflow.retry_policy import ConstantDelayRetryPolicy

from models import PresentationStructure
from agents.narrator import narrate


# Playback speed for the narration in the exported video. 1.0 = Kokoro's
# natural speaking pace. Values > 1.0 speed it up (1.4 was the old hardcoded
# default, which sounded rushed). The per-slide clip duration is derived from
# this same constant so audio and video stay in sync — change it in one place.
NARRATION_TEMPO = 1.0

# Demo clips must match the narrated slide clips exactly (1280x720, h264/yuv420p,
# 25fps, aac 48k stereo) so the final `concat -c copy` can stitch them without a
# re-encode.
DEMO_CLIP_VF = (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p,fps=25"
)


def _media_duration(path: str) -> float:
    """Duration (seconds) of a media file via ffprobe, or 0.0 if unknown."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _build_demo_clip(media_path, caption_mp3, duration: float, out_file: str) -> bool:
    """Render one demo recording as a 1280x720 clip matching the narrated clips.
    The demo animates (looped to fill ``duration``); audio is the spoken caption
    (padded with silence) or a silent stereo track. Returns True on success."""
    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", media_path]
    if caption_mp3:
        cmd += ["-i", caption_mp3, "-af", "apad"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += [
        "-t", f"{duration:.3f}", "-vf", DEMO_CLIP_VF,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        out_file,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.voice = voice
        self.lang_code = lang_code
        # Persona pronunciation lexicon applied to narration/captions before TTS.
        self.pronunciations = pronunciations or {}

    @step
    async def start(
        self, ctx: Context, ev: StartEvent
    ) -> NarrationRequestReceived | StopEvent:
        presentation_dir = ev.presentation_dir
        await ctx.store.set("presentation_dir", presentation_dir)
        structure_file = os.path.join(presentation_dir, "structure.pkl")
        if not os.path.exists(structure_file):
            return StopEvent(result="No structure found")
        with open(structure_file, "rb") as f:
            structure: PresentationStructure = pickle.load(f)
        await ctx.store.set("structure", structure)
        slides = structure.slides
        await ctx.store.set("num_slides", len(slides))
        for i in range(len(slides)):
            ctx.send_event(NarrationRequestReceived(slide_index=i))

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
        with open(narration_file, "r") as f:
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
            presentation_dir, f"presentation_{slide_index+1}_1280x720.png"
        )
        slide_audio_file = os.path.join(slide_dir, "narration.mp3")
        file_duration_command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            slide_audio_file,
        ]
        result = subprocess.run(
            file_duration_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = json.loads(result.stdout)
        duration = float(output["format"]["duration"]) / NARRATION_TEMPO + 0.5
        subprocess.run(
            shlex.split(
                f"""ffmpeg -loop 1 -i {slide_ss_file} -i {slide_audio_file} -c:v libx264 -c:a aac -b:a 192k -ar 48000 -ac 2 -shortest -t {duration} -vf "format=yuv420p" -filter:a "atempo={NARRATION_TEMPO}" {slide_clip_file}"""
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
                caption_mp3 = os.path.join(presentation_dir, f"demo_{idx}_caption.mp3")
                try:
                    await narrate(
                        script, self.voice, caption_mp3, lang_code=self.lang_code,
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
                if not _build_demo_clip(media_path, caption_mp3, duration, clip_file):
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
        shot = os.path.join(presentation_dir, f"presentation_{idx}_1280x720.png")
        if not idx or not os.path.exists(shot):
            print(f"\n> Closing CTA screenshot not found ({shot}); skipping.\n")
            return None
        clip_file = os.path.join(presentation_dir, "closing.mp4")
        if not os.path.exists(clip_file):
            print("\n> Creating closing CTA clip\n")
            caption_mp3 = os.path.join(presentation_dir, "closing_caption.mp3")
            try:
                await narrate(
                    closing.get("narration") or "Get the code linked on screen.",
                    self.voice, caption_mp3, lang_code=self.lang_code,
                    pronunciations=self.pronunciations,
                )
            except Exception:
                caption_mp3 = None
            if caption_mp3 and not os.path.exists(caption_mp3):
                caption_mp3 = None
            duration = max(_media_duration(caption_mp3) if caption_mp3 else 0.0, 4.0)
            if not _build_demo_clip(shot, caption_mp3, duration, clip_file):
                return None
        return os.path.relpath(clip_file, presentation_dir)

    @step
    async def combine_clips(self, ctx: Context, ev: SlideClipCreated) -> StopEvent:
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
        subprocess.run(
            shlex.split(
                f"""ffmpeg -y -f concat -safe 0 -i {all_clips_file} -c copy {presentation_video_file}"""
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f'\n> Presentation video created: "open {presentation_video_file}"\n')
        return StopEvent(result="Presentation video created")
