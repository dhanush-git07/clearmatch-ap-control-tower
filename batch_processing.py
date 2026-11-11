"""Sequential, auditable multi-invoice intake built on the core processor."""
from __future__ import annotations

from typing import Any, Callable, Iterable

from processor import process_invoice

BatchCallback = Callable[[int, int, str, str, str, str], None]


def process_batch(
    documents: Iterable[tuple[str, bytes]],
    db_path: str,
    document_dir: str | None = None,
    progress_callback: BatchCallback | None = None,
) -> list[dict[str, Any]]:
    """Process documents in order; each success is committed independently.

    A failure for one file is returned as an ERROR result and does not prevent
    later files from being processed. Sequential ordering is intentional:
    duplicate screening and cumulative PO exposure for later invoices must see
    earlier successful runs in the same batch.
    """
    items = list(documents)
    total = len(items)
    results: list[dict[str, Any]] = []

    for index, (file_name, payload) in enumerate(items, start=1):
        if progress_callback:
            progress_callback(index, total, file_name, "Batch intake", "running", "Preparing this document.")

        def on_stage(stage: str, state: str, detail: str) -> None:
            if progress_callback:
                progress_callback(index, total, file_name, stage, state, detail)

        try:
            record = process_invoice(
                payload,
                file_name,
                db_path,
                stage_callback=on_stage,
                document_dir=document_dir,
            )
            results.append({"file_name": file_name, "ok": True, "record": record, "error": None})
            if progress_callback:
                progress_callback(index, total, file_name, "Batch intake", "complete", f"Saved as {record['run_id']} · {record['status']}.")
        except Exception as exc:  # one malformed file must not poison the rest of the batch
            results.append({"file_name": file_name, "ok": False, "record": None, "error": str(exc)})
            if progress_callback:
                progress_callback(index, total, file_name, "Batch intake", "error", f"Not recorded · {exc}")

    return results
