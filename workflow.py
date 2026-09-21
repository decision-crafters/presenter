import os
import subprocess
import pickle
import time
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
from ingest import load_source_documents, extract_reference_urls
from design import Design, reveal_config_lines, apply_branding
from images import fetch_slide_image, POLLINATIONS_DELAY, MAX_IMAGES
from utils import (
    get_safe_foldername,
    sanitize_markdown,
    split_oversized_diagrams,
    references_slide,
)


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
    image_query: Optional[str] = None


class PresenterWorkflow(Workflow):
    def __init__(
        self,
        *args: Any,
        llm: LLM,
        target_slides: int = 15,
        guide: str = "",
        design: Optional[Design] = None,
        split_diagrams: bool = True,
        images_provider: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.llm = llm
        self.target_slides = target_slides
        self.guide = guide
        self.design = design
        self.split_diagrams = split_diagrams
        self.images_provider = images_provider

    @step
    async def start(self, ctx: Context, ev: StartEvent) -> TopicFound | SourceProvided:
        # A --source (GitHub repo or local Markdown/PDF path) routes to the
        # data-driven ingest branch; otherwise build from the topic string.
        await ctx.store.set("reference_urls", [])
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
        image_query_file = os.path.join(slide_folder, "image_query.txt")
        if os.path.exists(content_file) and os.path.exists(narration_file):
            with open(content_file, "r") as f:
                content = f.read()
            with open(narration_file, "r") as f:
                narration = f.read()
            image_query = None
            if os.path.exists(image_query_file):
                with open(image_query_file, "r") as f:
                    image_query = f.read().strip() or None
            return SlideCreated(
                slide_index=slide_index,
                content=content,
                narration=narration,
                image_query=image_query,
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
            topic,
            slide_info,
            prev_next_info,
            self.llm,
            self.guide,
            images_enabled=bool(self.images_provider),
        )
        content = slide.content
        narration = slide.narration
        image_query = (slide.image_query or "").strip() or None
        with open(content_file, "w") as f:
            f.write(content)
        with open(narration_file, "w") as f:
            f.write(narration)
        if image_query:
            with open(image_query_file, "w") as f:
                f.write(image_query)
        return SlideCreated(
            slide_index=slide_index,
            content=content,
            narration=narration,
            image_query=image_query,
        )

    def _fetch_slide_images(self, events, media_dir):
        """Fetch a photo for each slide that requested one.

        Returns {slide_index: inline-image markdown}. Sequential and capped, with
        a delay for Pollinations' throttle, and resumable (skips a cached file).
        """
        result = {}
        if not self.images_provider:
            return result
        queued = [
            (e.slide_index, e.image_query)
            for e in sorted(events, key=lambda x: x.slide_index)
            if e.image_query
        ]
        fetched = 0
        for idx, query in queued:
            out_path = os.path.join(media_dir, f"slide_{idx}.jpg")
            ref = f"\n\n![](./media/slide_{idx}.jpg)\n"
            if os.path.exists(out_path):
                result[idx] = ref
                continue
            if fetched >= MAX_IMAGES:
                break
            print(f"\n> Fetching image for slide {idx}: {query!r}\n")
            ok = fetch_slide_image(query, self.images_provider, out_path, seed=idx)
            if self.images_provider == "pollinations":
                time.sleep(POLLINATIONS_DELAY)
            if ok:
                fetched += 1
                result[idx] = ref
        return result

    @step
    async def combine_slides(self, ctx: Context, ev: SlideCreated) -> StopEvent:
        num_slides = await ctx.store.get("num_slides")
        presentation_folder = await ctx.store.get("presentation_folder")
        events = ctx.collect_events(ev, [SlideCreated] * num_slides)
        if events is None:
            return None

        slide_created_events: List[SlideCreated] = events
        media_dir = os.path.join(presentation_folder, "media")
        os.makedirs(media_dir, exist_ok=True)
        image_md = self._fetch_slide_images(slide_created_events, media_dir)
        slides_dict = {
            ev.slide_index: (
                f"{ev.content}{image_md.get(ev.slide_index, '')}"
                f"\n\nNote:\n{ev.narration}\n"
            )
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
        mmdc_result = subprocess.run(
            ["mmdc", "-i", template_file, "-o", presentation_file, "-e", "png"]
        )
        if not os.path.exists(presentation_file):
            raise RuntimeError(
                f"Diagram render failed: mmdc produced no {presentation_file} "
                f"(exit {mmdc_result.returncode}). Install @mermaid-js/mermaid-cli "
                "and ensure `mmdc` is on PATH."
            )
        if mmdc_result.returncode != 0:
            print("\n> Warning: mmdc reported errors; some diagrams may be missing.\n")

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

        # With diagrams rendered into media/, split any oversized one onto its
        # own slide and append a References slide (source + reference URLs).
        with open(presentation_file, "r") as f:
            deck_md = f.read()
        if self.split_diagrams:
            deck_md = split_oversized_diagrams(deck_md, media_dir)
        deck_md += references_slide(
            await ctx.store.get("source"),
            await ctx.store.get("reference_urls"),
        )
        with open(presentation_file, "w") as f:
            f.write(deck_md)

        # using mdslides to render presentation
        print("\n> Rendering presentation...\n")
        output_dir = os.path.join(presentation_folder, "output")
        html_file = os.path.join(output_dir, "index.html")
        pdf_file = os.path.join(presentation_folder, "presentation.pdf")
        mdslides_result = subprocess.run(
            [
                "mdslides",
                presentation_file,
                "--include",
                media_dir,
                "--output_dir",
                output_dir,
            ]
        )
        if mdslides_result.returncode != 0 or not os.path.exists(html_file):
            raise RuntimeError(
                f"Render failed: mdslides did not produce {html_file} "
                f"(exit {mdslides_result.returncode}). Install markdown-slides and "
                "ensure `mdslides` is on PATH."
            )
        # apply DESIGN.md branding (CSS + logo + assets) into the HTML before
        # decktape, so the PDF inherits the same theme.
        apply_branding(output_dir, self.design)
        print(
            f'\n> Presentation rendered. Run "open {html_file}" to view the presentation.\n'
        )

        print("\n> Exporting presentation to PDF...\n")
        decktape_result = subprocess.run(
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
        if decktape_result.returncode != 0 or not os.path.exists(pdf_file):
            raise RuntimeError(
                f"PDF export failed: decktape did not produce {pdf_file} "
                f"(exit {decktape_result.returncode}). Install decktape (and its "
                "Chrome) and ensure `decktape` is on PATH."
            )
        print(f'\n> Exported presentation to PDF. Open it using "open {pdf_file}"\n')

        return StopEvent(result=presentation_folder)
