from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtlasConfig:
    db_path: Path
    vault_path: Path

    @classmethod
    def from_env(cls) -> "AtlasConfig":
        return cls(
            db_path=Path(os.getenv("ATLAS_DB_PATH", "atlas/db/atlas.sqlite")),
            vault_path=Path(os.getenv("ATLAS_VAULT_PATH", "atlas/vault")),
        )


ENTITY_TYPE_DIRS = {
    "customer": "clientes",
    "contact": "clientes",
    "product": "productos",
    "project": "proyectos",
    "research_project": "proyectos",
    "cycle": "ciclos",
    "proposal": "ciclos",
    "ticket": "temas",
    "meeting": "temas",
    "topic": "temas",
    "decision": "decisiones",
    "risk": "temas",
    "supplier": "proveedores",
    "process": "procesos",
    "document": "temas",
    "quote": "clientes",
    "invoice": "clientes",
}


DEFAULT_VAULT_DIRS = [
    "clientes",
    "productos",
    "proyectos",
    "temas",
    "decisiones",
    "procesos",
    "ciclos",
    "proveedores",
]
