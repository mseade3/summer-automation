# Deployment Guide — Missed-Call Text-Back Engine

This guide takes the system off your laptop and puts it online 24/7, so it
keeps answering missed calls even when your computer is closed.

You'll deploy two things and one database:

| Piece | What it does | Who uses it |
|-------|--------------|-------------|
| **Backend** (Flask) | Answers Twilio calls/texts, runs the AI, sends text-backs | Twilio (machines) |
| **Dashboard** (Streamlit) | The clean screen showing leads to call first | The business owner |
| **Database** (Postgres) | Stores every lead permanently | Both, behind the scenes |

> **Why Postgres now?** On your laptop the app used a single SQLite file.
> Cloud hosts wipe their disks on every restart, so that file would vanish and
> you'd lose leads. A hosted Postgres database is permanent. The code already
> handles both: locally it uses SQLite, and when a `DATABASE_URL` is present it
> automatically switches to Postgres. **You don't change any code.**

---

## What changed in the project

- `db.py` — new shared database connector (SQLite locally, Postgres in production).
- `database.py` / `dashboard.py` — now talk to the database through `db.py`.
- `requirements.txt` — added `sqlalchemy`, `psycopg2-binary`, `gunicorn`.
- `Procfile`, `runtime.txt`, `render.yaml` — deployment configuration.
- `.env.example` — documents the new `DATABASE_URL` and `BUSINESS_NAME` settings.

Your `.env.local` secrets are **not** committed (protected by `.gitignore`).

---

## Step 0 — Put the code on GitHub

Both Render and Railway deploy from a GitHub repo.

```bash
cd summer-automation-engine
git add .
git commit -m "Add cloud deployment setup"
# create an empty repo on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/summer-automation-engine.git
git push -u origin master
```

---

## Option A — Render (recommended, one-click blueprint)

The repo includes `render.yaml`, which provisions the database and both
services automatically.

1. Go to **[render.com](https://render.com)** and sign up (free).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account and pick the `summer-automation-engine` repo.
4. Render reads `render.yaml` and shows: 1 database + 2 web services. Click **Apply**.
5. Render will ask you to fill in the secret values (marked `sync: false`):
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER` (e.g. `+15551234567`)
   - `OWNER_CELL_PHONE` (e.g. `+12407580338`)
   - `OPENAI_API_KEY`
   - `BUSINESS_NAME` (e.g. `Clinton Auto Care`)
6. Click **Create / Deploy**. Wait a few minutes for both services to go live.

You'll end up with two URLs:
- **Backend:** `https://leadengine-backend.onrender.com`
- **Dashboard:** `https://leadengine-dashboard.onrender.com`

The `DATABASE_URL` is wired into both services for you — no copy/paste needed.

---

## Option B — Railway

1. Go to **[railway.app](https://railway.app)** and sign up.
2. **New Project** → **Deploy from GitHub repo** → select the repo.
3. Add a database: **New** → **Database** → **PostgreSQL**. Railway sets a
   `DATABASE_URL` variable automatically.
4. Create the **backend** service from the repo:
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - Add variables: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
     `TWILIO_PHONE_NUMBER`, `OWNER_CELL_PHONE`, `OPENAI_API_KEY`,
     `BUSINESS_NAME`. Reference the shared `DATABASE_URL`.
5. Create a second service for the **dashboard** from the same repo:
   - Start command: `streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
   - Give it `DATABASE_URL` and `BUSINESS_NAME`.
6. Under each service's **Settings → Networking**, click **Generate Domain**
   to get public URLs.

---

## Step 1 — Point Twilio at the live backend

In the [Twilio Console](https://console.twilio.com) → **Phone Numbers** →
your number:

- **A CALL COMES IN** → Webhook → `https://YOUR-BACKEND-URL/webhook/voice` (HTTP POST)
- **A MESSAGE COMES IN** → Webhook → `https://YOUR-BACKEND-URL/webhook/sms` (HTTP POST)

Save. ngrok is no longer needed — these are permanent URLs.

---

## Step 2 — Test it

1. Open the dashboard URL. You should see the **Customer Response Center**.
2. From a different phone, call your Twilio number. It should reject the call
   and text you back within a few seconds.
3. Refresh the dashboard — the lead appears under **Call These First**.

---

## Important: Twilio A2P 10DLC registration

US carriers block texts from unregistered business numbers (error `30034`).
Before going live with a real client you must register the number for
**A2P 10DLC** in the Twilio Console under **Messaging → Regulatory Compliance →
A2P 10DLC**. This is a Twilio account step, not a code change. Approval can
take a day or two, so start it early.

---

## Notes on free tiers

- Render/Railway free web services **sleep after inactivity** and take ~30
  seconds to wake. That's fine for a demo. For a paying client, upgrade the
  backend to a paid instance (~$7/mo) so missed calls are always answered
  instantly.
- The free Postgres database is plenty for storing leads.

---

## Handing it off to a business

1. Deploy one copy per client (each gets its own Twilio number, env vars, and
   `BUSINESS_NAME`).
2. Give the owner **only the dashboard URL** — that's all they ever need to open.
3. Have them set up **conditional call forwarding** on their existing business
   line so missed/busy calls forward to their Twilio number.
4. Charge a setup fee plus a monthly retainer for keeping the engine running.
