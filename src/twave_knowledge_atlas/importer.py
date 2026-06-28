from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import AtlasDB
from .models import EntityCard


def load_entity_cards(path: Path) -> list[EntityCard]:
    raw_cards = _load_raw_cards(path)
    return [EntityCard.from_dict(card) for card in raw_cards]


def import_path(db: AtlasDB, path: Path) -> int:
    cards = load_entity_cards(path)
    gateway = _detect_gateway(cards)
    for card in cards:
        db.upsert_entity(card)
    db.record_import(path, gateway, len(cards), "ok")
    return len(cards)


def _load_raw_cards(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        cards: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
                if not isinstance(loaded, dict):
                    raise ValueError(f"Expected JSON object at {path}:{line_no}")
                cards.append(loaded)
        return cards

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        return loaded
    if isinstance(loaded, dict) and isinstance(loaded.get("entity_cards"), list):
        return loaded["entity_cards"]
    raise ValueError("Expected JSON list or object with entity_cards list")


def _detect_gateway(cards: list[EntityCard]) -> str | None:
    gateways: set[str] = set()
    for card in cards:
        gateways.update(card.known_in)
        gateways.update(ref.gateway for ref in card.source_refs)
    if len(gateways) == 1:
        return next(iter(gateways))
    return None
