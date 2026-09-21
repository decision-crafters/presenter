from typing import List

from llama_index.core.llms.llm import LLM
from llama_index.core import Document
from llama_index.core.prompts.base import PromptTemplate


from models import PresentationStructureWithTitle
from guide import format_steering

PRESENTATION_FROM_DATA_PROMPT = """
The key to creating a perfect presentation is following:
1. Understand Your Purpose and Audience
Define your goal: Why are you presenting? To inform, persuade, entertain, or inspire?
Key takeaway: Identify the one thing you want your audience to remember.
2. Develop a Clear Structure (Hook -> Pivot -> Deep Dive -> Zoom Out)
Organize your content into a logical flow. NEVER open with an agenda, a table of contents, or "what I'll cover" slide.
The Hook (first 1-2 slides): Frame the PROBLEM the source material addresses, then the PROMISE (why it matters / the stakes), then a one-line SOLUTION preview.
The Pivot: State the single KEY IDEA distilled from the source explicitly, in one sentence.
The Deep Dive (the bulk): This source is long. Do NOT summarize all of it with a broad, shallow overview. DISTILL THE SIGNAL: pick the ONE most important, elegant mechanism or insight and go deep on it (several atomic slides are fine). Cut the noise -- exhaustive related work, walls of equations, and tangential detail do not belong on slides.
Concrete example first: Always lead with a specific, tangible example from the source (a concrete case or a broken output), THEN generalize to the principle.
The Zoom Out (last 1-2 slides): Pull back to the impact and restate the one-sentence key takeaway.
3. Craft Powerful Content
Use storytelling: People connect with narratives. Frame your points as stories, with a beginning, middle, and end.
Be concise: Avoid overloading slides with text or data. Stick to one atomic core idea per slide.
Incorporate emotion: Make your audience feel something—excitement, curiosity, or inspiration.
Use data wisely: Visualize key stats (charts, infographics) but don’t overwhelm with too much detail.
Minimal Text: Use bullet points sparingly (6x6 rule: no more than 6 words per line and 6 lines per slide).
The first slide should only contain the title and optionally a diagram, nothing else.
EACH SLIDE MUST CONTAIN ONE ATOMIC CORE IDEA, and the content of each slide can be narrated in 40-50 seconds.

Now read these guidlines thoroughly and you will create the best presentation structure and the title for the presentation from the source material.
Aim for approximately {target_slides} slides by default (about 15 minutes of narrated content). More slides are fine when the depth justifies it, but do not go below {target_slides}; put the extra slides into the deep dive rather than into shallow breadth. EACH SLIDE MUST CONTAIN ONE ATOMIC CORE IDEA that can be narrated in 40-50 seconds; break down any slide that is too broad into smaller atomic slides. But DEPTH BEATS BREADTH: prefer going deep on the one core mechanism or insight from the source (spending multiple atomic slides on it) over shallow slides that skim everything the source contains. Follow the Hook -> Pivot -> Deep Dive -> Zoom Out flow above, lead with a concrete example before generalizing, and make sure the audience could articulate the single key idea in one sentence after watching. Now give me the title and core atomic idea for all the slides in the presentation in order. Your structure will be critiqued by the best presentation experts in the world, so make it perfect.{steering}

Build the presentation ONLY from this source material:
---
{source_text}
---
"""


def create_presentation_structure_from_data(
    docs: List[Document], llm: LLM, target_slides: int = 15, guide: str = ""
) -> PresentationStructureWithTitle:
    print("\n> Creating presentation structure from existing data...\n")
    source_text = "\n\n".join(d.text for d in docs)
    # Only target_slides (a number) is substituted into the template text;
    # steering and source_text are passed as values, so braces inside a guide
    # body or inside source code/JSON are never reparsed as template vars.
    instructions = PRESENTATION_FROM_DATA_PROMPT.replace(
        "{target_slides}", str(target_slides)
    )
    prompt = PromptTemplate(instructions)
    return llm.structured_predict(
        PresentationStructureWithTitle,
        prompt=prompt,
        source_text=source_text,
        steering=format_steering(guide),
    )
