# Missed Call Text-Back State Machine

This document explains the deterministic routing layer used by this project.
The goal is simple: the LLM (or offline baseline) only classifies intent, and Python code controls all state transitions and outbound messaging.

## Architecture Summary

- **Reasoning Layer (`ai_handler.py`)**
  - Extracts structured JSON intent (`BOOKING`, `LEAD_INQUIRY`, `UNKNOWN`).
  - Returns entities when present.
  - Never writes to the database directly.
  - Offline eval / sklearn baseline: see `ml/eval_intent.py` and README metrics.

- **Execution Layer (`app.py` + `database.py`)**
  - Reads customer profile context from SQLite / Postgres.
  - Applies hardcoded state transitions.
  - Logs deterministic lead metadata.
  - Returns predefined response templates.
  - Dispatches owner SMS alerts on high-priority states.

## Customer States (runtime)

| State | Meaning |
|-------|---------|
| `NEW` | First seen |
| `TEXT_BACK_SENT` | Missed-call auto SMS sent |
| `PRIORITY_BOOKING` | Booking intent captured |
| `NEW_LEAD` | Inquiry / lead intent captured |
| `HUMAN_INTERVENTION_REQUIRED` | Unknown / failed classification → human |

## Intent Labels (production)

- `BOOKING`
- `LEAD_INQUIRY`
- `UNKNOWN`

## Transition Rules

Defined in `decide_next_state(...)` in `app.py`. Mapping is **intent-driven** (prior state does not gate classification):

| Detected Intent | Next State |
| --- | --- |
| `BOOKING` | `PRIORITY_BOOKING` |
| `LEAD_INQUIRY` | `NEW_LEAD` |
| `UNKNOWN` (or anything else) | `HUMAN_INTERVENTION_REQUIRED` |

Owner alerts fire for `PRIORITY_BOOKING` and `HUMAN_INTERVENTION_REQUIRED`.

## Deterministic Response Rules

Defined in `build_deterministic_response(...)` in `app.py`.

- `BOOKING` → lead status `PRIORITY_BOOKING`, note `booking_queue`
- `LEAD_INQUIRY` → lead status `NEW_LEAD`, note `lead_queue`
- `UNKNOWN` → lead status `HUMAN_INTERVENTION_REQUIRED`, note `unknown_intent_fallback`

## Database Fields Used for Routing

### `customer_profiles`

- `phone_number` (primary key)
- `first_seen_at` / `last_seen_at`
- `customer_state`
- `total_messages`

### `leads`

- `phone_number`, `received_at`, `raw_text`
- `lead_status`, `intent_name`, `handling_note`

## Operational Fail-Safes

- Intent extraction API failure falls back to `UNKNOWN`.
- Unsupported intents route to `HUMAN_INTERVENTION_REQUIRED`.
- Database errors raise runtime exceptions and return safe server errors.

## How to Extend Safely

When adding a new intent (example: `RESCHEDULE`), update in this exact order:

1. Add the label to validation in `ai_handler.py` and to the synthetic dataset under `ml/data/`.
2. Add transition rules in `decide_next_state(...)` in `app.py`.
3. Add deterministic message + status mapping in `build_deterministic_response(...)`.
4. Re-run `python ml/eval_intent.py` and update README metrics.
5. Update this file so the architecture stays audit-friendly.

## Pitch Language (Client-Friendly)

- Deterministic integrity: AI understands language, but code controls business actions.
- Zero-script fail-safe: unclear requests route to human review instead of guessed answers.
- Unified intelligence: call and text outcomes are captured in one auditable pipeline.
