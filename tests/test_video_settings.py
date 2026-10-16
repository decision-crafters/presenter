from dataclasses import dataclass

from video_settings import (
    DEFAULT_RESOLUTION,
    parse_resolution,
    video_settings,
)


@dataclass
class _Design:
    tokens: dict


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
