# Summer Automation Engine

Missed-call text-back and SMS lead routing for local service businesses.

**Public repo:** [github.com/mseade3/summer-automation](https://github.com/mseade3/summer-automation)

Twilio captures the missed call or inbound SMS → an intent classifier labels the message → a **deterministic** Python state machine chooses the next state and reply → high-priority outcomes alert the owner. The LLM (or offline baseline) only classifies; business actions stay in code.

---

## Architecture

```
Caller / SMS
    │
    ▼
Twilio Voice + SMS webhooks  ──►  Flask (app.py)
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                   Intent router   State machine  Owner alerts
                   (OpenAI JSON    (decide_next_  (Twilio SMS to
                    BOOKING /       state +        OWNER_CELL)
                    LEAD_INQUIRY /  templates)
                    UNKNOWN)
                         │
                         ▼
                   SQLite (local) / Postgres (deploy)
                         │
                         ▼
                   Streamlit ops dashboard
```

| Layer | Role |
|-------|------|
| **Twilio** | Voice forward / SMS webhooks; outbound text-back + owner alerts |
| **Intent router** | Maps free-text SMS → `BOOKING` \| `LEAD_INQUIRY` \| `UNKNOWN` (+ entities) |
| **State machine** | Maps intent → customer state + fixed reply templates (no free-form LLM replies) |
| **Alerts** | `PRIORITY_BOOKING` and `HUMAN_INTERVENTION_REQUIRED` notify the owner |
| **Dashboard** | Streamlit view of leads and conversation state |

See `state_machine.md` for transition rules and `DEPLOYMENT.md` for cloud setup.

---

## Intent evaluation (ML / NLP)

Labeled **synthetic** SMS dataset (not real customer traffic — no production PII):

| Split | Count |
|-------|-------|
| Total labeled SMS | **165** |
| Per class | 55 × `BOOKING`, 55 × `LEAD_INQUIRY`, 55 × `UNKNOWN` |
| Held-out test (30%, seed=42) | 50 |

### Sklearn baseline (offline, no Twilio / OpenAI)

`TF-IDF (1–2 grams) + LogisticRegression` via `ml/eval_intent.py`:

| Metric | Score |
|--------|------:|
| **Accuracy** | **0.840** |
| **Macro F1** | **0.832** |
| Weighted F1 | 0.831 |

Confusion matrix (rows = true, cols = predicted):

|  | BOOKING | LEAD_INQUIRY | UNKNOWN |
|--|--------:|-------------:|--------:|
| **BOOKING** | 16 | 0 | 0 |
| **LEAD_INQUIRY** | 1 | 16 | 0 |
| **UNKNOWN** | 2 | 5 | 10 |

`UNKNOWN` is the hardest class (short / off-topic SMS); booking language is very separable.

### LLM router (same held-out test, optional)

Production path: `ai_handler.classify_incoming_intent` (OpenAI JSON). On the **same** 50-message test split:

| Metric | Sklearn | LLM router |
|--------|--------:|-----------:|
| **Accuracy** | **0.840** | **0.840** |
| **Macro F1** | **0.832** | **0.840** |
| Weighted F1 | 0.831 | 0.838 |

LLM confusion matrix (rows = true, cols = predicted):

|  | BOOKING | LEAD_INQUIRY | UNKNOWN |
|--|--------:|-------------:|--------:|
| **BOOKING** | 16 | 0 | 0 |
| **LEAD_INQUIRY** | 0 | 12 | 5 |
| **UNKNOWN** | 2 | 1 | 14 |

Takeaway: accuracy ties; the LLM recovers more `UNKNOWN` recall, while TF-IDF+logistic is stronger on `LEAD_INQUIRY` recall. Both are strong on `BOOKING`.

Eval is **opt-in** and **skipped** when `OPENAI_API_KEY` is missing:

```bash
python ml/eval_intent.py --llm
```

Results land in `ml/results/` (`sklearn_metrics.json`, optional `llm_metrics.json`, `eval_summary.json`).

### Reproduce offline

```bash
pip install -r ml/requirements.txt
python ml/eval_intent.py
```

Dataset + notes: `ml/data/sms_intent_dataset.jsonl`, `ml/data/README.md`.

---

## Quick start (local)

```bash
cp .env.example .env.local   # fill Twilio + OpenAI for live webhooks
pip install -r requirements.txt
python app.py                # Flask on :5000
# optional dashboard:
pip install -r requirements-dashboard.txt
streamlit run dashboard.py
```

Webhook paths (Twilio): SMS → `/webhook/sms`, voice → `/webhook/voice` (see `app.py`). Smoke script: `python test_pipeline.py` (needs the Flask app running).

**Secrets:** never commit `.env` / `.env.local`. Only `.env.example` is tracked.

---

## Deploy notes

Full walkthrough: **[DEPLOYMENT.md](./DEPLOYMENT.md)**.

- **Render:** `render.yaml` blueprints Postgres + Flask backend + Streamlit dashboard.
- **Vercel / other:** see deploy docs; set `DATABASE_URL` for Postgres (SQLite is wiped on ephemeral disks).
- Required env vars: `TWILIO_*`, `OWNER_CELL_PHONE`, `OPENAI_API_KEY`, `BUSINESS_NAME`, `DATABASE_URL` (prod).

---

## Repo map

| Path | Purpose |
|------|---------|
| `app.py` | Flask webhooks, state machine, alerts |
| `ai_handler.py` | OpenAI intent JSON router |
| `database.py` / `db.py` | Lead + conversation persistence |
| `dashboard.py` | Streamlit lead console |
| `ml/` | Synthetic SMS dataset + offline intent eval |
| `state_machine.md` | Routing design notes |
| `DEPLOYMENT.md` | Render / Railway / Postgres |
