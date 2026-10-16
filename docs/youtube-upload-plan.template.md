<!--
  YouTube upload plan — template.

  `youtube.py` reads this file, fills the {{placeholders}}, and writes a
  completed `UPLOAD_PLAN.md` into `<deck>/youtube/` (run `python youtube.py ...`
  or `run.py ... --export-video`). To use by hand, copy this file and replace
  the {{...}} tokens yourself.
-->

# YouTube Upload Plan — {{title}}

## What's ready
- Video: `{{deck_dir}}/presentation.mp4`
- YouTube kit (open `{{deck_dir}}/youtube/index.html` for copy buttons):
  - Title + 2 A/B alternates, hook, summary, tags, hashtags, pinned comment
  - Description, ready to paste: `youtube/description.txt`
  - Thumbnail: `youtube/thumbnail.jpg`
  - {{chapters_count}} chapters, computed from the rendered video (timestamps match)

## Review before uploading
- [ ] Title is ≤60 chars with the keyword first; honest, no clickbait.
- [ ] Hook (first ~150 chars) reads well above the fold.
- [ ] Description, tags, hashtags, and pinned comment are accurate.
- [ ] Chapters are correct (≥3 chapters of ≥10 s).

## Decide
- [ ] Thumbnail: keep `youtube/thumbnail.jpg`, or supply a custom image.
- [ ] Description links: add a repo/website/LinkedIn beyond the auto "▶ Code" line.
- [ ] Upload method: manual drag-and-drop, or full browser automation.

## Upload
1. Open https://studio.youtube.com/ (signed in).
2. Start an upload and drop `{{deck_dir}}/presentation.mp4`.
3. Paste the title, description (`youtube/description.txt`), and tags.
4. Upload the thumbnail (`youtube/thumbnail.jpg`).
5. Set the category and language if known (not auto-filled).

## Verify after publishing
- [ ] Title shows fully on mobile.
- [ ] Hook is visible above the fold.
- [ ] Chapters appear on the timeline.
- [ ] Thumbnail and metadata match what the video actually delivers.
