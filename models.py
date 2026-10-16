from typing import List, Optional
from pydantic import BaseModel, Field


class SlideInfo(BaseModel):
    title: str = Field(..., description="Title of the slide")
    atomic_core_idea: str = Field(
        ..., description="Atomic core idea for the content of this particular slide"
    )


class PresentationStructureWithTitle(BaseModel):
    title: str = Field(..., description="Title of the presentation")
    slides: List[SlideInfo] = Field(
        ..., description="List of slides information in the presentation"
    )


class PresentationStructure(BaseModel):
    slides: List[SlideInfo] = Field(
        ..., description="List of slides information in the presentation"
    )


class EpisodePlan(BaseModel):
    title: str = Field(..., description="Short episode title, 3-6 words")
    pillar: Optional[str] = Field(
        None, description="Optional content pillar or category for the episode"
    )
    thesis: str = Field(
        ...,
        description="The single idea or decision this episode goes deep on, in one sentence",
    )


class SeriesPlan(BaseModel):
    episodes: List[EpisodePlan] = Field(
        ..., description="Distinct, non-overlapping episodes, in viewing order"
    )


class YouTubeMetadata(BaseModel):
    title: str = Field(
        ...,
        description="Video title, 45-60 characters, the main search keyword in the first few words, specific and honest (no clickbait, no ALL CAPS, no emoji)",
    )
    alt_titles: List[str] = Field(
        ..., description="Two alternative titles with a different angle, same rules, for A/B testing"
    )
    hook: str = Field(
        ...,
        description="The description's first 1-2 sentences, at most 150 characters: the concrete problem and what the viewer gets. This is all that shows above the fold.",
    )
    summary: str = Field(
        ...,
        description="2 short paragraphs (80-150 words total) on what the video covers and the decision it helps with, using the main keywords naturally",
    )
    tags: List[str] = Field(
        ..., description="5-8 specific search tags, each at most 30 characters, most important first"
    )
    hashtags: List[str] = Field(
        ..., description="Exactly 3 relevant hashtags without spaces, e.g. #AIAgents"
    )
    thumbnail_text: str = Field(
        ...,
        description="At most 3 words for the thumbnail, bold and curiosity-driving; must not repeat the title verbatim",
    )
    pinned_comment: str = Field(
        ..., description="A short pinned comment asking viewers one specific question about their own experience"
    )


class StructureFeedback(BaseModel):
    is_perfect: bool = Field(
        ...,
        description="Whether all the slides represent atomic core ideas and can be narrated in 40-50 seconds",
    )
    feedback: Optional[str] = Field(
        None,
        description="If all the slides are not perfect then feedback on which slides need to be broken down and how",
    )


class Slide(BaseModel):
    content: str = Field(
        ...,
        description="The content of the slide in valid markdown, with no more than 6 words per line",
    )
    narration: str = Field(
        ...,
        description="Narration for the slide. The content should be narrated in 40-60 seconds",
    )
    image_query: Optional[str] = Field(
        None,
        description="Optional short search phrase or prompt for a supporting photo, only when a picture would strengthen the slide and it has no diagram",
    )
