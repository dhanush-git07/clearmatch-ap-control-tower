# Zamp AI Solutions Analyst — ClearMatch submission notes

## Selected problem

**PS-1 · Finance / Accounts Payable — Invoice processing, from PDF to decision.**

## Product

**ClearMatch | AP Control Tower** — an explainable invoice decision workbench for document intake, field evidence, duplicate screening, PO matching, deterministic financial validation, cumulative exposure monitoring and human review.

## Why this approach

The product addresses the operational loop rather than only extracting fields. An AP analyst can process one invoice or a sequential batch, inspect the source and evidence behind each field, understand why a control passed or failed, see portfolio exposure against PO tolerance and resolve eligible exceptions with an auditable reviewer rationale.

## Core design principle

AI is an extraction assistant. It proposes invoice fields and supporting evidence. Evidence-grounding checks and deterministic financial rules govern the final status. The LLM cannot independently release or approve payment.

## Decision outcomes

- `AUTO-CLEAR`: all configured checks pass; ready for AP approval only.
- `NEEDS REVIEW`: a human decision is needed because of missing, ambiguous or mismatched information or a financial exception.
- `BLOCKED`: a critical policy violation such as duplicate invoice, vendor/PO ownership mismatch or inactive PO.

## Product differentiators

1. Sequential batch intake with per-file run IDs and audit records.
2. Same-batch duplicate detection and cumulative PO exposure checks.
3. Field-level provenance and evidence-grounding rather than unqualified AI output.
4. Deterministic financial controls for arithmetic, vendor ownership, PO status, currency and cumulative exposure.
5. Human review workspace with reviewer name, rationale and timestamp.
6. PO exposure monitor with native-currency totals and tolerance-watch signals.
7. Searchable run ledger and CSV exports.

## Verification snapshot

- 30 automated unit tests passed in the build environment.
- Batch tests cover ordered split-invoice processing, invalid-file isolation and duplicate detection within one batch.
- Existing extraction, financial decision, review, OCR and SQLite migration tests remain passing.
- Streamlit interactive UI must be smoke-tested locally on Windows; it could not be launched in the build environment.
- Live LLM provider execution remains unverified until the candidate's provider connection test and actual invoice run both succeed.
- Public deployment has not been performed.

## Assumptions and limitations to explain

- Bundled vendors, purchase orders and invoices are synthetic.
- PO tolerance and arithmetic tolerance are case-study assumptions, not claims about Zamp or any specific customer's policy.
- No FX conversion, line-item/receipt three-way match, authenticated reviewer identity or production ERP integration is implemented.
- Evidence-grounding is contextual text verification, not visual bounding-box verification.
- Public hosting requires durable database and file storage, authentication, access controls and retention policies.

## Required submission artefacts

- Public, tested application URL (not yet available).
- Narrated five-minute live-process demo video (not yet recorded).
