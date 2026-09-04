# Deploying ReviveAI to Render

Render's free tier runs all three pieces — PostgreSQL, the FastAPI backend, and
the React frontend — with no credit card. `render.yaml` in the repository root
defines all of them, so deployment is one connection rather than three setups.

---

## Deploy

1. Sign in at **[dashboard.render.com](https://dashboard.render.com)** (GitHub login works).
2. **New → Blueprint**.
3. Connect **`Happybro2005/ReviveAI-`**.
4. Render reads `render.yaml` and shows three resources:
   - `reviveai-db` — PostgreSQL (free)
   - `reviveai-api` — Python web service (free)
   - `reviveai-web` — static site (free)
5. **Apply**.

First deploy takes **8–12 minutes**. Most of it is installing scikit-learn,
pandas and SHAP.

### Then do this one thing

Render generates the frontend URL only after the first deploy, and Vite inlines
the API URL at **build** time. So:

1. Open `reviveai-api` and copy its URL, e.g. `https://reviveai-api-x7k2.onrender.com`
2. Open `reviveai-web` → **Environment**
3. Set `VITE_API_BASE` to that URL **with `/api` appended**:
   ```
   https://reviveai-api-x7k2.onrender.com/api
   ```
4. **Manual Deploy → Deploy latest commit** (a restart is not enough — Vite
   inlines the value during the build)

CORS needs no change: the API is configured with `*`, which is correct for a
public read-only demo.

---

## What happens on first boot

`startCommand` runs `scripts/bootstrap.py` before uvicorn. It is idempotent and
skips any stage already done:

| Stage | Fresh deploy | Later restarts |
|---|---|---|
| Migrations | ~1s | skipped (already at head) |
| Seed 40,000 sessions | ~30s | skipped (rows exist) |
| Analyse ~22,000 reviews | ~35s | skipped (rows exist) |
| Train 6 models | ~15s | **re-runs** (see below) |

Measured locally at 20k sessions: 33s for a fully fresh database, 2.1s when
everything already exists. Render's CPU is slower, so expect roughly double.

> **Models retrain on every cold start.** Render's free filesystem is ephemeral,
> so `artifacts/*.joblib` disappears when the instance sleeps. The database
> persists, so only training re-runs — about 15–30 seconds added to the wake.
> To avoid it, commit the artifacts (3.7 MB) by removing the `*.joblib` line
> from `.gitignore`, or move to a paid instance with a persistent disk.

---

## Free-tier limits worth knowing before you demo

| Limit | Effect | What to do |
|---|---|---|
| **Sleeps after 15 min idle** | First request takes ~50s, plus retraining | **Open the URL 2 minutes before presenting** |
| **Database deleted after 30 days** | Everything disappears | Note the expiry date |
| **512 MB RAM** | OOM if the dataset is raised | Keep `BOOTSTRAP_SESSIONS` at 40000 |
| **750 instance-hours/month** | Shared across services | Fine for one project |

The sleeping is the one that ruins demos. Hit the URL before you present.

---

## Configuration

Set on `reviveai-api`:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | auto | Injected by Render from the database |
| `BOOTSTRAP_SESSIONS` | `40000` | Dataset size. Raise only on a paid instance |
| `FORCE_BOOTSTRAP` | unset | Set to `1` to rebuild everything on next start |
| `CORS_ORIGINS` | `*` | Credentials auto-disable on wildcard |
| `SEED` | `42` | Deterministic data |
| `PYTHON_VERSION` | `3.12.7` | Locally it runs on 3.14; 3.12 is what Render supports |
| `GROSS_MARGIN` and cost vars | see `render.yaml` | Drive every profit figure |

Set on `reviveai-web`:

| Variable | Notes |
|---|---|
| `VITE_API_BASE` | Backend URL + `/api`. **Inlined at build time** — rebuild after changing |

### Why the database URL just works

Render issues `postgres://...`, which SQLAlchemy 2.0 rejects as an unknown
dialect. `Settings.sqlalchemy_url` rewrites it to `postgresql+psycopg2://`, so
the platform's connection string can be injected unchanged.

---

## Dataset size and model quality

Smaller data means weaker models. Measured on the same seed:

| Model | 100,000 sessions | 20,000 sessions |
|---|---|---|
| abandonment | 0.766 | 0.700 |
| recovery | 0.695 | 0.634 |
| return_risk | 0.694 | 0.674 |
| rto_risk | **0.926** | **0.781** |
| sentiment_clf | 78.6% | 77.7% |

RTO suffers most. The default of 40,000 roughly halves that gap while using
about 130 MB — well inside the 1 GB database, and safely inside 512 MB of RAM
(peak generation memory measured at 155 MB).

---

## Troubleshooting

**Frontend loads but every panel errors.** `VITE_API_BASE` is wrong or was set
without a rebuild. Check it ends in `/api`, then **Manual Deploy**.

**Blank page on refresh at `/dashboard`.** The SPA rewrite is missing. It is in
`render.yaml`; confirm the static site shows a rewrite from `/*` to
`/index.html`.

**Backend won't start.** Open its logs and look for the `[bootstrap]` lines —
they name the stage that failed.

**"Model has not been trained" (503).** Training failed, most likely OOM. Lower
`BOOTSTRAP_SESSIONS` to `20000` and redeploy.

**First request hangs ~50s.** Normal: the instance is waking. Not a bug.

---

## Local alternative

Nothing here changes local development. `.env` still drives it, and the Vite
proxy still forwards `/api` to `127.0.0.1:8000`, so `VITE_API_BASE` stays unset
locally.
