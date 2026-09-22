import os
import re
import json
import shutil
import subprocess
import pickle
import urllib.request
from typing import Any, List, Optional

from llama_index.core.llms.llm import LLM
from llama_index.core.workflow import (
    step,
    Context,
    Workflow,
    Event,
    StartEvent,
    StopEvent,
)
from llama_index.core.workflow.retry_policy import ConstantDelayRetryPolicy

from models import PresentationStructure, StructureFeedback, Slide, SlideInfo
from agents.structure_creater import create_presentation_structure
from agents.structure_validator import validate_presentation_structure
from agents.structure_updater import update_presentation_structure
from agents.slide_maker import compose_slide
from agents.structure_creater_from_data import create_presentation_structure_from_data
from ingest import (
    load_source_documents,
    extract_reference_urls,
    extract_demo_media,
    fetch_repo_tape,
)
from agents.demo_narrator import write_demo_walkthrough
from design import Design, reveal_config_lines, apply_branding
from utils import (
    get_safe_foldername,
    sanitize_markdown,
    split_oversized_diagrams,
    references_slide,
    demo_slides,
    cta_slide,
)


_DEMO_MAX_BYTES = 25 * 1024 * 1024  # skip absurdly large demo downloads


def _media_seconds(path: str) -> float:
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


def _fetch_demo_media(url: str, media_dir: str):
    """Download an http(s) demo recording, or copy a local path, into
    ``media_dir``. Returns the media basename, or ``None`` on any failure (a
    missing demo must never break the deck)."""
    base = os.path.basename(re.split(r"[?#]", url, 1)[0]) or "demo"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    if not os.path.splitext(base)[1]:
        base += ".gif"
    dest = os.path.join(media_dir, base)
    try:
        if url.lower().startswith(("http://", "https://")):
            req = urllib.request.Request(url, headers={"User-Agent": "presenter"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read(_DEMO_MAX_BYTES + 1)
            if not data or len(data) > _DEMO_MAX_BYTES:
                return None
            with open(dest, "wb") as f:
                f.write(data)
        else:
            src = url[len("file://"):] if url.startswith("file://") else url
            if not os.path.exists(src):
                return None
            shutil.copyfile(src, dest)
        return base
    except Exception as e:  # network error, bad URL, etc. -- skip this demo
        print(f"\n> WARNING: could not fetch demo media {url}: {e}\n")
        return None


class SourceProvided(Event):
    pass


class TopicFound(Event):
    pass


class StructureRequestReceived(Event):
    topic: str


class ValidateStructureRequestReceived(Event):
    structure: PresentationStructure


class UpdateStructureRequestReceived(Event):
    structure: PresentationStructure
    feedback: StructureFeedback


class StructureFinalized(Event):
    structure: PresentationStructure


class ComposeSlideRequestReceived(Event):
    slide_index: int
    slide_info: SlideInfo


class SlideCreated(Event):
    slide_index: int
    content: str
    narration: str


class PresenterWorkflow(Workflow):
    def __init__(
        self,
        *args: Any,
        llm: LLM,
        target_slides: int = 15,
        guide: str = "",
        design: Optional[Design] = None,
        split_diagrams: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.llm = llm
        self.target_slides = target_slides
        self.guide = guide
        self.design = design
        self.split_diagrams = split_diagrams

    @step
    async def start(self, ctx: Context, ev: StartEvent) -> TopicFound | SourceProvided:
        # A --source (GitHub repo or local Markdown/PDF path) routes to the
        # data-driven ingest branch; otherwise build from the topic string.
        await ctx.store.set("reference_urls", [])
        await ctx.store.set("demo_media", [])
        source = getattr(ev, "source", None)
        await ctx.store.set("source", source)
        if source:
            return SourceProvided()
        topic = ev.query
        await ctx.store.set("topic", topic)
        return TopicFound()

    @step
    async def ingest_source_and_build_structure(
        self, ctx: Context, ev: SourceProvided
    ) -> StructureFinalized:
        source = await ctx.store.get("source")
        documents = load_source_documents(source)
        await ctx.store.set("reference_urls", extract_reference_urls(documents))
        await ctx.store.set("demo_media", extract_demo_media(documents, source))
        structure_with_title = create_presentation_structure_from_data(
            documents, self.llm, self.target_slides, self.guide
        )
        topic = structure_with_title.title
        await ctx.store.set("topic", topic)

        presentation_folder = os.path.join("presentations", get_safe_foldername(topic))
        await ctx.store.set("presentation_folder", presentation_folder)
        os.makedirs(presentation_folder, exist_ok=True)

        structure = PresentationStructure(slides=structure_with_title.slides)
        structure_file = os.path.join(presentation_folder, "structure.pkl")
        with open(structure_file, "wb") as f:
            pickle.dump(structure, f)
        return StructureFinalized(structure=structure)

    @step
    async def prepare_presentation_folder(
        self, ctx: Context, ev: TopicFound
    ) -> StructureRequestReceived | StructureFinalized:
        topic = await ctx.store.get("topic")
        presentation_folder = os.path.join("presentations", get_safe_foldername(topic))
        await ctx.store.set("presentation_folder", presentation_folder)
        if not os.path.exists(presentation_folder):
            os.makedirs(presentation_folder)
        structure_file = os.path.join(presentation_folder, "structure.pkl")
        if os.path.exists(structure_file):
            print(
                f"\n> Presentation structure already exists for topic: {topic}."
                " Skipping structure creation and using the existing structure.\n"
            )
            with open(structure_file, "rb") as f:
                structure = pickle.load(f)
            return StructureFinalized(structure=structure)
        return StructureRequestReceived(topic=topic)

    @step
    async def create_presentation_structure(
        self, ctx: Context, ev: StructureRequestReceived
    ) -> ValidateStructureRequestReceived:
        topic = ev.topic
        initial_structure = create_presentation_structure(
            topic, self.llm, self.target_slides, self.guide
        )
        return ValidateStructureRequestReceived(structure=initial_structure)

    @step
    async def validate_presentation_structure(
        self, ctx: Context, ev: ValidateStructureRequestReceived
    ) -> UpdateStructureRequestReceived | StructureFinalized:
        structure = ev.structure
        topic = await ctx.store.get("topic")
        feedback = validate_presentation_structure(topic, structure, self.llm)
        if feedback.is_perfect:
            return StructureFinalized(structure=structure)
        return UpdateStructureRequestReceived(structure=structure, feedback=feedback)

    @step
    async def update_presentation_structure(
        self, ctx: Context, ev: UpdateStructureRequestReceived
    ) -> StructureFinalized:
        structure = ev.structure
        feedback = ev.feedback
        topic = await ctx.store.get("topic")
        updated_structure = update_presentation_structure(
            topic, structure, feedback, self.llm
        )
        # pickle the structure in the presentation folder
        structure_file = os.path.join(
            await ctx.store.get("presentation_folder"), "structure.pkl"
        )
        with open(structure_file, "wb") as f:
            pickle.dump(updated_structure, f)
        return StructureFinalized(structure=updated_structure)

    @step
    async def create_slides(
        self, ctx: Context, ev: StructureFinalized
    ) -> ComposeSlideRequestReceived:
        structure = ev.structure
        await ctx.store.set("structure", structure)
        await ctx.store.set("num_slides", len(structure.slides))
        for slide_index, slide in enumerate(structure.slides):
            ctx.send_event(
                ComposeSlideRequestReceived(slide_index=slide_index, slide_info=slide)
            )

    @step(num_workers=6, retry_policy=ConstantDelayRetryPolicy())
    async def compose_one_slide(
        self, ctx: Context, ev: ComposeSlideRequestReceived
    ) -> SlideCreated:
        slide_index = ev.slide_index
        slide_info = ev.slide_info
        print(f"\n> Creating slide: {slide_info.title}...\n")
        presentation_folder = await ctx.store.get("presentation_folder")
        slide_folder = os.path.join(presentation_folder, f"slide_{slide_index}")
        if not os.path.exists(slide_folder):
            os.makedirs(slide_folder)
        content_file = os.path.join(slide_folder, "content.md")
        narration_file = os.path.join(slide_folder, "narration.txt")
        if os.path.exists(content_file) and os.path.exists(narration_file):
            with open(content_file, "r") as f:
                content = f.read()
            with open(narration_file, "r") as f:
                narration = f.read()
            return SlideCreated(
                slide_index=slide_index, content=content, narration=narration
            )
        topic = await ctx.store.get("topic")
        structure = await ctx.store.get("structure")
        slides_info: List[SlideInfo] = structure.slides
        num_slides = await ctx.store.get("num_slides")
        prev_next_info = ""
        if slide_index > 0:
            prev_next_info += f'The previous slide is "{slides_info[slide_index-1].title}"({slides_info[slide_index-1].atomic_core_idea}). '
        if slide_index < num_slides - 1:
            prev_next_info += f'The next slide is "{slides_info[slide_index+1].title}"({slides_info[slide_index+1].atomic_core_idea}). '
        slide = await compose_slide(
            topic, slide_info, prev_next_info, self.llm, self.guide
        )
        content = slide.content
        narration = slide.narration
        with open(content_file, "w") as f:
            f.write(content)
        with open(narration_file, "w") as f:
            f.write(narration)
        return SlideCreated(
            slide_index=slide_index, content=content, narration=narration
        )

    @step
    async def combine_slides(self, ctx: Context, ev: SlideCreated) -> StopEvent:
        num_slides = await ctx.store.get("num_slides")
        presentation_folder = await ctx.store.get("presentation_folder")
        events = ctx.collect_events(ev, [SlideCreated] * num_slides)
        if events is None:
            return None

        slide_created_events: List[SlideCreated] = events
        slides_dict = {
            ev.slide_index: f"{ev.content}\n\nNote:\n{ev.narration}\n"
            for ev in slide_created_events
        }
        slides_list = [slides_dict[i] for i in range(num_slides)]
        slides_separator = "\n\n[comment]: # (!!!)\n\n"
        full_presentation_template = sanitize_markdown(
            slides_separator.join(slides_list)
        )
        full_presentation_template = (
            reveal_config_lines(self.design) + full_presentation_template
        )
        template_file = os.path.join(presentation_folder, "presentation_template.md")
        with open(template_file, "w") as f:
            f.write(full_presentation_template)

        # using mermaid-cli to render mermaid diagrams
        print("\n> Rendering diagrams...\n")
        presentation_file = os.path.join(presentation_folder, "presentation.md")
        result = subprocess.run(
            ["mmdc", "-i", template_file, "-o", presentation_file, "-e", "png"]
        )
        # mmdc aborts (non-zero, no output file) if a *single* mermaid block fails
        # to parse. Don't let one bad diagram discard the whole (expensive) run:
        # fall back to the un-rendered template so the deck still builds.
        if result.returncode != 0 or not os.path.exists(presentation_file):
            print(
                "\n> WARNING: mermaid rendering failed (mmdc exit "
                f"{result.returncode}); falling back to un-rendered diagrams.\n"
            )
            shutil.copyfile(template_file, presentation_file)

        with open(presentation_file, "r") as f:
            presentation_content = f.read()
        with open(presentation_file, "w") as f:
            f.write(sanitize_markdown(presentation_content))

        media_dir = os.path.join(presentation_folder, "media")
        if not os.path.exists(media_dir):
            os.makedirs(media_dir)
        # copy all png files from presentation folder to media folder
        for filename in os.listdir(presentation_folder):
            if filename.endswith(".png"):
                os.rename(
                    os.path.join(presentation_folder, filename),
                    os.path.join(media_dir, filename),
                )

        # Download any detected demo recordings (e.g. a repo's VHS/asciinema GIF)
        # into media/ so mdslides can embed them; keep a manifest for the Demo
        # slides and for the video splice (agents/video_creator.py).
        source = await ctx.store.get("source")
        demo_items = []
        for item in await ctx.store.get("demo_media") or []:
            fname = _fetch_demo_media(item["url"], media_dir)
            if fname:
                demo_items.append(
                    {"title": item.get("title") or "Demo", "file": fname,
                     "url": item["url"]}
                )
        # Write a spoken walkthrough per demo, sized to the clip's runtime and
        # grounded in the repo's VHS .tape commands when we can fetch them, so the
        # narrator explains each demo as it plays (stored for video_creator).
        structure = await ctx.store.get("structure")
        deck_title = getattr(structure, "title", "") if structure else ""
        for item in demo_items:
            secs = _media_seconds(os.path.join(media_dir, item["file"]))
            # Size the walkthrough to the demo's full runtime (capped for sanity)
            # so the narrator talks through the whole clip, not just the first 90s.
            secs = max(12.0, min(secs or 25.0, 240.0))
            basename = os.path.splitext(item["file"])[0]
            tape = fetch_repo_tape(source, basename) if source else None
            try:
                item["narration"] = await write_demo_walkthrough(
                    item["title"], tape or "", deck_title, secs, self.llm, self.guide
                )
                item["seconds"] = secs
            except Exception as e:
                print(f"\n> WARNING: demo walkthrough failed for {item['file']}: {e}\n")
        if demo_items:
            with open(os.path.join(presentation_folder, "demos.json"), "w") as f:
                json.dump(demo_items, f, indent=2)

        # With diagrams rendered into media/, split any oversized one onto its own
        # slide, then append Demo slides, a "Get the Code" CTA, and a References
        # slide (all after the structure slides, so per-slide narration stays in
        # sync for --export-video).
        with open(presentation_file, "r") as f:
            deck_md = f.read()
        if self.split_diagrams:
            deck_md = split_oversized_diagrams(deck_md, media_dir)
        demo_md = demo_slides(demo_items)
        cta_md = cta_slide(source, [d["url"] for d in demo_items])
        ref_md = references_slide(source, await ctx.store.get("reference_urls"))
        deck_md += demo_md + cta_md + ref_md
        with open(presentation_file, "w") as f:
            f.write(deck_md)

        # The CTA slide is appended (not a narrated structure slide), so the video
        # wouldn't include it. Record its screenshot index + an outro so the video
        # workflow can append a closing clip — every recording ends on the links.
        if cta_md:
            from utils import SLIDES_SEPARATOR
            total_slides = deck_md.count(SLIDES_SEPARATOR) + 1
            cta_index = total_slides - (1 if ref_md else 0)  # CTA precedes References
            closing = {
                "screenshot_index": cta_index,
                "narration": (
                    "That wraps up the walkthrough. The code, demos, and "
                    "documentation are all linked on screen — grab them from the "
                    "project's repository."
                ),
            }
            with open(os.path.join(presentation_folder, "closing.json"), "w") as f:
                json.dump(closing, f, indent=2)

        # using mdslides to render presentation
        print("\n> Rendering presentation...\n")
        output_dir = os.path.join(presentation_folder, "output")
        html_file = os.path.join(output_dir, "index.html")
        pdf_file = os.path.join(presentation_folder, "presentation.pdf")
        subprocess.run(
            [
                "mdslides",
                presentation_file,
                "--include",
                media_dir,
                "--output_dir",
                output_dir,
            ]
        )
        # apply DESIGN.md branding (CSS + logo + assets) into the HTML before
        # decktape, so the PDF inherits the same theme.
        apply_branding(output_dir, self.design, source)
        print(
            f'\n> Presentation rendered. Run "open {html_file}" to view the presentation.\n'
        )

        print("\n> Exporting presentation to PDF...\n")
        subprocess.run(
            [
                "decktape",
                "--headless=true",
                "--screenshots",
                "--screenshots-directory=.",
                "reveal",
                html_file,
                pdf_file,
            ]
        )
        print(f'\n> Exported presentation to PDF. Open it using "open {pdf_file}"\n')

        return StopEvent(result=presentation_folder)
