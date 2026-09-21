from llama_index.core.llms.llm import LLM
from llama_index.core.prompts.base import PromptTemplate


from models import PresentationStructure, StructureFeedback

PRESENTATION_STRUCTURE_VALIDATOR_PROMPT = """
you are world's best presentation creator with 10 years of experience, you've created hundreds of perfect presentations and every single one of them kept the audience captive for the whole time. your apprentice prepared a presentation structure. Review it against these criteria:
1. Atomicity: each slide must contain just ONE atomic core idea that can be narrated in 40-50 seconds. If a slide is too broad, it must be broken into smaller atomic slides.
2. Hook: the presentation must open by framing the problem and why it matters (a hook), NOT with an agenda, a table of contents, or a "what I'll cover" slide.
3. Concrete example first: it should lead with a concrete, tangible example before the abstract/general idea.
4. Depth over breadth: it should go DEEP on the single most important mechanism rather than skim the whole topic with shallow slides. Spending SEVERAL atomic slides on that one core mechanism is GOOD -- do NOT ask for it to be flattened or generalized; that is the intended deep dive.
5. Zoom out: it should end on the impact / the one-sentence key takeaway.
The presentation on the topic: "{topic}"
Here is the initial structure the apprentice created:
---
{structure}
---
Now think closely about the slides above. If they satisfy all five criteria, the structure is perfect. Otherwise, tell the apprentice exactly which slides are too broad and how to break them down, and/or which of the hook / concrete-example-first / deep-dive / zoom-out criteria are missing and how to fix them -- all without breaking the flow.
"""


def validate_presentation_structure(
    topic: str, structure: PresentationStructure, llm: LLM
) -> StructureFeedback:
    print("\n> Getting expert feedback about the presentation structure...\n")
    structure_strs = []
    for i, slide in enumerate(structure.slides):
        structure_strs.append(
            f"Slide {i+1}"
            f"\nTitle: {slide.title}"
            f"\nCore Idea for this slide: {slide.atomic_core_idea}"
        )
    prompt = PromptTemplate(PRESENTATION_STRUCTURE_VALIDATOR_PROMPT)
    structure_str = "\n\n".join(structure_strs)
    # print(structure_str)
    return llm.structured_predict(
        StructureFeedback,
        prompt=prompt,
        topic=topic,
        structure=structure_str,
    )
