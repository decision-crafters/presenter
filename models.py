import os
from typing import Any

from pydantic import BaseModel, Field, create_model


class SlideInfo(BaseModel):
    title: str = Field(..., description="Title of the slide")
    atomic_core_idea: str = Field(
        ..., description="Atomic core idea for the content of this particular slide"
    )


class PresentationStructureWithTitle(BaseModel):
    title: str = Field(..., description="Title of the presentation")
    slides: list[SlideInfo] = Field(
        ..., description="List of slides information in the presentation"
    )


class PresentationStructure(BaseModel):
    slides: list[SlideInfo] = Field(
        ..., description="List of slides information in the presentation"
    )


def make_structure_model(with_title: bool, target_slides: int | None = None):
    """Return the structured-output model for a presentation structure.

    ``with_title`` adds the ``title`` field (the data-driven path). When
    ``target_slides`` is given, the ``slides`` field is pinned to exactly that
    count via JSON-schema ``minItems``/``maxItems`` (strict mode); otherwise the
    plain static class is returned (the loose "target" behavior).
    """
    if target_slides is None:
        return PresentationStructureWithTitle if with_title else PresentationStructure
    slides = Field(
        ...,
        min_length=target_slides,
        max_length=target_slides,
        description="List of slides information in the presentation",
    )
    fields: dict[str, Any] = {}
    if with_title:
        fields["title"] = (str, Field(..., description="Title of the presentation"))
    fields["slides"] = (list[SlideInfo], slides)
    name = "PresentationStructureWithTitle" if with_title else "PresentationStructure"
    return create_model(name, **fields)


def enforce_slide_count(
    structure: "PresentationStructure", target: int
) -> "PresentationStructure":
    """Trim a structure to exactly ``target`` slides by dropping excess deep-dive
    slides, preserving the first (hook) and last (zoom-out) slides. A no-op when
    the structure already has ``<= target`` slides."""
    slides = structure.slides
    if len(slides) <= target:
        return structure
    if target <= 2:
        trimmed = slides[:target]
    else:
        trimmed = [slides[0]] + slides[1:target - 1] + [slides[-1]]
    return PresentationStructure(slides=trimmed)


class EpisodePlan(BaseModel):
    title: str = Field(..., description="Short episode title, 3-6 words")
    pillar: str | None = Field(
        None, description="Optional content pillar or category for the episode"
    )
    thesis: str = Field(
        ...,
        description="The single idea or decision this episode goes deep on, in one sentence",
    )


class SeriesPlan(BaseModel):
    episodes: list[EpisodePlan] = Field(
        ..., description="Distinct, non-overlapping episodes, in viewing order"
    )


class YouTubeMetadata(BaseModel):
    title: str = Field(
        ...,
        description="Video title, 45-60 characters, the main search keyword in the first few words, specific and honest (no clickbait, no ALL CAPS, no emoji)",
    )
    alt_titles: list[str] = Field(
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
    tags: list[str] = Field(
        ..., description="5-8 specific search tags, each at most 30 characters, most important first"
    )
    hashtags: list[str] = Field(
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
    feedback: str | None = Field(
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
    image_query: str | None = Field(
        None,
        description="Optional short search phrase or prompt for a supporting photo, only when a picture would strengthen the slide and it has no diagram",
    )


# ---- structure cache (JSON, migrated from a legacy pickle) ----

STRUCTURE_FILE = "structure.json"
_LEGACY_STRUCTURE_FILE = "structure.pkl"


def structure_cache_path(folder: str) -> str | None:
    """Path to a cached structure, preferring JSON over the legacy pickle."""
    for name in (STRUCTURE_FILE, _LEGACY_STRUCTURE_FILE):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    return None


def save_structure(folder: str, structure: "PresentationStructure") -> str:
    """Persist the presentation structure as JSON; returns the file path."""
    path = os.path.join(folder, STRUCTURE_FILE)
    with open(path, "w") as f:
        f.write(structure.model_dump_json(indent=2))
    return path


def load_structure(folder: str) -> "PresentationStructure":
    """Load a cached structure, migrating a legacy ``structure.pkl`` to JSON."""
    path = structure_cache_path(folder)
    if path is None:
        raise FileNotFoundError(f"No structure cache in {folder}")
    if path.endswith(STRUCTURE_FILE):
        with open(path) as f:
            return PresentationStructure.model_validate_json(f.read())
    # One-time migration from the pre-JSON pickle cache.
    import pickle

    with open(path, "rb") as f:
        structure = pickle.load(f)
    os.remove(path)
    save_structure(folder, structure)
    return structure
