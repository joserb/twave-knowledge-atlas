# Entity Model

The core object is `EntityCard`.

Required fields:

- `id`: stable atlas id such as `customer:resonins`.
- `type`: one of the initial supported entity types.
- `canonical_name`: display name and primary alias.

Routing fields:

- `known_in`: gateways where the entity is known.
- `best_tools`: map of question intent to tool name.
- `source_refs`: concrete source records in gateway exports.

Knowledge fields:

- `summary`: short human-readable summary.
- `relations`: links to other entities by id.
- `confidence`: `low`, `medium`, or `high`.
- `staleness`: freshness label from importer/gateway policy.
- `warnings`: caveats for consumers.

Initial entity types:

`customer`, `contact`, `product`, `project`, `research_project`, `cycle`, `proposal`, `ticket`, `meeting`, `topic`, `decision`, `risk`, `supplier`, `process`, `document`, `quote`, `invoice`.
