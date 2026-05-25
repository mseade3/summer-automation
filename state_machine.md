# Missed Call Text-Back State Machine

This document explains the deterministic routing layer used by this project.
The goal is simple: the LLM only classifies intent, and Python code controls all state transitions and outbound messaging.

## Architecture Summary

- **Reasoning Layer (`ai_handler.py`)**
  - Extracts structured JSON intent (`BOOKING`, `LEAD`, `CANCEL`, `SUPPORT`, `UNKNOWN`).
  - Returns entities and confidence score.
  - Never writes to the database directly.

- **Execution Layer (`app.py` + `database.py`)**
  - Reads customer profile context from SQLite.
  - Applies hardcoded state transitions.
  - Logs deterministic lead metadata.
  - Returns predefined response templates.

## Customer States

- `NEW`
- `TEXT_BACK_SENT`
- `BOOKING_PENDING`
- `LEAD_PENDING`
- `SUPPORT_PENDING`
- `CANCEL_REVIEW`
- `HUMAN_REVIEW`

## Intent Labels

- `BOOKING`
- `LEAD`
- `CANCEL`
- `SUPPORT`
- `UNKNOWN`

## Transition Rules

These are defined in `decide_next_state(...)` in `app.py`.

| Current State | Detected Intent | Next State |
| --- | --- | --- |
| `NEW` | `BOOKING` | `BOOKING_PENDING` |
| `NEW` | `LEAD` | `LEAD_PENDING` |
| `NEW` | `SUPPORT` | `SUPPORT_PENDING` |
| `TEXT_BACK_SENT` | `BOOKING` | `BOOKING_PENDING` |
| `TEXT_BACK_SENT` | `LEAD` | `LEAD_PENDING` |
| `TEXT_BACK_SENT` | `SUPPORT` | `SUPPORT_PENDING` |
| `BOOKING_PENDING` | `CANCEL` | `CANCEL_REVIEW` |
| `LEAD_PENDING` | `CANCEL` | `CANCEL_REVIEW` |
| `SUPPORT_PENDING` | `CANCEL` | `CANCEL_REVIEW` |
| Any state + unmatched pair | Any unsupported/low confidence intent | `HUMAN_REVIEW` |

## Confidence Guardrail

- If intent confidence is below `0.5`, the system forces `UNKNOWN`.
- `UNKNOWN` routes to `HUMAN_REVIEW` with status `REQUIRES_HUMAN_INTERVENTION`.

## Deterministic Response Rules

These are defined in `build_deterministic_response(...)` in `app.py`.

- `BOOKING`:
  - lead status: `HIGH_PRIORITY_BOOKING`
  - note: `booking_queue`
- `LEAD`:
  - lead status: `NEW_INQUIRY`
  - note: `lead_queue`
- `SUPPORT`:
  - lead status: `SUPPORT_REQUEST`
  - note: `support_queue`
- `CANCEL`:
  - if active pending state exists:
    - lead status: `CANCELLATION_REVIEW`
    - note: `human_confirmation_required`
  - otherwise:
    - lead status: `REQUIRES_HUMAN_INTERVENTION`
    - note: `cancel_without_active_flow`
- `UNKNOWN`:
  - lead status: `REQUIRES_HUMAN_INTERVENTION`
  - note: `intent_unknown_or_low_confidence`

## Database Fields Used for Routing

### `customer_profiles`

- `phone_number` (primary key)
- `first_seen_at`
- `last_seen_at`
- `customer_state`
- `total_messages`

### `leads`

- `phone_number`
- `received_at`
- `raw_text`
- `lead_status`
- `intent_name`
- `handling_note`

## Operational Fail-Safes

- Intent extraction API failure automatically falls back to `UNKNOWN`.
- Unsupported transitions automatically route to `HUMAN_REVIEW`.
- Database errors raise runtime exceptions and return safe server errors.

## How to Extend Safely

When adding a new intent (example: `RESCHEDULE`), update in this exact order:

1. Add new intent label to `extract_caller_intent(...)` validation in `ai_handler.py`.
2. Add transition rules in `decide_next_state(...)` in `app.py`.
3. Add deterministic message + status mapping in `build_deterministic_response(...)`.
4. Add any new database statuses/notes used for reporting.
5. Update this file so the architecture stays audit-friendly.

## Pitch Language (Client-Friendly)

- Deterministic integrity: AI understands language, but code controls business actions.
- Zero-script fail-safe: unclear requests route to human review instead of guessed answers.
- Unified intelligence: call and text outcomes are captured in one auditable SQLite pipeline.

