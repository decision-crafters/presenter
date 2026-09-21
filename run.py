import asyncio
import argparse
import json
import os
import sys

from dotenv import load_dotenv

from providers import build_llm
from guide import load_guide
from design import load_design
from images import resolve_image_provider
from workflow import PresenterWorkflow
from agents.video_creator import PresenterVideoCreaterWorkflow

# Local models are much slower than the OpenAI cloud, so give the workflows a
# generous timeout (seconds) for structure generation and per-slide composition.
WORKFLOW_TIMEOUT = 1800.0

MODES_HELP = """\
Three ways to make a deck:

  Topic          python run.py "the observer design pattern"
  GitHub repo    python run.py --source https://github.com/owner/repo
  Research/docs  python run.py --source ./research.md        (a file or a folder)

With --source, the title and slide structure are DERIVED from the source, so you
do not need a topic -- just point it at your repo or research.

Shape the result: --guide (focus the angle), --design (branding/theme),
--images (inline photos), --provider/--model (LLM backend), --export-video.

Output lands in presentations/<slug>/: output/index.html and presentation.pdf.
"""


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Presenter - turn a topic, a GitHub repo, or a research/Markdown "
        "source into a narrated slide deck (reveal.js HTML + PDF, optional MP4).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=MODES_HELP,
    )
    parser.add_argument(
        "topic",
        type=str,
        nargs="?",
        default=None,
        help="The topic of the presentation (omit when using --source)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Build from a GitHub repo URL or a local Markdown/PDF file/folder. "
        "The title and structure are derived from the source (no topic needed).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider: ollama (default), ollama-cloud, or openai",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model name (e.g. qwen2.5:7b, llama3.1:8b, gpt-4o-mini)",
    )
    parser.add_argument(
        "--slides",
        type=int,
        default=15,
        help="Target number of slides / ~15 min of content (default 15; longer is fine)",
    )
    parser.add_argument(
        "--guide",
        type=str,
        default=None,
        help=(
            "Path to a guidance file (SKILL.md / AGENT.md, agentskills.io format) "
            "that steers generation, e.g. to focus a broad source on one angle. "
            "Auto-discovers AGENT.md/SKILL.md in the project root if omitted."
        ),
    )
    parser.add_argument(
        "--design",
        type=str,
        default=None,
        help=(
            "Path to a DESIGN.md (google-labs-code/design.md format) that brands "
            "the deck: colors, fonts, reveal theme, background, logo, and voice. "
            "Auto-discovers DESIGN.md in the project root if omitted."
        ),
    )
    parser.add_argument(
        "--images",
        type=str,
        default=None,
        help=(
            "Add inline slide images from a free service: pollinations (no key), "
            "pexels (needs PEXELS_API_KEY), or picsum. Off by default."
        ),
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="af_heart",
        help="Kokoro TTS voice name for narration",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="a",
        help="Kokoro language code (a = American English)",
    )
    parser.add_argument(
        "--export-video",
        action="store_true",
        help="Export a video of the presentation with voiceover",
    )
    args = parser.parse_args()

    if not args.topic and not args.source:
        print("Nothing to build yet. Give a topic, or point --source at a repo/docs.\n")
        print(MODES_HELP)
        sys.exit(1)

    llm = build_llm(args.provider, args.model)
    design = load_design(args.design)
    # DESIGN.md's voice merges with the --guide body into one steering block.
    steering = "\n\n".join(x for x in [load_guide(args.guide), design.voice] if x)
    workflow = PresenterWorkflow(
        llm=llm,
        target_slides=args.slides,
        guide=steering,
        design=design,
        # Splitting diagrams onto their own slide changes the slide count, which
        # would desync the per-slide narration used by --export-video.
        split_diagrams=not args.export_video,
        images_provider=resolve_image_provider(args.images),
        verbose=False,
        timeout=WORKFLOW_TIMEOUT,
    )
    presentation_dir = await workflow.run(query=args.topic, source=args.source)

    if args.export_video:
        print("\n> Exporting video of the presentation with voiceover...\n")
        video_creator_workflow = PresenterVideoCreaterWorkflow(
            voice=args.voice,
            lang_code=args.lang,
            verbose=False,
            timeout=WORKFLOW_TIMEOUT,
        )
        await video_creator_workflow.run(presentation_dir=presentation_dir)

    # A stable, machine-readable line so any caller (agent or script) can locate
    # the outputs without parsing the human-readable log.
    mp4 = os.path.join(presentation_dir, "presentation.mp4")
    result = {
        "presentation_dir": presentation_dir,
        "html": os.path.join(presentation_dir, "output", "index.html"),
        "pdf": os.path.join(presentation_dir, "presentation.pdf"),
        "mp4": mp4 if (args.export_video and os.path.exists(mp4)) else None,
    }
    print("PRESENTER_RESULT " + json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
