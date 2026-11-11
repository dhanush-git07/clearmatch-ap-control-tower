# ClearMatch — 5-minute demo plan

**Narration:** Record in your own voice. Keep the application live. No slides and no AI-generated voice.

The goal is to demonstrate an AP operating workflow rather than narrate a feature list.

| Time | What to show | What to explain |
|---|---|---|
| 0:00–0:25 | Control Tower landing page | "ClearMatch is an AP decision workbench. It turns invoice PDFs into traceable decisions, while financial rules—not an LLM—control the outcome." |
| 0:25–1:05 | Single invoice: happy-path Northstar sample | Show the live stage trace, extracted fields, field evidence, PO checks and AUTO-CLEAR decision. Emphasise that this means ready for AP approval, not paid. |
| 1:05–1:50 | Batch Intake: process the three split invoices in order | Show the three real run results. Explain why sequential processing matters: the next invoice sees exposure already recorded for the same PO. |
| 1:50–2:25 | PO Exposure Monitor | Show PO-1002 at/over its tolerance cap and explain the ₹40k + ₹35k + ₹30k cumulative exposure example. |
| 2:25–3:10 | Exception Desk: missing-date or arithmetic-mismatch invoice | Open the source PDF and extracted fields. Explain the missing/failed control, then record a reviewer name and rationale. Do not approve unless the scenario is genuinely suitable and your rationale is defensible. |
| 3:10–3:45 | Wrong-vendor or closed-PO invoice | Show BLOCKED and explain why a critical policy violation is not overridable in this MVP. |
| 3:45–4:25 | Run Ledger and CSV export | Show the searchable audit record, source document, decision evidence and export. |
| 4:25–5:00 | Policy & system | Explain field-grounded extraction, deterministic decisions, the human-in-the-loop boundary and honest limitations. |

## Rehearsal checklist

- [ ] Start with a clean demo history from Policy & system → Clear demo history.
- [ ] Confirm the PO register remains intact after reset.
- [ ] Run the happy path once.
- [ ] Batch-process split parts 1, 2 and 3 in that order (or reset again before this sequence).
- [ ] Confirm PO-1002 displays cumulative exposure above the 2% tolerance cap.
- [ ] Run a missing-date or arithmetic-mismatch case and show the source evidence.
- [ ] Run a wrong-vendor or closed-PO case to demonstrate BLOCKED.
- [ ] Ensure the Review Queue and CSV export are working.
- [ ] Confirm any live LLM claim with a successful provider connection and actual invoice run. If unavailable, describe deterministic fallback honestly.
- [ ] Keep the final recording under five minutes.

## Suggested opening

"Accounts payable teams don't just need invoice data extracted. They need to know whether the data can be trusted, whether the invoice matches procurement controls, and what action should happen next. ClearMatch brings those steps into one reviewable workflow."

## Suggested closing

"The key design choice is that AI assists with understanding messy documents, but it does not approve payments. Every decision is backed by deterministic controls, preserved evidence and a human review path for exceptions."
