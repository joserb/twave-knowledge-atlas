"""Adaptador de contrato para twave-agent-hub.

Lee un ToolRequest JSON por STDIN y devuelve un ToolResponse JSON por STDOUT, igual
que los gateways. Expone las cuatro capacidades que el hub espera del atlas:

- search_entities(query, limit)
- get_entity_card(entity_id)
- get_routes_for_entity(entity_id)
- suggest_tools_for_question(question)

Uso (desde el hub, vía local_script):
    uv run python -m twave_knowledge_atlas.agent_adapter   # ToolRequest por STDIN

El atlas NO llama a Odoo/Notion/SGC: responde desde su base local (SQLite). Los
campos `best_tools` se traducen del formato interno `modulo.funcion` a los ids de
herramienta del hub para que el planificador pueda enrutar.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from .config import AtlasConfig
from .db import AtlasDB
from .models import EntityCard
from .search import entity_routes

# modulo interno del atlas -> id de herramienta en el hub
_MODULE_TO_TOOL = {
    "notion_knowledge": "notion-knowledge",
    "cycle_reports": "notion-cycles",
    "notion_cycles": "notion-cycles",
    "twave_odoo_gateway": "odoo-gateway",
    "odoo_gateway": "odoo-gateway",
    "odoo": "odoo-gateway",
    "twave_research_projects": "research-projects",
    "research_projects": "research-projects",
    "research": "research-projects",
    "rnd_docs": "research-projects",
    "sgc_iso": "sgc-iso",
    "sgc": "sgc-iso",
}

# palabras vacías (es) que solo añaden ruido al MATCH de FTS
_STOPWORDS = {
    "de", "del", "el", "la", "los", "las", "un", "una", "en", "y", "a", "que",
    "con", "por", "para", "al", "lo", "su", "se", "o", "como", "cual", "cuales",
    "resume", "dame", "sobre",
}


def _tool_id_from_best(value: str) -> str:
    """'notion_knowledge.get_document' -> 'notion-knowledge'."""
    module = value.split(".", 1)[0]
    return _MODULE_TO_TOOL.get(module, value)


def _translate_best_tools(best_tools: dict[str, str]) -> dict[str, str]:
    return {purpose: _tool_id_from_best(v) for purpose, v in (best_tools or {}).items()}


def _fts_query(text: str) -> str:
    """Convierte texto libre en una consulta FTS5 segura (tokens OR, entrecomillados)."""
    tokens = [t for t in re.findall(r"\w+", text.lower()) if len(t) >= 2 and t not in _STOPWORDS]
    if not tokens:
        tokens = re.findall(r"\w+", text.lower())  # fallback: todo
    return " OR ".join(f'"{t}"' for t in tokens)


def _entity_brief(db: AtlasDB, row: dict[str, Any]) -> dict[str, Any]:
    """Resumen ligero de una entidad para search/suggest, enriquecido con rutas."""
    card = db.get_entity(str(row["id"]))
    known_in = card.known_in if card else []
    best_tools = _translate_best_tools(card.best_tools) if card else {}
    return {
        "id": row["id"],
        "type": row["type"],
        "canonical_name": row["canonical_name"],
        "summary": row.get("summary", ""),
        "known_in": known_in,
        "best_tools": best_tools,
        "confidence": card.confidence if card else "medium",
    }


def _ok(req: dict[str, Any], result: dict[str, Any], **extra: Any) -> dict[str, Any]:
    resp = {
        "request_id": req.get("request_id", ""),
        "tool": req.get("tool", "knowledge-atlas"),
        "capability": req.get("capability", ""),
        "status": "ok",
        "result": result,
        "sources": extra.get("sources", []),
        "entities": extra.get("entities", []),
        "warnings": extra.get("warnings", []),
        "confidence": extra.get("confidence", 0.9),
        "suggested_actions": [],
        "meta": {"adapter": "atlas_contract"},
    }
    return resp


def _fail(req: dict[str, Any], code: str, message: str, status: str = "partial") -> dict[str, Any]:
    return {
        "request_id": req.get("request_id", ""),
        "tool": req.get("tool", "knowledge-atlas"),
        "capability": req.get("capability", ""),
        "status": status,
        "result": {},
        "sources": [],
        "entities": [],
        "warnings": [{"code": code, "severity": "warning", "message": message}],
        "confidence": 0.0,
        "suggested_actions": [],
        "meta": {"adapter": "atlas_contract"},
    }


def _atlas_source(entity_id: str, name: str) -> dict[str, Any]:
    return {
        "id": f"atlas:{entity_id}",
        "kind": "sql",
        "title": f"Atlas · {name}",
        "reference": f"atlas://entity/{entity_id}",
        "retrieved_at": "",
    }


# --------------------------------------------------------------------------- #
# Capacidades
# --------------------------------------------------------------------------- #
def cap_search_entities(db: AtlasDB, req: dict[str, Any]) -> dict[str, Any]:
    payload = req.get("payload", {})
    query = str(payload.get("query", "")).strip()
    limit = int(payload.get("limit", 10) or 10)
    if not query:
        return _fail(req, "missing_query", "Falta 'query'.")
    try:
        rows = db.search(_fts_query(query), limit=limit)
    except Exception as exc:  # noqa: BLE001 — FTS puede fallar con texto raro
        return _fail(req, "search_error", f"Fallo de búsqueda: {exc}")

    entities = [_entity_brief(db, r) for r in rows]
    sources = [_atlas_source(e["id"], e["canonical_name"]) for e in entities]
    trace = [
        {"type": e["type"], "id": e["id"], "label": e["canonical_name"], "confidence": 0.9}
        for e in entities
    ]
    return _ok(
        req,
        {"query": query, "entities": entities},
        sources=sources,
        entities=trace,
        confidence=0.9 if entities else 0.3,
    )


def cap_get_entity_card(db: AtlasDB, req: dict[str, Any]) -> dict[str, Any]:
    entity_id = str(req.get("payload", {}).get("entity_id", "")).strip()
    if not entity_id:
        return _fail(req, "missing_entity_id", "Falta 'entity_id'.")
    card: EntityCard | None = db.find_entity(entity_id)
    if card is None:
        return _fail(req, "entity_not_found", f"No hay tarjeta para '{entity_id}'.")
    data = card.to_dict()
    data["best_tools"] = _translate_best_tools(card.best_tools)
    sources = [_atlas_source(card.id, card.canonical_name)]
    trace = [{"type": card.type, "id": card.id, "label": card.canonical_name, "confidence": 0.95}]
    return _ok(req, {"card": data}, sources=sources, entities=trace, confidence=0.95)


def cap_get_routes_for_entity(db: AtlasDB, req: dict[str, Any]) -> dict[str, Any]:
    entity_id = str(req.get("payload", {}).get("entity_id", "")).strip()
    if not entity_id:
        return _fail(req, "missing_entity_id", "Falta 'entity_id'.")
    routes = entity_routes(db, entity_id)
    if routes is None:
        return _fail(req, "entity_not_found", f"No hay rutas para '{entity_id}'.")
    out = {
        "entity_id": routes["id"],
        "type": routes["type"],
        "canonical_name": routes["canonical_name"],
        "known_in": routes["known_in"],
        "best_tools": _translate_best_tools(routes.get("best_tools", {})),
        "source_refs": routes.get("source_refs", []),
    }
    trace = [
        {"type": routes["type"], "id": routes["id"], "label": routes["canonical_name"], "confidence": 0.95}
    ]
    return _ok(req, {"routes": out}, entities=trace, confidence=0.9)


def cap_suggest_tools_for_question(db: AtlasDB, req: dict[str, Any]) -> dict[str, Any]:
    question = str(req.get("payload", {}).get("question", "")).strip()
    if not question:
        return _fail(req, "missing_question", "Falta 'question'.")
    try:
        rows = db.search(_fts_query(question), limit=5)
    except Exception as exc:  # noqa: BLE001
        return _fail(req, "search_error", f"Fallo de búsqueda: {exc}")

    entities = [_entity_brief(db, r) for r in rows]

    # Agrega herramientas sugeridas desde known_in (ids del hub) de las entidades top.
    suggested: dict[str, dict[str, Any]] = {}
    for e in entities:
        label = e["canonical_name"]
        for tool_id in e.get("known_in", []):
            if tool_id not in suggested:
                suggested[tool_id] = {
                    "tool": tool_id,
                    "reason": f"El atlas conoce «{label}» en {tool_id}.",
                    "confidence": 0.8,
                }
        for tool_id in _translate_best_tools(
            db.get_entity(e["id"]).best_tools if db.get_entity(e["id"]) else {}
        ).values():
            suggested.setdefault(
                tool_id,
                {"tool": tool_id, "reason": f"Ruta del atlas para «{label}».", "confidence": 0.7},
            )

    trace = [
        {"type": e["type"], "id": e["id"], "label": e["canonical_name"], "confidence": 0.85}
        for e in entities
    ]
    return _ok(
        req,
        {
            "question": question,
            "suggested_tools": list(suggested.values()),
            "entities": entities,
        },
        entities=trace,
        confidence=0.8 if suggested else 0.3,
    )


_CAPS = {
    "search_entities": cap_search_entities,
    "get_entity_card": cap_get_entity_card,
    "get_routes_for_entity": cap_get_routes_for_entity,
    "suggest_tools_for_question": cap_suggest_tools_for_question,
}


def handle(request: dict[str, Any]) -> dict[str, Any]:
    capability = request.get("capability", "")
    handler = _CAPS.get(capability)
    if handler is None:
        return _fail(request, "unknown_capability", f"Capacidad desconocida: {capability}", status="error")
    db = AtlasDB(AtlasConfig.from_env().db_path)
    try:
        return handler(db, request)
    except Exception as exc:  # noqa: BLE001 — nunca romper el contrato
        return _fail(request, "adapter_error", f"Error interno del atlas: {exc}", status="error")


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps(_fail({}, "bad_request", f"STDIN no es JSON válido: {exc}", status="error")))
        return 0
    print(json.dumps(handle(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
