from dataclasses import dataclass

from video_settings import (
    DEFAULT_RESOLUTION,
    WatermarkSettings,
    parse_resolution,
    video_settings,
    watermark_filter,
    watermark_issue,
)


@dataclass
class _Design:
    tokens: dict
    source_dir: str = None


def test_default_is_1080p():
    assert DEFAULT_RESOLUTION == (1920, 1080)


def test_named_sizes():
    assert parse_resolution("480p") == (854, 480)
    assert parse_resolution("720p") == (1280, 720)
    assert parse_resolution("1080p") == (1920, 1080)
    assert parse_resolution("1440p") == (2560, 1440)
    assert parse_resolution("2160p") == (3840, 2160)
    assert parse_resolution("4k") == (3840, 2160)


def test_explicit_wxh_and_case():
    assert parse_resolution("1920x1080") == (1920, 1080)
    assert parse_resolution("1280X720") == (1280, 720)
    assert parse_resolution([2560, 1440]) == (2560, 1440)


def test_fallback_on_bad_input():
    assert parse_resolution(None) == DEFAULT_RESOLUTION
    assert parse_resolution("") == DEFAULT_RESOLUTION
    assert parse_resolution("bogus") == DEFAULT_RESOLUTION
    assert parse_resolution("999x999") == DEFAULT_RESOLUTION  # odd dimensions rejected


def test_design_resolution_overrides_default():
    d = _Design({"video": {"resolution": "720p"}})
    assert video_settings(d).resolution == (1280, 720)
    # no design / no video block -> default 1080p
    assert video_settings(None).resolution == DEFAULT_RESOLUTION


def test_watermark_disabled_by_default():
    assert video_settings(_Design({})).watermark is None
    assert video_settings(_Design({"video": {}})).watermark is None
    assert video_settings(_Design({"logo": "logo.png"})).watermark is None


def test_watermark_uses_logo_by_default():
    d = _Design({"logo": "logo.png", "video": {"watermark": {}}})
    wm = video_settings(d).watermark
    assert wm is not None
    assert wm.image.endswith("logo.png")
    assert wm.position == "bottom-right"
    assert wm.height == 64


def test_watermark_image_override_and_position():
    d = _Design({
        "logo": "logo.png",
        "video": {"watermark": {"image": "bug.png", "position": "top-left", "height": 100}},
    })
    wm = video_settings(d).watermark
    assert wm.image.endswith("bug.png")
    assert wm.position == "top-left"
    assert wm.height == 100


def test_watermark_resolves_relative_to_source_dir():
    d = _Design({"logo": "logo.png", "video": {"watermark": {}}}, source_dir="/brand")
    assert video_settings(d).watermark.image == "/brand/logo.png"


def test_watermark_filter_positions():
    wm = WatermarkSettings(image="x.png")
    f = watermark_filter(wm, 1080)
    assert "scale=-1:64" in f
    assert f.endswith("overlay=W-w-24:H-h-24")  # bottom-right default
    assert watermark_filter(WatermarkSettings(image="x.png", position="top-left"), 1080).endswith("overlay=24:24")
    assert watermark_filter(WatermarkSettings(image="x.png", position="top-right"), 1080).endswith("overlay=W-w-24:24")
    assert watermark_filter(WatermarkSettings(image="x.png", position="bottom-left"), 1080).endswith("overlay=24:H-h-24")
    # height scales with the render resolution
    assert "scale=-1:32" in watermark_filter(WatermarkSettings(image="x.png", height=64), 540)


def test_watermark_enabled_flag():
    # `enabled: false` opts out even when a logo is present.
    d = _Design({"logo": "logo.png", "video": {"watermark": {"enabled": False}}})
    assert video_settings(d).watermark is None
    # `enabled: true` is the explicit form of the default and enables.
    d2 = _Design({"logo": "logo.png", "video": {"watermark": {"enabled": True}}})
    assert video_settings(d2).watermark.image.endswith("logo.png")


def test_watermark_issue(tmp_path):
    # Not configured -> no warning.
    assert watermark_issue(None) is None
    assert watermark_issue(WatermarkSettings(image=None)) is None
    # A valid local PNG -> no warning.
    png = tmp_path / "logo.png"
    png.write_bytes(b"x")
    assert watermark_issue(WatermarkSettings(image=str(png))) is None
    # URL / SVG / missing -> each yields a reason.
    assert "URL" in watermark_issue(WatermarkSettings(image="https://x/logo.png"))
    assert "SVG" in watermark_issue(WatermarkSettings(image="logo.svg"))
    assert "not found" in watermark_issue(WatermarkSettings(image=str(tmp_path / "nope.png")))
