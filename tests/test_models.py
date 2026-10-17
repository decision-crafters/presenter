from models import (
    PresentationStructure,
    PresentationStructureWithTitle,
    SlideInfo,
    enforce_slide_count,
    make_structure_model,
)


def _slides(n):
    return [SlideInfo(title=f"Slide {i}", atomic_core_idea=f"Idea {i}") for i in range(n)]


def _structure(n):
    return PresentationStructure(slides=_slides(n))


def test_make_structure_model_returns_static_without_target():
    assert make_structure_model(False, None) is PresentationStructure
    assert make_structure_model(True, None) is PresentationStructureWithTitle


def test_make_structure_model_pins_slide_count_in_schema():
    model = make_structure_model(False, 6)
    slides = model.model_json_schema()["properties"]["slides"]
    assert slides["minItems"] == 6
    assert slides["maxItems"] == 6

    with_title = make_structure_model(True, 6)
    schema = with_title.model_json_schema()
    assert "title" in schema["properties"]
    assert schema["properties"]["slides"]["minItems"] == 6


def test_enforce_slide_count_noop_when_within_target():
    structure = _structure(5)
    assert enforce_slide_count(structure, 6) is structure


def test_enforce_slide_count_trims_preserving_ends():
    structure = _structure(8)
    out = enforce_slide_count(structure, 6)
    assert len(out.slides) == 6
    assert out.slides[0].title == structure.slides[0].title  # hook kept
    assert out.slides[-1].title == structure.slides[-1].title  # zoom-out kept
    assert out.slides[1].title == structure.slides[1].title  # middle kept in order


def test_enforce_slide_count_small_target():
    out = enforce_slide_count(_structure(5), 2)
    assert [s.title for s in out.slides] == ["Slide 0", "Slide 1"]
