"""Explainable YouTube best-practice advisories.

An *advisory* is a rule that failed for a rendered video, with a human reason
and a source link the user can follow. Rules live in ``advisories/rules.yaml``
(data, not code); this package loads and validates them and renders the results.

Nothing here ever raises out of a render: advisories are collected and printed,
never fatal. Severity ``error`` is only a stronger message.

Public API:
    load_rules()          -> list[Rule]        (validates against the schema)
    advise(rule_id, **ctx) -> Advisory          (build one advisory from a rule id)
    apply_overrides(rules, design) -> list[Rule]
    content_settings(design) -> dict
    resolve_content_type(cli_value, design) -> str
    resolve_rights(design) -> str
    unique_sources(advisories) -> list[(url, source_type)]
    sources_plain / sources_markdown / sources_html
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

CONTENT_TYPES = [
    "explainer",
    "tutorial",
    "course",
    "documentary",
    "book_summary",
    "audiobook",
    "short",
]
DEFAULT_CONTENT_TYPE = "explainer"
RIGHTS_VALUES = ["own", "public_domain", "licensed", "summary", "unknown"]
SEVERITIES = ["info", "warn", "error"]
SOURCE_TYPES = ["official", "industry", "community"]
APPLIES_TO_VALUES = CONTENT_TYPES + ["all", "long_form"]

_RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.yaml")
_RULES: dict[str, Rule] = {}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Rule:
    id: str
    applies_to: list[str]
    check: str
    params: dict
    severity: str
    message: str
    why: str
    source_url: str
    source_type: str
    last_verified: str


@dataclass
class Advisory:
    rule_id: str
    severity: str
    message: str
    why: str
    source_url: str
    source_type: str
    last_verified: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "why": self.why,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "last_verified": self.last_verified,
        }

    def to_plain(self) -> str:
        return (
            f"[{self.severity.upper()}] [{self.rule_id}] {self.message} "
            f"Why: {self.why} Source: {self.source_url} "
            f"({self.source_type}, verified {self.last_verified})"
        )

    def to_markdown(self) -> str:
        return (
            f"- **[{self.rule_id}]** {self.message} — *Why:* {self.why} — "
            f"*Source:* [{self.source_url}]({self.source_url}) "
            f"({self.source_type}, verified {self.last_verified})"
        )

    def to_html(self) -> str:
        esc = _html_escape
        return (
            f'<li class="adv"><span class="badge {esc(self.source_type)}">{esc(self.source_type)}</span>'
            f'<span class="sev {esc(self.severity)}">{esc(self.severity)}</span>'
            f'<strong>[{esc(self.rule_id)}]</strong> {esc(self.message)}'
            f'<div class="why">Why: {esc(self.why)}</div>'
            f'<div class="src">Source: <a href="{esc(self.source_url)}" '
            f'target="_blank" rel="noopener">{esc(self.source_url)}</a> '
            f'({esc(self.source_type)}, verified {esc(self.last_verified)})</div></li>'
        )


def _html_escape(text: Any) -> str:
    import html

    return html.escape(str(text), quote=True)


def _safe_format(template: str, ctx: dict) -> str:
    """Format ``template`` with ``ctx``, leaving unknown ``{placeholders}`` intact."""

    class _Defaults(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(_Defaults(ctx))


def make_advisory(rule: Rule, ctx: dict) -> Advisory:
    """Build an Advisory from a rule and the measured values a check returned.

    Message and why are formatted with ``rule.params`` plus ``ctx``, so
    ``{placeholders}`` can reference both rule params and measured facts."""
    values = {**rule.params, **ctx}
    return Advisory(
        rule_id=rule.id,
        severity=rule.severity,
        message=_safe_format(rule.message, values),
        why=_safe_format(rule.why, values),
        source_url=rule.source_url,
        source_type=rule.source_type,
        last_verified=rule.last_verified,
    )


def advise(rule_id: str, **ctx: Any) -> Advisory:
    """Build one advisory for a loaded rule id. Use ``engine.advise`` to evaluate
    a whole video; this is a convenience for a single known rule."""
    rule = _RULES.get(rule_id)
    if rule is None:
        raise KeyError(f"Unknown rule id: {rule_id} (call load_rules() first)")
    return make_advisory(rule, ctx)


# ---- rule loading / validation ----

def _validate(rule: dict) -> list[str]:
    errors: list[str] = []
    rule_id = rule.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        errors.append(f"rule missing id: {rule!r}")
    if not isinstance(rule.get("applies_to"), list) or not rule.get("applies_to"):
        errors.append(f"{rule_id}: applies_to must be a non-empty list")
    else:
        for token in rule["applies_to"]:
            if token not in APPLIES_TO_VALUES:
                errors.append(f"{rule_id}: unknown applies_to {token!r}")
    if not isinstance(rule.get("check"), str) or not rule["check"].strip():
        errors.append(f"{rule_id}: missing check")
    if not isinstance(rule.get("params"), dict):
        errors.append(f"{rule_id}: params must be a dict")
    if rule.get("severity") not in SEVERITIES:
        errors.append(f"{rule_id}: severity must be one of {SEVERITIES}")
    for key in ("message", "why"):
        if not isinstance(rule.get(key), str) or not rule[key].strip():
            errors.append(f"{rule_id}: missing {key}")
    source_url = rule.get("source_url")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        errors.append(f"{rule_id}: source_url must be an https URL")
    if rule.get("source_type") not in SOURCE_TYPES:
        errors.append(f"{rule_id}: source_type must be one of {SOURCE_TYPES}")
    last_verified = rule.get("last_verified")
    if not isinstance(last_verified, str) or not _ISO_DATE_RE.match(last_verified):
        errors.append(f"{rule_id}: last_verified must be an ISO date YYYY-MM-DD")
    else:
        try:
            date.fromisoformat(last_verified)
        except ValueError:
            errors.append(f"{rule_id}: last_verified is not a real date")
    return errors


def validate_rules(rules: list[dict]) -> list[str]:
    """Return a list of schema errors (empty means valid)."""
    errors: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        errors.extend(_validate(rule))
        rule_id = rule.get("id")
        if isinstance(rule_id, str) and rule_id in seen:
            errors.append(f"duplicate rule id: {rule_id}")
        if isinstance(rule_id, str):
            seen.add(rule_id)
    return errors


def load_rules(path: str | None = None) -> list[Rule]:
    """Load and validate ``advisories/rules.yaml``; raises on schema errors."""
    import yaml

    global _RULES
    path = path or _RULES_FILE
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a top-level `rules:` list")
    errors = validate_rules(raw)
    if errors:
        raise ValueError(f"{path}: invalid rules:\n  " + "\n  ".join(errors))
    rules = [
        Rule(
            id=r["id"],
            applies_to=list(r["applies_to"]),
            check=r["check"],
            params=dict(r["params"]),
            severity=r["severity"],
            message=r["message"],
            why=r["why"],
            source_url=r["source_url"],
            source_type=r["source_type"],
            last_verified=r["last_verified"],
        )
        for r in raw
    ]
    _RULES = {r.id: r for r in rules}
    return rules


# ---- DESIGN.md integration ----

def content_settings(design) -> dict:
    """Read the DESIGN.md ``content:`` block (type, rights, and per-rule fields
    the advisory checks read, e.g. made_for_kids). Empty-safe."""
    tokens = getattr(design, "tokens", None) or {}
    content = tokens.get("content") if isinstance(tokens, dict) else None
    return content if isinstance(content, dict) else {}


def resolve_content_type(cli_value: str | None, design) -> str:
    """--content-type > DESIGN.md content.type > ``explainer``."""
    value = cli_value or content_settings(design).get("type")
    return value if value in CONTENT_TYPES else DEFAULT_CONTENT_TYPE


def resolve_rights(design) -> str:
    value = content_settings(design).get("rights")
    return value if value in RIGHTS_VALUES else "unknown"


def apply_overrides(rules: list[Rule], design) -> list[Rule]:
    """Apply the DESIGN.md ``advisories:`` block: ``enabled: false`` drops a rule,
    any other key overrides a param."""
    tokens = getattr(design, "tokens", None) or {}
    overrides = tokens.get("advisories") if isinstance(tokens, dict) else None
    if not isinstance(overrides, dict):
        return rules
    out: list[Rule] = []
    for rule in rules:
        ov = overrides.get(rule.id)
        if not isinstance(ov, dict):
            out.append(rule)
            continue
        if ov.get("enabled") is False:
            continue
        extra = {k: v for k, v in ov.items() if k != "enabled"}
        if extra:
            params = dict(rule.params)
            params.update(extra)
            out.append(replace(rule, params=params))
        else:
            out.append(rule)
    return out


# ---- source summaries ----

def unique_sources(advisories: list[Advisory]) -> list[tuple[str, str]]:
    """Deduplicated (url, source_type) pairs in first-seen order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for adv in advisories:
        if adv.source_url not in seen:
            seen.add(adv.source_url)
            out.append((adv.source_url, adv.source_type))
    return out


def sources_plain(advisories: list[Advisory]) -> str:
    return "\n".join(f"  - {url} ({src_type})" for url, src_type in unique_sources(advisories))


def sources_markdown(advisories: list[Advisory]) -> str:
    return "\n".join(
        f"- [{url}]({url}) ({src_type})" for url, src_type in unique_sources(advisories)
    )


def sources_html(advisories: list[Advisory]) -> str:
    esc = _html_escape
    return "".join(
        f'<li><a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a> '
        f'<span class="badge {esc(src_type)}">{esc(src_type)}</span></li>'
        for url, src_type in unique_sources(advisories)
    )
