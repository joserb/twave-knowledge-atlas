from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import AtlasConfig
from .db import AtlasDB
from .importer import import_path
from .merger import merge_entities
from .search import entity_routes, search_entities
from .vault import build_vault, init_vault


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    parser.add_argument("--db", type=Path, help="SQLite DB path")
    parser.add_argument("--vault", type=Path, help="Obsidian vault path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local DB and vault directories")

    import_parser = subparsers.add_parser("import", help="Import gateway entity cards from JSONL or JSON")
    import_parser.add_argument("path", type=Path)

    subparsers.add_parser("merge", help="Merge entities that share aliases")
    subparsers.add_parser("build-vault", help="Generate Obsidian Markdown pages")

    search_parser = subparsers.add_parser("search", help="Search entities")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=10)

    entity_parser = subparsers.add_parser("entity", help="Show one entity card")
    entity_parser.add_argument("name")

    routes_parser = subparsers.add_parser("routes", help="Show gateways and tools for an entity")
    routes_parser.add_argument("entity")

    args = parser.parse_args(argv)
    config = AtlasConfig.from_env()
    db_path = args.db or config.db_path
    vault_path = args.vault or config.vault_path
    db = AtlasDB(db_path)

    if args.command == "init":
        db.init()
        init_vault(vault_path)
        print(f"Initialized DB at {db_path}")
        print(f"Initialized vault at {vault_path}")
        return 0

    db.init()
    if args.command == "import":
        count = import_path(db, args.path)
        print(f"Imported {count} entity cards from {args.path}")
        return 0

    if args.command == "merge":
        count = merge_entities(db)
        print(f"Merged {count} duplicate entities")
        return 0

    if args.command == "build-vault":
        count = build_vault(db, vault_path)
        print(f"Generated {count} Markdown pages in {vault_path}")
        return 0

    if args.command == "search":
        results = search_entities(db, args.query, limit=args.limit)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if args.command == "entity":
        entity = db.find_entity(args.name)
        if entity is None:
            print(f"Entity not found: {args.name}")
            return 1
        print(json.dumps(entity.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "routes":
        routes = entity_routes(db, args.entity)
        if routes is None:
            print(f"Entity not found: {args.entity}")
            return 1
        print(json.dumps(routes, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
