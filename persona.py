"""Presenter personas: a reusable bundle of narrator *voice*, *tone/style*
steering, and a deterministic *pronunciation lexicon*.

A persona makes "how I present and how I speak" a portable, declared artifact
(inspired by OpenPersona's declare-once philosophy) instead of scattering a TTS
voice, a house style, and a pronunciation file across three flags. It plugs into
the existing seams:

- the Markdown body becomes STEERING GUIDANCE (like ``--guide``),
- ``voice``/``lang`` pick the Kokoro TTS voice (like ``--voice``/``--lang``),
- ``pronunciations`` is applied deterministically right before TTS
  (:func:`agents.narrator.apply_pronunciations`), so slide text stays intact.

A ``PERSONA.md`` mirrors the SKILL.md/DESIGN.md convention: YAML frontmatter
(``name``/``description``/``voice``/``lang``/``design``/``domains``/
``pronunciations``) plus a free-form Markdown body (the steering). Everything is
additive and empty-safe: with no persona the common-term built-ins still apply
and nothing else changes.
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from guide import _split_frontmatter


# Cross-cutting technical terms Kokoro tends to mangle. Always applied (even with
# no --persona) so decks sound better by default; a persona's own map overrides
# any of these. Values are respellings a general-English TTS says correctly.
BUILTIN_PRONUNCIATIONS = {
    "kubectl": "koob control",
    "kubernetes": "koober netties",
    "k8s": "kates",
    "yaml": "yammel",
    "yml": "yammel",
    "json": "jason",
    "nginx": "engine x",
    "postgres": "post gres",
    "postgresql": "post gres Q L",
    "sqlite": "sequel light",
    "jq": "jay Q",
    "cli": "C L I",
    "sdk": "S D K",
    "api": "A P I",
    "oauth": "oh auth",
    "jwt": "J W T",
    "grpc": "G R P C",
    "graphql": "graph Q L",
    "redis": "red iss",
    "nosql": "no sequel",
    "ci/cd": "C I C D",
    "cicd": "C I C D",
    ".ipynb": "notebook",
    "ipynb": "notebook",
    "regex": "reg ex",
    "jupyter": "Jupiter",
    "jupyterlab": "Jupiter lab",
    "env": "envy",
    "repo": "repo",
    "async": "a sync",
    "middleware": "middle ware",
}


# Kokoro voice names are ``<accent><gender>_<name>`` — accent letter (a=American,
# b=British, …), then f=female / m=male (e.g. ``am_michael`` = American male,
# ``af_heart`` = American female). We use this to keep a persona's voice consistent
# with its declared gender.
DEFAULT_VOICE_BY_GENDER = {"female": "af_heart", "male": "am_michael"}


def voice_gender(voice: str) -> Optional[str]:
    """Return 'female'/'male' inferred from a Kokoro voice name, or None."""
    if not voice or len(voice) < 3 or voice[2] != "_":
        return None
    return {"f": "female", "m": "male"}.get(voice[1])


@dataclass
class Persona:
    """A loaded persona. All fields are optional/empty-safe."""

    name: str = ""
    description: str = ""
    voice: str = ""  # Kokoro TTS voice (distinct from Design.voice prose)
    lang: str = ""  # Kokoro language code
    gender: str = ""  # 'female'/'male' — kept consistent with the voice
    steering: str = ""  # Markdown body -> STEERING GUIDANCE
    pronunciations: dict = field(default_factory=dict)
    domains: List[str] = field(default_factory=list)
    design_ref: Optional[str] = None
    source_dir: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not (self.name or self.voice or self.steering.strip())


AUTO_DISCOVERY_NAMES = ("PERSONA.md",)


def _resolve_file(path: str) -> str:
    """A PERSONA.md file, or a persona directory containing PERSONA.md."""
    if os.path.isdir(path):
        return os.path.join(path, "PERSONA.md")
    return path


def load_persona(path: Optional[str] = None) -> Persona:
    """Load a persona from a ``PERSONA.md`` (file or directory).

    ``path`` explicit -> must exist (fail loudly). ``path`` None -> auto-discover
    ``PERSONA.md`` in the cwd. Either way the returned persona's ``pronunciations``
    always includes :data:`BUILTIN_PRONUNCIATIONS` (the persona's own entries take
    precedence), so common terms are handled even when no persona is given.
    """
    if path and str(path).lower() == "auto":
        # Sentinel handled by run.py's select_persona; treat as "no file".
        return Persona(pronunciations=dict(BUILTIN_PRONUNCIATIONS))

    resolved = None
    if path:
        resolved = _resolve_file(path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Persona file not found: {resolved}")
    else:
        resolved = next(
            (n for n in AUTO_DISCOVERY_NAMES if os.path.exists(n)), None
        )
        if resolved is None:
            return Persona(pronunciations=dict(BUILTIN_PRONUNCIATIONS))

    with open(resolved, "r") as f:
        text = f.read()
    frontmatter, body = _split_frontmatter(text)

    tokens = {}
    if frontmatter:
        try:
            import yaml

            tokens = yaml.safe_load(frontmatter) or {}
        except Exception:
            tokens = {}
    if not isinstance(tokens, dict):
        tokens = {}

    declared = tokens.get("pronunciations") or {}
    if not isinstance(declared, dict):
        declared = {}
    # Persona entries override the built-ins; both are applied.
    merged = {**BUILTIN_PRONUNCIATIONS, **{str(k): str(v) for k, v in declared.items()}}

    domains = tokens.get("domains") or []
    if isinstance(domains, str):
        domains = [domains]

    name = str(tokens.get("name") or "")
    voice = str(tokens.get("voice") or "")
    gender = str(tokens.get("gender") or "").strip().lower()
    # Keep voice consistent with the declared gender: no male-persona/female-voice
    # (or vice-versa) mismatches. Auto-correct to a matching default and say so.
    if gender in DEFAULT_VOICE_BY_GENDER:
        vg = voice_gender(voice)
        if not voice:
            voice = DEFAULT_VOICE_BY_GENDER[gender]
        elif vg and vg != gender:
            corrected = DEFAULT_VOICE_BY_GENDER[gender]
            print(
                f"\n> Persona '{name or resolved}': voice '{voice}' is {vg} but "
                f"gender is '{gender}'; auto-correcting voice to '{corrected}'.\n"
            )
            voice = corrected
    elif not gender and voice:
        gender = voice_gender(voice) or ""

    persona = Persona(
        name=name,
        description=str(tokens.get("description") or ""),
        voice=voice,
        lang=str(tokens.get("lang") or ""),
        gender=gender,
        steering=body or "",
        pronunciations=merged,
        domains=[str(d) for d in domains],
        design_ref=(str(tokens["design"]) if tokens.get("design") else None),
        source_dir=os.path.dirname(os.path.abspath(resolved)),
    )
    label = f" ({persona.name})" if persona.name else ""
    print(f"\n> Using persona from {resolved}{label}\n")
    return persona


def list_personas(personas_dir: str = "personas") -> List[Persona]:
    """Load every ``personas/<name>/PERSONA.md`` for selection/cataloguing."""
    out = []
    if not os.path.isdir(personas_dir):
        return out
    for name in sorted(os.listdir(personas_dir)):
        pm = os.path.join(personas_dir, name, "PERSONA.md")
        if os.path.exists(pm):
            try:
                out.append(load_persona(pm))
            except Exception:
                continue
    return out


def select_persona(summary: str, llm, personas_dir: str = "personas"):
    """Pick the best-fit persona for ``summary`` from the library, or None.

    Returns ``(Persona|None, reason)``. Uses one structured LLM call over the
    personas' name/description/domains. A low-confidence / no-fit answer returns
    ``(None, <detected-domain>)`` so the caller can offer to file a gap issue.
    """
    from pydantic import BaseModel, Field
    from llama_index.core.prompts.base import PromptTemplate

    personas = list_personas(personas_dir)
    if not personas:
        return None, "no personas installed"

    catalog = "\n".join(
        f"- {p.name}: {p.description} (domains: {', '.join(p.domains) or 'n/a'})"
        for p in personas
    )

    class PersonaChoice(BaseModel):
        best_persona: str = Field(
            description="Exact name of the best-fit persona, or 'none' if none fits."
        )
        detected_domain: str = Field(
            description="A short label for the content's domain (e.g. 'cloud', 'cooking')."
        )
        fits: bool = Field(description="True only if a listed persona genuinely fits.")

    prompt = (
        "Match the presentation content to the best presenter persona.\n\n"
        f"CONTENT SUMMARY:\n{summary[:2000]}\n\n"
        f"AVAILABLE PERSONAS:\n{catalog}\n\n"
        "Return the exact best_persona name only if one genuinely fits the "
        "content's subject; otherwise set fits=false and best_persona='none'."
    )
    try:
        choice = llm.structured_predict(PersonaChoice, prompt=PromptTemplate(prompt))
    except Exception as e:
        return None, f"selection failed: {e}"

    if choice.fits and choice.best_persona.lower() != "none":
        for p in personas:
            if p.name.strip().lower() == choice.best_persona.strip().lower():
                return p, "matched"
    return None, choice.detected_domain or "unknown"


def _persona_stub(domain: str, terms: List[str]) -> str:
    """A ready-to-edit PERSONA.md skeleton for a missing domain."""
    slug = "".join(c if c.isalnum() else "-" for c in domain.lower()).strip("-") or "new"
    lex = "\n".join(f"  {t}: {t}" for t in terms[:12]) or "  # term: spoken form"
    return (
        f"personas/{slug}/PERSONA.md\n"
        "---\n"
        f"name: {domain.title()}\n"
        f"description: Narrator for {domain} content.\n"
        "voice: af_heart\n"
        "lang: a\n"
        f"domains: [{domain.lower()}]\n"
        "pronunciations:\n"
        f"{lex}\n"
        "---\n"
        f"Speak as a knowledgeable {domain} presenter: clear, concrete, and confident.\n"
    )


def open_persona_gap_issue(
    domain: str,
    terms: Optional[List[str]] = None,
    repo: Optional[str] = None,
) -> bool:
    """File a 'new persona needed' GitHub issue via ``gh``. Opt-in / confirmed by
    the caller. If ``gh`` is missing or unauthed, print the prefilled body and
    return False instead of raising."""
    import shutil

    terms = terms or []
    title = f"New presenter persona needed: {domain}"
    body = (
        f"The presenter content did not match any existing persona.\n\n"
        f"**Detected domain:** {domain}\n\n"
        f"**Jargon that needs pronunciations:** {', '.join(terms) or '(none detected)'}\n\n"
        "Suggested starting point:\n\n"
        "```\n" + _persona_stub(domain, terms) + "```\n"
    )
    if not shutil.which("gh"):
        print("\n> gh not found; prefilled persona-gap issue below:\n")
        print(f"TITLE: {title}\n\n{body}")
        return False
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    if repo:
        cmd += ["--repo", repo]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n> gh issue create failed: {result.stderr.strip()}\n")
            print(f"TITLE: {title}\n\n{body}")
            return False
        print(f"\n> Filed persona-gap issue: {result.stdout.strip()}\n")
        return True
    except Exception as e:
        print(f"\n> Could not file issue ({e}); prefilled body:\n")
        print(f"TITLE: {title}\n\n{body}")
        return False
