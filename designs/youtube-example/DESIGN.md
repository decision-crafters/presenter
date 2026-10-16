---
name: youtube-example
description: A neutral example brand pack showing the optional `youtube:` upload settings block.
theme: white
codeTheme: base16/one-light
colors:
  background: "#ffffff"
  text: "#1b1f24"
  heading: "#0b1020"
  accent: "#0b5cff"
typography:
  heading:
    fontFamily: "'Inter', sans-serif"
  body:
    fontFamily: "'Inter', sans-serif"
    fontSize: "40px"
fontImports:
  - "https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"
# Shared video-export settings (see video_settings.py): the spoken closing line
# on the repo-deck CTA slide.
video:
  closingLine: "The code and the links are on screen — grab them and dig in."
  holdSeconds: 4
# YouTube upload settings (see youtube.py `youtube_settings`). Every key here is
# optional; with no `youtube:` block the description is unchanged from the
# pre-settings format. Replace the example.org placeholders with your own
# channel, footer, and links. Leave `subscribe:` out to keep a single call to
# action (the footer/link); add it to append one "Subscribe for more:" line.
youtube:
  category: 28          # Science & Technology
  language: en
  descriptionFooter: "— Example · https://example.org"
  links:
    - label: Website
      url: https://example.org
  # subscribe: "https://example.org/subscribe"   # optional extra CTA (off by default)
---

# YouTube example

A neutral, copy-friendly example of a brand pack. Its only special feature is the
`youtube:` block above: category, language, a description footer, extra links,
and an *optional* subscribe call-to-action. Use it as a starting point for your
own brand (or copy it into a gitignored `.presenter-local/<brand>/` folder).
