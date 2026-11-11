# Updating ClearMatch V4 to V4.1

V4.1 is a focused UI and operational-clarity refinement. It preserves the V4 processor, database and batch-processing code.

## Before replacing files

1. Stop Streamlit in CMD with `Ctrl+C`.
2. Make a backup of your current `clearmatch_app` folder.
3. Keep your existing `.venv`, `.streamlit/secrets.toml`, `data/clearmatch.db` and `data/documents/`. They are intentionally not included in the clean release ZIP.

## Extract V4.1

Extract the ZIP directly into your existing `clearmatch_app` folder and choose **Replace files in destination** when Windows asks.

The archive contains the project root files and folders, not an extra nested project folder. It updates `app.py` and the release documentation. It preserves V4's processor, database, batch-processing service, samples, requirements and secrets template.

## Verify locally

Open CMD in the existing project folder:

```cmd
.venv\\Scripts\\python.exe -m unittest discover -s tests -v
.venv\\Scripts\\python.exe -m streamlit run app.py
```

No new third-party dependency was introduced.

## Windows UI smoke test

1. **Control Tower:** confirm run counts, review counts and PO signals match the local database.
2. **Invoice Intake:** run one happy-path invoice; inspect the actual execution trace and decision evidence.
3. **Batch Intake:** run the three split invoices sequentially in a clean demo database. Expected: AUTO-CLEAR, AUTO-CLEAR, NEEDS REVIEW.
4. **Exception Desk:** confirm `Unresolved records`, `Awaiting human review`, `Blocked by policy` and `Human resolutions` are clearly distinguished. Create or retain one unreviewed NEEDS REVIEW case to demonstrate the action workspace.
5. **Run Ledger:** confirm the table does not show excess blank rows, search to zero results, then open a record and inspect its complete evidence.
6. **PO Exposure:** confirm the chart only includes POs with recorded eligible exposure, while the table still lists every registered PO and shows remaining tolerance headroom.
7. **Policy & System:** confirm no absolute local filesystem paths are shown. Treat an API provider as unverified until the live connection test succeeds.
8. Check that primary buttons have readable white text at your actual browser size.

Do not reset local history unless you intend to remove the run records and retained source PDFs. The PO register is retained by the reset operation.

## Verification limits

The source code compiles and all 30 automated tests pass in the build environment. The Streamlit browser UI was not launched in that environment, so the Windows UI smoke test remains necessary. Mocked LLM tests do not prove live provider connectivity. No deployment was performed.
