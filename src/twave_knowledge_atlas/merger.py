from __future__ import annotations

from .db import AtlasDB


def merge_entities(db: AtlasDB) -> int:
    return db.merge_alias_duplicates()
