from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import DEFAULT_VAULT_DIRS, ENTITY_TYPE_DIRS
from .db import AtlasDB
from .linker import obsidian_link_label
from .models import EntityCard


def init_vault(path: Path) -> None:
    for directory in DEFAULT_VAULT_DIRS:
        (path / directory).mkdir(parents=True, exist_ok=True)


def build_vault(db: AtlasDB, vault_path: Path) -> int:
    init_vault(vault_path)
    count = 0
    for entity in db.list_entities():
        rel_dir = ENTITY_TYPE_DIRS.get(entity.type, "temas")
        target_dir = vault_path / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{slugify(entity.canonical_name)}.md").write_text(render_entity_markdown(entity), encoding="utf-8")
        count += 1
    return count


def render_entity_markdown(entity: EntityCard) -> str:
    frontmatter = {
        "id": entity.id,
        "type": entity.type,
        "aliases": entity.aliases,
        "known_in": entity.known_in,
        "best_tools": entity.best_tools,
        "last_seen": entity.last_seen,
        "last_updated": entity.last_updated,
        "confidence": entity.confidence,
        "staleness": entity.staleness,
        "warnings": entity.warnings,
    }
    lines = ["---", *_yaml_lines(frontmatter), "---", "", f"# {entity.canonical_name}", ""]
    lines.extend(["## Resumen rapido", "", entity.summary or "_Sin resumen breve todavia._", ""])
    lines.extend(["## Estado conocido", "", f"- Tipo: `{entity.type}`", f"- Confianza: `{entity.confidence}`", f"- Frescura: `{entity.staleness}`", ""])
    lines.extend(["## Donde preguntar", ""])
    if entity.known_in:
        for gateway in entity.known_in:
            lines.append(f"- {gateway}")
    else:
        lines.append("- _Sin gateway conocido._")
    if entity.best_tools:
        lines.append("")
        for purpose, tool in sorted(entity.best_tools.items()):
            lines.append(f"- {purpose}: `{tool}`")
    lines.append("")
    lines.extend(["## Relaciones", ""])
    if entity.relations:
        for relation in entity.relations:
            label = relation.label or relation.target_id
            lines.append(f"- {relation.type}: [[{obsidian_link_label(label)}]]")
    else:
        lines.append("- _Sin relaciones registradas._")
    lines.append("")
    lines.extend(["## Fuentes", ""])
    if entity.source_refs:
        for ref in entity.source_refs:
            title = ref.title or ref.source_id
            suffix = f" - {ref.url}" if ref.url else ""
            lines.append(f"- {ref.gateway}: {title} (`{ref.source_id}`){suffix}")
    else:
        lines.append("- _Sin fuentes registradas._")
    lines.append("")
    return "\n".join(lines)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", slug).strip("-") or "entity"


def _yaml_lines(data: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            if value:
                for child_key, child_value in value.items():
                    lines.append(f"{prefix}  {child_key}: {_yaml_scalar(child_value)}")
            continue
        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            if value:
                for item in value:
                    lines.append(f"{prefix}  - {_yaml_scalar(item)}")
            continue
        lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
    return lines


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text == "" or any(char in text for char in [":", "#", "[", "]", "{", "}", "\n"]):
        return '"' + text.replace('"', '\\"') + '"'
    return text
