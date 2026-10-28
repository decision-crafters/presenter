"""CI grader: the checks a builder never controls (Invoice Exception Desk playbook, L7).

Runs after ruff/mypy/pytest in CircleCI:

1. **Acceptance tests** -- ``pytest acceptance/`` when that directory has tests. They are
   written by the grader (never the builder) from the ruling issue and land as their own commit.
2. **Base test IDs still exist** -- every test ID collected at the merge-base with the base
   branch must still be collected now, so a builder cannot delete or rename a test to go green.
   A ruling that approves removing a test lists the exact ID in
   ``acceptance/issue-<N>/allowed-missing.txt`` (written by the grader).
3. **Diff-size summary** -- ``git diff --shortstat`` against the merge-base, for the reviewer.

Exit status is non-zero when (1) or (2) fails.

Usage: ``python scripts/ci_grade.py``  (base branch: ``$CI_GRADE_BASE``, default ``master``)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = "tests"
ACCEPTANCE_DIR = "acceptance"


def parse_collected(output: str) -> set[str]:
    """Test IDs from ``pytest --collect-only -q`` output (lines containing ``::``)."""
    return {line.strip() for line in output.splitlines() if "::" in line}


def missing_ids(
    base: set[str], head: set[str], allowed: frozenset[str] | set[str] = frozenset()
) -> list[str]:
    """Base test IDs that are gone from ``head`` and not explicitly allowed, sorted."""
    return sorted(base - head - set(allowed))


def read_allowed_missing(root: Path) -> set[str]:
    """IDs a ruling allows to disappear, from ``acceptance/**/allowed-missing.txt``."""
    allowed: set[str] = set()
    for f in (root / ACCEPTANCE_DIR).glob("**/allowed-missing.txt"):
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                allowed.add(line)
    return allowed


def format_summary(shortstat: str, base_sha: str) -> str:
    stat = shortstat.strip() or "no changes"
    return f"Diff vs merge-base {base_sha[:7]}: {stat}"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def collect_ids(cwd: Path) -> set[str]:
    out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", TESTS_DIR], cwd)
    return parse_collected(out.stdout)


def merge_base(base_branch: str) -> str:
    _run(["git", "fetch", "-q", "origin", base_branch], ROOT)
    for ref in (f"origin/{base_branch}", base_branch):
        out = _run(["git", "merge-base", ref, "HEAD"], ROOT)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    raise SystemExit(f"ci_grade: cannot find merge-base with {base_branch}")


def base_ids(sha: str) -> set[str]:
    """Collect test IDs in a temporary worktree checked out at ``sha``."""
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "base"
        _run(["git", "worktree", "add", "-q", "--detach", str(wt), sha], ROOT)
        try:
            return collect_ids(wt)
        finally:
            _run(["git", "worktree", "remove", "--force", str(wt)], ROOT)


def run_acceptance() -> bool:
    adir = ROOT / ACCEPTANCE_DIR
    if not any(adir.glob("**/test_*.py")):
        print("Acceptance: none present (no ruled change in this PR).")
        return True
    print("Acceptance: running pytest acceptance/ ...")
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", ACCEPTANCE_DIR], cwd=ROOT)
    return res.returncode == 0


def main() -> int:
    base_branch = os.environ.get("CI_GRADE_BASE", "master")
    ok = run_acceptance()

    sha = merge_base(base_branch)
    gone = missing_ids(base_ids(sha), collect_ids(ROOT), read_allowed_missing(ROOT))
    if gone:
        ok = False
        print(f"Base test IDs: {len(gone)} missing vs {sha[:7]} (deleted or renamed):")
        for test_id in gone:
            print(f"  - {test_id}")
    else:
        print(f"Base test IDs: all present vs {sha[:7]}.")

    stat = _run(["git", "diff", "--shortstat", sha, "HEAD"], ROOT).stdout
    print(format_summary(stat, sha))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
