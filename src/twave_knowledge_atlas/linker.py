from __future__ import annotations

import re


def obsidian_link_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
