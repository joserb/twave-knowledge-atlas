from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import EntityCard, Relation, SourceRef, utc_now_iso


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  known_in TEXT NOT NULL DEFAULT '[]',
  best_tools TEXT NOT NULL DEFAULT '{}',
  last_seen TEXT,
  last_updated TEXT,
  confidence TEXT NOT NULL DEFAULT 'medium',
  staleness TEXT NOT NULL DEFAULT 'unknown',
  warnings TEXT NOT NULL DEFAULT '[]',
  merged_into TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aliases (
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  PRIMARY KEY (entity_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  label TEXT,
  confidence TEXT,
  source_gateway TEXT,
  UNIQUE(entity_id, relation_type, target_id)
);

CREATE TABLE IF NOT EXISTS source_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  gateway TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_type TEXT,
  url TEXT,
  title TEXT,
  last_seen TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  UNIQUE(entity_id, gateway, source_id)
);

CREATE TABLE IF NOT EXISTS gateway_exports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  gateway TEXT,
  imported_at TEXT NOT NULL,
  cards_imported INTEGER NOT NULL,
  status TEXT NOT NULL,
  message TEXT
);

CREATE TABLE IF NOT EXISTS update_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT,
  action TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
  entity_id UNINDEXED,
  canonical_name,
  aliases,
  summary,
  tokenize='unicode61 remove_diacritics 2'
);
"""


class AtlasDB:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def upsert_entity(self, card: EntityCard) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM entities WHERE id = ?", (card.id,)).fetchone()
            conn.execute(
                """
                INSERT INTO entities (
                  id, type, canonical_name, summary, known_in, best_tools,
                  last_seen, last_updated, confidence, staleness, warnings,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  type=excluded.type,
                  canonical_name=excluded.canonical_name,
                  summary=excluded.summary,
                  known_in=excluded.known_in,
                  best_tools=excluded.best_tools,
                  last_seen=excluded.last_seen,
                  last_updated=excluded.last_updated,
                  confidence=excluded.confidence,
                  staleness=excluded.staleness,
                  warnings=excluded.warnings,
                  updated_at=excluded.updated_at
                """,
                (
                    card.id,
                    card.type,
                    card.canonical_name,
                    card.summary,
                    json.dumps(card.known_in, ensure_ascii=False),
                    json.dumps(card.best_tools, ensure_ascii=False, sort_keys=True),
                    card.last_seen,
                    card.last_updated,
                    card.confidence,
                    card.staleness,
                    json.dumps(card.warnings, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.execute("DELETE FROM aliases WHERE entity_id = ?", (card.id,))
            for alias in card.normalized_aliases():
                conn.execute(
                    "INSERT OR IGNORE INTO aliases (entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                    (card.id, alias, normalize(alias)),
                )

            conn.execute("DELETE FROM relations WHERE entity_id = ?", (card.id,))
            for relation in card.relations:
                self._insert_relation(conn, card.id, relation)

            conn.execute("DELETE FROM source_refs WHERE entity_id = ?", (card.id,))
            for source_ref in card.source_refs:
                self._insert_source_ref(conn, card.id, source_ref)

            self.rebuild_search_index(conn, [card.id])
            conn.execute(
                "INSERT INTO update_log (entity_id, action, details, created_at) VALUES (?, ?, ?, ?)",
                (
                    card.id,
                    "entity_updated" if existing else "entity_created",
                    json.dumps({"canonical_name": card.canonical_name}, ensure_ascii=False),
                    now,
                ),
            )

    def record_import(self, path: Path, gateway: str | None, count: int, status: str, message: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO gateway_exports (path, gateway, imported_at, cards_imported, status, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(path), gateway, utc_now_iso(), count, status, message),
            )

    def get_entity(self, entity_id: str) -> EntityCard | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ? AND merged_into IS NULL",
                (entity_id,),
            ).fetchone()
            if not row:
                return None
            return self._entity_from_row(conn, row)

    def find_entity(self, name_or_id: str) -> EntityCard | None:
        normalized = normalize(name_or_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ? AND merged_into IS NULL",
                (name_or_id,),
            ).fetchone()
            if row:
                return self._entity_from_row(conn, row)

            alias_row = conn.execute(
                """
                SELECT e.* FROM aliases a
                JOIN entities e ON e.id = a.entity_id
                WHERE a.normalized_alias = ? AND e.merged_into IS NULL
                ORDER BY e.updated_at DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if alias_row:
                return self._entity_from_row(conn, alias_row)
        return None

    def list_entities(self) -> list[EntityCard]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entities WHERE merged_into IS NULL ORDER BY type, canonical_name"
            ).fetchall()
            return [self._entity_from_row(conn, row) for row in rows]

    def search(self, query: str, limit: int = 10) -> list[dict[str, str | float]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.entity_id, e.type, e.canonical_name, e.summary, rank
                FROM search_index s
                JOIN entities e ON e.id = s.entity_id
                WHERE search_index MATCH ? AND e.merged_into IS NULL
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            return [
                {
                    "id": row["entity_id"],
                    "type": row["type"],
                    "canonical_name": row["canonical_name"],
                    "summary": row["summary"],
                    "rank": row["rank"],
                }
                for row in rows
            ]

    def merge_alias_duplicates(self) -> int:
        merged = 0
        now = utc_now_iso()
        with self.connect() as conn:
            duplicate_aliases = conn.execute(
                """
                SELECT normalized_alias
                FROM aliases a
                JOIN entities e ON e.id = a.entity_id
                WHERE e.merged_into IS NULL
                GROUP BY normalized_alias
                HAVING COUNT(DISTINCT entity_id) > 1
                """
            ).fetchall()
            for alias_row in duplicate_aliases:
                rows = conn.execute(
                    """
                    SELECT e.*
                    FROM aliases a
                    JOIN entities e ON e.id = a.entity_id
                    WHERE a.normalized_alias = ? AND e.merged_into IS NULL
                    ORDER BY e.created_at ASC, e.id ASC
                    """,
                    (alias_row["normalized_alias"],),
                ).fetchall()
                if len(rows) < 2:
                    continue
                survivor = rows[0]
                survivor_id = survivor["id"]
                for duplicate in rows[1:]:
                    self._merge_entity_rows(conn, survivor_id, duplicate["id"], now)
                    merged += 1
        return merged

    def rebuild_search_index(self, conn: sqlite3.Connection | None = None, entity_ids: Iterable[str] | None = None) -> None:
        owns_conn = conn is None
        if conn is None:
            conn = self.connect()
        try:
            if entity_ids is None:
                conn.execute("DELETE FROM search_index")
                rows = conn.execute("SELECT id FROM entities WHERE merged_into IS NULL").fetchall()
                entity_ids = [row["id"] for row in rows]
            else:
                for entity_id in entity_ids:
                    conn.execute("DELETE FROM search_index WHERE entity_id = ?", (entity_id,))

            for entity_id in entity_ids:
                row = conn.execute("SELECT * FROM entities WHERE id = ? AND merged_into IS NULL", (entity_id,)).fetchone()
                if not row:
                    continue
                aliases = [
                    alias_row["alias"]
                    for alias_row in conn.execute("SELECT alias FROM aliases WHERE entity_id = ?", (entity_id,))
                ]
                conn.execute(
                    """
                    INSERT INTO search_index (entity_id, canonical_name, aliases, summary)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entity_id, row["canonical_name"], " ".join(aliases), row["summary"]),
                )
        finally:
            if owns_conn:
                conn.commit()
                conn.close()

    def _merge_entity_rows(self, conn: sqlite3.Connection, survivor_id: str, duplicate_id: str, now: str) -> None:
        survivor = conn.execute("SELECT * FROM entities WHERE id = ?", (survivor_id,)).fetchone()
        duplicate = conn.execute("SELECT * FROM entities WHERE id = ?", (duplicate_id,)).fetchone()
        known_in = sorted(set(json.loads(survivor["known_in"])) | set(json.loads(duplicate["known_in"])))
        best_tools = json.loads(survivor["best_tools"])
        best_tools.update(json.loads(duplicate["best_tools"]))
        warnings = sorted(set(json.loads(survivor["warnings"])) | set(json.loads(duplicate["warnings"])))
        summary = survivor["summary"] if len(survivor["summary"]) >= len(duplicate["summary"]) else duplicate["summary"]
        confidence = max_confidence(survivor["confidence"], duplicate["confidence"])
        last_seen = max_optional_text(survivor["last_seen"], duplicate["last_seen"])
        last_updated = max_optional_text(survivor["last_updated"], duplicate["last_updated"])

        conn.execute(
            """
            UPDATE entities
            SET summary = ?, known_in = ?, best_tools = ?, last_seen = ?, last_updated = ?,
                confidence = ?, warnings = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                summary,
                json.dumps(known_in, ensure_ascii=False),
                json.dumps(best_tools, ensure_ascii=False, sort_keys=True),
                last_seen,
                last_updated,
                confidence,
                json.dumps(warnings, ensure_ascii=False),
                now,
                survivor_id,
            ),
        )
        for alias_row in conn.execute("SELECT alias, normalized_alias FROM aliases WHERE entity_id = ?", (duplicate_id,)):
            conn.execute(
                "INSERT OR IGNORE INTO aliases (entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                (survivor_id, alias_row["alias"], alias_row["normalized_alias"]),
            )
        for rel in conn.execute("SELECT * FROM relations WHERE entity_id = ?", (duplicate_id,)):
            conn.execute(
                """
                INSERT OR IGNORE INTO relations (entity_id, relation_type, target_id, label, confidence, source_gateway)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    survivor_id,
                    rel["relation_type"],
                    rel["target_id"],
                    rel["label"],
                    rel["confidence"],
                    rel["source_gateway"],
                ),
            )
        conn.execute("DELETE FROM relations WHERE entity_id = ?", (duplicate_id,))
        for ref in conn.execute("SELECT * FROM source_refs WHERE entity_id = ?", (duplicate_id,)):
            conn.execute(
                """
                INSERT OR IGNORE INTO source_refs
                  (entity_id, gateway, source_id, source_type, url, title, last_seen, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    survivor_id,
                    ref["gateway"],
                    ref["source_id"],
                    ref["source_type"],
                    ref["url"],
                    ref["title"],
                    ref["last_seen"],
                    ref["metadata"],
                ),
            )
        conn.execute("DELETE FROM source_refs WHERE entity_id = ?", (duplicate_id,))
        for rel in conn.execute("SELECT * FROM relations WHERE target_id = ?", (duplicate_id,)):
            conn.execute(
                """
                INSERT OR IGNORE INTO relations (entity_id, relation_type, target_id, label, confidence, source_gateway)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rel["entity_id"],
                    rel["relation_type"],
                    survivor_id,
                    rel["label"],
                    rel["confidence"],
                    rel["source_gateway"],
                ),
            )
        conn.execute("DELETE FROM relations WHERE target_id = ?", (duplicate_id,))
        conn.execute("UPDATE entities SET merged_into = ?, updated_at = ? WHERE id = ?", (survivor_id, now, duplicate_id))
        conn.execute(
            "INSERT INTO update_log (entity_id, action, details, created_at) VALUES (?, ?, ?, ?)",
            (
                survivor_id,
                "entity_merged",
                json.dumps({"merged_entity_id": duplicate_id}, ensure_ascii=False),
                now,
            ),
        )
        self.rebuild_search_index(conn, [survivor_id, duplicate_id])

    def _entity_from_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> EntityCard:
        aliases = [
            alias_row["alias"]
            for alias_row in conn.execute(
                "SELECT alias FROM aliases WHERE entity_id = ? ORDER BY alias",
                (row["id"],),
            )
        ]
        source_refs = [
            SourceRef(
                gateway=ref["gateway"],
                source_id=ref["source_id"],
                source_type=ref["source_type"],
                url=ref["url"],
                title=ref["title"],
                last_seen=ref["last_seen"],
                metadata=json.loads(ref["metadata"]),
            )
            for ref in conn.execute("SELECT * FROM source_refs WHERE entity_id = ? ORDER BY gateway, source_id", (row["id"],))
        ]
        relations = [
            Relation(
                type=rel["relation_type"],
                target_id=rel["target_id"],
                label=rel["label"],
                confidence=rel["confidence"],
                source_gateway=rel["source_gateway"],
            )
            for rel in conn.execute("SELECT * FROM relations WHERE entity_id = ? ORDER BY relation_type, target_id", (row["id"],))
        ]
        return EntityCard(
            id=row["id"],
            type=row["type"],
            canonical_name=row["canonical_name"],
            aliases=[a for a in aliases if normalize(a) != normalize(row["canonical_name"])],
            summary=row["summary"],
            known_in=json.loads(row["known_in"]),
            best_tools=json.loads(row["best_tools"]),
            source_refs=source_refs,
            relations=relations,
            last_seen=row["last_seen"],
            last_updated=row["last_updated"],
            confidence=row["confidence"],
            staleness=row["staleness"],
            warnings=json.loads(row["warnings"]),
        )

    @staticmethod
    def _insert_relation(conn: sqlite3.Connection, entity_id: str, relation: Relation) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO relations (entity_id, relation_type, target_id, label, confidence, source_gateway)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entity_id, relation.type, relation.target_id, relation.label, relation.confidence, relation.source_gateway),
        )

    @staticmethod
    def _insert_source_ref(conn: sqlite3.Connection, entity_id: str, source_ref: SourceRef) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO source_refs
              (entity_id, gateway, source_id, source_type, url, title, last_seen, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                source_ref.gateway,
                source_ref.source_id,
                source_ref.source_type,
                source_ref.url,
                source_ref.title,
                source_ref.last_seen,
                json.dumps(source_ref.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def max_confidence(left: str, right: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return left if rank.get(left, 1) >= rank.get(right, 1) else right


def max_optional_text(left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
