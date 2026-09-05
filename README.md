# ReviveAI

**Recover lost revenue. Protect future revenue. Listen to customers.**

An AI revenue intelligence platform for e-commerce. It predicts where a store is
leaking money, explains *why* in plain terms, and then does the part most tools
skip: works out whether acting is worth more than it costs.

### Live demo

| | |
|---|---|
| **Application** | **https://reviveai-web.onrender.com** |
| API | https://reviveai-api.onrender.com |
| Interactive API docs | https://reviveai-api.onrender.com/docs |
| Health check | https://reviveai-api.onrender.com/api/health |

> **First load takes ~50 seconds.** The free Render instance sleeps after 15
> minutes of inactivity and has to wake up. It is not broken — give it a moment.
> If you are demoing, open the link a couple of minutes beforehand.

The deployed instance runs on 40,000 synthetic checkout sessions (the local
setup below generates 100,000), so its model scores are slightly lower than the
figures in the table further down. Live scores are always visible at
`/api/models/metrics` and on the Model Insights page.

> **Demo data is synthetic.** Model performance and financial figures are
> simulated and should not be read as production results. Every API response
> carries this disclosure.

---

## What problem it solves

An online store leaks money in three places, and this handles all three as one
system rather than three dashboards:

| Pillar | The leak | What ReviveAI does |
|---|---|---|
| **Recover** | Customers fill a cart, then leave | Predicts who will abandon, diagnoses why, and picks the outreach that actually pays for itself |
| **Protect** | Goods come back, or never get delivered | Scores return and RTO risk at order placement, while prevention is still possible |
| **Listen** | 54,000 reviews contain the reasons for both, and nobody reads them | Reads every review and turns the findings into ranked business actions |

The three are wired together. Review complaints are not a side panel — they are
**input features to the return-risk model**, so what customers write moves the
risk score directly.

---

## The core idea: profit, not conversion

Most tools optimise for conversion. That is usually the wrong target.

A ₹80,000 cart, three options:

```
Do nothing        12% recovery
Send a reminder   19% recovery
10% discount      31% recovery   ← wins on conversion
```

The discount wins on conversion and often loses on profit, because it is paid to
everyone who redeems it — including customers who would have bought anyway. So
the engine prices the **uplift over doing nothing**:

```
uplift        = 31% − 12% = 19 points
extra sales   = ₹80,000 × 0.19          = ₹15,200
gross profit  = ₹15,200 × 35% margin    = ₹5,320

discount cost = ₹80,000 × 10% × 31%     = ₹2,480   ← charged on p(action), not uplift
outreach cost = ₹0.25

expected profit = ₹2,840      ROI = 114%
```

All seven actions are priced this way and shown side by side, so you can see what
was rejected and why.

---

## Stack

**Backend** — Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 18 · Alembic
**ML/NLP** — scikit-learn 1.9 · SHAP · VADER · pandas 3.0 · NumPy 2.4
**Frontend** — React 18 · Vite 5 · React Router 6 · Recharts 2

| | |
|---|---|
| Database | 22 tables, ~728,000 rows |
| API | 27 endpoints |
| Frontend | 14 pages |
| Models | 6 (4 supervised, 1 unsupervised, 1 NLP) |
| Code | ~11,300 lines |

---

## Models

Trained on synthetic data, evaluated on a held-out **later** time period:

| Model | Predicts | ROC-AUC | PR-AUC |
|---|---|---|---|
| `abandonment` | Will this checkout be abandoned? | 0.7656 | 0.5435 |
| `recovery` | Will this action win the cart back? | 0.6948 | 0.6777 |
| `return_risk` | Will this order be returned? | 0.6939 | 0.3765 |
| `rto_risk` | Will this shipment come back undelivered? | 0.9261 | 0.8514 |
| `sentiment_clf` | Review sentiment | 78.6% accuracy | 0.741 macro-F1 |
| `anomaly` | Unusual behaviour | unsupervised | 3.0% flagged |

RTO scores highest because cash-on-delivery is a dominant signal. Returns are
genuinely hard to predict — they depend partly on customer mood, which no feature
captures.

### Where the predictions come from

The data is a **causal simulation**, not random numbers. Hidden traits — customer
price sensitivity, product size accuracy, courier reliability — drive the
outcomes, and are never stored in the database. The models must infer the pattern
from observable features, exactly as they would with real data. The signal is
verifiable:

| Condition | Rate |
|---|---|
| Shipping > 15% of cart | **37.9%** abandonment |
| Shipping < 3% of cart | 25.9% abandonment |
| Payment failed | **62.9%** abandonment |
| COD order | **31.7%** RTO |
| Prepaid order | 12.0% RTO |

### No target leakage

Three defences, enforced in code:

1. **A forbidden-feature list checked before every fit** (`ml/leakage.py`). A leaky
   feature set raises and no model artifact is written.
2. **Time-based splits** — oldest 80% trains, newest 20% tests. A random split
   would let a model train on a customer's later behaviour and be tested on their
   earlier behaviour.
3. **As-of joins** — an order from March sees only reviews written before March,
   via `pandas.merge_asof`. Later reviews can never leak into earlier predictions.

### Every prediction is explained

SHAP produces per-feature contributions for the specific row being scored — not
a hardcoded list:

```
Return risk 55.9%  — why?
  Product has sizes      INCREASES  40%
  Previous return rate   INCREASES  27%
  Product rating         INCREASES   9%
```

---

## Deploying your own

`render.yaml` provisions the database, backend and frontend together on
Render's free tier. Connect the repository as a Blueprint and it builds all
three; `docs/DEPLOYMENT.md` covers the one manual step and the free-tier limits
that matter for a demo.

## Running it locally

**Requires:** Python 3.11+, Node 18+, PostgreSQL 14+ running locally.

```bash
# 1. Backend dependencies
cd backend
pip install -r requirements.txt

# 2. Database credentials — prompts for your password with hidden input,
#    URL-encodes it, writes .env, and tests the connection
python scripts/set_db_url.py

# 3. Create the database and its 22 tables
python scripts/init_db.py
alembic upgrade head

# 4. Generate ~728,000 rows of synthetic data      (~10s)
python scripts/generate_data.py --reset

# 5. Analyse all 54,115 reviews                    (~72s)
python scripts/analyze_reviews.py

# 6. Train all six models                          (~6s)
python scripts/train_models.py

# 7. Frontend dependencies
cd ../frontend
npm install
```

> **Order matters.** Step 5 must run before step 6 — the return model joins each
> product's review signals as of the order date, so those signals must exist
> before training.

### Running it

Two terminals:

```bash
# Terminal 1 — API on :8000
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# Terminal 2 — UI on :5173
cd frontend
npm run dev
```

| URL | What |
|---|---|
| http://localhost:5173 | The application |
| http://127.0.0.1:8000/docs | Interactive API documentation |
| http://127.0.0.1:8000/api/health | System status |

The frontend calls a relative `/api` path, which Vite proxies to the backend — so
requests are same-origin and no CORS is involved in development.

---

## Project layout

```
backend/
  app/          FastAPI — 22 models, Pydantic schemas, 27 endpoints
  ml/
    leakage.py       target-leakage guard
    datasets.py      point-in-time training sets
    recovery/        abandonment, recovery, reason engine
    protection/      return, RTO, hybrid anomaly detection
    nlp/             7-file Voice of Customer pipeline
    explainability/  SHAP explainer
    decision/        decision engine + profit optimizer
  scripts/      data generation, review analysis, training
  alembic/      database migrations

frontend/src/
  api/          single client for every network call
  components/   Panel, Stat, Risk, LedgerStrip, Contributions
  pages/        14 screens
  styles/       design tokens

docs/
  ReviveAI_Complete_Documentation.docx   full deep-study guide (Hinglish)
  build_doc.js                           regenerates it
```

---

## How the NLP works

One review, six stages:

> *"The product quality is good but delivery took 8 days. Packaging was damaged.
> Please improve delivery speed."*

```
PRODUCT_QUALITY  →  POSITIVE
DELIVERY         →  NEGATIVE
PACKAGING        →  NEGATIVE
Overall          →  MIXED
Suggestion       →  "Improve delivery speed"
```

The review is split into clauses first, so a single sentence can praise quality
and criticise delivery at the same time. VADER supplies base sentiment; a layer
of ~40 commerce phrase rules covers what a general lexicon misses — *"took 8
days"* has no opinion words but is obviously a complaint. A request never reads
as praise: any clause containing *please* / *you should* / *I suggest* is capped
at negative, because asking for an improvement means the current state is
lacking.

Suggestions require an explicit request pattern, so a complaint alone never
becomes a fabricated demand.

---

## Honest limitations

- **Data is synthetic.** Metrics describe performance on simulated data.
- **Protection effectiveness is assumed, not learned.** There is no history of
  protection interventions to learn an uplift from, so figures like "order
  confirmation cuts RTO by 35%" are stated planning assumptions. The API tags
  these `ASSUMED` and the UI shows a badge; recovery uplift is tagged `LEARNED`.
- **No automated tests yet.** Everything has been verified by hand.
- **No authentication.** Local development only.
- **The feedback loop is one-way.** Outcomes are recorded but do not yet retrain
  the models.

---

## Documentation

`docs/ReviveAI_Complete_Documentation.docx` — an 18-section deep-study guide in
Hinglish covering every technology, the causal data generator with its actual
equations, the full NLP trace, all 27 endpoints, the bugs found during
development, and viva questions with answers.

`docs/DEPLOYMENT.md` — deploying to Render, the free-tier limits worth knowing
before a demo, and troubleshooting.
