from __future__ import annotations

from pathlib import Path

from twave_knowledge_atlas.cli import main
from twave_knowledge_atlas.db import AtlasDB
from twave_knowledge_atlas.importer import import_path
from twave_knowledge_atlas.merger import merge_entities
from twave_knowledge_atlas.search import entity_routes, search_entities
from twave_knowledge_atlas.vault import build_vault


ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "atlas" / "sources" / "mock" / "entity_cards.jsonl"
DUPLICATE = ROOT / "atlas" / "sources" / "mock" / "entity_cards_duplicate.jsonl"


def test_import_search_routes_and_vault(tmp_path: Path) -> None:
    db = AtlasDB(tmp_path / "atlas.sqlite")
    db.init()

    assert import_path(db, MOCK) == 3

    results = search_entities(db, "Resonins")
    assert results
    assert results[0]["id"] == "customer:resonins"

    routes = entity_routes(db, "Resonins")
    assert routes is not None
    assert "odoo-gateway" in routes["known_in"]
    assert routes["best_tools"]["commercial"] == "odoo.get_customer_summary"

    generated = build_vault(db, tmp_path / "vault")
    assert generated == 3
    page = tmp_path / "vault" / "clientes" / "resonins.md"
    assert page.exists()
    content = page.read_text(encoding="utf-8")
    assert "known_in:" in content
    assert "[[TWist]]" in content


def test_merge_alias_duplicates(tmp_path: Path) -> None:
    db = AtlasDB(tmp_path / "atlas.sqlite")
    db.init()
    import_path(db, MOCK)
    import_path(db, DUPLICATE)

    assert merge_entities(db) == 1
    entity = db.find_entity("Resonins Audio")
    assert entity is not None
    assert "odoo-gateway" in entity.known_in
    assert db.find_entity("customer:resonins-odoo") is None


def test_cli_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.sqlite"
    vault_path = tmp_path / "vault"

    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "init"]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "import", MOCK.as_posix()]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "merge"]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "build-vault"]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "entity", "Resonins"]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "routes", "Resonins"]) == 0
    assert main(["--db", db_path.as_posix(), "--vault", vault_path.as_posix(), "search", "TWist"]) == 0
