import json
import os
import tempfile

from run import build_result


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("x")


def test_result_paths_full():
    with tempfile.TemporaryDirectory() as d:
        _touch(os.path.join(d, "output", "index.html"))
        _touch(os.path.join(d, "presentation.pdf"))
        _touch(os.path.join(d, "presentation.mp4"))
        _touch(os.path.join(d, "captions.srt"))
        _touch(os.path.join(d, "captions.vtt"))
        for name in ("metadata.json", "description.txt", "thumbnail.jpg",
                     "index.html", "UPLOAD_PLAN.md"):
            _touch(os.path.join(d, "youtube", name))

        result = build_result(d, export_video=True, youtube=True)

        assert result["presentation_dir"] == d
        assert result["mp4"] == os.path.join(d, "presentation.mp4")
        assert result["captions"] == {
            "srt": os.path.join(d, "captions.srt"),
            "vtt": os.path.join(d, "captions.vtt"),
        }
        assert result["youtube"] == {
            "metadata": os.path.join(d, "youtube", "metadata.json"),
            "description": os.path.join(d, "youtube", "description.txt"),
            "thumbnail": os.path.join(d, "youtube", "thumbnail.jpg"),
            "page": os.path.join(d, "youtube", "index.html"),
            "plan": os.path.join(d, "youtube", "UPLOAD_PLAN.md"),
        }


def test_result_paths_only_existing():
    """Missing files are omitted rather than listed."""
    with tempfile.TemporaryDirectory() as d:
        _touch(os.path.join(d, "presentation.mp4"))
        _touch(os.path.join(d, "captions.srt"))  # srt only, no vtt
        _touch(os.path.join(d, "youtube", "metadata.json"))

        result = build_result(d, export_video=True, youtube=True)
        assert result["captions"] == {"srt": os.path.join(d, "captions.srt")}
        assert result["youtube"] == {"metadata": os.path.join(d, "youtube", "metadata.json")}


def test_result_no_video():
    with tempfile.TemporaryDirectory() as d:
        result = build_result(d, export_video=False, youtube=False)
        assert result["mp4"] is None
        assert result["captions"] is None
        assert result["youtube"] is None


def test_result_slides_field():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "structure.json"), "w") as f:
            json.dump(
                {"slides": [{"title": "a", "atomic_core_idea": "x"} for _ in range(4)]},
                f,
            )
        result = build_result(d, False, False, slides_requested=6)
        assert result["slides"] == {"requested": 6, "actual": 4}

    with tempfile.TemporaryDirectory() as d:
        result = build_result(d, False, False)
        assert result["slides"] == {"requested": None, "actual": None}
