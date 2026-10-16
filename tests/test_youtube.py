from PIL import Image, ImageFont

from youtube import (
    build_description,
    youtube_settings,
    YouTubeSettings,
    _font_has_glyph,
    _sanitize_thumbnail_text,
    render_thumbnail,
)


def _meta():
    return {
        "hook": "A short hook.",
        "summary": "A two paragraph summary.",
        "hashtags": ["#AI", "#ML", "#Dev"],
    }


def _chapters():
    return [{"start": 0, "title": "Intro"}, {"start": 12, "title": "Deep dive"}]


def test_backward_compat_no_youtube_block():
    """With no `youtube:` block the description is byte-for-byte the pre-settings
    format (hook, summary, code link, chapters, hashtags)."""
    desc = build_description(_meta(), _chapters(), "https://github.com/o/r", None, None)
    assert desc == (
        "A short hook.\n"
        "\n"
        "A two paragraph summary.\n"
        "\n"
        "▶ Code: https://github.com/o/r\n"
        "\n"
        "Chapters\n"
        "0:00 Intro\n"
        "0:12 Deep dive\n"
        "\n"
        "#AI #ML #Dev\n"
    )


def test_no_design_is_empty_settings():
    assert youtube_settings(None).subscribe is None
    assert youtube_settings(None).category is None
    assert youtube_settings(None).description_footer == ""


def test_single_cta_no_subscribe():
    """Without `subscribe:`, the footer is the only call-to-action (no
    "Subscribe for more:" line is auto-added)."""
    yt = YouTubeSettings(
        category=28,
        language="en",
        description_footer="— Sign up: https://example.org/signup",
    )
    desc = build_description(_meta(), _chapters(), "https://github.com/o/r", None, None, yt)
    assert "Subscribe for more:" not in desc
    assert "— Sign up: https://example.org/signup" in desc


def test_subscribe_when_set_appears_once():
    yt = YouTubeSettings(subscribe="https://example.org/subscribe")
    desc = build_description(_meta(), _chapters(), None, None, None, yt)
    assert desc.count("Subscribe for more:") == 1
    assert "Subscribe for more: https://example.org/subscribe" in desc


def test_footer_and_links_ordering():
    """Links and footer land before chapters/hashtags; the subscribe CTA follows
    the links."""
    yt = YouTubeSettings(
        subscribe="https://example.org/subscribe",
        description_footer="— Footer",
        links=[("Website", "https://example.org")],
    )
    desc = build_description(_meta(), _chapters(), None, None, None, yt)
    assert desc.index("▶ Website: https://example.org") < desc.index("Subscribe for more:")
    assert desc.index("Subscribe for more:") < desc.index("Chapters")
    assert desc.index("— Footer") < desc.index("#AI #ML #Dev")


def test_sanitize_transliterates_symbols():
    assert _sanitize_thumbnail_text("A ≠ B") == "A != B"
    assert _sanitize_thumbnail_text("Connected ≠ Authorized") == "Connected != Authorized"
    assert _sanitize_thumbnail_text("A → B") == "A -> B"
    assert _sanitize_thumbnail_text("≤ 3") == "<= 3"


def test_sanitize_strips_unsupported_non_ascii():
    # Without a font, any non-ASCII char not in the map is dropped to whitespace.
    result = _sanitize_thumbnail_text("A 🔥 B")
    assert "🔥" not in result
    assert result.split() == ["A", "B"]


def test_font_has_glyph_detects_tofu():
    font = ImageFont.load_default(60)  # limited font: has ASCII, lacks ≠
    assert _font_has_glyph(font, "A") is True
    assert _font_has_glyph(font, "≠") is False


def test_sanitized_text_has_no_missing_glyphs():
    font = ImageFont.load_default(60)
    text = _sanitize_thumbnail_text("Connected ≠ Authorized", font)
    assert text == "Connected != Authorized"
    for ch in text.replace(" ", ""):
        assert _font_has_glyph(font, ch), ch


def test_render_thumbnail_handles_symbol_text(tmp_path):
    out = str(tmp_path / "thumbnail.jpg")
    render_thumbnail(out, "Connected ≠ Authorized", None, None)
    with Image.open(out) as im:
        assert im.format == "JPEG"
        assert im.size == (1280, 720)
