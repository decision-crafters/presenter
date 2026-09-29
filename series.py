"""Plan and track a series of videos made from one source.

One repo or research source often holds several talks, not one. A series file
(``series/<slug>.yaml``) lists those episodes; each episode is built with its own
thesis as steering and lands in a fixed folder, so reruns resume in place.

Progress is *derived from disk*, never self-reported, so the tracker can't claim
work that wasn't done:

    planned      the episode is listed in the series file
    in progress  its folder exists but the deck isn't finished
    generated    output/index.html and presentation.pdf exist
    rendered     presentation.mp4 exists
    published    a youtube URL is recorded (``series.py publish``)

Usage:
    python series.py plan <repo-url|path> [--episodes 4] [--design <dir>]
    python run.py --series series/<slug>.yaml --episode 2 [--export-video]
    python series.py publish series/<slug>.yaml 2 https://youtu.be/...
    python series.py status [--brief] [--html presentations/status.html]
"""

import argparse
import glob
import html
import os
import re
import sys
from datetime import datetime
from typing import List, Optional

SERIES_DIR = "series"
PRESENTATIONS_DIR = "presentations"
DEFAULT_STATUS_HTML = os.path.join(PRESENTATIONS_DIR, "status.html")

STATUSES = ["planned", "in progress", "generated", "rendered", "published"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def series_slug(source: str) -> str:
    """repo-governor for https://github.com/tosin2013/repo-governor, else basename."""
    name = source.rstrip("/").split("/")[-1]
    name = re.sub(r"\.(git|md|pdf)$", "", name)
    return _slug(name) or "series"


# ---- series file I/O ----

def load_series(path: str) -> dict:
    import yaml

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("episodes", [])
    data["_path"] = path
    data.setdefault("slug", os.path.splitext(os.path.basename(path))[0])
    return data


def save_series(series: dict) -> None:
    import yaml

    path = series["_path"]
    out = {k: v for k, v in series.items() if not k.startswith("_")}
    with open(path, "w") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=88)


def get_episode(series: dict, episode_id: int) -> dict:
    for ep in series["episodes"]:
        if int(ep.get("id", -1)) == int(episode_id):
            return ep
    ids = [ep.get("id") for ep in series["episodes"]]
    raise SystemExit(f"No episode {episode_id} in {series['_path']} (have: {ids})")


def episode_folder(series: dict, ep: dict) -> str:
    """Fixed output folder; an explicit ``folder:`` adopts an existing deck."""
    if ep.get("folder"):
        return ep["folder"]
    return os.path.join(
        PRESENTATIONS_DIR, series["slug"], f"ep{int(ep['id']):02d}-{_slug(ep['title'])}"
    )


def episode_steering(series: dict, ep: dict) -> str:
    """Steering text that narrows the whole source down to this one episode."""
    others = [
        f"- {e['title']}: {e.get('thesis', '')}"
        for e in series["episodes"]
        if e is not ep
    ]
    lines = [
        f'This deck is episode {ep["id"]} of a {len(series["episodes"])}-part series '
        f'on the same source, titled "{ep["title"]}". Never open by announcing the '
        "episode number or the series; the opening is the hook. Any mention of the "
        "series or other episodes belongs in the final slides only.",
        f"Go deep on ONLY this episode's thesis: {ep.get('thesis', '')}",
        "Treat everything else in the source as context, not content.",
    ]
    if ep.get("pillar"):
        lines.append(f"Series pillar: {ep['pillar']}.")
    if ep.get("focus"):
        lines.append(
            "Ground this episode primarily in these source files: "
            + ", ".join(ep["focus"])
        )
    if others:
        lines.append(
            "Other episodes cover these topics -- mention them at most in passing, "
            "never explain them here:\n" + "\n".join(others)
        )
    if ep.get("notes"):
        lines.append(str(ep["notes"]))
    # Series-wide rules (e.g. a required disclaimer) apply to every episode.
    if series.get("steering"):
        lines.append(str(series["steering"]))
    return "\n".join(lines)


# ---- status (derived from disk) ----

def episode_status(series: dict, ep: dict) -> str:
    folder = episode_folder(series, ep)
    if ep.get("youtube"):
        return "published"
    if os.path.exists(os.path.join(folder, "presentation.mp4")):
        return "rendered"
    if os.path.exists(os.path.join(folder, "output", "index.html")) and os.path.exists(
        os.path.join(folder, "presentation.pdf")
    ):
        return "generated"
    if os.path.isdir(folder):
        return "in progress"
    return "planned"


def next_step(series: dict, ep: dict, status: str) -> Optional[str]:
    path, eid = series["_path"], ep["id"]
    if status in ("planned", "in progress"):
        return f"python run.py --series {path} --episode {eid} --export-video"
    if status == "generated":
        return f"python run.py --series {path} --episode {eid} --export-video  # render video"
    if status == "rendered":
        if not os.path.exists(os.path.join(episode_folder(series, ep), "youtube", "index.html")):
            return f"python youtube.py --series {path} --episode {eid} --open"
        return f"python series.py publish {path} {eid} <youtube-url>"
    return None


def collect(series_dir: str = SERIES_DIR) -> List[dict]:
    """Every series with each episode's derived status."""
    result = []
    for path in sorted(glob.glob(os.path.join(series_dir, "*.yaml"))):
        try:
            series = load_series(path)
        except Exception as e:  # a broken file shouldn't hide the others
            print(f"! Could not read {path}: {e}", file=sys.stderr)
            continue
        for ep in series["episodes"]:
            ep["_status"] = episode_status(series, ep)
            ep["_folder"] = episode_folder(series, ep)
        result.append(series)
    return result


def unfiled_decks(all_series: List[dict]) -> List[str]:
    """Decks in presentations/ that no series tracks (candidates to adopt)."""
    tracked = {
        os.path.normpath(ep["_folder"]) for s in all_series for ep in s["episodes"]
    }
    tracked_roots = {os.path.join(PRESENTATIONS_DIR, s["slug"]) for s in all_series}
    out = []
    for d in sorted(glob.glob(os.path.join(PRESENTATIONS_DIR, "*", ""))):
        d = os.path.normpath(d)
        if d not in tracked and d not in tracked_roots:
            out.append(d)
    return out


def brief(all_series: List[dict]) -> str:
    """Short plain-text summary for session start; empty when nothing is open."""
    open_lines = []
    for s in all_series:
        for ep in s["episodes"]:
            if ep["_status"] == "published":
                continue
            open_lines.append(
                f"  - {s['slug']} ep{ep['id']} \"{ep['title']}\" -- {ep['_status']}\n"
                f"      next: {next_step(s, ep, ep['_status'])}"
            )
    if not open_lines:
        return ""
    total = sum(len(s["episodes"]) for s in all_series)
    done = total - len(open_lines)
    return (
        f"Presenter video projects: {len(open_lines)} episode(s) still open "
        f"({done}/{total} published across {len(all_series)} series).\n"
        + "\n".join(open_lines)
        + f"\n  Board: python series.py status --open  (writes {DEFAULT_STATUS_HTML})"
    )


# ---- HTML board ----

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#5d6670;--line:#dde1e6;
--planned:#8a94a0;--progress:#b7791f;--generated:#2b6cb0;--rendered:#6b46c1;--published:#2f855a}
@media (prefers-color-scheme:dark){:root{--bg:#081426;--card:#0f1e35;--text:#e6edf3;
--muted:#9aa7b5;--line:#1e3350;--planned:#7d8896;--progress:#e0a43a;--generated:#5a9be6;
--rendered:#a58af0;--published:#1FEB50}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 Inter,system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 28px}
h2{font-size:18px;margin:32px 0 4px}.src{color:var(--muted);font-size:13px;margin:0 0 12px;
word-break:break-all}.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;
margin:0 0 14px}.bar i{display:block;height:100%;background:var(--published)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.ep{color:var(--muted);font-size:12px;letter-spacing:.04em}.t{font-weight:600;margin:2px 0 6px}
.th{color:var(--muted);font-size:13px;margin:0 0 10px}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:99px;
border:1px solid currentColor}
.planned{color:var(--planned)}.in-progress{color:var(--progress)}.generated{color:var(--generated)}
.rendered{color:var(--rendered)}.published{color:var(--published)}
.brand{font-weight:600}.warn{color:var(--progress)}
.links{margin-top:10px;font-size:13px}.links a{color:inherit;margin-right:10px}
code{display:block;margin-top:10px;font-size:11.5px;color:var(--muted);word-break:break-all}
ul{color:var(--muted);font-size:13px}
"""


def _rel(target: str, base_dir: str) -> str:
    return os.path.relpath(target, base_dir).replace(os.sep, "/")


def render_html(all_series: List[dict], out_path: str) -> str:
    base = os.path.dirname(os.path.abspath(out_path))
    esc = html.escape
    parts = []
    for s in all_series:
        eps = s["episodes"]
        done = sum(1 for e in eps if e["_status"] == "published")
        pct = int(100 * done / len(eps)) if eps else 0
        cards = []
        for ep in eps:
            st, folder = ep["_status"], ep["_folder"]
            links = []
            for label, rel in (
                ("Deck", os.path.join("output", "index.html")),
                ("PDF", "presentation.pdf"),
                ("Video", "presentation.mp4"),
                ("YouTube kit", os.path.join("youtube", "index.html")),
            ):
                p = os.path.join(folder, rel)
                if os.path.exists(p):
                    links.append(f'<a href="{esc(_rel(os.path.abspath(p), base))}">{label}</a>')
            if ep.get("youtube"):
                links.append(f'<a href="{esc(ep["youtube"])}">YouTube</a>')
            nxt = next_step(s, ep, st)
            cards.append(
                '<div class="card">'
                f'<div class="ep">EP {int(ep["id"]):02d}'
                + (f" · {esc(str(ep['pillar']))}" if ep.get("pillar") else "")
                + "</div>"
                f'<div class="t">{esc(ep["title"])}</div>'
                f'<p class="th">{esc(str(ep.get("thesis", "")))}</p>'
                f'<span class="pill {st.replace(" ", "-")}">{st}</span>'
                + (f'<div class="links">{"".join(links)}</div>' if links else "")
                + (f"<code>{esc(nxt)}</code>" if nxt else "")
                + "</div>"
            )
        parts.append(
            f"<h2>{esc(s.get('title') or s['slug'])}</h2>"
            f'<p class="src">{esc(str(s.get("source", "")))} · {done}/{len(eps)} published · '
            + (
                f'brand: <span class="brand">{esc(os.path.basename(str(s["design"]).rstrip("/")))}</span>'
                if s.get("design")
                else '<span class="warn">brand not set</span>'
            )
            + "</p>"
            f'<div class="bar"><i style="width:{pct}%"></i></div>'
            f'<div class="grid">{"".join(cards)}</div>'
        )
    loose = unfiled_decks(all_series)
    if loose:
        parts.append(
            "<h2>Decks not in a series</h2><ul>"
            + "".join(f"<li>{esc(d)}</li>" for d in loose)
            + "</ul><p class='src'>Track one by adding an episode with "
            "<b>folder:</b> set to its path in a series file.</p>"
        )
    if not all_series:
        parts.append(
            "<p>No series yet. Start one with "
            "<b>python series.py plan &lt;repo-url&gt;</b>.</p>"
        )
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Video Projects</title><style>{_CSS}</style></head><body><main>"
        "<h1>Video projects</h1>"
        f"<p class='sub'>Status is read from disk · updated "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
        + "".join(parts)
        + "</main></body></html>"
    )
    os.makedirs(base, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(page)
    return out_path


# ---- planning (one LLM call over the source) ----

PLAN_PROMPT = """
You are planning a SERIES of short technical videos from one source (a code
repository or research documents). Each episode becomes its own ~10-15 minute
narrated slide deck.

Propose {episodes} episodes. Rules:
- Each episode goes deep on ONE distinct idea, mechanism, or decision from the
  source. No two episodes may overlap; together they should cover what matters.
- Episode 1 is the entry point: the problem the source solves and why it matters.
- Later episodes each take one concrete capability, design decision, or workflow
  that the source actually documents. Never invent features that are not in it.
- Titles are short (3-6 words). The thesis is one sentence naming the single
  takeaway a viewer should leave with.
- Order the episodes so each builds on the ones before it.{steering}

Plan ONLY from this source material:
---
{source_text}
---
"""


def plan_series(source: str, llm, episodes: int = 4, guide: str = ""):
    from llama_index.core.prompts.base import PromptTemplate

    from guide import format_steering
    from ingest import load_source_documents
    from models import SeriesPlan

    docs = load_source_documents(source)
    source_text = "\n\n".join(d.text for d in docs)
    instructions = PLAN_PROMPT.replace("{episodes}", str(episodes))
    print(f"\n> Planning a {episodes}-episode series from {source}...\n")
    return llm.structured_predict(
        SeriesPlan,
        prompt=PromptTemplate(instructions),
        source_text=source_text,
        steering=format_steering(guide),
    )


# ---- CLI ----

def _cmd_plan(args) -> None:
    from dotenv import load_dotenv

    from design import load_design
    from providers import build_llm

    load_dotenv()
    os.makedirs(SERIES_DIR, exist_ok=True)
    slug = args.slug or series_slug(args.source)
    path = os.path.join(SERIES_DIR, f"{slug}.yaml")
    if os.path.exists(path) and not args.force:
        raise SystemExit(f"{path} already exists (edit it, or pass --force to re-plan).")
    design = load_design(args.design) if args.design else None
    plan = plan_series(
        args.source,
        build_llm(args.provider, args.model),
        args.episodes,
        design.voice if design else "",
    )
    series = {
        "_path": path,
        "title": args.title or slug.replace("-", " ").title(),
        "slug": slug,
        "source": args.source,
        "design": args.design,
        "slides": args.slides,
        "episodes": [
            {
                "id": i,
                "title": ep.title,
                "pillar": ep.pillar,
                "thesis": ep.thesis,
                "youtube": None,
            }
            for i, ep in enumerate(plan.episodes, start=1)
        ],
    }
    save_series(series)
    print(f"\n> Wrote {path} with {len(plan.episodes)} episodes:\n")
    for ep in series["episodes"]:
        print(f"  {ep['id']}. {ep['title']} -- {ep['thesis']}")
    print(
        f"\nEdit the file (cut, reorder, retitle), then build one with:\n"
        f"  python run.py --series {path} --episode 1 --export-video\n"
    )


def _cmd_publish(args) -> None:
    series = load_series(args.series)
    ep = get_episode(series, args.episode)
    ep["youtube"] = args.url
    save_series(series)
    print(f"> Marked {series['slug']} ep{ep['id']} \"{ep['title']}\" published: {args.url}")


def _cmd_status(args) -> None:
    all_series = collect()
    if args.brief or args.hook:
        text = brief(all_series)
        if text and args.hook:
            # SessionStart hook: show the user, and tell the agent too.
            import json

            print(json.dumps({
                "systemMessage": text,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text
                    + "\nMention these open video projects to the user at the start.",
                },
            }))
        elif text:
            print(text)
        return
    for s in all_series:
        print(f"\n{s.get('title') or s['slug']}  ({s['_path']})")
        for ep in s["episodes"]:
            print(f"  ep{ep['id']:<3}{ep['_status']:<13}{ep['title']}")
    loose = unfiled_decks(all_series)
    if loose:
        print("\nDecks not in a series:")
        for d in loose:
            print(f"  {d}")
    if not all_series:
        print("No series yet. Start one with: python series.py plan <repo-url|path>")
    out = render_html(all_series, args.html)
    print(f"\n> Board written to {out}")
    if args.open:
        import webbrowser

        webbrowser.open("file://" + os.path.abspath(out))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Plan and track multi-video series.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="Draft a series file from a repo or docs source")
    pl.add_argument("source")
    pl.add_argument("--episodes", type=int, default=4)
    pl.add_argument("--slug", default=None, help="Series file name (default: from source)")
    pl.add_argument("--title", default=None)
    pl.add_argument("--design", default=None, help="DESIGN.md dir to brand every episode")
    pl.add_argument("--slides", type=int, default=12, help="Target slides per episode")
    pl.add_argument("--provider", default=None)
    pl.add_argument("--model", default=None)
    pl.add_argument("--force", action="store_true", help="Overwrite an existing plan")
    pl.set_defaults(func=_cmd_plan)

    pu = sub.add_parser("publish", help="Record an episode's YouTube URL")
    pu.add_argument("series")
    pu.add_argument("episode", type=int)
    pu.add_argument("url")
    pu.set_defaults(func=_cmd_publish)

    st = sub.add_parser("status", help="Show progress and write the HTML board")
    st.add_argument("--brief", action="store_true", help="Short summary; silent when all done")
    st.add_argument("--hook", action="store_true", help="Emit Claude Code SessionStart hook JSON")
    st.add_argument("--html", nargs="?", const=DEFAULT_STATUS_HTML, default=DEFAULT_STATUS_HTML)
    st.add_argument("--open", action="store_true", help="Open the board in a browser")
    st.set_defaults(func=_cmd_status)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
