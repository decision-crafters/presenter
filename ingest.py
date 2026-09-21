"""Local source ingestion for the data-driven presentation path.

Turns a ``--source`` (a GitHub repo URL, or a local file/directory) into a list
of ``Document`` objects — no cloud LlamaParse. A GitHub repo is packed by
``repomix`` (which fetches it, honors .gitignore, and runs a Secretlint secret
scan before anything reaches the LLM), restricted to documentation globs. Local
sources are read directly: Markdown and plain text are the primary inputs, and
PDFs work too when ``llama-index-readers-file`` is installed.

A large repo can hold far more text than fits one structured-generation call, so
we prioritize the most descriptive files (root README, then specs/references) and
cap the total that gets ingested.
"""

import os
import re
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from llama_index.core import Document

# Extensions worth reading for building a presentation from a repo/folder.
TEXT_EXTS = {".md", ".mdx", ".markdown", ".rst", ".txt"}
DOC_EXTS = {".pdf"}
INGEST_EXTS = TEXT_EXTS | DOC_EXTS

# Directories that never contain useful narrative content.
EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "venv", "__pycache__", ".next", ".cache", "site-packages",
}

# Guards so a big repo can't overwhelm the model's context.
MAX_FILES = 40
MAX_TOTAL_BYTES = 400_000  # ~400 KB total for a local folder
MAX_FILE_BYTES = 40_000  # no single local file may consume more than ~40 KB
# A repomix-packed repo is one blob fed to a single structured-generation call.
# Keep it small (~15K tokens) so it resolves in one LLM call -- and so we distill
# the signal, not the whole repo.
MAX_REPO_BYTES = 60_000
MIN_DOC_CHARS = 800  # below this, the source has too little text for a deck

GITHUB_URL_RE = re.compile(
    r"^(https?://|git@)(www\.)?github\.com[/:].+", re.IGNORECASE
)

# Doc-first glob set repomix packs from a remote repo (comma-separated).
REPO_INCLUDE_GLOBS = "**/*.md,**/*.mdx,**/*.markdown,**/*.rst,**/*.txt"


def _is_github_url(source: str) -> bool:
    return bool(GITHUB_URL_RE.match(source.strip()))


def _repomix_command() -> List[str]:
    """Prefer a globally installed `repomix`, else run it via `npx`."""
    if shutil.which("repomix"):
        return ["repomix"]
    if shutil.which("npx"):
        return ["npx", "--yes", "repomix"]
    raise RuntimeError(
        "repomix is required to ingest a GitHub repo but was not found. "
        "Install Node.js and run `npm install -g repomix`, or ensure `npx` is on PATH."
    )


_FILE_SECTION_RE = re.compile(r"^## File: (.+?)\s*$", re.MULTILINE)


def _prioritize_packed(packed: str) -> str:
    """Reorder repomix's per-file sections so README/specs come first.

    repomix packs files in directory order; because we then cap total size, we
    reorder by the same priority used for local folders (``_file_priority``) so
    the highest-signal docs survive the cap. The leading File-Summary /
    Directory-Structure preamble is kept as-is.
    """
    matches = list(_FILE_SECTION_RE.finditer(packed))
    if not matches:
        return packed
    preamble = packed[: matches[0].start()]
    sections = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(packed)
        path = m.group(1).strip()
        sections.append((_file_priority(path), i, packed[m.start() : end]))
    sections.sort(key=lambda s: (s[0], s[1]))  # priority, then original order
    return preamble + "".join(s[2] for s in sections)


def _pack_repo(url: str) -> str:
    """Pack a remote repo's docs into one Markdown blob via repomix.

    repomix handles the remote fetch, honors .gitignore, and runs a Secretlint
    secret scan before we ship any content to the LLM. We restrict to
    documentation globs (``REPO_INCLUDE_GLOBS``) to keep the signal high.
    """
    cmd = _repomix_command()
    fd, out_path = tempfile.mkstemp(suffix=".md", prefix="presenter_repomix_")
    os.close(fd)
    print(f"\n> Packing {url} with repomix ...\n")
    try:
        subprocess.run(
            cmd
            + [
                "--remote", url,
                "--include", REPO_INCLUDE_GLOBS,
                "--style", "markdown",
                "--output", out_path,
                "--quiet",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with open(out_path, "r") as f:
            return _prioritize_packed(f.read())
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


def _file_priority(rel_path: str) -> int:
    """Lower sorts first: README, then specs/references, then docs/, then rest.

    Many repos keep their real conceptual signal in ``*.spec.md`` files and in
    ``references/``/``schemas/`` folders, while ``docs/`` holds peripheral notes.
    """
    lowered = rel_path.lower()
    base = os.path.basename(lowered)
    is_root = "/" not in lowered
    if base.startswith("readme"):
        return 0 if is_root else 2  # the root README (the overview) leads
    if (
        base.endswith(".spec.md")
        or "references/" in lowered
        or "schemas/" in lowered
        or "architecture" in base
        or "overview" in base
    ):
        return 1
    if lowered.startswith("docs/") or "/docs/" in lowered:
        return 3
    return 4


def _collect_files(root: str) -> List[str]:
    """Walk ``root`` and return prioritized, capped list of ingestible files."""
    candidates = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in INGEST_EXTS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            candidates.append((_file_priority(rel), rel, full))

    candidates.sort(key=lambda c: (c[0], c[1]))

    selected: List[str] = []
    total = 0
    for _, _, full in candidates:
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        # A huge file (e.g. a 149 KB ROADMAP) only counts as MAX_FILE_BYTES
        # against the budget -- it will be truncated on read -- so it can't
        # crowd out the higher-signal spec/reference files.
        effective = min(size, MAX_FILE_BYTES)
        if len(selected) >= MAX_FILES or total + effective > MAX_TOTAL_BYTES:
            break
        selected.append(full)
        total += effective
    return selected


_URL_RE = re.compile(r"""https?://[^\s)\]}"'>]+""")


def extract_reference_urls(docs, limit: int = 8) -> List[str]:
    """Collect up to ``limit`` unique http(s) URLs from the ingested documents."""
    seen, out = set(), []
    for d in docs:
        for raw in _URL_RE.findall(getattr(d, "text", "") or ""):
            url = raw.rstrip(".,;:")
            if url not in seen:
                seen.add(url)
                out.append(url)
                if len(out) >= limit:
                    return out
    return out


def load_source_documents(source: str) -> "List[Document]":
    """Load documents from a GitHub URL or a local file/directory.

    Oversized files are truncated so none dominates the model's context, and a
    source with too little extractable text is rejected rather than turned into
    a weak presentation.
    """
    from llama_index.core import Document, SimpleDirectoryReader

    if _is_github_url(source):
        # repomix packs the repo's docs into one blob (README/specs first); cap
        # to the tighter repo budget so we distill signal, not the whole repo.
        packed = _pack_repo(source)[:MAX_REPO_BYTES]
        docs = [Document(text=packed)]
    else:
        root = source
        if not os.path.exists(root):
            raise FileNotFoundError(f"Source path does not exist: {source}")
        input_files = [root] if os.path.isfile(root) else _collect_files(root)
        if not input_files:
            raise ValueError(
                f"No ingestible files ({', '.join(sorted(INGEST_EXTS))}) found in {source}."
            )
        print(f"\n> Ingesting {len(input_files)} file(s) from {source}...\n")
        raw = SimpleDirectoryReader(input_files=input_files).load_data()
        docs = [
            Document(text=(d.text or "")[:MAX_FILE_BYTES], metadata=d.metadata)
            for d in raw
        ]

    total_chars = sum(len(d.text) for d in docs)
    if total_chars < MIN_DOC_CHARS:
        raise ValueError(
            f"Insufficient documentation in {source} to build a presentation "
            f"({total_chars} chars of extractable text; need >= {MIN_DOC_CHARS}). "
            "Add a README/docs (or point at a documented source) and retry."
        )
    print(f"\n> Ingested {len(docs)} document(s), {total_chars} chars of text.\n")
    return docs
