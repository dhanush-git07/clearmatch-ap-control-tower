# ClearMatch V4.1 — Implementation changelog

V4.1 is a targeted refinement on top of V4, not a rewrite.

## Product experience retained from V4
- ClearMatch | AP Control Tower positioning and finance-operations design system.
- Control Tower, Invoice Intake, Exception Desk, Run Ledger, PO Exposure and Policy & System workspaces.
- Sequential batch intake using the same underlying invoice processor and SQLite audit ledger.
- Explainable invoice decisions, source-document preview and field-level provenance.

## V4.1 refinements
- Exception Desk metric terminology now distinguishes unresolved records, actionable reviews, policy-blocked cases and human resolutions.
- Actionable-review empty state explains why blocked records remain separate from human-review work.
- Exception and ledger tables use row-aware heights.
- Run Ledger primary table is narrower, uses a compact processed timestamp, and provides a no-results state.
- Full selected-record detail remains available below the ledger table.
- PO Exposure chart plots only POs with eligible recorded exposure, avoiding large empty chart categories. The full register still lists all POs.
- PO register adds remaining tolerance headroom.
- Policy & System hides local executable/database paths and avoids rendering raw SQLite exception strings.
- AI provider status explicitly says configured but not verified until a live request is made.
- Primary button CSS uses additional selectors for readable contrast across Streamlit button DOM variants.

## Backend preservation
The following V4 files were not changed in V4.1:
- `processor.py`
- `database.py`
- `batch_processing.py`
- `requirements.txt`
- `data/purchase_orders.csv`
- Existing sample invoice PDFs and test modules

No AI provider request, paid API call, public deployment or hosted-persistence configuration was performed.

## Verification
- Python compilation passed.
- 30 automated tests passed.
- Interactive Streamlit UI rendering must be verified on the candidate's Windows machine; this build environment did not launch the browser UI.
