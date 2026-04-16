from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(raw: str, fallback_prefix: str = "skill") -> str:
    raw = raw.strip().lower()
    if not raw:
        raw = fallback_prefix
    slug = re.sub(r"[^a-z0-9]+", "-", raw)
    slug = slug.strip("-")
    if not slug:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        slug = f"{fallback_prefix}-{digest}"
    if len(slug) < 3:
        slug = f"{fallback_prefix}-{slug}"
    if len(slug) > 54:
        slug = slug[:54].rstrip("-")
    return slug


def display_name_from_slug(slug: str) -> str:
    parts = [part for part in slug.split("-") if part]
    if not parts:
        return "Skill"
    return " ".join(item.capitalize() for item in parts)

