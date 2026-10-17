# YouTube best practices

This is the human-readable explanation of Presenter's YouTube advisory rules.
The machine-readable source of truth is [`advisories/rules.yaml`](../advisories/rules.yaml);
keep the two in sync.

Presenter does not just link you to pages to judge for yourself — it checks
every rendered video against these rules and, when one fails, prints the reason
and the source link so you can act or verify. Advisories never block a render.

## Content types

Set the content type per video with `--content-type` or the DESIGN.md
`content.type` token. Default: `explainer`.

| type | typical length |
| --- | --- |
| `short` | up to 3 minutes (Shorts) |
| `explainer` | 3–10 minutes |
| `tutorial` | 5–20 minutes |
| `course` | 5–30 minutes per video |
| `documentary` | 8–60 minutes |
| `book_summary` | 5–15 minutes |
| `audiobook` | 30–120 minutes |

Declare `content.rights` (one of `own`, `public_domain`, `licensed`, `summary`,
`unknown`) for book-related content so the copyright rule can check it.

## Rules by topic

### Length
- **Runtime matches the content type.** Viewers reward videos whose length
  matches the content; padding hurts satisfaction surveys.
- **Shorts are ≤ 3 minutes.** Vertical/square uploads up to 3 minutes are
  Shorts; a longer Short loses Shorts features.
- **Documentaries favor TV.** TV viewing favors longer documentaries; check the
  final render on a TV.
- **Mid-roll ads need 8 minutes.** Monetized videos under 8 minutes cannot show
  mid-roll ads.
- **15-minute verification.** Uploads over 15 minutes need a verified account.
- **12-hour / 256 GB cap.** The maximum upload is 12 hours or 256 GB.

### Chapters
- **At least 3 chapters, starting at 0:00, each ≥ 10 s.** Otherwise YouTube
  will not show chapters.
- **Long videos need chapters.** Videos of 10+ minutes should have chapters.

### Hook & retention
- **First speech within 15 seconds.** The share of viewers still watching at
  30 s is a key retention signal.
- **Deliver the promise in 15 s.** Hooks must deliver on the thumbnail and title
  promise.
- **Hook above the fold.** Only the first ~150 characters of the description
  show above the fold.

### End screens
- **End screens in the last 5–20 seconds.**
- **End screens need a video ≥ 25 seconds.**
- **Shorts have no chapters or end screens.**

### Shorts
- **Vertical, up to 1080p.**
- **Set the made-for-kids audience choice.**
- **Hook in the first second.**
- **Add a related-video link in the final seconds.**

### Thumbnails
- **16:9 (9:16 for Shorts), under 2 MB.**
- **A/B test up to 3 variants**, chosen by watch-time share.
- **Keep the thumbnail legible at small sizes.**

### Title
- **45–60 characters**, keyword in the first few words, no ALL CAPS or emoji
  overuse.

### Captions
- **Add captions**, and translations for your audience.

### Series & courses
- **Add videos to playlists.**
- **Publish courses as YouTube Courses** (at least 3 videos, up to 5 PDFs each).

### Legal & disclosure
- **Disclose realistic AI-generated content** (own-voice cloning is exempt).
- **Book content needs clear rights** — own, public domain, or licensed. Fair
  use is not automatic, and credit/disclaimers are not fair use.

## Official sources

These are the primary Google/YouTube pages the rules cite (shown verbatim in
the advisory output):

1. <https://www.youtube.com/watch?v=G1tHzUGdMwY> — YouTube Creators (Cristos Goodrow): runtime should match content; padding hurts; satisfaction surveys.
2. <https://support.google.com/youtube/answer/15424877> — Three-minute Shorts.
3. <https://blog.youtube/creator-and-artist-stories/creators-are-taking-over-tv-here-are-10-tips/> — TV viewing favors longer documentaries/series.
4. <https://support.google.com/youtube/answer/6175006> — Mid-roll ads on 8-minute monetized videos.
5. <https://support.google.com/youtube/answer/71673> — 15-minute verification; 12-hour / 256 GB cap.
6. <https://support.google.com/youtube/answer/9884579> — Chapters (00:00, at least 3, each ≥ 10 s).
7. <https://support.google.com/youtube/answer/9314415> — Key moments / audience retention.
8. <https://www.youtube.com/creators/grow/overview/> — Grow: hooks, embeds, descriptions.
9. <https://support.google.com/youtube/answer/6388789> — End screens (last 5–20 s, ≥ 25 s videos).
10. <https://support.google.com/youtube/answer/10059070> — Shorts basics (vertical ≤ 1080p, made-for-kids).
11. <https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/> — Related-video link and CTA.
12. <https://support.google.com/youtube/answer/72431> — Custom thumbnails (16:9 / 9:16, file limits).
13. <https://support.google.com/youtube/answer/13861714> — A/B test titles & thumbnails.
14. <https://www.youtube.com/creators/grow/optimize-your-content/> — Optimize: keywords early, no caps/emoji, readable thumbnails, captions.
15. <https://www.youtube.com/creators/grow/understand-your-audience/> — Understand your audience: captions/translations, playlists.
16. <https://support.google.com/youtube/answer/14328491> — Disclosing GenAI content.
17. <https://support.google.com/youtube/answer/9783148> — Fair use on YouTube.
18. <https://support.google.com/youtube/answer/15128409> — YouTube Courses.

## Controlling advisories

Disable or override rules from DESIGN.md:

```yaml
advisories:
  thumb.variants:
    enabled: false      # stop reminding me
  title.length:
    max_chars: 70       # override a param
```
