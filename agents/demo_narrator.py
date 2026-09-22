"""Write a spoken walkthrough for a demo recording (GIF/terminal capture).

The narration is generated to roughly fill the demo's runtime so the narrator
explains what's happening *while it plays*, instead of a bare title + silence.
When the repo's VHS ``.tape`` (the actually-typed commands) is available, the
walkthrough is grounded in those real steps.
"""

from llama_index.core.llms.llm import LLM
from llama_index.core.prompts.base import PromptTemplate
from pydantic import BaseModel, Field

from guide import format_steering

# Kokoro speaks at roughly this rate; used to size the script to the clip length.
WORDS_PER_SECOND = 2.4


class DemoWalkthrough(BaseModel):
    narration: str = Field(
        description=(
            "Spoken walkthrough of the demo as it plays: the goal, each step, and "
            "the result. Present tense, plain spoken sentences — no headings, "
            "lists, markdown, or stage directions."
        )
    )


async def write_demo_walkthrough(
    title: str,
    tape_commands: str,
    context: str,
    target_seconds: float,
    llm: LLM,
    guide: str = "",
) -> str:
    """Return a walkthrough script ~``target_seconds`` long (persona-steered)."""
    words = max(30, int(target_seconds * WORDS_PER_SECOND))
    steering = format_steering(guide)
    commands = (
        f"\nThe demo runs these terminal commands in order (from its VHS tape):\n"
        f"{tape_commands.strip()[:2000]}\n"
        if tape_commands
        else ""
    )
    prompt = (
        "You are narrating a screen-recorded terminal demo that plays on screen "
        "while you speak. Explain what the viewer is seeing as it happens.\n\n"
        f"Presentation context: {context or 'a technical project'}\n"
        f"Demo title: {title}\n"
        f"{commands}\n"
        f"Write about {words} words (~{target_seconds:.0f} seconds at a natural "
        "speaking pace). Walk through the goal, each step as it runs, and the "
        "outcome. Present tense, spoken prose only — no headings, no bullet lists, "
        "no markdown, no 'in this demo' filler. Start directly with the action."
        f"{steering}"
    )
    result = await llm.astructured_predict(DemoWalkthrough, prompt=PromptTemplate(prompt))
    return result.narration
