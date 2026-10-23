from design import Design
from layouts import (
    LAYOUT_INSTRUCTION,
    LAYOUTS,
    layout_css,
    layouts_enabled,
    normalize_layout,
    separate_blocks,
    tag_slide,
)


def test_normalize_layout_accepts_known_names_only():
    assert normalize_layout("Boundary ") == "boundary"
    assert normalize_layout("tradeoff") == "tradeoff"
    assert normalize_layout("hero") is None
    assert normalize_layout("") is None
    assert normalize_layout(None) is None


def test_tag_slide_prefixes_reveal_class_comment():
    tagged = tag_slide("### Title", "result")
    assert tagged.startswith('<!-- .slide: class="layout-result" -->\n')
    assert tagged.endswith("### Title")


def test_tag_slide_leaves_default_layout_untouched():
    assert tag_slide("### Title", None) == "### Title"
    assert tag_slide("### Title", "unknown") == "### Title"


def test_layouts_enabled_defaults_on_with_opt_outs():
    assert layouts_enabled(None)
    assert layouts_enabled(Design())
    assert not layouts_enabled(Design(), flag=False)
    assert not layouts_enabled(Design(tokens={"layouts": False}))


def test_layout_css_covers_every_layout_and_uses_brand_colors():
    design = Design(tokens={"colors": {"background": "#081426", "accent": "#1FEB50"}})
    css = layout_css(design)
    for name in LAYOUTS:
        assert f".layout-{name}" in css
    assert "#1FEB50" in css and "#081426" in css


def test_layout_css_works_without_a_design():
    assert ".layout-boundary" in layout_css(None)


def test_instruction_names_every_layout():
    for name in LAYOUTS:
        assert name in LAYOUT_INSTRUCTION


def test_separate_blocks_splits_list_from_following_quote():
    md = "### T\nOne line.\n1. a\n2. b\n> **X** — y"
    out = separate_blocks(md)
    assert "2. b\n\n> **X**" in out
    assert "### T\n\nOne line.\n\n1. a\n2. b" in out


def test_separate_blocks_keeps_well_formed_markdown():
    md = "### T\n\n1. a\n2. b\n\n> q"
    assert separate_blocks(md) == md


def test_tag_slide_separates_blocks_on_layout_slides():
    assert "1. a\n\n> q" in tag_slide("1. a\n> q", "boundary")
