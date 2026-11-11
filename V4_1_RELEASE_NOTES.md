# ClearMatch V4.1 — AP Control Tower refinement release

V4.1 is a focused UX and operational-clarity refinement on top of V4. It does not replace the invoice processor or database layer.

## Changes

### Exception Desk
- Renamed the ambiguous `Open exceptions` metric to `Unresolved records`.
- Clarified that unresolved records comprise actionable reviews and policy-blocked records.
- Improved the empty state so reviewers can distinguish a clear action queue from blocked records and previously resolved cases.
- Made exception, blocked and resolved table heights respond to the number of displayed records.

### Run Ledger
- Removed lower-priority columns from the primary scan table to reduce horizontal scrolling.
- Added a compact processed timestamp for easier scanning.
- Made the table height respond to the filtered result count.
- Added an explicit no-results state when search and filters return no records.
- Clarified that the selected record contains the complete source document, field provenance, controls and review history.

### PO Exposure Monitor
- The chart now plots only purchase orders with eligible recorded invoice exposure. The complete PO register remains visible below it.
- The PO register now includes remaining headroom to the configured tolerance cap, in addition to remaining PO value.
- Chart and table heights are sized to the amount of visible data.

### Policy & System
- Changed API status wording to `Configured · not yet verified` until a live request succeeds.
- Removed absolute local paths for Tesseract and SQLite from the user interface.
- Replaced raw SQLite exception text with a non-sensitive diagnostic message.
- Added broader primary-button selectors to improve white-text contrast across supported Streamlit button DOM variants.

## Preserved

- `processor.py`, `database.py`, `batch_processing.py`, sample invoices, PO master data and dependency declarations are unchanged from V4.
- Existing decision rules, database schema, API handling and batch-processing logic are unchanged.
- No public deployment or paid API request was performed.

## Verification

- All Python source and test files pass `py_compile`.
- All 30 automated tests pass.
- The interactive Streamlit browser UI must still be smoke-tested in the candidate's Windows environment. In particular, confirm button contrast, table sizing and the no-results states at the actual browser width.
