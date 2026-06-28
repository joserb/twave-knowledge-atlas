# Convención de exports gateway → atlas

Contrato común por el que cada gateway alimenta al `twave-knowledge-atlas`. Es el
otro lado del contrato del hub: el hub **invoca** capacidades de los gateways en
vivo; el atlas **ingiere** ficheros que los gateways exportan periódicamente para
mantener el mapa global de entidades, alias y rutas.

## Principio

- El gateway es la autoridad de su dominio y el único que sabe leer su fuente.
- El atlas no llama a Odoo/Notion/etc.; solo consume ficheros exportados.
- El export es **derivado y desechable**: se puede regenerar siempre desde la fuente
  o la caché local del gateway. No es una base de datos nueva.
- Las cards son **ligeras**: identidad, alias, resumen corto, dónde mirar
  (`known_in`, `best_tools`, `source_refs`) y relaciones. El detalle se obtiene
  llamando a las capacidades del gateway, no del atlas.

## Ubicación y formato

Cada gateway escribe en su propio repo:

```text
<gateway>/data/exports/entity_cards.jsonl
```

(Cumple el rol de `local/exports/` de la arquitectura global; se mantiene bajo
`data/` para alinearse con la convención de caché ya existente en cada repo.)

Formatos que el atlas acepta al importar:

- `.jsonl`: un objeto `EntityCard` por línea (recomendado).
- `.json`: lista de cards.
- `.json`: objeto con una lista `entity_cards`.

## Esquema

Cada card cumple `schemas/entity_card.schema.json`, con `source_refs` y `relations`
según `schemas/source_ref.schema.json` y `schemas/relation.schema.json`.

Campos: `id` (obligatorio, `"{tipo}:{id_estable}"`), `type` (obligatorio),
`canonical_name` (obligatorio), `aliases`, `summary`, `known_in`, `best_tools`
(`{rol: "gateway.capability"}`), `source_refs`, `relations`, `last_seen`,
`last_updated`, `confidence` (`low|medium|high`), `staleness`, `warnings`.

Convenciones de identidad:

- `id`: `customer:123`, `cycle:26-2`, `proposal:26-2:mejora-pipeline`, `document:<page_id>`.
- `source_refs[].source_id`: id nativo en la fuente (`res.partner:123`, `page:<id>`).
- `relations[].target_id`: el `id` de otra card (permite que el atlas teja el grafo).

Tipos de entidad: usar el catálogo común del hub (`customer, contact, supplier,
product, quote, invoice, project, cycle, proposal, ticket, document, process,
decision, risk`). El schema del atlas admite además `meeting`/`topic`; cuando una
fuente no encaja (p. ej. una acta), modelarla como `document` y conservar el matiz
en `source_refs[].source_type`.

## Comando de import

```bash
atlas import <gateway>/data/exports/entity_cards.jsonl
atlas merge        # fusiona entidades que comparten alias
atlas build-vault  # regenera el vault Obsidian
```

## Cómo lo genera cada gateway

| Gateway            | Comando                                            | Produce (type)              | Origen        |
| ------------------ | -------------------------------------------------- | --------------------------- | ------------- |
| odoo-gateway       | `python -m twave_odoo_gateway.atlas_export`        | customer, supplier, product | Odoo (live)   |
| notion-cycles      | `python -m cycle_reports.atlas_export`             | cycle, proposal, project    | caché local   |
| notion-knowledge   | `python -m notion_knowledge.atlas_export`          | document, ticket            | caché local   |

Todas las capacidades de export se declaran como `export_entity_cards` en el
`tool_manifest.yml` de cada gateway (acceso `read-only`, `side_effects: writes`
porque escriben un fichero local; nunca modifican la fuente).

## Ejemplo de card

```json
{
  "id": "customer:123",
  "type": "customer",
  "canonical_name": "Resonins",
  "aliases": ["Resonins SA", "R1"],
  "summary": "Cliente registrado en Odoo. País: Turquía.",
  "known_in": ["odoo-gateway"],
  "best_tools": {
    "commercial": "odoo.get_customer_summary",
    "invoices": "odoo.get_customer_statement"
  },
  "source_refs": [
    {"gateway": "odoo-gateway", "source_id": "res.partner:123", "source_type": "customer", "title": "Resonins"}
  ],
  "relations": [],
  "last_seen": "2026-06-28",
  "last_updated": "2026-06-28",
  "confidence": "high",
  "staleness": "fresh",
  "warnings": []
}
```
