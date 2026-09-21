import asyncio
import argparse

from dotenv import load_dotenv

from providers import build_llm
from guide import load_guide
from design import load_design
from workflow import PresenterWorkflow
from agents.video_creator import PresenterVideoCreaterWorkflow

# Local models are much slower than the OpenAI cloud, so give the workflows a
# generous timeout (seconds) for structure generation and per-slide composition.
WORKFLOW_TIMEOUT = 1800.0


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Presenter - Create beautiful presentations using AI.",
        usage=(
            "python run.py [<topic>] [--source <path|github-url>] "
            "[--provider ollama|ollama-cloud|openai] [--model <name>] "
            "[--voice <kokoro-voice>] [--export-video] [-h]"
        ),
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
        help="Build from a GitHub repo URL or a local Markdown/PDF file or folder",
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
        parser.error("Provide a <topic> or --source.")

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


if __name__ == "__main__":
    asyncio.run(main())
