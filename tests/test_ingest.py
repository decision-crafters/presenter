from ingest import _is_asset_or_tracking, _strip_utm, extract_reference_urls


class _Doc:
    def __init__(self, text):
        self.text = text


def test_strip_utm():
    assert _strip_utm("https://example.com/a?utm_source=x&utm_medium=y&keep=1") == "https://example.com/a?keep=1"
    assert _strip_utm("https://example.com/a?utm_source=x") == "https://example.com/a"
    assert _strip_utm("https://example.com/a") == "https://example.com/a"
    assert _strip_utm("https://example.com/a?keep=1&utm_campaign=api-credit") == "https://example.com/a?keep=1"


def test_is_asset_or_tracking():
    # Image-credit hosts (and their subdomains).
    assert _is_asset_or_tracking("https://unsplash.com/@steve_j?utm_source=ghost&utm_campaign=api-credit") is True
    assert _is_asset_or_tracking("https://images.unsplash.com/photo-123") is True
    assert _is_asset_or_tracking("https://images.pexels.com/photos/1.jpeg") is True
    assert _is_asset_or_tracking("https://cdn.pixabay.com/photo/1.png") is True
    assert _is_asset_or_tracking("https://gravatar.com/avatar/abc") is True
    # Tracking marker.
    assert _is_asset_or_tracking("https://example.com/redirect?utm_campaign=api-credit") is True
    # Image file extensions.
    assert _is_asset_or_tracking("https://example.com/photo.jpg") is True
    assert _is_asset_or_tracking("https://example.com/photo.svg?w=100") is True
    # Real sources survive.
    assert _is_asset_or_tracking("https://example.com/article") is False
    assert _is_asset_or_tracking("https://example.com/article?utm_source=x") is False


def test_extract_reference_urls_filters_ghost_caption():
    doc = _Doc(
        "# My Post\n\n"
        "A paragraph linking https://example.com/body-link.\n\n"
        "![photo](https://images.unsplash.com/photo-123?auto=format)\n\n"
        "Photo by [Steve Johnson](https://unsplash.com/@steve_j?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit) "
        "on [Unsplash](https://unsplash.com/?utm_source=ghost&utm_medium=referral&utm_campaign=api-credit).\n\n"
        "## Sources\n\n"
        "- https://example.com/the-real-article?utm_source=newsletter&utm_medium=email\n"
        "- https://example.org/second-source\n"
    )
    result = extract_reference_urls([doc])
    assert result == [
        "https://example.com/the-real-article",
        "https://example.org/second-source",
        "https://example.com/body-link",
    ]
    assert not any("unsplash" in u for u in result)
    assert not any("utm_" in u for u in result)


def test_extract_reference_urls_prefers_sources_heading():
    # The URL under "Sources" is listed first, body links after.
    doc = _Doc(
        "Intro https://example.com/body-link.\n\n"
        "## References\n\n"
        "- https://example.com/real-source\n"
    )
    assert extract_reference_urls([doc]) == [
        "https://example.com/real-source",
        "https://example.com/body-link",
    ]


def test_extract_reference_urls_dedupes_after_utm_strip():
    doc = _Doc("https://example.com/a?utm_source=one\nhttps://example.com/a?utm_source=two\n")
    assert extract_reference_urls([doc]) == ["https://example.com/a"]


def test_extract_reference_urls_respects_limit():
    doc = _Doc(
        "## Sources\n\n"
        + "\n".join(f"- https://example.com/s{i}" for i in range(10))
    )
    assert extract_reference_urls([doc], limit=3) == [
        "https://example.com/s0",
        "https://example.com/s1",
        "https://example.com/s2",
    ]
