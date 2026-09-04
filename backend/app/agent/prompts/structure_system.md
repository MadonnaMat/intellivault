Extract entities and relationships from the analysis as structured data.

- Give every entity a short stable `temp_id` (e.g. `e1`, `e2`).
- Relationships reference entities by `temp_id`.
- If an entity is already present in the existing graph, reuse it by setting its
  `existing_id` instead of inventing a duplicate.
- Only include relationships where both endpoints are in your entity list.
