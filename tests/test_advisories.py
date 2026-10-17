"""Tests for the YouTube best-practice advisory system.

Covers: rule-schema validation (including source_url + last_verified freshness),
the numeric boundaries, applies_to filtering, DESIGN.md override/disable, source
display in every output surface, and the individual check functions.
"""

import datetime
import os

import pytest

import youtube
from advisories import (
    apply_overrides,
    load_rules,
    make_advisory,
    resolve_content_type,
    resolve_rights,
    sources_html,
    sources_markdown,
    sources_plain,
    unique_sources,
)
from advisories.engine import VideoFacts, advise

# The 18 official Google/YouTube URLs the rules cite. This list must stay in
# sync with advisories/rules.yaml (asserted below).
OFFICIAL_URLS = [
    "https://www.youtube.com/watch?v=G1tHzUGdMwY",
    "https://support.google.com/youtube/answer/15424877",
    "https://blog.youtube/creator-and-artist-stories/creators-are-taking-over-tv-here-are-10-tips/",
    "https://support.google.com/youtube/answer/6175006",
    "https://support.google.com/youtube/answer/71673",
    "https://support.google.com/youtube/answer/9884579",
    "https://support.google.com/youtube/answer/9314415",
    "https://www.youtube.com/creators/grow/overview/",
    "https://support.google.com/youtube/answer/6388789",
    "https://support.google.com/youtube/answer/10059070",
    "https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/",
    "https://support.google.com/youtube/answer/72431",
    "https://support.google.com/youtube/answer/13861714",
    "https://www.youtube.com/creators/grow/optimize-your-content/",
    "https://www.youtube.com/creators/grow/understand-your-audience/",
    "https://support.google.com/youtube/answer/14328491",
    "https://support.google.com/youtube/answer/9783148",
    "https://support.google.com/youtube/answer/15128409",
]


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def rules_by_id(rules):
    return {r.id: r for r in rules}


def fired_ids(facts, rules):
    return {a.rule_id for a in advise(facts, rules)}


# ---- schema / data quality ----

def test_rules_load_and_have_unique_ids(rules):
    assert len(rules) >= 30
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids)), "duplicate rule ids"


def test_rules_schema(rules):
    for r in rules:
        assert r.id and r.id.strip()
        assert r.applies_to
        assert r.check and r.check.strip()
        assert isinstance(r.params, dict)
        assert r.severity in ("info", "warn", "error")
        assert r.message.strip() and r.why.strip()
        assert r.source_url.startswith("https://")
        assert r.source_type in ("official", "industry", "community")
        datetime.date.fromisoformat(r.last_verified)  # raises if malformed


def test_last_verified_within_12_months(rules):
    today = datetime.date.today()
    for r in rules:
        verified = datetime.date.fromisoformat(r.last_verified)
        assert verified <= today, f"{r.id}: last_verified in the future"
        assert (today - verified).days <= 366, f"{r.id}: last_verified stale"


def test_all_official_urls_present_in_rules(rules):
    urls = {r.source_url for r in rules}
    for url in OFFICIAL_URLS:
        assert url in urls


# ---- numeric boundaries ----

def test_short_length_boundary_180_181(rules):
    ok = VideoFacts(content_type="short", aspect_ratio="9:16", duration_seconds=180)
    assert "length.type_range.short" not in fired_ids(ok, rules)
    bad = VideoFacts(content_type="short", aspect_ratio="9:16", duration_seconds=181)
    ids = fired_ids(bad, rules)
    assert "length.type_range.short" in ids
    assert "length.vertical_long" in ids


def test_midroll_boundary_7m59_8m00(rules):
    assert "length.midroll_8min" in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=479), rules
    )
    assert "length.midroll_8min" not in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=480), rules
    )


def test_verify_15min_boundary_14m59_15m01(rules):
    assert "length.verify_15min" not in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=899), rules
    )
    assert "length.verify_15min" in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=901), rules
    )


def test_endscreen_min_video_24_25(rules):
    assert "endscreen.min_video_25s" in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=24), rules
    )
    assert "endscreen.min_video_25s" not in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=25), rules
    )


def test_max_12h_cap(rules):
    assert "length.max_12h_256gb" not in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=43200), rules
    )
    assert "length.max_12h_256gb" in fired_ids(
        VideoFacts(content_type="explainer", duration_seconds=43201), rules
    )


# ---- applies_to filtering ----

def test_applies_to_content_type(rules):
    explainer = fired_ids(VideoFacts(content_type="explainer", duration_seconds=300), rules)
    assert "length.type_range.documentary" not in explainer
    assert "tv.quality_check" not in explainer
    assert "copyright.book_content" not in explainer

    book = VideoFacts(content_type="book_summary", duration_seconds=300, rights="unknown")
    assert "copyright.book_content" in fired_ids(book, rules)

    doc = VideoFacts(content_type="documentary", duration_seconds=100)
    assert "length.type_range.documentary" in fired_ids(doc, rules)


# ---- DESIGN.md overrides ----

def test_apply_overrides_disable_and_param(rules):
    class _Design:
        tokens = {"advisories": {"title.length": {"enabled": False},
                                 "chapters.min_count": {"min_count": 2}}}

    over = apply_overrides(rules, _Design())
    ids = {r.id for r in over}
    assert "title.length" not in ids
    assert "chapters.min_count" in ids
    for r in over:
        if r.id == "chapters.min_count":
            assert r.params["min_count"] == 2

    # A 2-chapter video now passes the overridden rule.
    facts = VideoFacts(content_type="explainer", duration_seconds=300,
                       chapters=[{"start": 0}, {"start": 15}])
    assert "chapters.min_count" not in fired_ids(facts, over)


def test_content_type_and_rights_resolution():
    class _Design:
        tokens = {"content": {"type": "tutorial", "rights": "licensed",
                              "made_for_kids": False}}

    assert resolve_content_type(None, _Design()) == "tutorial"
    assert resolve_content_type("course", _Design()) == "course"
    assert resolve_content_type(None, None) == "explainer"
    assert resolve_rights(_Design()) == "licensed"
    assert resolve_rights(None) == "unknown"


# ---- source display ----

def test_advisory_plain_contains_why_and_source(rules_by_id):
    adv = make_advisory(rules_by_id["length.verify_15min"],
                        {"duration": "15:01", "limit": "15:00"})
    line = adv.to_plain()
    assert "Why:" in line
    assert adv.source_url in line
    assert "15:00" in line  # message placeholder {limit} was filled


def _known_advisories(rules):
    facts = VideoFacts(
        content_type="explainer",
        duration_seconds=901,          # length.verify_15min
        chapters=[{"start": 0}, {"start": 15}],  # chapters.min_count
        title="x" * 64,                # title.length
        hook="A short hook.",
        aspect_ratio="16:9",
    )
    return advise(facts, rules)


def test_known_set_fires_expected_rules(rules):
    ids = {a.rule_id for a in _known_advisories(rules)}
    assert {"length.verify_15min", "chapters.min_count", "title.length"} <= ids


def test_source_url_in_all_outputs(rules):
    advs = _known_advisories(rules)
    urls = {a.source_url for a in advs}
    assert urls  # the three known rules fired with sources

    plain = "\n".join(a.to_plain() for a in advs)
    markdown = "\n".join(a.to_markdown() for a in advs)
    html = "".join(a.to_html() for a in advs)
    for url in urls:
        assert url in plain
        assert f"[{url}]({url})" in markdown
        assert f'href="{url}"' in html

    # Deduplicated Sources list (first-seen order) includes every cited URL.
    src_urls = {u for u, _ in unique_sources(advs)}
    assert urls <= src_urls
    for url in urls:
        assert url in sources_plain(advs)
        assert url in sources_markdown(advs)
        assert url in sources_html(advs)


def test_render_page_and_plan_contain_sources(tmp_path, rules):
    advs = _known_advisories(rules)
    meta = {
        "title": "x" * 64,
        "hook": "A short hook.",
        "tags": [],
        "pinned_comment": "",
        "thumbnail_text": "Words",
        "alt_titles": [],
    }
    page = str(tmp_path / "index.html")
    youtube.render_page(page, meta, meta["title"], [], advs)
    html_text = open(page).read()

    out_dir = os.path.join(str(tmp_path), "youtube")
    os.makedirs(out_dir, exist_ok=True)
    plan = youtube.write_upload_plan(str(tmp_path), meta, [], advs)
    plan_text = open(plan).read()

    for adv in advs:
        assert adv.source_url in html_text
        assert f'href="{adv.source_url}"' in html_text
        assert adv.source_url in plan_text
        assert f"[{adv.source_url}]({adv.source_url})" in plan_text


# ---- individual check functions ----

def test_integrated_loudness_check():
    from advisories.engine import _integrated_loudness

    assert _integrated_loudness(VideoFacts(loudness_lufs=-11.0), {"max_lufs": -14.0}) is not None
    assert _integrated_loudness(VideoFacts(loudness_lufs=-16.0), {"max_lufs": -14.0}) is None
    assert _integrated_loudness(VideoFacts(loudness_lufs=None), {"max_lufs": -14.0}) is None


def test_first_audio_offset_check():
    from advisories.engine import _first_audio_offset

    assert _first_audio_offset(VideoFacts(first_audio_offset=16.0), {"max_seconds": 15}) is not None
    assert _first_audio_offset(VideoFacts(first_audio_offset=10.0), {"max_seconds": 15}) is None
    assert _first_audio_offset(VideoFacts(first_audio_offset=None), {"max_seconds": 15}) is None


def test_hook_first_speech_rule(rules):
    facts = VideoFacts(content_type="explainer", duration_seconds=300,
                       first_audio_offset=20.0, title="A reasonable title")
    assert "hook.first_speech" in fired_ids(facts, rules)


def test_unimplemented_check_skipped():
    from advisories import Rule

    rule = Rule(id="x", applies_to=["all"], check="does_not_exist", params={},
                severity="info", message="m", why="w",
                source_url="https://example.com", source_type="official",
                last_verified="2026-10-17")
    assert advise(VideoFacts(), [rule]) == []


def test_build_facts_no_mp4_is_safe(tmp_path):
    from advisories.engine import build_facts

    facts = build_facts(str(tmp_path), meta={"title": "T"}, content_type="course")
    assert facts.content_type == "course"
    assert facts.duration_seconds is None
    assert facts.captions is False
