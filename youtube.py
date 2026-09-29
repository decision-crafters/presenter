"""YouTube kit for a rendered presentation: metadata, chapters, and a thumbnail.

Writes ``<presentation_dir>/youtube/``:

    metadata.json    title (+2 alternates), description, tags, hashtags, chapters
    description.txt  the full description, ready to paste
    thumbnail.jpg    1280x720, branded from the DESIGN.md ``thumbnail`` tokens
    index.html       a page with every field, character counts, and copy buttons

Chapters are *computed* from the rendered clips (``clips.txt`` + ffprobe), never
guessed by the model, so timestamps always match the video. Only the wording
(title, hook, summary, tags, hashtags, thumbnail text) comes from one structured
LLM call, steered by the brand voice and persona.

Rules encoded (YouTube, 2026): title 45-60 chars with the keyword first; the
description's first ~150 chars are the hook; chapters start at 0:00, need at
least 3, each >= 10 s; 5-8 tags, each <= 30 chars, <= 500 chars total; 3
hashtags; thumbnail 1280x720, < 2 MB.

Usage:
    python youtube.py --series series/<slug>.yaml --episode 1
    python youtube.py presentations/<deck-dir> [--design designs/<brand>]
Options: --force (re-ask the model), --thumbnail-text "Three Words Max".
"""

import argparse
import html
import json
import os
import pickle
import re
import subprocess
from typing import List, Optional

TITLE_MAX = 60
HOOK_MAX = 150
TAG_MAX = 30
TAGS_TOTAL_MAX = 500
MIN_CHAPTER_SECS = 10
THUMB_W, THUMB_H = 1280, 720
THUMB_MAX_BYTES = 2 * 1024 * 1024


# ---- chapters (computed from the rendered clips) ----

def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _slide_titles(presentation_dir: str) -> List[str]:
    with open(os.path.join(presentation_dir, "structure.pkl"), "rb") as f:
        structure = pickle.load(f)
    return [s.title for s in structure.slides]


def _clip_label(rel: str, titles: List[str], demos: List[dict]) -> str:
    m = re.match(r"slide_(\d+)/clip\.mp4$", rel)
    if m and int(m.group(1)) < len(titles):
        return titles[int(m.group(1))]
    m = re.match(r"demo_(\d+)\.mp4$", rel)
    if m:
        idx = int(m.group(1))
        name = demos[idx].get("title") if idx < len(demos) else None
        return f"Demo: {name}" if name else "Demo"
    if rel.startswith("closing"):
        return "Get the Code"
    return os.path.splitext(os.path.basename(rel))[0]


def _fmt_ts(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def compute_chapters(presentation_dir: str) -> List[dict]:
    """[{start, title}] in video order; short clips fold into the previous chapter."""
    clips_file = os.path.join(presentation_dir, "clips.txt")
    if not os.path.exists(clips_file):
        raise SystemExit(f"No clips.txt in {presentation_dir}: render the video first (--export-video).")
    titles = _slide_titles(presentation_dir)
    demos = []
    demos_file = os.path.join(presentation_dir, "demos.json")
    if os.path.exists(demos_file):
        with open(demos_file) as f:
            demos = json.load(f) or []
    rels = re.findall(r"file '([^']+)'", open(clips_file).read())

    chapters, t = [], 0.0
    for rel in rels:
        dur = _duration(os.path.join(presentation_dir, rel))
        # YouTube rejects chapters under 10 s: a short clip folds into the one before.
        if not chapters or dur >= MIN_CHAPTER_SECS:
            chapters.append({"start": t, "title": _clip_label(rel, titles, demos)})
        t += dur
    # A too-short first chapter absorbs the next one (it must stay at 0:00).
    while len(chapters) > 1 and chapters[1]["start"] < MIN_CHAPTER_SECS:
        del chapters[1]
    return chapters


# ---- wording (one structured LLM call) ----

METADATA_PROMPT = """
You write YouTube metadata for a technical video. Follow YouTube best practices:
- Title: 45-60 characters. Put the main search keyword in the first few words.
  Specific and honest; it must match what the video actually delivers. No
  clickbait, no ALL CAPS, no emoji, no "Episode 1" in the title.
- Hook: the description's first 1-2 sentences, at most 150 characters. Name the
  concrete problem and what the viewer gets; this is all that shows above the fold.
- Summary: 2 short paragraphs, 80-150 words, keywords used naturally.
  No URLs or links anywhere in the hook or summary; links are added separately.
- Tags: 5-8 specific search phrases people actually type, each at most 30 characters.
- Hashtags: exactly 3.
- Thumbnail text: at most 3 words, bold, curiosity-driving, and different from
  the title so the two work together.
- Pinned comment: one specific question that invites viewers to share their own experience.
{steering}

Video context:
---
{context}
---
"""


def _video_context(presentation_dir: str, series: Optional[dict], ep: Optional[dict]) -> str:
    with open(os.path.join(presentation_dir, "structure.pkl"), "rb") as f:
        structure = pickle.load(f)
    parts = []
    if series and ep:
        parts.append(
            f"Series: {series.get('title')} (episode {ep['id']} of {len(series['episodes'])})\n"
            f"Episode title: {ep['title']}\nThesis: {ep.get('thesis', '')}\n"
            f"Source repo: {series.get('source', '')}"
        )
    parts.append("Slides:\n" + "\n".join(
        f"- {s.title}: {s.atomic_core_idea}" for s in structure.slides
    ))
    narration = []
    for i in range(len(structure.slides)):
        p = os.path.join(presentation_dir, f"slide_{i}", "narration.txt")
        if os.path.exists(p):
            narration.append(open(p).read().strip())
    parts.append("Narration:\n" + "\n".join(narration)[:12000])
    return "\n\n".join(parts)


def generate_wording(presentation_dir, llm, steering, series=None, ep=None):
    from llama_index.core.prompts.base import PromptTemplate

    from guide import format_steering
    from models import YouTubeMetadata

    return llm.structured_predict(
        YouTubeMetadata,
        prompt=PromptTemplate(METADATA_PROMPT),
        context=_video_context(presentation_dir, series, ep),
        steering=format_steering(steering),
    )


def _clean_tags(tags: List[str]) -> List[str]:
    out, total = [], 0
    for t in tags:
        t = t.strip().strip("#")
        if not t or len(t) > TAG_MAX or t.lower() in {x.lower() for x in out}:
            continue
        if total + len(t) + (1 if out else 0) > TAGS_TOTAL_MAX:
            break
        out.append(t)
        total += len(t) + (1 if len(out) > 1 else 0)
    return out[:8]


def _clean_hashtags(tags: List[str]) -> List[str]:
    out = []
    for t in tags:
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:3]


def build_description(meta: dict, chapters: List[dict], source: Optional[str],
                      series: Optional[dict], ep: Optional[dict]) -> str:
    lines = [meta["hook"], "", meta["summary"].strip(), ""]
    if source:
        lines.append(f"▶ Code: {source}")  # brand: the repo link comes first
    if series and ep:
        lines.append(f"▶ Series: {series.get('title')} — part {ep['id']} of {len(series['episodes'])}")
    lines += ["", "Chapters"]
    lines += [f"{_fmt_ts(c['start'])} {c['title']}" for c in chapters]
    if series and series.get("disclaimer"):
        lines += ["", str(series["disclaimer"]).strip()]
    lines += ["", " ".join(meta["hashtags"])]
    return "\n".join(lines).strip() + "\n"


# ---- thumbnail ----

def _hex(color: Optional[str], default: str) -> str:
    c = (color or default).strip()
    return c if c.startswith("#") else default


def _load_font(design, size: int):
    from PIL import ImageFont

    thumb = (design.tokens.get("thumbnail") or {}) if design else {}
    font_path = thumb.get("font")
    if font_path and design and design.source_dir and not os.path.isabs(font_path):
        font_path = os.path.join(design.source_dir, font_path)
    if font_path and os.path.exists(font_path):
        font = ImageFont.truetype(font_path, size)
        try:
            font.set_variation_by_name(thumb.get("fontWeight", "Bold"))
        except Exception:
            pass  # not a variable font
        return font
    for fallback in ("/System/Library/Fonts/Supplemental/Arial Black.ttf",
                     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if os.path.exists(fallback):
            return ImageFont.truetype(fallback, size)
    return ImageFont.load_default(size)


def render_thumbnail(out_path: str, text: str, design, image_path: Optional[str]) -> str:
    """Brand thumbnail: ground color, image faded in from the right, stacked bold
    words (last word in the accent color), and the logo bug in one corner."""
    from PIL import Image, ImageDraw

    from design import _colors

    tokens = design.tokens if design else {}
    thumb = tokens.get("thumbnail") or {}
    colors = _colors(tokens)
    bg = _hex(colors["background"], "#111111")
    fg = _hex(colors["heading"], "#FFFFFF")
    accent = _hex(colors["accent"], "#FFD400")

    canvas = Image.new("RGB", (THUMB_W, THUMB_H), bg)

    # Image on the right ~60%, fading into the ground so text stays legible.
    if image_path and os.path.exists(image_path):
        from PIL import ImageEnhance, ImageFilter

        im = Image.open(image_path).convert("RGB")
        scale = THUMB_H / im.height
        im = im.resize((int(im.width * scale), THUMB_H))
        # Backdrop, not content: soften and darken so the title always wins.
        im = im.filter(ImageFilter.GaussianBlur(2.2))
        im = ImageEnhance.Brightness(im).enhance(0.55)
        x0 = THUMB_W - im.width + int(im.width * 0.12)
        mask = Image.new("L", im.size, 255)
        md = ImageDraw.Draw(mask)
        fade = int(im.width * 0.45)
        for x in range(fade):
            md.line([(x, 0), (x, THUMB_H)], fill=int(255 * (x / fade) ** 1.6))
        canvas.paste(im, (x0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    max_words = int(thumb.get("maxWords", 3))
    words = re.sub(r"\s+", " ", text).strip().upper().split(" ")[:max_words]

    # Largest size where the widest word fits the text column and the stack fits vertically.
    col_w, top, bottom = 820, 150, THUMB_H - 50
    size = 190
    while size > 40:
        font = _load_font(design, size)
        widths = [draw.textlength(w, font=font) for w in words]
        line_h = int(size * 1.02)
        if max(widths) <= col_w and line_h * len(words) <= bottom - top:
            break
        size -= 6
    y = top + ((bottom - top) - line_h * len(words)) // 2
    for i, w in enumerate(words):
        color = accent if i == len(words) - 1 and len(words) > 1 else fg
        draw.text((60, y), w, font=font, fill=color, stroke_width=max(3, size // 40), stroke_fill=bg)
        y += line_h

    # Logo bug in its corner.
    logo = thumb.get("logo") or tokens.get("logo")
    if logo and design and design.source_dir and not os.path.isabs(logo):
        logo = os.path.join(design.source_dir, logo)
    if logo and os.path.exists(logo):
        bug = Image.open(logo).convert("RGB").resize((104, 104))
        corner = thumb.get("logoCorner", "top-left")
        pos = {
            "top-left": (48, 36), "top-right": (THUMB_W - 152, 36),
            "bottom-left": (48, THUMB_H - 140), "bottom-right": (THUMB_W - 152, THUMB_H - 140),
        }.get(corner, (48, 36))
        canvas.paste(bug, pos)

    quality = 92
    canvas.save(out_path, "JPEG", quality=quality)
    while os.path.getsize(out_path) > THUMB_MAX_BYTES and quality > 50:
        quality -= 10
        canvas.save(out_path, "JPEG", quality=quality)
    return out_path


def _thumbnail_image(presentation_dir: str, design) -> Optional[str]:
    thumb = (design.tokens.get("thumbnail") or {}) if design else {}
    face = thumb.get("face")
    if face and design and design.source_dir and not os.path.isabs(face):
        face = os.path.join(design.source_dir, face)
    if face and os.path.exists(face):
        return face
    # Otherwise the opening slide still (the hook) -- "demo still" in the brand system.
    still = os.path.join(presentation_dir, "presentation_1_1280x720.png")
    return still if os.path.exists(still) else None


# ---- page ----

_PAGE_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#5d6670;--line:#dde1e6;--ok:#2f855a;--warn:#b7791f;--btn:#1b1f24;--btnt:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#081426;--card:#0f1e35;--text:#e6edf3;--muted:#9aa7b5;--line:#1e3350;--ok:#1FEB50;--warn:#e0a43a;--btn:#1FEB50;--btnt:#081426}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,system-ui,-apple-system,sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 24px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 14px}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 8px;display:flex;justify-content:space-between;align-items:center}
.val{white-space:pre-wrap;word-break:break-word}.count{font-weight:600}.ok{color:var(--ok)}.warn{color:var(--warn)}
button{font:inherit;font-size:12px;font-weight:600;border:0;border-radius:6px;padding:4px 10px;background:var(--btn);color:var(--btnt);cursor:pointer}
img{width:100%;height:auto;border-radius:8px;display:block}ul{margin:0;padding-left:18px}.alt{color:var(--muted)}
"""


def _count(n: int, limit: int) -> str:
    cls = "ok" if n <= limit else "warn"
    return f'<span class="count {cls}">{n}/{limit}</span>'


def render_page(out_path: str, meta: dict, description: str, chapters: List[dict]) -> None:
    esc = html.escape
    tags_line = ", ".join(meta["tags"])
    fields = [
        ("Title", meta["title"], _count(len(meta["title"]), TITLE_MAX)),
        ("Description", description, _count(len(meta["hook"]), HOOK_MAX) + " hook"),
        ("Tags", tags_line, _count(len(tags_line), TAGS_TOTAL_MAX)),
        ("Pinned comment", meta["pinned_comment"], ""),
    ]
    blocks = [
        '<section><h2>Thumbnail <a href="thumbnail.jpg" download><button>Download</button></a></h2>'
        f'<img src="thumbnail.jpg" alt="Thumbnail: {esc(meta["thumbnail_text"])}"></section>'
    ]
    for i, (label, value, count) in enumerate(fields):
        blocks.append(
            f'<section><h2>{label} <span>{count} <button data-copy="f{i}">Copy</button></span></h2>'
            f'<div class="val" id="f{i}">{esc(value)}</div>'
            + (
                '<p class="alt">Alternatives for A/B testing:</p><ul class="alt">'
                + "".join(f"<li>{esc(t)}</li>" for t in meta.get("alt_titles", []))
                + "</ul>"
                if label == "Title" else ""
            )
            + "</section>"
        )
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>YouTube Kit</title><style>{_PAGE_CSS}</style></head><body><main>"
        f"<h1>{esc(meta['title'])}</h1><p class='sub'>YouTube kit · {len(chapters)} chapters · "
        "chapters are computed from the rendered video</p>"
        + "".join(blocks)
        + "</main><script>document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>{"
        "const t=document.getElementById(b.dataset.copy).innerText;"
        "navigator.clipboard.writeText(t).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1200)})})"
        "</script></body></html>"
    )
    with open(out_path, "w") as f:
        f.write(page)


# ---- orchestration ----

def build_kit(presentation_dir: str, llm=None, design=None, steering: str = "",
              series=None, ep=None, source=None, force=False,
              thumbnail_text: Optional[str] = None) -> str:
    out_dir = os.path.join(presentation_dir, "youtube")
    os.makedirs(out_dir, exist_ok=True)
    meta_file = os.path.join(out_dir, "metadata.json")

    chapters = compute_chapters(presentation_dir)
    if len(chapters) < 3:
        print("! Fewer than 3 chapters of 10 s+; YouTube will not show chapters for this video.")

    if os.path.exists(meta_file) and not force:
        with open(meta_file) as f:
            meta = json.load(f)
        print(f"> Reusing wording from {meta_file} (pass --force to regenerate)")
    else:
        if llm is None:
            from providers import build_llm

            llm = build_llm(None, None)
        print("\n> Writing YouTube title, description, and tags...\n")
        w = generate_wording(presentation_dir, llm, steering, series, ep)
        meta = {
            "title": w.title.strip(),
            "alt_titles": [t.strip() for t in w.alt_titles][:2],
            "hook": w.hook.strip(),
            "summary": w.summary.strip(),
            "tags": _clean_tags(w.tags),
            "hashtags": _clean_hashtags(w.hashtags),
            "thumbnail_text": w.thumbnail_text.strip(),
            "pinned_comment": w.pinned_comment.strip(),
        }
    if thumbnail_text:
        meta["thumbnail_text"] = thumbnail_text
    meta["chapters"] = [{"time": _fmt_ts(c["start"]), "title": c["title"]} for c in chapters]
    description = build_description(meta, chapters, source, series, ep)
    meta["description"] = description

    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "description.txt"), "w") as f:
        f.write(description)
    render_thumbnail(
        os.path.join(out_dir, "thumbnail.jpg"),
        meta["thumbnail_text"],
        design,
        _thumbnail_image(presentation_dir, design),
    )
    page = os.path.join(out_dir, "index.html")
    render_page(page, meta, description, chapters)

    if len(meta["title"]) > TITLE_MAX:
        print(f"! Title is {len(meta['title'])} chars (> {TITLE_MAX}); it will truncate on mobile.")
    if len(meta["hook"]) > HOOK_MAX:
        print(f"! Hook is {len(meta['hook'])} chars (> {HOOK_MAX}); it will be cut above the fold.")
    print(f"> YouTube kit written to {out_dir}/ (open {page})")
    return page


def main(argv=None) -> None:
    from dotenv import load_dotenv

    from design import load_design
    from persona import load_persona

    load_dotenv()
    p = argparse.ArgumentParser(description="Generate YouTube metadata + thumbnail for a rendered deck.")
    p.add_argument("presentation_dir", nargs="?", default=None)
    p.add_argument("--series", default=None)
    p.add_argument("--episode", type=int, default=None)
    p.add_argument("--design", default=None)
    p.add_argument("--persona", default=None)
    p.add_argument("--provider", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--force", action="store_true", help="Regenerate the wording with the model")
    p.add_argument("--thumbnail-text", default=None, help="Override the thumbnail words (max 3)")
    p.add_argument("--open", action="store_true")
    args = p.parse_args(argv)

    series = ep = None
    source = None
    if args.series:
        from series import episode_folder, get_episode, load_series

        if args.episode is None:
            p.error("--series needs --episode")
        series = load_series(args.series)
        ep = get_episode(series, args.episode)
        args.presentation_dir = args.presentation_dir or episode_folder(series, ep)
        args.design = args.design or series.get("design")
        args.persona = args.persona or series.get("persona")
        source = series.get("source")
    if not args.presentation_dir:
        p.error("give a presentation dir, or --series and --episode")

    design = load_design(args.design) if args.design else None
    persona = load_persona(args.persona) if args.persona else None
    steering = "\n\n".join(
        x for x in [design.voice if design else "", persona.steering if persona else ""] if x
    )
    llm = None
    if args.provider or args.model:
        from providers import build_llm

        llm = build_llm(args.provider, args.model)
    page = build_kit(args.presentation_dir, llm, design, steering, series, ep, source,
                     force=args.force, thumbnail_text=args.thumbnail_text)
    if args.open:
        subprocess.run(["open", page])


if __name__ == "__main__":
    main()
