# ClearMatch | AP Control Tower

**An explainable Accounts Payable decision workbench**

ClearMatch turns vendor invoice PDFs into traceable AP decisions. It combines document extraction, field-level evidence, deterministic financial controls, cumulative purchase-order exposure, exception triage and human review.

> **Product principle:** AI can interpret the document. Deterministic finance controls decide what happens next. A human owns exceptions.


**Current release: V4.1.** This is a focused usability refinement: a clearer exception queue, a compact run ledger with responsive table height, PO tolerance headroom, and privacy-safe system diagnostics. The invoice processor, database, and batch-processing service remain unchanged from V4.

This is a case-study MVP using synthetic vendors, purchase orders and invoices. `AUTO-CLEAR` means ready for AP approval; it does not mean paid or released for payment.

## What makes this more than an invoice reader

ClearMatch is designed around the AP team's operating loop, not just the extraction step:

1. **Control tower** — a portfolio view of real recorded decisions, open exceptions and PO exposure signals.
2. **Single and batch intake** — upload one PDF or process up to 10 PDFs in a sequential batch. Every successful file receives its own run ID, decision and audit record. A failure for one file does not cancel the rest.
3. **Field evidence** — each extracted field shows its source, verification state and supporting text snippet. Extraction completeness is not presented as model confidence.
4. **Deterministic decision engine** — required fields, arithmetic, duplicates, PO ownership, PO status, currency consistency and cumulative exposure are evaluated in Python.
5. **Exception desk** — prioritise, inspect and resolve `NEEDS REVIEW` cases. Blocked cases remain visible but cannot be overridden in this MVP.
6. **PO exposure monitor** — compare eligible recorded invoices against PO value plus the PO's configured tolerance. Near-cap signals are visible before they become over-tolerance cases.
7. **Run ledger and exports** — search, filter and export recorded runs and PO exposure as CSV.

All dashboard counts, charts and exposure values are derived from the local SQLite database. No demo-only activity counters are used.

## Workflow

```text
Invoice PDF(s)
    ↓
Document ingestion and integrity checks
    ↓
Embedded PDF text extraction or OCR
    ↓
AI-assisted field extraction (optional)
    ↓
Field-context evidence verification
    ↓
Deterministic fallback for unsupported fields
    ↓
Duplicate screening + PO matching
    ↓
Financial controls + cumulative PO exposure
    ↓
AUTO-CLEAR / NEEDS REVIEW / BLOCKED
    ↓
SQLite decision ledger + retained source PDF
    ↓
Exception review, PO exposure monitoring and CSV exports
```

## Technology

| Layer | Implementation |
|---|---|
| Application UI | Streamlit with custom ClearMatch design system |
| Processing | Python |
| PDF text | PyMuPDF |
| OCR | Tesseract via pytesseract |
| Optional AI extraction | Groq, OpenAI or custom OpenAI-compatible endpoint |
| Decision engine | Deterministic Python rules |
| Data and audit persistence | SQLite |
| Tables and analysis | Pandas |
| Charts | Plotly |

## Local setup — Windows CMD

Python 3.11+ is recommended. The project has previously been exercised with Python 3.13.

```cmd
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Keep the CMD window running while you use the application.

### OCR on Windows

`pytesseract` is a Python wrapper; the Tesseract executable is a separate dependency. Install Tesseract OCR and ensure `tesseract.exe` is on PATH. ClearMatch also checks `C:\Program Files\Tesseract-OCR\tesseract.exe`.

The scanned sample is intended to exercise OCR and contains a deliberately missing invoice date, so the expected final status is `NEEDS REVIEW`.

## Optional AI extraction

ClearMatch operates without an API key using deterministic, field-labelled extraction. To enable AI-assisted extraction, configure one provider locally:

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Add your own API key to the copied file.
3. Restart Streamlit.
4. Open **Policy & system → Run live connection test**.
5. Process an invoice and inspect the `Extraction service` and field provenance in the decision record.

Groq example:

```toml
GROQ_API_KEY = "your-key"
GROQ_MODEL = "llama-3.3-70b-versatile"
```

OpenAI example:

```toml
OPENAI_API_KEY = "your-key"
OPENAI_MODEL = "gpt-4o-mini"
```

Custom OpenAI-compatible endpoint:

```toml
LLM_API_KEY = "your-key"
LLM_BASE_URL = "https://your-provider.example/v1"
LLM_MODEL = "your-model"
LLM_PROVIDER_NAME = "Custom"
```

Provider credentials are never displayed by the UI or the diagnostic script. API billing is separate from a ChatGPT subscription. Never commit `.streamlit/secrets.toml` or include it in a release ZIP.

A configured key is not proof of connectivity. The live connection test and a real invoice extraction run are required to demonstrate successful provider execution. Automated LLM tests use mocked responses and do not prove live API access.

## Product workspace

### 1. Control tower

Shows live counts and charts derived from recorded runs: auto-clear rate, review backlog, blocked invoices, human resolutions, recent decisions and PO exposure signals. Values are not synthetic placeholders.

### 2. Invoice intake

**Single invoice:** choose a bundled sample or upload an actual PDF (maximum 15 MB), then watch the seven processing stages execute. The result includes the source PDF, extracted field cards, provenance, checks and decision rationale.

**Batch intake:** upload up to 10 PDFs with a 50 MB combined limit. Files are processed sequentially. Later files see earlier successful files in the same batch for duplicate and cumulative-exposure checks. A single invalid file is reported as an error without rolling back successful runs. Batch results can be exported as CSV.

### 3. Exception desk

Open `NEEDS REVIEW` and `BLOCKED` cases are separated. Reviewable invoices can be approved or rejected only after entering a reviewer name and rationale. The name is self-declared; this demo does not authenticate identity. Blocked cases are read-only and require the underlying issue to be corrected before resubmission.

### 4. Run ledger

Search and filter recorded invoices by decision and human review status. Open a run to inspect the original document, extracted fields, source evidence, decision controls and extraction diagnostics. Export the filtered ledger as CSV.

### 5. PO exposure monitor

Shows invoice exposure against each PO and its configured tolerance. `WATCH` indicates at least 80% of the allowed exposure cap has been used. `OVER TOLERANCE` indicates the cap has been exceeded. These are portfolio signals, not additional payment decisions.

Exposure includes recorded `AUTO-CLEAR` and `NEEDS REVIEW` invoices whose currency matches the PO, except rejected human reviews. Blocked duplicates and currency-mismatched invoices are excluded. Values remain in native currency; there is no FX conversion.

### 6. Policy & system

Explains decision rules, assumptions and runtime diagnostics. The LLM connection test makes a real provider request only when explicitly clicked. OCR and SQLite status are displayed separately from AI configuration.

## Decision policy and assumptions

- Required fields: vendor, invoice number, invoice date, PO number, subtotal, tax and invoice total.
- Arithmetic: subtotal + tax must reconcile with invoice total within the greater of one currency unit or 1% of invoice total.
- Duplicate detection: exact PDF fingerprint or matching vendor + invoice number already in recorded run history.
- PO ownership: invoice vendor must match the vendor assigned to the referenced PO.
- PO status: only `ACTIVE` purchase orders are eligible for auto-clear.
- Currency: an unambiguous document currency must match the PO currency. No foreign-exchange conversion is performed. An ambiguous or mismatched currency requires review.
- Cumulative exposure: prior eligible invoices plus the current invoice are compared with the PO amount and PO-specific tolerance. A review invoice remains in exposure until rejected by a human; approved review cases continue to count.
- Decision priority: blocking violation → `BLOCKED`; otherwise review condition → `NEEDS REVIEW`; only all configured checks passing → `AUTO-CLEAR`.

These are explicit case-study assumptions. A real deployment would configure thresholds and accounting policies to the customer's procurement and finance controls.

## Synthetic invoice scenarios

The Process Invoice dropdown includes:

| Scenario | Expected result / behaviour |
|---|---|
| Happy path · Northstar | `AUTO-CLEAR` |
| Split invoice · parts 1–3 | First two clear; third requires review due to cumulative exposure |
| Missing invoice date | `NEEDS REVIEW` |
| Closed PO | `BLOCKED` |
| Wrong vendor for PO | `BLOCKED` |
| Arithmetic mismatch | `NEEDS REVIEW` |
| Currency mismatch | `NEEDS REVIEW`; excluded from PO exposure |
| Alternative layout | Tests alternate field labels |
| Table layout | Tests tabular invoice formatting |
| Compact pipe layout | Tests pipe-delimited field formatting |
| Scanned PDF | OCR path; missing date routes to review |

All bundled inputs and PO master data are synthetic. Do not upload confidential supplier documents to this case-study prototype.

## Tests

Run from the project folder:

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers processor decisions, evidence-grounded LLM extraction, API fallback without key leakage, currency policy, layouts, OCR (when Tesseract is installed), review-state rules, database migration, source-PDF retention and sequential batch processing.

The batch tests verify that:
- Split invoices in a batch respect sequence and cumulative exposure.
- An invalid PDF does not stop later files from processing.
- A repeated invoice in the same batch is detected as a duplicate.

## Data, security and limitations

- Local SQLite: `data/clearmatch.db` (created automatically at first launch).
- Retained source PDFs: `data/documents/` (created automatically for new runs).
- These local data paths are excluded from the clean release package and Git.
- `.streamlit/secrets.toml` is excluded from Git; only the example template is included.
- Reviewer identity is self-declared; there is no authentication or role-based permission model.
- Evidence verification checks verbatim text in the expected labelled context. It is not visual bounding-box verification and does not prove the PDF's visual layout semantics.
- Unfamiliar supplier layouts need additional testing. OCR quality depends on scan quality, resolution and language.
- No line-item/PO-receipt three-way match or FX conversion is implemented.
- SQLite is suitable for this local MVP. Public hosting needs durable managed database and document storage, authentication, access controls, retention policies, monitoring and end-to-end deployment tests.
- No public deployment is included in this package.

## Project structure

```text
clearmatch_app/
├── app.py
├── processor.py
├── batch_processing.py
├── database.py
├── requirements.txt
├── packages.txt
├── README.md
├── DEMO_VIDEO_SCRIPT.md
├── CASE_STUDY_SUBMISSION_NOTES.md
├── IMPLEMENTATION_CHANGELOG.md
├── test_llm_connection.py
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── data/
│   └── purchase_orders.csv
├── samples/
│   └── synthetic invoice PDFs
└── tests/
    ├── test_processor.py
    ├── test_llm_extraction.py
    ├── test_review_and_edge_cases.py
    └── test_batch_intake.py
```
