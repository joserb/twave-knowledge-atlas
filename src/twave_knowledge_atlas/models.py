from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


ENTITY_TYPES = {
    "customer",
    "contact",
    "product",
    "project",
    "research_project",
    "cycle",
    "proposal",
    "ticket",
    "meeting",
    "topic",
    "decision",
    "risk",
    "supplier",
    "process",
    "document",
    "quote",
    "invoice",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


@dataclass
class SourceRef:
    gateway: str
    source_id: str
    source_type: str | None = None
    url: str | None = None
    title: str | None = None
    last_seen: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRef":
        return cls(
            gateway=str(data["gateway"]),
            source_id=str(data["source_id"]),
            source_type=data.get("source_type"),
            url=data.get("url"),
            title=data.get("title"),
            last_seen=data.get("last_seen"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gateway": self.gateway,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "url": self.url,
            "title": self.title,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }


@dataclass
class Relation:
    type: str
    target_id: str
    label: str | None = None
    confidence: str | None = None
    source_gateway: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relation":
        return cls(
            type=str(data["type"]),
            target_id=str(data["target_id"]),
            label=data.get("label"),
            confidence=data.get("confidence"),
            source_gateway=data.get("source_gateway"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target_id": self.target_id,
            "label": self.label,
            "confidence": self.confidence,
            "source_gateway": self.source_gateway,
        }


@dataclass
class EntityCard:
    id: str
    type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    known_in: list[str] = field(default_factory=list)
    best_tools: dict[str, str] = field(default_factory=dict)
    source_refs: list[SourceRef] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    last_seen: str | None = None
    last_updated: str | None = None
    confidence: str = "medium"
    staleness: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityCard":
        entity_type = str(data["type"])
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        return cls(
            id=str(data["id"]),
            type=entity_type,
            canonical_name=str(data["canonical_name"]),
            aliases=[str(v) for v in data.get("aliases", [])],
            summary=str(data.get("summary", "")),
            known_in=[str(v) for v in data.get("known_in", [])],
            best_tools={str(k): str(v) for k, v in (data.get("best_tools") or {}).items()},
            source_refs=[SourceRef.from_dict(v) for v in data.get("source_refs", [])],
            relations=[Relation.from_dict(v) for v in data.get("relations", [])],
            last_seen=data.get("last_seen"),
            last_updated=data.get("last_updated"),
            confidence=str(data.get("confidence", "medium")),
            staleness=str(data.get("staleness", "unknown")),
            warnings=[str(v) for v in data.get("warnings", [])],
        )

    def normalized_aliases(self) -> list[str]:
        values = [self.canonical_name, *self.aliases]
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            clean = " ".join(value.split())
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "canonical_name": self.canonical_name,
            "aliases": self.aliases,
            "summary": self.summary,
            "known_in": self.known_in,
            "best_tools": self.best_tools,
            "source_refs": [v.to_dict() for v in self.source_refs],
            "relations": [v.to_dict() for v in self.relations],
            "last_seen": self.last_seen,
            "last_updated": self.last_updated,
            "confidence": self.confidence,
            "staleness": self.staleness,
            "warnings": self.warnings,
        }
