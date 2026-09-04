/**
 * ReviveAI — complete project documentation (Hinglish) as a Word document.
 *
 * Run: node build_doc.js
 * Out: ReviveAI_Complete_Documentation.docx
 */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, TableOfContents, LevelFormat, convertInchesToTwip,
} = require("docx");

// ---------------------------------------------------------------- palette
const INK = "14181D";
const GREEN = "0B6B52";   // viridian  — retained / correct
const RUST = "C25A2B";    // oxide     — leaking / warning
const BRASS = "A8801F";   // watch
const SLATE = "33414F";   // structure
const MUTED = "5C6570";
const CODEBG = "F2F1EC";
const HEADBG = "E7EAE8";

const BODY = "Calibri";
const HEAD = "Segoe UI";
const MONO = "Consolas";

const TABLE_W = 9000;

// ---------------------------------------------------------------- helpers
const kids = [];
const push = (...x) => kids.push(...x);

function h1(text, num) {
  push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 420, after: 160 },
    children: [
      new TextRun({ text: num ? `${num}.  ` : "", font: HEAD, size: 30, bold: true, color: RUST }),
      new TextRun({ text, font: HEAD, size: 30, bold: true, color: GREEN }),
    ],
  }));
}

function h2(text) {
  push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 110 },
    children: [new TextRun({ text, font: HEAD, size: 24, bold: true, color: SLATE })],
  }));
}

function h3(text) {
  push(new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: HEAD, size: 21, bold: true, color: INK })],
  }));
}

/** Body paragraph. Pass an array of {t, b, i, c, mono} for mixed formatting. */
function p(content, opts = {}) {
  const runs = (typeof content === "string" ? [{ t: content }] : content).map(
    (r) => new TextRun({
      text: r.t,
      bold: !!r.b,
      italics: !!r.i,
      font: r.mono ? MONO : BODY,
      size: r.mono ? 19 : 21,
      color: r.c || INK,
    }),
  );
  push(new Paragraph({
    spacing: { after: opts.after ?? 130, line: 290 },
    indent: opts.indent ? { left: convertInchesToTwip(0.25) } : undefined,
    children: runs,
  }));
}

function bullets(items, ref = "bullets") {
  items.forEach((it) => {
    const content = typeof it === "string" ? [{ t: it }] : it;
    push(new Paragraph({
      numbering: { reference: ref, level: 0 },
      spacing: { after: 70, line: 280 },
      children: content.map((r) => new TextRun({
        text: r.t, bold: !!r.b, italics: !!r.i,
        font: r.mono ? MONO : BODY, size: r.mono ? 19 : 21, color: r.c || INK,
      })),
    }));
  });
}

/** Monospace block with light shading. Each line is its own paragraph. */
function code(lines, opts = {}) {
  const arr = Array.isArray(lines) ? lines : lines.split("\n");
  arr.forEach((ln, i) => {
    push(new Paragraph({
      shading: { type: ShadingType.CLEAR, fill: opts.fill || CODEBG },
      spacing: { before: i === 0 ? 90 : 0, after: i === arr.length - 1 ? 150 : 0, line: 250 },
      indent: { left: convertInchesToTwip(0.14), right: convertInchesToTwip(0.1) },
      border: {
        left: { style: BorderStyle.SINGLE, size: 12, color: opts.accent || GREEN, space: 6 },
      },
      children: [new TextRun({ text: ln || " ", font: MONO, size: 18, color: opts.color || INK })],
    }));
  });
}

/** Callout box for warnings / key insights. */
function note(title, body, color = BRASS) {
  push(new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: "FAF6EC" },
    spacing: { before: 130, after: 0, line: 280 },
    indent: { left: convertInchesToTwip(0.12), right: convertInchesToTwip(0.1) },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color, space: 8 } },
    children: [new TextRun({ text: title, font: HEAD, size: 20, bold: true, color })],
  }));
  push(new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: "FAF6EC" },
    spacing: { before: 0, after: 170, line: 280 },
    indent: { left: convertInchesToTwip(0.12), right: convertInchesToTwip(0.1) },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color, space: 8 } },
    children: [new TextRun({ text: body, font: BODY, size: 20, color: INK })],
  }));
}

function cell(text, w, o = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({
      alignment: o.align || AlignmentType.LEFT,
      spacing: { after: 0, line: 250 },
      children: [new TextRun({
        text: String(text),
        bold: !!o.b, font: o.mono ? MONO : BODY,
        size: o.mono ? 17 : 19, color: o.c || INK,
      })],
    })],
  });
}

/** rows[0] is the header. widths must sum to TABLE_W. */
function table(rows, widths, opts = {}) {
  const trs = rows.map((r, ri) => new TableRow({
    tableHeader: ri === 0,
    children: r.map((c, ci) => {
      const spec = typeof c === "object" && c !== null ? c : { t: c };
      return cell(spec.t, widths[ci], {
        b: ri === 0 || spec.b,
        fill: ri === 0 ? HEADBG : spec.fill,
        c: ri === 0 ? SLATE : spec.c,
        mono: ri === 0 ? false : (opts.mono?.includes(ci) || spec.mono),
        align: opts.right?.includes(ci) ? AlignmentType.RIGHT : undefined,
      });
    }),
  }));
  push(new Table({
    columnWidths: widths,
    width: { size: TABLE_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "C9CCC8" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "C9CCC8" },
      left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "DDE0DC" },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
    },
    rows: trs,
  }));
  push(new Paragraph({ spacing: { after: 170 }, children: [] }));
}

function pagebreak() {
  push(new Paragraph({ children: [new PageBreak()] }));
}

function rule() {
  push(new Paragraph({
    spacing: { before: 60, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "D6D9D4" } },
    children: [],
  }));
}

// ================================================================ COVER
push(new Paragraph({ spacing: { before: 2100, after: 0 }, children: [
  new TextRun({ text: "REVIVE", font: HEAD, size: 76, bold: true, color: INK }),
  new TextRun({ text: "AI", font: HEAD, size: 76, bold: true, color: GREEN }),
]}));
push(new Paragraph({ spacing: { after: 260 }, children: [new TextRun({
  text: "Recover Lost Revenue.  Protect Future Revenue.  Listen to Customers.",
  font: HEAD, size: 23, color: MUTED })]}));
push(new Paragraph({
  spacing: { after: 120 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 14, color: GREEN } },
  children: [],
}));
push(new Paragraph({ spacing: { before: 200, after: 90 }, children: [new TextRun({
  text: "Complete Project Documentation", font: HEAD, size: 34, bold: true, color: SLATE })]}));
push(new Paragraph({ spacing: { after: 400 }, children: [new TextRun({
  text: "Deep-study guide  ·  Hinglish  ·  Har ek technology explained",
  font: BODY, size: 22, color: RUST })]}));

table([
  ["Field", "Detail"],
  ["Project type", "AI Revenue Intelligence Platform (E-commerce)"],
  ["Backend", "Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL 18"],
  ["Frontend", "React 18 · Vite 5 · React Router 6 · Recharts 2"],
  ["ML / NLP", "scikit-learn 1.9 · SHAP · VADER · pandas 3.0 · NumPy 2.4"],
  ["Database size", "22 tables · ~728,000 rows"],
  ["Code size", "~11,300 lines (8,000 backend + 3,300 frontend)"],
  ["API endpoints", "27"],
  ["Frontend pages", "14"],
  ["ML models", "6 (4 supervised + 1 unsupervised + 1 NLP)"],
  ["Data", "Synthetic (causally simulated)"],
], [2400, 6600]);

push(new Paragraph({ spacing: { before: 260 }, children: [new TextRun({
  text: "Note: Is project ka data synthetic hai. Saare model scores aur financial figures "
      + "simulated data par based hain — inhe production performance mat samajhna.",
  font: BODY, size: 18, italics: true, color: MUTED })]}));

pagebreak();

// ================================================================ TOC
push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({
  text: "Table of Contents", font: HEAD, size: 32, bold: true, color: GREEN })]}));
push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-3" }));
push(new Paragraph({ spacing: { before: 200 }, children: [new TextRun({
  text: "(Word mein kholne ke baad: Ctrl+A dabao, phir F9 — TOC page numbers ke saath update ho jayega.)",
  font: BODY, size: 18, italics: true, color: MUTED })]}));

pagebreak();

// ================================================================ 1
h1("Project Kya Hai", 1);

p("ReviveAI ek AI-powered revenue intelligence platform hai jo online store ke liye banaya gaya hai. "
+ "Iska basic idea simple hai: ek e-commerce business teen jagah paisa leak karta hai, aur yeh platform "
+ "teeno ko ek saath handle karta hai.");

h2("Teen Pillars — teeno leak points");

table([
  ["Pillar", "Problem", "Kya karta hai"],
  ["RECOVER", "Sale se pehle: customer cart bharta hai, phir chala jaata hai (checkout abandonment)",
   "Predict karta hai kaun chhodega, kyun chhodega, aur use wapas laane ke liye kya bhejna chahiye"],
  ["PROTECT", "Sale ke baad: product wapas aa jaata hai (return) ya deliver hi nahi hota (RTO)",
   "Order place hote hi risk predict karta hai, taaki prevention possible ho"],
  ["LISTEN", "Customer reviews mein upar wale dono ke reasons likhe hote hain — par 54,000 reviews koi nahi padhta",
   "Har review ko NLP se padhta hai aur usse business action banata hai"],
], [1500, 3400, 4100]);

h2("Sabse important baat — yeh sirf dashboard nahi hai");

p([{ t: "Zyada tar tools sirf prediction dete hain: \"is customer ka abandonment risk 82% hai\". "
       + "Lekin seller ke liye woh number akela useless hai. Asli sawaal yeh hai: " },
   { t: "kya kuch karne se profit hoga, ya ulta nuksaan?", b: true }]);

p("ReviveAI is sawaal ka jawab deta hai. Har possible action ki cost aur expected profit calculate karta hai, "
+ "aur wahi action recommend karta hai jisme maximum incremental profit ho — sirf maximum conversion nahi. "
+ "Yeh difference is project ka core hai, aur Section 10 mein detail mein samjhaya gaya hai.");

note("Ek line mein",
"DETECT (problem dhoondo) → UNDERSTAND (kyun hua samjho) → PREDICT (aage kya hoga) → "
+ "EXPLAIN (kaaran batao) → DECIDE (kya karna hai) → ACT (karo) → MEASURE (result naapo) → LEARN.",
GREEN);

pagebreak();

// ================================================================ 2
h1("Complete Technology Stack — Har Ek Cheez", 2);

p("Neeche har technology, library aur tool listed hai jo is project mein use hui hai, "
+ "aur ye bhi ki wo kyun chuni gayi.");

h2("2.1  Backend — Core");

table([
  ["Technology", "Version", "Kaam kya hai", "Kyun yahi"],
  ["Python", "3.14.3", "Poori backend language", "ML/NLP ecosystem sabse strong Python mein hai"],
  ["FastAPI", "0.138", "Web framework — 27 API endpoints banata hai", "Async, tez, aur automatic API docs (/docs) deta hai"],
  ["Uvicorn", "0.49", "ASGI server — FastAPI ko actually run karta hai", "FastAPI ka standard server; --reload se auto-restart"],
  ["Pydantic", "2.x", "Request/response validation", "Galat data code tak pahunchne se pehle hi reject"],
  ["pydantic-settings", "2.14", ".env file se config padhta hai", "Password kabhi code mein hardcode na ho"],
], [1700, 900, 3200, 3200]);

h2("2.2  Database Layer");

table([
  ["Technology", "Version", "Kaam kya hai", "Kyun yahi"],
  ["PostgreSQL", "18.1", "Main database — saara data yahan", "Complex aggregation aur window functions support karta hai"],
  ["SQLAlchemy", "2.0.51", "ORM — Python classes ko tables se jodta hai", "Tables Python mein define hote hain, SQL injection se safe"],
  ["psycopg2-binary", "2.9.11", "PostgreSQL driver", "Python aur Postgres ke beech ka actual connector"],
  ["Alembic", "1.19", "Database migrations (version control)", "Schema reproducible rehta hai, manual CREATE TABLE nahi"],
], [1700, 900, 3200, 3200]);

h2("2.3  Machine Learning");

table([
  ["Technology", "Version", "Kaam kya hai", "Kyun yahi"],
  ["scikit-learn", "1.9.0", "4 classification models + IsolationForest + TF-IDF", "Tabular data ke liye industry standard"],
  ["SHAP", "0.52", "Har prediction ka explanation deta hai", "Game theory based — mathematically fair attribution"],
  ["pandas", "3.0.2", "Data ko table form mein handle karta hai", "merge_asof jaise time-aware joins ke liye zaroori"],
  ["NumPy", "2.4.4", "Numerical calculations", "pandas aur sklearn dono iske upar bane hain"],
  ["joblib", "1.5.3", "Trained models ko file mein save karta hai", "Model ek baar train ho, baar baar use ho"],
  ["XGBoost", "3.4.1", "Installed hai (alternative gradient boosting)", "Abhi HistGradientBoosting use ho raha hai"],
], [1700, 900, 3200, 3200]);

h2("2.4  NLP (Natural Language Processing)");

table([
  ["Technology", "Version", "Kaam kya hai", "Kyun yahi"],
  ["vaderSentiment", "3.3.2", "Rule-based sentiment scoring", "Bina training data ke kaam karta hai, fully explainable"],
  ["TfidfVectorizer", "sklearn", "Text ko numbers mein convert karta hai", "Sentiment classifier ka input banata hai"],
  ["LogisticRegression", "sklearn", "Rating-supervised sentiment classifier", "Simple, tez, aur interpretable"],
  ["re (regex)", "built-in", "Aspect detection + suggestion patterns", "Domain rules ke liye precise control"],
], [1700, 900, 3200, 3200]);

h2("2.5  Frontend");

table([
  ["Technology", "Version", "Kaam kya hai", "Kyun yahi"],
  ["React", "18.3", "Poora UI banata hai", "Component-based, industry standard"],
  ["Vite", "5.4", "Dev server + build tool", "Bahut tez, aur API proxy built-in"],
  ["React Router", "6.26", "14 pages ke beech navigation", "Single-page app routing"],
  ["Recharts", "2.15", "Saare charts (line, bar, pie, diverging)", "React ke liye bana hai, SVG based"],
  ["Google Fonts", "—", "Archivo, Public Sans, JetBrains Mono", "Design system ka type pairing"],
  ["Plain CSS", "—", "1,148 lines ka design token system", "Koi CSS framework nahi — full control"],
], [1700, 900, 3200, 3200]);

h2("2.6  Testing & Tools");

table([
  ["Technology", "Kaam kya hai", "Status"],
  ["pytest", "Python test framework", "Installed hai, tests abhi likhe nahi gaye"],
  ["httpx", "API testing ke liye HTTP client", "Installed"],
  ["Git", "Version control", "4 commits ho chuke hain"],
  ["python-dotenv", ".env file load karta hai", "Use ho raha hai"],
  ["python-multipart", "CSV file upload handle karta hai", "Bulk review upload ke liye"],
], [2200, 4200, 2600]);

note("Jo use NAHI kiya, aur kyun",
"Transformers / BERT: Python 3.14 par heavy hai aur 54,000 reviews par slow. VADER + domain rules "
+ "se 1,292 reviews/second speed mili aur poora explainable bhi raha. "
+ "Deep learning (PyTorch/TensorFlow): tabular data par gradient boosted trees generally better perform "
+ "karte hain, seconds mein train hote hain, aur SHAP se exactly explain ho jaate hain.");

pagebreak();

// ================================================================ 3
h1("Folder Structure — Kaunsi File Kya Karti Hai", 3);

code([
"G:\\cl razor\\",
"|",
"+-- backend\\                      (Python — 8,000 lines)",
"|   +-- app\\                      WEB SERVER (API layer)",
"|   |   +-- main.py                FastAPI app + error handling",
"|   |   +-- config.py              .env se settings padhta hai",
"|   |   +-- db.py                  Database connection + session",
"|   |   +-- deps.py                Model store singleton (cache)",
"|   |   +-- models\\               22 SQLAlchemy tables (5 files)",
"|   |   +-- schemas\\              Pydantic validation (4 files)",
"|   |   +-- routers\\              27 API endpoints (8 files)",
"|   |",
"|   +-- ml\\                       DIMAAG (brains) — 2,900 lines",
"|   |   +-- leakage.py             Cheating rokne ka guard",
"|   |   +-- datasets.py            Training data banata hai",
"|   |   +-- common.py              Model save/load + metrics",
"|   |   +-- pipeline_builder.py    sklearn pipeline banata hai",
"|   |   +-- recovery\\             Abandonment + recovery + reason",
"|   |   +-- protection\\           Return + RTO + anomaly",
"|   |   +-- nlp\\                  7 files — poora NLP engine",
"|   |   +-- explainability\\       SHAP explainer",
"|   |   +-- decision\\             Decision engine + profit math",
"|   |",
"|   +-- scripts\\                  DATA + TRAINING — 2,000 lines",
"|   |   +-- init_db.py             Database create karta hai",
"|   |   +-- set_db_url.py          Password safely .env mein daalta hai",
"|   |   +-- generate_data.py       728,000 rows ka synthetic data",
"|   |   +-- review_text.py         Realistic review text banata hai",
"|   |   +-- analyze_reviews.py     54,115 reviews par NLP chalata hai",
"|   |   +-- train_models.py        6 models train karta hai",
"|   |",
"|   +-- alembic\\                  Database migrations",
"|   +-- artifacts\\                Trained models (.joblib files)",
"|   +-- tests\\                    (abhi khaali)",
"|",
"+-- frontend\\                     (React — 3,300 lines)",
"|   +-- src\\",
"|       +-- App.jsx                Navigation rail + 14 routes",
"|       +-- api\\client.js         Har network call yahan se",
"|       +-- hooks\\useApi.js       Loading / error / retry logic",
"|       +-- components\\           Reusable UI pieces",
"|       +-- pages\\                14 screens",
"|       +-- styles\\tokens.css     Poora design system",
"|",
"+-- .env                          PASSWORD (git mein NAHI jaata)",
"+-- .env.example                  Template (git mein jaata hai)",
"+-- .gitignore                    .env, node_modules, models ignore",
]);

h2("Data ka flow — kis order mein chalta hai");

code([
"1. init_db.py         ->  database banata hai",
"2. alembic upgrade    ->  22 tables banati hai",
"3. generate_data.py   ->  728,000 rows daalta hai",
"4. analyze_reviews.py ->  reviews padhta hai, signals banata hai",
"5. train_models.py    ->  6 models train karta hai",
"6. uvicorn            ->  API start hoti hai",
"7. npm run dev        ->  frontend start hota hai",
], { accent: RUST });

note("Order zaroori kyun hai",
"Step 4 (reviews) ko step 5 (training) se PEHLE chalana zaroori hai. Kyunki return-risk model "
+ "product ke review signals ko input feature ki tarah use karta hai. Agar reviews analyse nahi hue, "
+ "to wo columns khaali rahenge aur model kamzor ban jayega.", RUST);

pagebreak();

// ================================================================ 4
h1("Database Layer — Neev (Foundation)", 4);

p([{ t: "Location: " }, { t: "backend/app/models/", mono: true },
   { t: "  —  Technology: PostgreSQL 18 + SQLAlchemy 2.0 + Alembic" }]);

h2("4.1  Database kyun, simple file kyun nahi");

p("Dashboard par jo bhi number dikh raha hai, wo us waqt ka live SQL query result hai. "
+ "Jab likha hota hai \"Rs 4.2Cr recovered\", wo actually yeh chal raha hota hai:");
code("SELECT SUM(recovered_revenue) FROM abandoned_carts WHERE recovered = TRUE;");
p("Kuch bhi hardcode nahi hai. Database mein ek row badlo, dashboard turant badal jayega. "
+ "Yahi cheez isse fake demo se alag karti hai.");

h2("4.2  Saari 22 tables — abhi ka actual data");

table([
  ["Table", "Rows", "Kya store karta hai"],
  ["customers", "8,000", "Customer profile + rolling counters (orders, returns, RTO)"],
  ["products", "600", "Catalogue — price, category, size variants hain ya nahi"],
  ["checkout_sessions", "100,000", "HAR checkout attempt — yeh raw material hai"],
  ["abandoned_carts", "25,617", "Jo 25.6% abandon hue, unka diagnosis + outcome"],
  ["orders", "74,383", "Jo successfully convert hue"],
  ["order_items", "74,383", "Order ke andar kaunsa product, kitni quantity"],
  ["payments", "111,856", "Har payment attempt — fail wale bhi"],
  ["interventions", "19,992", "Cart wapas laane ke liye jo outreach bheja gaya"],
  ["conversions", "9,485", "Jo outreach actually kaam kar gaya"],
  ["shipments", "74,383", "Courier, promised vs actual days, RTO flag"],
  ["logistics_events", "160,242", "Picked up -> delivered / failed -> RTO"],
  ["returns", "12,834", "Return + reason (size, quality, damaged...)"],
  ["return_risk_scores", "0", "Scored return risks (API se bharti hai)"],
  ["rto_risk_scores", "0", "Scored RTO risks (API se bharti hai)"],
  ["fraud_events", "2,768", "Detect hui anomalies"],
  ["reviews", "54,115", "Raw review text"],
  ["review_analysis", "54,115", "Har review ka NLP verdict"],
  ["review_aspects", "131,445", "Har review se nikle topics (~2.4 per review)"],
  ["customer_suggestions", "18,149", "\"Please improve X\" type explicit requests"],
  ["seller_recommendations", "48", "Final business actions"],
  ["product_voc_signals", "600", "REVIEWS KA NICHOD — sabse important table"],
  ["model_registry", "12", "Kaunsa model version live hai + uske scores"],
], [2500, 1100, 5400], { right: [1] });

h2("4.3  Sabse important table — product_voc_signals");

p("Yeh table sirf 600 rows ki hai, lekin poore project ka hinge yahi hai. "
+ "Har product ke liye ye 4 numbers store karti hai:");

code([
"size_fit_complaint_rate   = 0.42    <- 42% reviews mein fit ki complaint",
"quality_complaint_rate    = 0.18",
"delivery_complaint_rate   = 0.08",
"packaging_complaint_rate  = 0.05",
]);

p([{ t: "Ye chaaron numbers " }, { t: "return-risk model ke input features", b: true },
   { t: " ban-te hain. Iska matlab: agar customers kisi product ke fit ki shikayat karte hain, "
       + "to us product ka return risk score badh jaata hai — automatically, model ke through. "
       + "Yahi wo cheez hai jo \"Voice of Customer\" ko sirf ek dashboard se badalkar "
       + "actual business impact banati hai." }]);

h2("4.4  Table relationships");

code([
"Customer",
"  |",
"  +-- Orders",
"  |     +-- OrderItems  -->  Products",
"  |     +-- Payments",
"  |     +-- Shipments   -->  LogisticsEvents",
"  |     +-- Returns",
"  |",
"  +-- CheckoutSessions",
"  |     +-- AbandonedCarts",
"  |           +-- Interventions",
"  |                 +-- Conversions",
"  |",
"  +-- Reviews",
"        +-- ReviewAnalysis",
"        +-- ReviewAspects",
"        +-- CustomerSuggestions",
]);

h2("4.5  Database quality — kya kya lagaya gaya hai");

bullets([
  [{ t: "Primary keys: ", b: true }, { t: "har table mein unique id" }],
  [{ t: "Foreign keys: ", b: true }, { t: "orphan rows impossible — order delete ho to uske items bhi jaate hain (CASCADE)" }],
  [{ t: "Indexes: ", b: true }, { t: "har wo column jispar search hota hai (customer_id, dates, status). Inke bina 100,000 rows par query slow ho jaati" }],
  [{ t: "Check constraints: ", b: true }, { t: "database khud galat data reject karta hai — jaise rating 1-5 ke bahar nahi ja sakti, cart_value negative nahi ho sakti" }],
  [{ t: "Timestamps: ", b: true }, { t: "created_at / updated_at har table mein, automatic" }],
]);

note("Integrity verify kiya gaya",
"10 checks chalaye gaye the — orphan foreign keys, out-of-range probabilities, contradictory shipment "
+ "states (jaise RTO hone ke baad bhi delivered_at bhara ho). Sabhi 10 clean nikle, zero problems.", GREEN);

pagebreak();

// ================================================================ 5
h1("Synthetic Data Generator — Predictions Aati Kahan Se Hain", 5);

p([{ t: "Location: " }, { t: "backend/scripts/generate_data.py", mono: true }, { t: " (886 lines)" }]);

note("Yeh section sabse important hai",
"Agar tumse poocha jaaye \"predictions aa kahan se rahi hain?\", to jawab yahin hai. "
+ "Baaki sab isi ke upar khada hai.", RUST);

h2("5.1  Problem kya thi");

p("Tumhare paas real store ka data nahi tha. Aam tareeka hota hai random numbers bana dena. "
+ "Lekin us se system kuch bhi predict nahi kar paata — agar cart_value random hai aur abandoned "
+ "ek coin flip hai, to koi pattern hi nahi hoga. Aise data par trained model ka ROC-AUC ~0.50 aata "
+ "hai, matlab pure guessing.");

h2("5.2  Solution — causal simulation");

p("Maine iske bajaye ek causal simulation banaya. Har simulated customer ko chhupi hui "
+ "personality traits di gayi hain, jo database mein KABHI store nahi hoti:");

code([
"price_sens   = 0.73   # price dekhkar kitna ghabraata hai",
"return_prone = 0.61   # wapas bhejne ki aadat kitni hai",
"rto_prone    = 0.22   # delivery refuse karne ki aadat",
"patience     = 0.31   # kitni der mein bore ho jaata hai",
]);

p("Products ko bhi hidden traits mile — asli quality, asli size_accuracy, fragility. "
+ "Har courier ko asli reliability mili. Phir outcomes in causes se CALCULATE hote hain:");

code([
"z  = -2.05                                 # baseline",
"z += 3.40 * shipping_ratio                 # mehnga shipping -> chala jaayega",
"z += 1.55 * payment_failed                 # card decline -> chala jaayega",
"z += 1.00 * price_sens * log(cart_value)   # price-sensitive + bada cart",
"z -= 0.22 * prior_orders                   # loyal customer rukta hai",
"z += 0.35 * (1 - patience)                 # be-sabr log jaldi jaate hain",
"z += random_noise                          # thoda randomness",
"",
"abandoned = random() < sigmoid(z)          # sigmoid: z ko 0-1 probability banata hai",
], { accent: RUST });

h2("5.3  Yeh kaam kyun karta hai");

p([{ t: "Kyunki hidden traits database mein " }, { t: "kabhi store nahi hote", b: true },
   { t: " — sirf unke observable results store hote hain. Isliye model ko wahi karna padta hai "
       + "jo asli data mein karna padta: visible cheezon se pattern nikalna." }]);

p("Signal actually maujood hai, ye verify kiya ja sakta hai:");

table([
  ["Condition", "Abandonment / RTO rate"],
  [{ t: "Shipping cart ka 15% se zyada" }, { t: "37.9%", b: true, c: RUST }],
  ["Shipping cart ka 3% se kam", "25.9%"],
  [{ t: "Payment fail hua" }, { t: "62.9%", b: true, c: RUST }],
  ["Payment theek tha", "24.3%"],
  [{ t: "COD order" }, { t: "31.7% RTO", b: true, c: RUST }],
  ["Prepaid order", "12.0% RTO"],
], [5400, 3600], { right: [1] });

p([{ t: "Yeh gaps hi signal hain. Model inhe dhoondh leta hai. " },
   { t: "Predictions yahin se aati hain.", b: true, c: GREEN }]);

h2("5.4  Reviews experience se likhe jaate hain");

p("Yeh detail subtle hai lekin bahut zaroori. Review random text nahi hai — wo us particular "
+ "simulated customer ke saath jo hua, usse likha jaata hai:");

code([
"AGAR shipment 3 din late tha        -> review delivery ki complaint karega",
"AGAR product.size_accuracy kam hai  -> review fit ki complaint karega",
"AGAR return ka reason SIZE_FIT tha  -> review pakka fit mention karega",
]);

p("Isliye jab baad mein NLP kehta hai \"is product ke 42% reviews fit ki shikayat karte hain\", "
+ "to wo number sach mein us product ke return hone se correlated hai. "
+ "Reviews → returns ka chain asli hai, banaya hua nahi.");

h2("5.5  Point-in-time correctness");

p("Sessions ko chronological order mein replay kiya jaata hai. Har session ke waqt customer ka "
+ "history snapshot liya jaata hai — prior_order_count, prior_abandonment_count, prior_return_count. "
+ "Iska matlab: March ke session ko April ka data kabhi nahi dikhta. "
+ "Yeh training ke liye zaroori hai, warna model cheat kar jayega (Section 8 dekho).");

h2("5.6  Generated data ke final rates");

table([
  ["Metric", "Value", "Real world se comparison"],
  ["Checkout abandonment", "24.6%", "Industry ~25-30% — realistic"],
  ["Overall RTO rate", "12.2%", "India ~10-15% — realistic"],
  ["COD RTO rate", "31.7%", "COD mein zyada hota hai — sahi"],
  ["Return rate", "17.9%", "Apparel-heavy catalogue ke liye plausible"],
  ["Recovery rate", "46.9%", "Historical policy simulation ka result"],
], [3000, 1500, 4500]);

pagebreak();

// ================================================================ 6
h1("NLP Engine — 54,115 Reviews Padhna", 6);

p([{ t: "Location: " }, { t: "backend/ml/nlp/", mono: true },
   { t: " (7 files, ~1,200 lines)  ·  Speed: 54,115 reviews in 71 seconds" }]);

p("Ek asli review lo:");
code("\"The product quality is good but delivery took 8 days. Packaging was damaged. Please improve delivery speed.\"");

h2("6.1  Step 1 — Clauses mein todo (preprocess.py)");

p("Text ko sentence enders aur connectives par toda jaata hai: . ! ? ; but however although");

code([
"1. \"The product quality is good\"",
"2. \"delivery took 8 days\"",
"3. \"Packaging was damaged\"",
"4. \"Please improve delivery speed\"",
]);

p([{ t: "Todna kyun? ", b: true },
   { t: "Agar poore review ko ek saath score karo to ek dhundhla \"thoda negative\" verdict milega. "
       + "Todne ke baad tum keh sakte ho ki quality ACHHI hai lekin delivery KHARAB — ek hi sentence se." }]);

h2("6.2  Step 2 — Har clause ko score karo (sentiment.py)");

p([{ t: "VADER", b: true }, { t: " use hota hai — ek dictionary jisme har word ka score hai "
   + "(excellent +3.2, damaged -2.2). Sab jodo, -1 se +1 ke beech squash karo." }]);

note("VADER ki problem",
"VADER ko shopping ki samajh nahi hai. \"Delivery took 8 days\" mein koi emotional word nahi hai, "
+ "isliye VADER ise 0.0 (neutral) score karta hai. Lekin ye clearly ek complaint hai.", RUST);

p([{ t: "Isliye maine " }, { t: "phrase_rules.py", mono: true },
   { t: " banaya — 40 commerce-specific patterns:" }]);

code([
"r\"took \\d+ days\"          -> -0.45   # \"took 8 days\"",
"r\"runs (much )?smaller\"    -> -0.45   # \"runs smaller than chart\"",
"r\"doesn'?t match\"          -> -0.50",
"r\"arrived (crushed|torn)\"  -> -0.55",
"r\"true to size\"            -> +0.45",
"r\"value for money\"         -> +0.45",
]);

p([{ t: "Aur ek zaroori rule: " }, { t: "request kabhi tareef nahi hoti.", b: true },
   { t: " \"Please improve delivery\" mein \"improve\" hai (VADER ke liye positive), "
       + "lekin matlab clearly ye hai ki delivery kharab hai. Isliye jis bhi clause mein "
       + "please / you should / I suggest ho, uska score maximum -0.30 par cap kar diya jaata hai." }]);

p("Final scores:");
code([
"\"The product quality is good\"    -> +0.44  positive",
"\"delivery took 8 days\"           -> -0.45  negative",
"\"Packaging was damaged\"          -> -0.99  negative",
"\"Please improve delivery speed\"  -> -0.30  negative (request)",
], { accent: GREEN });

h2("6.3  Step 3 — Clauses ko topics se jodo (aspects.py)");

p("Ek dictionary 9 aspects ke words rakhti hai. Har clause ka score us aspect ko mil jaata hai jise wo mention karta hai:");

code([
"PRODUCT_QUALITY  ->  POSITIVE  (+0.44)",
"DELIVERY         ->  NEGATIVE  (-0.375)   <- clause 2 aur 4 ka average",
"PACKAGING        ->  NEGATIVE  (-0.99)",
]);

p("9 aspects: PRODUCT_QUALITY, PRICE, DELIVERY, PACKAGING, SIZE_FIT, CUSTOMER_SUPPORT, PAYMENT, WEBSITE, RETURNS");

h2("6.4  Step 4 — Suggestions nikalo (suggestions.py)");

p("Sirf tab fire hota hai jab explicit request pattern mile. Sirf complaint kabhi suggestion nahi banti — "
+ "isliye system aisi demand invent nahi kar sakta jo customer ne ki hi nahi:");

code([
"\"Please improve delivery speed\"  ->  \"Improve delivery speed\"   (suggestion mili)",
"\"delivery took 8 days\"           ->  (kuch nahi — complaint hai, request nahi)",
]);

h2("6.5  Step 5 — Overall verdict");

p("Positive aur negative dono clauses maujood → MIXED. Yeh average nahi hai, "
+ "yeh review ke baare mein ek structural fact hai.");

table([
  ["Sentiment", "Kab milta hai"],
  ["POSITIVE", "Document score >= +0.22, koi strong negative clause nahi"],
  ["NEGATIVE", "Document score <= -0.22"],
  ["NEUTRAL", "Beech mein, koi clear polarity nahi"],
  ["MIXED", "Positive AUR negative dono clauses maujood"],
], [2200, 6800]);

h2("6.6  Step 6 — product_voc_signals mein roll up");

p("131,445 aspect rows ko product ke hisaab se group karke wo 4 complaint rates banti hain. "
+ "Yahi ML layer ko handoff hai.");

h2("6.7  Sentiment classifier — dusri opinion");

p([{ t: "Ek TF-IDF + LogisticRegression model bhi train hota hai. Labels " },
   { t: "star rating se", b: true },
   { t: " aate hain (1-2 = NEGATIVE, 3 = NEUTRAL, 4-5 = POSITIVE). Rating ek asli human label hai "
       + "jo review ke saath hi aata hai — isliye ye normal supervised learning hai, koi jugaad nahi." }]);

table([
  ["Metric", "Value"],
  ["Accuracy", "78.57%"],
  ["Macro F1", "0.7410"],
  ["Training rows", "43,292"],
  ["Test rows", "10,823"],
], [4500, 4500], { right: [1] });

pagebreak();

// ================================================================ 7
h1("Machine Learning Models — Prediction Kaise Banti Hai", 7);

h2("7.1  Chhe models");

table([
  ["Model", "Kya predict karta hai", "Features", "Score"],
  ["abandonment", "Ye checkout abandon hoga?", "20", "ROC-AUC 0.766"],
  ["recovery", "Ye action cart wapas layega?", "16", "ROC-AUC 0.695"],
  ["return_risk", "Ye order wapas aayega?", "18", "ROC-AUC 0.694"],
  ["rto_risk", "Ye shipment RTO hoga?", "14", "ROC-AUC 0.926"],
  ["anomaly", "Behaviour unusual hai?", "11", "Unsupervised"],
  ["sentiment_clf", "Positive / negative / neutral?", "text", "78.6% accuracy"],
], [2100, 3600, 1400, 1900], { right: [2] });

h2("7.2  ROC-AUC padhna kaise hai");

p("0.50 = coin flip (bekaar). 1.00 = perfect. 0.766 ka matlab: ek abandoned aur ek completed "
+ "checkout randomly uthao — model 76.6% baar abandoned wale ko zyada score dega. "
+ "RTO ka 0.926 isliye zyada hai kyunki COD ek bahut strong signal hai.");

h2("7.3  Algorithm — Gradient Boosted Trees");

p([{ t: "HistGradientBoostingClassifier", mono: true, b: true },
   { t: " use hua hai. Simple bhasha mein: ek chhota decision tree banao, dekho kahan galti kar raha hai, "
       + "phir dusra tree banao jo un galtiyon ko sudhaare, aisa ~300 baar repeat karo. "
       + "Har tree haan/na sawalon ka set hai (jaise \"kya shipping cart ka 12% se zyada hai?\")." }]);

p("Neural network ke bajaye yeh isliye chuna:");
bullets([
  "Tabular (table wala) data par trees generally better perform karte hain",
  "Seconds mein train ho jaate hain — poora training 6 seconds mein",
  "SHAP inhe exactly explain kar sakta hai — neural net ko utna nahi",
  "Missing values khud handle kar lete hain",
]);

h2("7.4  Training pipeline");

code([
"ColumnTransformer",
"   +-- numeric columns   -> SimpleImputer(median)     # khaali jagah bharo",
"   +-- text columns      -> OneHotEncoder             # text -> 0/1 columns",
"        |",
"        v",
"HistGradientBoostingClassifier",
"   max_iter=300, learning_rate=0.08, early_stopping=True",
]);

p([{ t: "OneHotEncoder kya karta hai: ", b: true },
   { t: "\"payment_method\" mein UPI/CARD/COD ho sakta hai. Model text nahi samajhta, "
       + "isliye ye 3 alag columns bana deta hai — payment_method_UPI, payment_method_CARD, "
       + "payment_method_COD — jinme 0 ya 1 hota hai." }]);

h2("7.5  Prediction ke waqt exactly kya hota hai");

code([
"1. Missing values ke liye defaults bharo",
"2. Derived features banao (shipping / cart = ratio)",
"3. product_voc_signals dekho          <- REVIEWS YAHAN ENTER HOTE HAIN",
"4. Ek row ki table banao, exactly 18 expected columns ke saath",
"5. Preprocessing chalao (model ke saath hi save hui thi)",
"6. 300 trees vote karte hain  ->  0.5588",
"7. 0.5588 -> \"MEDIUM\"  (thresholds: 0.35 / 0.60)",
], { accent: GREEN });

note("Ye number aata kahan se hai",
"0.5588 ek lookup table se nahi aaya, na hi maine koi formula likha. Ye 300 trees ka vote hai, "
+ "jo 50,325 historical orders se seekhe hue patterns par based hai.", GREEN);

h2("7.6  Risk levels");

table([
  ["Probability", "Risk level"],
  ["0.00 - 0.35", "LOW"],
  ["0.35 - 0.60", "MEDIUM"],
  ["0.60 - 1.00", "HIGH"],
], [4500, 4500]);

h2("7.7  Anomaly detection — IsolationForest");

p("Ye unsupervised hai — koi label nahi hai, kyunki data mein \"ye fraud tha\" wala column nahi hai. "
+ "IsolationForest ka idea: outliers ko isolate karna aasaan hota hai. Random cuts lagao; "
+ "jo point kam cuts mein alag ho jaaye, wo anomaly hai.");

p([{ t: "Lekin akela model use nahi hota. " },
   { t: "Hybrid approach hai: business rules + IsolationForest.", b: true }]);

code([
"Rules (explainable):                    Weight",
"  RETURN_RATE_HIGH   (>60% returns)      0.30",
"  RTO_RATE_HIGH      (>50% RTO)          0.30",
"  COD_REFUSAL_PATTERN (2+ refusals)      0.25",
"  ORDER_VELOCITY     (unusual speed)     0.20",
"  WEIGHT_MISMATCH    (declared vs real)  0.30",
"  REPEATED_DELIVERY_FAILURE              0.25",
"",
"Final score = 0.65 * rules + 0.35 * IsolationForest",
]);

note("Ek zaroori design decision",
"Do cheezein alag rakhi gayi hain: CUSTOMER_BEHAVIOR (customer ne kya kiya) aur "
+ "LOGISTICS_OPERATIONAL (shipment kaise handle hua). Weight mismatch warehouse ki galti hai, "
+ "customer ki nahi. In dono ko mila dena hi wo tareeka hai jisse honest customers ko "
+ "courier ki galti ki saza mil jaati hai. Aur kisi cheez ko seedha \"fraud\" nahi kaha jaata — "
+ "sirf \"review karo\" kaha jaata hai.", BRASS);

pagebreak();

// ================================================================ 8
h1("Data Leakage Prevention — Cheating Rokna", 8);

p([{ t: "Location: " }, { t: "backend/ml/leakage.py", mono: true }]);

h2("8.1  Problem kya hai");

p("Ek model galti se bhi brilliant lag sakta hai. Maan lo abandonment predict kar rahe ho aur "
+ "galti se `recovered` column include ho gaya. Model seekh lega: \"agar recovered exists, "
+ "matlab abandon hua tha\" — 99% accuracy! Lekin production mein bilkul bekaar, "
+ "kyunki prediction ke waqt tumhe pata hi nahi hota ki recover hoga ya nahi.");

h2("8.2  Teen defences");

h3("Defence 1 — Hard-coded forbidden list");

code([
"MODEL_FORBIDDEN = {",
"  \"abandonment\": {\"abandoned\", \"recovered\", \"order_value\", \"action\", ...},",
"  \"rto_risk\":    {\"is_rto\", \"actual_days\", \"delivery_attempts\", ...},",
"  \"return_risk\": {\"returned\", \"return_reason\", \"refund_amount\", ...},",
"}",
"",
"assert_no_leakage(features, \"abandonment\")   # violate hua to CRASH",
], { accent: RUST });

p([{ t: "Yeh har training se PEHLE chalta hai. Agar koi leaky feature mila to " },
   { t: "training crash ho jaati hai", b: true },
   { t: " aur model file likhi hi nahi jaati." }]);

h3("Defence 2 — Time-based split");

p("Purane 80% par train, naye 20% par test. Random split se model ek customer ka "
+ "BAAD wala behaviour dekh leta hai aur PEHLE wale par test hota hai — "
+ "isse score achha lagta hai lekin reality mein aisa possible hi nahi hai.");

h3("Defence 3 — As-of joins (sabse subtle)");

p([{ t: "Jab return-risk model March ke ek order par train hota hai, use sirf wo reviews dikhte hain "
       + "jo March se PEHLE likhe gaye the. Ye " },
   { t: "pandas merge_asof", mono: true, b: true },
   { t: " se implement hua hai. Iske bina model ko \"future ki complaints\" pata hoti, "
       + "aur score jhootha achha aata." }]);

h2("8.3  Har model ke liye kya block hai");

table([
  ["Model", "Ye features BLOCKED hain", "Kyun"],
  ["abandonment", "recovered, recovered_revenue, action, order_value",
   "Ye sab abandon hone ke BAAD pata chalte hain"],
  ["rto_risk", "is_rto, actual_days, delivery_attempts, measured_weight",
   "Ye dispatch ke baad ki baatein hain — order place karte waqt pata nahi"],
  ["return_risk", "returned, return_reason, refund_amount",
   "Target khud, aur uske results"],
  ["recovery", "recovered, recovered_at",
   "Sirf target. `action` ALLOWED hai — kyunki wahi to poocha ja raha hai"],
], [1700, 3400, 3900]);

pagebreak();

// ================================================================ 9
h1("XAI — SHAP se Prediction Explain Karna", 9);

p([{ t: "Location: " }, { t: "backend/ml/explainability/explainer.py", mono: true }]);

h2("9.1  Kyun zaroori hai");

p("Sirf probability seller ke liye bekaar hai. Agar system kehta hai \"return risk 81%\", "
+ "seller ka agla sawaal hoga: \"kyun?\" SHAP wahi jawab deta hai.");

h2("9.2  SHAP ka idea");

p("SHAP game theory par based hai (Shapley values). Idea: features ko ek team ke players "
+ "ki tarah socho, aur result ka \"credit\" unke beech fairly baanto. "
+ "Har feature ke liye ye batata hai ki usne is SPECIFIC prediction ko kitna upar ya neeche dhakela.");

h2("9.3  Actual output");

code([
"Return risk 55.9%   -   kyun?",
"",
"  Product has sizes      INCREASES  40%",
"  Previous return rate   INCREASES  27%",
"  Product rating         INCREASES   9%",
], { accent: RUST });

code([
"RTO risk 70.0%   -   kyun?",
"",
"  Previous RTOs          INCREASES  45%",
"  Cash on delivery       INCREASES  28%",
"  Previous RTO rate      INCREASES   9%",
], { accent: RUST });

h2("9.4  Do technical details");

bullets([
  [{ t: "One-hot folding: ", b: true },
   { t: "Model ko category_Apparel, category_Footwear alag columns dikhte hain. "
       + "Maine unhe wapas jod diya, taaki UI mein \"Product category: Apparel\" dikhe, "
       + "internal encoding names nahi." }],
  [{ t: "Har request par compute hota hai: ", b: true },
   { t: "input badlo, explanation badal jayega. Kuch bhi hardcoded nahi hai. "
       + "Same input hamesha same explanation dega (deterministic)." }],
]);

h2("9.5  Global importance — permutation importance");

p("Local explanation (ek prediction) ke alawa, global bhi nikalta hai: "
+ "ek feature ko randomly shuffle karo aur dekho model ka score kitna gir gaya. "
+ "Jitna zyada gira, utna important feature. Ye Model Insights page par dikhta hai.");

pagebreak();

// ================================================================ 10
h1("Decision Engine — Asli Product Yahi Hai", 10);

p([{ t: "Location: " }, { t: "backend/ml/decision/", mono: true }, { t: " (4 files, 730 lines)" }]);

h2("10.1  Wo trap jisme zyada tar tools phans jaate hain");

p("Cart Rs 80,000 ka hai. Recovery chances:");

table([
  ["Action", "Recovery probability"],
  ["Kuch mat karo", "12%"],
  ["Reminder bhejo", "19%"],
  [{ t: "10% discount do", b: true }, { t: "31%  <- sabse zyada conversion!", b: true, c: RUST }],
], [5400, 3600]);

p([{ t: "Agar sirf conversion optimize karo to discount jeet jayega. " },
   { t: "Lekin ye aksar galat jawab hai", b: true, c: RUST },
   { t: " — kyunki discount un sabko dena padta hai jo use redeem karte hain, "
       + "un customers ko bhi jo waise bhi kharid lete." }]);

h2("10.2  Asli calculation");

p([{ t: "Key concept: " }, { t: "uplift", b: true },
   { t: " — kuch na karne se kitna behtar." }]);

code([
"uplift       = 31% - 12%  = 19 percentage points",
"extra sales  = Rs 80,000 x 0.19        = Rs 15,200",
"gross profit = Rs 15,200 x 35% margin  = Rs 5,320",
"",
"Costs:",
"  discount = Rs 80,000 x 10% x 31%  = Rs 2,480   <- p(action) par, uplift par NAHI",
"  outreach = Rs 0.25 (ek SMS)",
"",
"Expected profit = Rs 5,320 - Rs 2,480 = Rs 2,840",
"ROI = 2,840 / 2,480 = 114%",
], { accent: GREEN });

note("Wo x 31% wali line dhyaan se dekho",
"Discount ko uplift (19%) se nahi, balki p(action) (31%) se multiply kiya gaya hai. Ye deliberate hai. "
+ "Agar discount sirf uplift par charge karte, to discounts hamesha zyada acche lagte — "
+ "aur yahi wo galti hai jise rokne ke liye ye optimizer bana hai.", GREEN);

h2("10.3  Saare 7 recovery actions");

table([
  ["Action", "Channel", "Cost", "Discount"],
  ["NO_ACTION", "—", "Rs 0", "—"],
  ["PERSONALIZED_REMINDER", "Email", "Rs 0.50", "—"],
  ["PAYMENT_ASSISTANCE", "WhatsApp", "Rs 0.35", "—"],
  ["FREE_SHIPPING", "Email", "Rs 0.50", "shipping cost"],
  ["DISCOUNT_5", "SMS", "Rs 0.25", "5%"],
  ["DISCOUNT_10", "SMS", "Rs 0.25", "10%"],
  ["TECH_SUPPORT", "Call", "Rs 18.00", "—"],
], [3200, 2000, 1900, 1900]);

h2("10.4  Protection actions");

table([
  ["Action", "RTO kam karta hai", "Return kam karta hai", "Cost"],
  ["ORDER_CONFIRMATION", "35%", "—", "Rs 0.35"],
  ["PAYMENT_CONFIRMATION", "55%", "—", "Rs 0.35"],
  ["MANUAL_REVIEW", "60%", "25%", "Rs 45.00"],
  ["LOGISTICS_REVIEW", "20%", "10%", "Rs 25.00"],
  ["SIZE_RECOMMENDATION", "—", "25%", "Rs 0.50"],
  ["PACKAGING_REVIEW", "—", "30%", "Rs 12.00"],
  ["DELIVERY_ESCALATION", "18%", "8%", "Rs 15.00"],
], [2800, 2200, 2200, 1800]);

h2("10.5  LEARNED vs ASSUMED — honesty ka hissa");

table([
  ["Type", "Kaunsa", "Matlab"],
  [{ t: "LEARNED", b: true, c: GREEN }, "Recovery uplift",
   "Data mein aise carts hain jinhe har action mila — model asli effect estimate karta hai"],
  [{ t: "ASSUMED", b: true, c: BRASS }, "Protection effectiveness",
   "Protection interventions ka koi history nahi hai, isliye \"35% RTO kam hoga\" ek STATED assumption hai"],
], [1600, 2400, 5000]);

p("API dono ko tag karti hai aur UI mein badge dikhta hai. Assumption ko measurement bataana "
+ "is system ki sabse badi be-imaani hoti — isliye clearly alag rakha gaya hai.");

h2("10.6  Reviews decision ko kaise influence karti hain");

code([
"Reviews -> \"Size doesn't match description\"",
"        -> SIZE_FIT aspect NEGATIVE",
"        -> product_voc_signals.size_fit_complaint_rate = 0.42",
"        -> return_risk model ka INPUT feature",
"        -> return probability BADH gayi",
"        -> SIZE_RECOMMENDATION action shortlist mein FORCE hua",
"        -> Seller recommendation: \"Size chart theek karo\"",
], { accent: GREEN });

pagebreak();

// ================================================================ 11
h1("Revenue Simulator", 11);

p([{ t: "Location: " }, { t: "backend/ml/decision/simulator.py", mono: true }]);

p("Yeh pure arithmetic hai — koi model involved nahi, aur jaan boojhkar. Ye business question "
+ "ka jawab deta hai: \"agar recovery rate 18% ho to kitna paisa banega?\" Ye prediction nahi hai.");

h2("11.1  Poora formula");

code([
"abandoned_checkouts = checkout_volume x abandonment_rate",
"revenue_at_risk     = abandoned_checkouts x average_order_value",
"recovered_orders    = abandoned_checkouts x recovery_rate",
"recovered_revenue   = recovered_orders x average_order_value",
"",
"gross_profit        = recovered_revenue x gross_margin",
"discount_cost       = recovered_revenue x discount_rate",
"delivery_cost       = recovered_orders x delivery_cost_per_order",
"outreach_cost       = abandoned_checkouts x intervention_cost   <- SABKO bhejte hain",
"",
"total_cost          = discount + delivery + outreach",
"net_profit          = gross_profit - total_cost",
"roi                 = net_profit / total_cost x 100",
], { accent: GREEN });

note("Outreach cost par dhyaan do",
"Outreach har contact kiye gaye cart par charge hota hai, sirf convert hone waalon par nahi. "
+ "Kyunki asli zindagi mein yahi hota hai — message sabko jaata hai, kharidta koi koi hai.", GREEN);

h2("11.2  Example calculation");

table([
  ["Input", "Value"],
  ["Monthly checkouts", "100,000"],
  ["Average order value", "Rs 2,400"],
  ["Abandonment rate", "30%"],
  ["Recovery rate", "18%"],
  ["Discount", "5%"],
  ["Gross margin", "35%"],
], [5400, 3600], { right: [1] });

table([
  ["Output", "Value"],
  ["Revenue at risk", "Rs 7,20,00,000"],
  ["Recovered revenue", "Rs 1,29,60,000"],
  ["Gross profit", "Rs 45,36,000"],
  ["Total cost", "Rs 9,87,000"],
  [{ t: "Net profit", b: true }, { t: "Rs 35,49,000", b: true, c: GREEN }],
  [{ t: "ROI" }, { t: "359.57%", b: true, c: GREEN }],
], [5400, 3600], { right: [1] });

pagebreak();

// ================================================================ 12
h1("Backend API — 27 Endpoints", 12);

p([{ t: "Location: " }, { t: "backend/app/", mono: true }, { t: "  ·  Framework: FastAPI" }]);

h2("12.1  Architecture");

code([
"app/models/    ->  22 table definitions   (SQLAlchemy)",
"app/schemas/   ->  input/output validation (Pydantic)",
"app/routers/   ->  27 endpoints           (8 files)",
"app/deps.py    ->  model cache (singleton)",
"app/main.py    ->  wiring + error handling + CORS",
]);

h2("12.2  Saare 27 endpoints");

table([
  ["Method", "Endpoint", "Kya karta hai"],
  ["GET", "/api/health", "System status — DB connected? models trained?"],
  ["GET", "/api/models/status", "Kaunse models trained hain"],
  ["GET", "/api/models/metrics", "Har model ke scores + feature list"],
  ["GET", "/api/dashboard", "Main dashboard ke saare KPIs"],
  ["GET", "/api/recovery/overview", "Recovery funnel + trends + reasons"],
  ["POST", "/api/recovery/predict", "Abandonment risk + reason + explanation"],
  ["POST", "/api/recovery/decision", "7 actions compare karke best chunta hai"],
  ["POST", "/api/recovery/intervention", "Bheja gaya action record karta hai"],
  ["GET", "/api/recovery/carts", "Abandoned carts ki list (paginated)"],
  ["GET", "/api/protection/overview", "RTO + returns + courier performance"],
  ["POST", "/api/returns/predict", "Return risk + top factors"],
  ["POST", "/api/rto/predict", "RTO risk + prevention action"],
  ["POST", "/api/fraud/analyze", "Anomaly analysis (rules + model)"],
  ["GET", "/api/protection/anomalies", "Detect hui anomalies ki list"],
  ["POST", "/api/protection/decision", "Protection action chunta hai"],
  ["POST", "/api/reviews/analyze", "Ek review ka poora NLP analysis"],
  ["POST", "/api/reviews/bulk-analyze", "CSV upload — bulk analysis"],
  ["GET", "/api/reviews/insights", "Aggregated VOC metrics"],
  ["GET", "/api/reviews/recommendations", "Seller recommendations"],
  ["GET", "/api/customers", "Customer list (search + filter)"],
  ["GET", "/api/customer/{id}", "Customer 360 — sab kuch"],
  ["GET", "/api/customer/{id}/intelligence", "Teeno risk scores + decisions"],
  ["POST", "/api/decision/next-best-action", "Unified decision endpoint"],
  ["GET", "/api/decision/actions", "Action catalogue + cost model"],
  ["POST", "/api/simulator/calculate", "Revenue simulation"],
  ["GET", "/api/simulator/defaults", "Real data se default values"],
  ["GET", "/", "API info"],
], [1000, 3200, 4800]);

h2("12.3  Pydantic validation");

p("Har request pehle validate hoti hai. Galat data code tak pahunchta hi nahi:");

code([
"cart_value: float = Field(gt=0, le=10_000_000)      # positive hona chahiye",
"rating: int = Field(ge=1, le=5)                     # 1 se 5 ke beech",
"payment_method: Literal[\"UPI\",\"CARD\",\"COD\",...]     # sirf ye values",
]);

p("Galat input par 422 status code + readable message milta hai. Verify kiya gaya 8 cases par — sab sahi.");

h2("12.4  Error handling");

table([
  ["Status", "Kab", "Response"],
  ["422", "Input validation fail", "Kaunsa field galat hai + kyun"],
  ["404", "Customer/product nahi mila", "Clear message"],
  ["503", "Model train nahi hua", "\"Run train_models.py\" ka instruction"],
  ["503", "Database down", "Connection check karne ko bolta hai"],
  ["500", "Unexpected error", "Generic message; detail server log mein"],
], [1200, 3200, 4600]);

note("Model cache — performance ka kaam",
"Models sirf EK BAAR load hote hain (ModelStore singleton in deps.py) aur memory mein rehte hain. "
+ "Agar har request par load karte to har call 30 second leti. Ab ~300ms lagta hai.", GREEN);

pagebreak();

// ================================================================ 13
h1("Frontend — 14 Pages", 13);

p([{ t: "Location: " }, { t: "frontend/src/", mono: true },
   { t: "  ·  React 18 + Vite 5 + Recharts 2" }]);

h2("13.1  Structure");

code([
"api/client.js       ->  har network call yahin se jaati hai",
"hooks/useApi.js     ->  loading / error / retry ek jagah",
"components/         ->  reusable pieces (Panel, Stat, Risk, LedgerStrip...)",
"pages/              ->  14 screens",
"styles/tokens.css   ->  poora design system (1,148 lines)",
]);

h2("13.2  Saare 14 pages");

table([
  ["Route", "Page", "Kya dikhata hai"],
  ["/dashboard", "Revenue intelligence", "Ledger strip, 8 KPIs, 9 charts, recommendations"],
  ["/recovery", "Recovery overview", "Funnel, reasons, worklist, per-cart decision"],
  ["/interventions", "Interventions", "Kya bheja, kya kaam aaya, kitna profit"],
  ["/protection", "Protection overview", "RTO, returns, courier performance"],
  ["/returns", "Return risk", "Order score karo + SHAP factors"],
  ["/rto", "RTO risk", "Order score karo + prevention action"],
  ["/fraud", "Anomalies", "Rules + IsolationForest results"],
  ["/voice-of-customer", "Voice of Customer", "Insights, analyzer, bulk upload, recommendations"],
  ["/ai-decision-center", "AI Decision Center", "Ek customer ke teeno risks + best action"],
  ["/customer-360", "Customer 360", "Ek customer ka poora record, 6 tabs"],
  ["/revenue-simulator", "Revenue simulator", "Sliders + live profit calculation"],
  ["/analytics", "Analytics", "Teeno pillars ka crosswalk"],
  ["/model-insights", "Model insights", "Har model ke metrics + importance"],
  ["/settings", "Settings", "System status + cost model (read-only)"],
], [2300, 2400, 4300]);

h2("13.3  Design system — \"The Ledger\"");

p("Maine ise ek financial instrument ki tarah design kiya, marketing dashboard ki tarah nahi:");

table([
  ["Choice", "Kya", "Kyun"],
  ["Colors", "Viridian #0B6B52, Oxide #C25A2B, Brass #A8801F", "Balance-sheet ki ink — green = bacha, rust = gaya"],
  ["Fonts", "Archivo (headings), Public Sans (body), JetBrains Mono (numbers)", "Mono numbers decimal par align hote hain"],
  ["Shadows", "Bilkul nahi", "Flat instrument look, SaaS card look nahi"],
  ["Corners", "Max 3px radius", "Sharp, precise feel"],
  ["Risk badge", "Left mein colored rule, pill nahi", "Ledger ke margin annotation jaisa"],
], [1500, 3300, 4200]);

h2("13.4  Signature element — Ledger Strip");

p("Dashboard par jo colored band dikhta hai — Completed → Recovered → At Risk → Lost — "
+ "wo proportionally sized hai. Yahi element Decision Center mein profit arithmetic "
+ "dikhane ke liye dobara use hota hai. Ek idea, do jagah, aur poore product ka core "
+ "claim express karta hai: hisaab dikhao.");

h2("13.5  Data screen tak kaise pahunchta hai");

code([
"useApi(() => api.dashboard(180))",
"   |",
"   +-- loading  ->  skeleton shimmer",
"   +-- error    ->  message + \"Try again\" button",
"   +-- success  ->  render",
]);

p("Har page teeno states handle karta hai. Koi bhi page ye assume nahi karta ki call successful hogi.");

h2("13.6  Frontend-backend connection");

p("Frontend relative path `/api` call karta hai, absolute URL nahi. Vite dev server "
+ "us request ko backend tak proxy karta hai:");

code([
"browser  ->  localhost:5173/api/dashboard",
"         ->  Vite proxy",
"         ->  127.0.0.1:8000/api/dashboard",
]);

p("Isse do problems khatam ho jaati hain: CORS ki zaroorat nahi (same origin hai), "
+ "aur frontend ko backend ka port jaanne ki zaroorat nahi.");

pagebreak();

// ================================================================ 14
h1("Complete Request Flow — Ek Click, Poora Safar", 14);

p("Tum AI Decision Center kholte ho aur Customer 1598 par click karte ho. Ye hota hai:");

code([
"1. BROWSER   GET localhost:5173/api/customer/1598/intelligence",
"",
"2. VITE      proxy karke bhejta hai -> 127.0.0.1:8000",
"",
"3. FASTAPI   customer.py router par route karta hai",
"",
"4. SQL       profile nikalo",
"             latest abandoned cart nikalo",
"             latest order nikalo",
"             us product ke review signals nikalo",
"",
"5. ML        abandonment model  ->  43.8%",
"             SHAP explainer     ->  kyun (12 factors)",
"             reason engine      ->  cause + evidence",
"             recovery model     ->  7 actions ek saath score",
"             return model       ->  43.6%   <- voc_size_fit_rate padhta hai",
"             rto model          ->  98.4%",
"",
"6. DECISION  7 recovery actions ki profit calculate karo -> best chuno",
"             protection actions price karo, review signals force karo",
"",
"7. JSON      ek response mein sab kuch",
"",
"8. REACT     render: 3 risk scores, 12 SHAP bars,",
"             profit ledger, 2 comparison tables,",
"             aur chain: Reviews -> Size/Fit -> Return risk -> Action",
], { accent: GREEN });

p([{ t: "Total time: lagbhag 300 milliseconds. Har number us waqt calculate hua.", b: true }]);

pagebreak();

// ================================================================ 15
h1("Setup aur Run Karne Ke Commands", 15);

h2("15.1  Pehli baar setup");

code([
"# 1. Python dependencies",
"cd \"G:\\cl razor\\backend\"",
"pip install -r requirements.txt",
"",
"# 2. Database password .env mein daalo (password chhupa rehta hai)",
"python scripts\\set_db_url.py",
"",
"# 3. Database banao",
"python scripts\\init_db.py",
"",
"# 4. 22 tables banao",
"alembic upgrade head",
"",
"# 5. 728,000 rows ka data banao  (~10 second)",
"python scripts\\generate_data.py --reset",
"",
"# 6. 54,115 reviews analyse karo  (~72 second)",
"python scripts\\analyze_reviews.py",
"",
"# 7. 6 models train karo  (~6 second)",
"python scripts\\train_models.py",
"",
"# 8. Frontend dependencies",
"cd \"G:\\cl razor\\frontend\"",
"npm install",
]);

h2("15.2  Roz chalane ke liye — do terminal");

p("Terminal 1 — Backend:");
code([
"cd \"G:\\cl razor\\backend\"",
"python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload",
], { accent: SLATE });

p("Terminal 2 — Frontend:");
code([
"cd \"G:\\cl razor\\frontend\"",
"npm run dev",
], { accent: SLATE });

p("Phir browser mein kholo:");
table([
  ["URL", "Kya milega"],
  ["http://localhost:5173", "Poora application"],
  ["http://127.0.0.1:8000/docs", "Automatic API documentation (FastAPI)"],
  ["http://127.0.0.1:8000/api/health", "System status check"],
], [3600, 5400]);

h2("15.3  5-minute demo ka flow");

code([
"1. Dashboard          ->  Revenue at risk dikhao (ledger strip)",
"2. Recovery           ->  ek abandoned cart kholo",
"3.                    ->  AI risk predict karta hai",
"4.                    ->  SHAP se KYUN dikhao",
"5.                    ->  7 actions ka comparison table",
"6.                    ->  NEXT BEST ACTION + profit + ROI",
"7. Protection         ->  Return / RTO risk dikhao",
"8. Voice of Customer  ->  ek review analyse karo live",
"9.                    ->  sentiment + aspects + suggestion",
"10.                   ->  seller recommendation + evidence",
"11.                   ->  Reviews -> Return risk ka chain dikhao",
"12. Simulator         ->  recovery rate slider hilao",
"13.                   ->  financial impact live badalta hai",
], { accent: RUST });

pagebreak();

// ================================================================ 16
h1("Jo Bugs Mile Aur Fix Hue", 16);

p("Development ke dauraan 3 asli bugs mile. Ye isliye document kiye hain kyunki "
+ "viva mein ye achha jawab bante hain — aur honesty bhi.");

h2("16.1  SIZE_FIT false positives (sabse serious)");

table([
  ["", ""],
  [{ t: "Kya hua", b: true }, "Electronics products par CRITICAL recommendation aa raha tha: "
   + "\"publish an accurate size chart with garment measurements\" — 816 reviews par, "
   + "un products ke liye jinme size hoti hi nahi"],
  [{ t: "Kyun hua", b: true }, "SIZE_FIT word list mein bare word \"loose\" tha. "
   + "\"the stitching came loose\" (quality defect) aur \"the item was loose inside the box\" (packaging) "
   + "dono ko fit complaint gina ja raha tha"],
  [{ t: "Fix", b: true }, "Bare adjectives (small, large, tight, loose) hata diye. "
   + "Ab sirf clear sizing terms (\"runs small\", \"too tight\", \"size chart\") count hote hain"],
  [{ t: "Result", b: true }, "Electronics par size complaints: 816 -> 0. "
   + "Phir saare reviews dobara analyse kiye aur return model retrain kiya"],
], [1800, 7200]);

h2("16.2  Har custom validator par 500 error");

table([
  ["", ""],
  [{ t: "Kya hua", b: true }, "Khaali review text bhejne par 500 Internal Server Error aata tha, "
   + "422 validation error ke bajaye"],
  [{ t: "Kyun hua", b: true }, "Pydantic v2 jab custom validator ValueError raise karta hai, "
   + "to exception OBJECT ko error dict mein daal deta hai. Use JSON mein convert karte waqt crash ho jaata tha"],
  [{ t: "Fix", b: true }, "Errors ko serialize karne se pehle saaf kiya jaata hai. "
   + "Ab readable message milta hai"],
  [{ t: "Result", b: true }, "8 validation paths test kiye — sab 422 return karte hain ab"],
], [1800, 7200]);

h2("16.3  Frontend-backend connect nahi ho raha tha");

table([
  ["", ""],
  [{ t: "Kya hua", b: true }, "Dono running the, phir bhi \"Could not reach the API\" aa raha tha"],
  [{ t: "Kyun hua", b: true }, "Frontend absolute URL (127.0.0.1:8000) call kar raha tha "
   + "localhost:5173 se — cross-origin. Browser localhost ko IPv6 (::1) resolve karta tha "
   + "jabki backend sirf IPv4 par bind tha. Saath hi Vite chupchaap 5174 par shift ho jaata tha"],
  [{ t: "Fix", b: true }, "Relative /api path + Vite proxy. Ab same-origin hai. "
   + "strictPort:true lagaya taaki port silently na badle"],
], [1800, 7200]);

pagebreak();

// ================================================================ 17
h1("Limitations — Imaandaari Se", 17);

p("Har project ki limitations hoti hain. Inhe chhupana nahi chahiye — "
+ "viva mein khud batana zyada achha impression banata hai.");

table([
  ["Limitation", "Detail"],
  ["Data synthetic hai", "Saare model scores simulated data par hain. Har API response ke saath "
   + "disclosure attach hai — chhupaya nahi gaya"],
  ["Protection effectiveness assumed hai", "\"Order confirmation se 35% RTO kam hoga\" — ye measured nahi, "
   + "stated assumption hai. UI mein ASSUMED badge dikhta hai"],
  ["Tests nahi hain", "Sab kuch manually verify kiya gaya hai. Automated tests abhi nahi likhe — "
   + "matlab future changes ki galti automatically nahi pakdi jayegi"],
  ["Authentication nahi hai", "Local development ke liye bana hai. Production mein login/roles chahiye honge"],
  ["Feedback loop one-way hai", "Outcomes record hote hain lekin abhi models ko dobara train nahi karte"],
  ["Return model ka PR-AUC kam hai", "0.3765 — matlab returns predict karna genuinely mushkil hai, "
   + "kyunki wo customer ke mood par bhi depend karta hai"],
], [2600, 6400]);

pagebreak();

// ================================================================ 18
h1("Viva / Interview Ke Liye Sawaal-Jawaab", 18);

p("Ye wo sawaal hain jo judges ya interviewer poochh sakte hain, aur unke seedhe jawab.");

h3("Q1. Predictions actually aa kahan se rahi hain?");
p("Data ek causal simulation se bana hai jisme hidden traits (price sensitivity, product quality, "
+ "courier reliability) se outcomes calculate hote hain. Ye traits database mein store nahi hote. "
+ "Model ko visible features se pattern nikalna padta hai — bilkul waise hi jaise real data mein. "
+ "Signal verify ho sakta hai: high shipping par abandonment 37.9% vs low shipping par 25.9%.");

h3("Q2. Model ne cheating to nahi ki? (data leakage)");
p("Teen defences hain. Ek: har model ke liye forbidden features ki hard-coded list, jo training se "
+ "pehle check hoti hai aur violate hone par crash kar deti hai. Do: time-based split — purane 80% "
+ "par train, naye 20% par test. Teen: as-of joins — March ke order ko sirf March se pehle ke reviews dikhte hain.");

h3("Q3. Neural network kyun nahi use kiya?");
p("Tabular data par gradient boosted trees generally better perform karte hain, 6 second mein train "
+ "ho jaate hain, missing values khud handle karte hain, aur SHAP unhe exactly explain kar sakta hai. "
+ "Neural net yahan koi advantage nahi deta, sirf complexity badhata.");

h3("Q4. Ye tool baaki dashboards se alag kaise hai?");
p("Baaki tools prediction dete hain. Ye decision deta hai. Har action ki expected profit calculate "
+ "karta hai aur maximum INCREMENTAL PROFIT wala chunta hai, maximum conversion wala nahi. "
+ "10% discount aksar conversion mein jeetta hai lekin profit mein haarta hai, kyunki wo un logon "
+ "ko bhi milta hai jo waise bhi kharidte.");

h3("Q5. Voice of Customer sirf ek alag dashboard to nahi hai?");
p("Nahi. Reviews se nikle complaint rates (size_fit_complaint_rate, quality_complaint_rate) "
+ "return-risk model ke ACTUAL INPUT FEATURES hain. Matlab customer ki shikayat seedha risk score "
+ "badalti hai. Ye integration model ke through hai, side panel se nahi.");

h3("Q6. Sentiment ke liye BERT kyun nahi?");
p("Python 3.14 par transformers heavy hai aur 54,000 reviews par slow hota. VADER + domain phrase "
+ "rules se 1,292 reviews/second mile aur poora explainable raha. Saath mein ek TF-IDF + "
+ "LogisticRegression classifier bhi train kiya jo star ratings se supervised hai — 78.6% accuracy.");

h3("Q7. MIXED sentiment kaise detect karte ho?");
p("Structurally, average se nahi. Review ko clauses mein toda jaata hai. Agar positive aur negative "
+ "dono clauses maujood hain to verdict MIXED hai. Isiliye \"quality achhi hai but delivery slow thi\" "
+ "MIXED aata hai, neutral nahi.");

h3("Q8. Return model ka score sirf 0.69 hai — kam nahi?");
p("Returns genuinely predict karna mushkil hai kyunki wo customer ke mood par bhi depend karta hai, "
+ "jo koi feature capture nahi kar sakta. 0.69 random (0.50) se kaafi behtar hai aur business "
+ "value deta hai — high risk orders par prevention action lagakar. Isse zyada score aata to "
+ "shayad leakage hoti.");

h3("Q9. Agar model train nahi hua to kya hota hai?");
p("API 503 status code deti hai clear message ke saath: \"Run train_models.py\". "
+ "Koi fake prediction return nahi hoti. Ye deliberate design hai.");

h3("Q10. Business impact ke rupee figures kahan se aaye?");
p("Wo forecast nahi hain — database mein already observed loss hai. Jaise SIZE_FIT recommendation "
+ "ke liye: actual returns count karo jinka reason SIZE_FIT tha, aur unhe published cost model se "
+ "multiply karo (reverse logistics + restocking + margin erosion). Har card par \"impact_basis\" "
+ "mein poora calculation likha hota hai.");

rule();

push(new Paragraph({ spacing: { before: 200, after: 100 }, children: [new TextRun({
  text: "Documentation end", font: HEAD, size: 22, bold: true, color: GREEN })]}));
p([{ t: "ReviveAI  ·  Complete Project Documentation  ·  Har technology explained", c: MUTED }]);

// ================================================================ BUILD
const doc = new Document({
  creator: "ReviveAI",
  title: "ReviveAI — Complete Project Documentation",
  description: "Deep-study guide in Hinglish covering every technology used",
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "\u2022",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 460, hanging: 240 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: BODY, size: 21, color: INK } },
    },
  },
  sections: [{
    properties: {
      page: {
        margin: { top: 1200, right: 1300, bottom: 1200, left: 1300 },
      },
    },
    children: kids,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("ReviveAI_Complete_Documentation.docx", buf);
  console.log("Written: ReviveAI_Complete_Documentation.docx");
  console.log("Size:", (buf.length / 1024).toFixed(1), "KB");
  console.log("Paragraphs/tables:", kids.length);
});
