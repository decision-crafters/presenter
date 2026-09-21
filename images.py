"""Optional free image provider for slide images.

Fetches one image per slide from a free service, mirroring the optional,
additive pattern of the LLM provider and DESIGN.md branding. Off by default;
enabled with ``--images <provider>``.

Providers:
- ``pollinations``: no API key, generative text-to-image via a URL GET.
- ``pexels``: real stock photos, needs a free ``PEXELS_API_KEY``.
- ``picsum``: Lorem Picsum, deterministic placeholder, no key. Also the
  automatic fallback when another provider fails.
"""

import hashlib
import os
from typing import Optional
from urllib.parse import quote

IMAGE_W = 1024
IMAGE_H = 576  # 16:9 landscape, so photos never trip the tall-diagram split
# Pollinations generation itself takes ~20-40s, which already spaces requests
# under the anonymous rate limit; this is just a small courtesy gap.
POLLINATIONS_DELAY = 5.0
MAX_IMAGES = 8  # cap fetches per deck

_VALID = {"pollinations", "pexels", "picsum"}


def resolve_image_provider(name: Optional[str]) -> Optional[str]:
    """Return a valid provider name, or None to keep the feature off."""
    name = (name or os.getenv("IMAGE_PROVIDER") or "").strip().lower()
    return name if name in _VALID else None


def _seed_from(query: str, seed: Optional[int]) -> int:
    if seed is not None:
        return seed
    return int(hashlib.md5(query.encode()).hexdigest()[:8], 16)


def _download(url: str, out_path: str, headers: Optional[dict] = None) -> bool:
    import httpx

    with httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=90.0
    ) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return os.path.getsize(out_path) > 0


def _pollinations(query: str, out_path: str, seed: int) -> bool:
    url = (
        f"https://image.pollinations.ai/prompt/{quote(query)}"
        f"?width={IMAGE_W}&height={IMAGE_H}&model=flux&nologo=true&seed={seed}"
    )
    return _download(url, out_path)


def _pexels(query: str, out_path: str) -> bool:
    import httpx

    key = os.getenv("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY is not set")
    r = httpx.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": 1, "orientation": "landscape"},
        headers={"Authorization": key},
        timeout=30.0,
    )
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        raise RuntimeError(f"no Pexels results for {query!r}")
    src = photos[0]["src"]
    return _download(src.get("large2x") or src.get("large") or src["original"], out_path)


def _picsum(out_path: str, seed: int) -> bool:
    url = f"https://picsum.photos/seed/{seed}/{IMAGE_W}/{IMAGE_H}.jpg"
    return _download(url, out_path)


def fetch_slide_image(
    query: str, provider: str, out_path: str, seed: Optional[int] = None
) -> bool:
    """Fetch one image for ``query`` to ``out_path``. Falls back to Picsum."""
    seed = _seed_from(query, seed)
    try:
        if provider == "pollinations":
            return _pollinations(query, out_path, seed)
        if provider == "pexels":
            return _pexels(query, out_path)
        if provider == "picsum":
            return _picsum(out_path, seed)
    except Exception as e:
        print(f"  ! image fetch failed ({provider}): {e}; falling back to picsum")
    try:
        return _picsum(out_path, seed)
    except Exception as e:
        print(f"  ! picsum fallback failed: {e}")
        return False
