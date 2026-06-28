# TWave Knowledge Atlas

Lightweight multidomain knowledge layer for TWave.

The atlas keeps a global view of entities, relationships, summaries, and routes to the right source gateways. It does not call Odoo, Notion, SGC, or research systems directly. It only consumes exported files such as `entity_cards.jsonl`.

## Scope

- Local SQLite database for entity cards, aliases, relations, source references, gateway exports, update logs, and search.
- Markdown vault compatible with Obsidian.
- CLI for importing exports, merging aliases, building vault pages, searching, inspecting entities, and listing routes.
- Prepared for `twave-agent-hub` to query local atlas data.

## Quickstart

```bash
uv sync --dev
uv run atlas init
uv run atlas import atlas/sources/mock/entity_cards.jsonl
uv run atlas merge
uv run atlas build-vault
uv run atlas search "resonins"
uv run atlas entity "Resonins"
uv run atlas routes "Resonins"
```

## Import Format

Gateway exports can be JSONL or JSON. JSONL should contain one entity card per line. JSON can contain either a list of cards or an object with an `entity_cards` list.

Each card follows `schemas/entity_card.schema.json`.

## Repository Layout

```text
atlas/
  vault/       Markdown vault generated from local DB
  db/          SQLite database files
  exports/     Generated exports
  sources/     Gateway export inputs and mocks
src/twave_knowledge_atlas/
schemas/
docs/
tests/
```
