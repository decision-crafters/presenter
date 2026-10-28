import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ci_grade", Path(__file__).resolve().parent.parent / "scripts" / "ci_grade.py"
)
assert _spec and _spec.loader
ci_grade = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_grade)


def test_parse_collected_keeps_only_test_ids():
    out = "tests/test_a.py::test_one\ntests/test_a.py::test_two\n\n2 tests collected in 0.1s\n"
    assert ci_grade.parse_collected(out) == {
        "tests/test_a.py::test_one",
        "tests/test_a.py::test_two",
    }


def test_missing_ids_reports_deleted_or_renamed_tests():
    base = {"t::a", "t::b", "t::c"}
    head = {"t::a", "t::c_renamed"}
    assert ci_grade.missing_ids(base, head) == ["t::b", "t::c"]


def test_missing_ids_honours_allowed_list():
    assert ci_grade.missing_ids({"t::a", "t::b"}, {"t::a"}, {"t::b"}) == []


def test_new_tests_are_never_flagged():
    assert ci_grade.missing_ids({"t::a"}, {"t::a", "t::new"}) == []


def test_read_allowed_missing_skips_comments_and_blanks(tmp_path):
    d = tmp_path / "acceptance" / "issue-7"
    d.mkdir(parents=True)
    (d / "allowed-missing.txt").write_text("# approved in #7\n\ntests/test_x.py::test_old\n")
    assert ci_grade.read_allowed_missing(tmp_path) == {"tests/test_x.py::test_old"}


def test_read_allowed_missing_without_acceptance_dir(tmp_path):
    assert ci_grade.read_allowed_missing(tmp_path) == set()


def test_format_summary():
    assert ci_grade.format_summary(" 3 files changed, 10 insertions(+)\n", "abcdef123") == (
        "Diff vs merge-base abcdef1: 3 files changed, 10 insertions(+)"
    )
    assert ci_grade.format_summary("", "abcdef123").endswith("no changes")
