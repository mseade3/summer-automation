# SMS intent dataset (synthetic)

Labeled SMS messages for evaluating the production intent router.

| Field | Description |
|-------|-------------|
| `id` | Stable example id (`bk_*` / `ld_*` / `un_*`) |
| `text` | Customer SMS body |
| `label` | One of `BOOKING`, `LEAD_INQUIRY`, `UNKNOWN` |
| `source` | Always `synthetic` in this file |

**Important:** All examples are **invented** for evaluation. They are not real customer traffic and contain no PII from production databases.

Format: JSON Lines (`sms_intent_dataset.jsonl`).
