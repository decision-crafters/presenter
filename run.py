import asyncio
import argparse
import json
import os
import sys

from dotenv import load_dotenv

from providers import build_llm
from guide import load_guide
from design import load_design
from persona import load_persona, select_persona, open_persona_gap_issue
from images import resolve_image_provider
from series import load_series, get_episode, episode_folder, episode_steering
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


def _maybe_file_gap_issue(domain: str, repo) -> None:
    """File a persona-gap GitHub issue. The --suggest-persona-issue flag is the
    opt-in; when running interactively, confirm first (outward action)."""
    import sys

    if sys.stdin.isatty():
        ans = input(
            f"File a GitHub issue to add a '{domain}' persona? [y/N] "
        ).strip().lower()
        if ans not in ("y", "yes"):
            print("\n> Skipped filing persona-gap issue.\n")
            return
    open_persona_gap_issue(domain, terms=[], repo=repo)


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
        default=None,
        help="Target number of slides / ~15 min of content (default 15; longer is fine)",
    )
    parser.add_argument(
        "--series",
        type=str,
        default=None,
        help="A series file (series/<slug>.yaml, from `python series.py plan`). "
        "Use with --episode to build one episode into its fixed folder.",
    )
    parser.add_argument(
        "--episode",
        type=int,
        default=None,
        help="Episode id within --series to build",
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
        default=None,
        help="Kokoro TTS voice name for narration (overrides the persona's voice)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Kokoro language code (a = American English; overrides the persona)",
    )
    parser.add_argument(
        "--persona",
        type=str,
        default=None,
        help=(
            "Path to a PERSONA.md (or persona dir) bundling a TTS voice, tone, "
            "and a technical-term pronunciation lexicon. Pass 'auto' to pick the "
            "best-fit persona from personas/ by content."
        ),
    )
    parser.add_argument(
        "--suggest-persona-issue",
        action="store_true",
        help=(
            "When --persona auto finds no fitting persona, offer to file a "
            "'new persona needed' GitHub issue (via gh) for the detected domain."
        ),
    )
    parser.add_argument(
        "--persona-issue-repo",
        type=str,
        default=None,
        help="Target repo (owner/name) for --suggest-persona-issue; default: current repo.",
    )
    parser.add_argument(
        "--youtube",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="With --export-video, also write a YouTube kit (title, description, "
        "chapters, tags, branded thumbnail) to <deck>/youtube/ (default: on; "
        "--no-youtube to skip)",
    )
    parser.add_argument(
        "--export-video",
        action="store_true",
        help="Export a video of the presentation with voiceover",
    )
    args = parser.parse_args()

    # A series episode supplies the source, design, slide count, folder, and a
    # thesis that narrows the whole source down to this one episode.
    series = episode = None
    if args.series or args.episode is not None:
        if not (args.series and args.episode is not None):
            parser.error("--series and --episode must be given together")
        series = load_series(args.series)
        episode = get_episode(series, args.episode)
        args.source = args.source or series.get("source")
        args.design = args.design or series.get("design")
        args.persona = args.persona or series.get("persona")
        args.slides = args.slides or series.get("slides")
        print(f"\n> Building {series['slug']} episode {episode['id']}: {episode['title']}\n")
    args.slides = args.slides or 15

    if not args.topic and not args.source:
        print("Nothing to build yet. Give a topic, or point --source at a repo/docs.\n")
        print(MODES_HELP)
        sys.exit(1)

    llm = build_llm(args.provider, args.model)

    # Resolve the persona: an explicit PERSONA.md, an auto-picked best fit, or
    # none (which still carries the common-term pronunciation built-ins).
    if args.persona and args.persona.lower() == "auto":
        persona, reason = select_persona(args.topic or args.source or "", llm)
        if persona:
            print(f"\n> Auto-selected persona: {persona.name}\n")
        else:
            print(
                f"\n> No persona fits this content (domain: {reason}); "
                "using built-in pronunciations only.\n"
            )
            if args.suggest_persona_issue:
                _maybe_file_gap_issue(reason, args.persona_issue_repo)
            persona = load_persona(None)
    elif args.persona:
        persona = load_persona(args.persona)
    else:
        persona = load_persona(None)

    # --design > persona's design; --voice/--lang > persona > built-in default.
    design = load_design(args.design or persona.design_ref)
    voice = args.voice or persona.voice or "af_heart"
    lang = args.lang or persona.lang or "a"
    # Guide body + DESIGN.md voice + persona tone merge into one steering block.
    steering = "\n\n".join(
        x
        for x in [
            episode_steering(series, episode) if episode else "",
            load_guide(args.guide),
            design.voice,
            persona.steering,
        ]
        if x
    )
    workflow = PresenterWorkflow(
        llm=llm,
        target_slides=args.slides,
        guide=steering,
        design=design,
        # Splitting diagrams onto their own slide changes the slide count, which
        # would desync the per-slide narration used by --export-video.
        split_diagrams=not args.export_video,
        images_provider=resolve_image_provider(args.images),
        presentation_folder=episode_folder(series, episode) if episode else None,
        title=episode["title"] if episode else None,
        source_focus=episode.get("focus") if episode else None,
        verbose=False,
        timeout=WORKFLOW_TIMEOUT,
    )
    presentation_dir = await workflow.run(query=args.topic, source=args.source)

    if args.export_video:
        print("\n> Exporting video of the presentation with voiceover...\n")
        video_creator_workflow = PresenterVideoCreaterWorkflow(
            voice=voice,
            lang_code=lang,
            pronunciations=persona.pronunciations,
            verbose=False,
            timeout=WORKFLOW_TIMEOUT,
        )
        await video_creator_workflow.run(presentation_dir=presentation_dir)

    if args.youtube and args.export_video:
        from youtube import build_kit

        # Best-effort: the video is already done, so a kit failure only warns.
        try:
            build_kit(
                presentation_dir,
                llm=llm,
                design=design,
                steering="\n\n".join(x for x in [design.voice, persona.steering] if x),
                series=series,
                ep=episode,
                source=args.source,
            )
        except Exception as e:
            print(
                f"\n! YouTube kit failed ({e}); the video is fine. Retry with: "
                f"python youtube.py {presentation_dir}\n"
            )

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
