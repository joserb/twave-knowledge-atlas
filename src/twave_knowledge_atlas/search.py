from __future__ import annotations

from .db import AtlasDB


def search_entities(db: AtlasDB, query: str, limit: int = 10) -> list[dict[str, str | float]]:
    return db.search(query, limit=limit)


def entity_routes(db: AtlasDB, name_or_id: str) -> dict[str, object] | None:
    entity = db.find_entity(name_or_id)
    if entity is None:
        return None
    return {
        "id": entity.id,
        "type": entity.type,
        "canonical_name": entity.canonical_name,
        "known_in": entity.known_in,
        "best_tools": entity.best_tools,
        "source_refs": [ref.to_dict() for ref in entity.source_refs],
        "warnings": entity.warnings,
    }
