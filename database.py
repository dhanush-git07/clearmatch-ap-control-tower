from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "clearmatch.db"
PO_CSV = DATA_DIR / "purchase_orders.csv"


@contextmanager
def get_connection(db_path: Path | str = DB_PATH):
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def initialize_database(db_path: Path | str = DB_PATH) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_number TEXT PRIMARY KEY,
                vendor_id TEXT NOT NULL,
                vendor_name TEXT NOT NULL,
                po_amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                tolerance_pct REAL NOT NULL DEFAULT 2.0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,
                vendor_name TEXT,
                invoice_number TEXT,
                invoice_date TEXT,
                po_number TEXT,
                invoice_total REAL,
                currency TEXT,
                status TEXT NOT NULL,
                decision_reason TEXT NOT NULL,
                extraction_method TEXT NOT NULL,
                confidence REAL,
                extraction_completeness REAL,
                fields_json TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                extracted_text TEXT,
                processing_ms INTEGER NOT NULL DEFAULT 0,
                document_path TEXT
            )
            """
        )
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
        for col in ["review_decision", "review_note", "reviewed_at", "reviewed_by", "document_path", "extraction_completeness"]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {'REAL' if col == 'extraction_completeness' else 'TEXT'}")
        conn.execute("UPDATE runs SET extraction_completeness = confidence WHERE extraction_completeness IS NULL AND confidence IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_po ON runs(po_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_invoice ON runs(vendor_name, invoice_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at)")

        existing = conn.execute("SELECT COUNT(*) AS n FROM purchase_orders").fetchone()["n"]
        if existing == 0 and PO_CSV.exists():
            po_df = pd.read_csv(PO_CSV).fillna("")
            for row in po_df.to_dict(orient="records"):
                conn.execute(
                    """INSERT OR IGNORE INTO purchase_orders
                    (po_number, vendor_id, vendor_name, po_amount, currency, status, tolerance_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(row["po_number"]), str(row["vendor_id"]), str(row["vendor_name"]),
                        float(row["po_amount"]), str(row.get("currency", "INR")),
                        str(row.get("status", "ACTIVE")), float(row.get("tolerance_pct", 2.0)),
                    ),
                )
        conn.commit()


def get_purchase_orders(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT po_number, vendor_id, vendor_name, po_amount, currency, status, tolerance_pct FROM purchase_orders ORDER BY po_number",
            conn,
        )


def get_run(run_id: str, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["fields"] = json.loads(result.pop("fields_json") or "{}")
    result["checks"] = json.loads(result.pop("checks_json") or "[]")
    return result


def get_runs(db_path: Path | str = DB_PATH, limit: int | None = None) -> pd.DataFrame:
    query = """SELECT run_id, created_at, file_name, vendor_name, invoice_number, po_number,
               invoice_total, currency, status, decision_reason, extraction_method, extraction_completeness,
               processing_ms, review_decision FROM runs ORDER BY created_at DESC"""
    if limit is not None:
        query += " LIMIT ?"
        params: tuple[Any, ...] = (int(limit),)
    else:
        params = ()
    with get_connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


def find_duplicate(vendor_name: str | None, invoice_number: str | None, file_sha256: str,
                   db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT run_id, created_at, file_name, status, vendor_name, invoice_number
               FROM runs WHERE file_sha256 = ? AND status != 'ERROR' AND extraction_method != 'Unreadable document'
               ORDER BY created_at DESC LIMIT 1""",
            (file_sha256,),
        ).fetchone()
        if row is None and vendor_name and invoice_number:
            row = conn.execute(
                """SELECT run_id, created_at, file_name, status, vendor_name, invoice_number
                   FROM runs WHERE lower(trim(vendor_name)) = lower(trim(?))
                   AND lower(trim(invoice_number)) = lower(trim(?)) AND status != 'ERROR' AND extraction_method != 'Unreadable document'
                   ORDER BY created_at DESC LIMIT 1""",
                (vendor_name, invoice_number),
            ).fetchone()
    return dict(row) if row else None


def get_po(po_number: str | None, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    if not po_number:
        return None
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM purchase_orders WHERE lower(po_number) = lower(?)", (po_number,)).fetchone()
    return dict(row) if row else None


def get_prior_po_total(po_number: str, db_path: Path | str = DB_PATH) -> float:
    """Sum only eligible runs whose currency matches the registered PO currency."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(r.invoice_total), 0) AS total
               FROM runs AS r
               JOIN purchase_orders AS p ON lower(r.po_number) = lower(p.po_number)
               WHERE lower(r.po_number) = lower(?)
                 AND r.status IN ('AUTO-CLEAR', 'NEEDS REVIEW')
                 AND COALESCE(r.review_decision, '') != 'REJECTED'
                 AND r.currency IS NOT NULL
                 AND upper(r.currency) = upper(p.currency)""",
            (po_number,),
        ).fetchone()
    return float(row["total"] or 0.0)


def insert_run(record: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO runs (
                run_id, created_at, file_name, file_sha256, vendor_name, invoice_number,
                invoice_date, po_number, invoice_total, currency, status, decision_reason,
                extraction_method, confidence, extraction_completeness, fields_json, checks_json, extracted_text, processing_ms, document_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["run_id"], record["created_at"], record["file_name"], record["file_sha256"],
                record.get("vendor_name"), record.get("invoice_number"), record.get("invoice_date"),
                record.get("po_number"), record.get("invoice_total"), record.get("currency"),
                record["status"], record["decision_reason"], record["extraction_method"],
                None, record.get("extraction_completeness", record.get("confidence")),
                json.dumps(record.get("fields", {}), ensure_ascii=False),
                json.dumps(record.get("checks", []), ensure_ascii=False), record.get("extracted_text", ""),
                int(record.get("processing_ms", 0)), record.get("document_path"),
            ),
        )
        conn.commit()


def clear_demo_history(db_path: Path | str = DB_PATH) -> None:
    """Clear run history and its retained local PDFs; purchase-order data is retained."""
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT document_path FROM runs WHERE document_path IS NOT NULL").fetchall()
        conn.execute("DELETE FROM runs")
        conn.commit()
    allowed_root = (DATA_DIR / "documents").resolve()
    for row in rows:
        raw_path = row["document_path"]
        if not raw_path:
            continue
        try:
            path = Path(raw_path).resolve()
            if allowed_root in path.parents and path.is_file():
                path.unlink()
        except OSError:
            pass


REVIEW_COLUMNS = """run_id, created_at, file_name, vendor_name, invoice_number, po_number,
                    invoice_total, currency, status, decision_reason, review_decision, review_note,
                    reviewed_by, reviewed_at"""


def get_review_queue(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """NEEDS REVIEW runs that no human has decided yet, oldest first."""
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            f"SELECT {REVIEW_COLUMNS} FROM runs WHERE status = 'NEEDS REVIEW' AND review_decision IS NULL ORDER BY created_at ASC",
            conn,
        )


def get_reviewed(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            f"SELECT {REVIEW_COLUMNS} FROM runs WHERE status = 'NEEDS REVIEW' AND review_decision IS NOT NULL ORDER BY reviewed_at DESC",
            conn,
        )


def get_exception_queue(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """Unresolved review and blocked outcomes for visibility; only NEEDS REVIEW is actionable."""
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            f"SELECT {REVIEW_COLUMNS} FROM runs WHERE status IN ('NEEDS REVIEW', 'BLOCKED') AND review_decision IS NULL ORDER BY created_at ASC",
            conn,
        )


def set_review(run_id: str, decision: str, note: str = "", db_path: Path | str = DB_PATH,
               *, reviewed_by: str | None = None) -> bool:
    """Record a human decision (APPROVED or REJECTED). Returns False if the run is not awaiting review."""
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("decision must be APPROVED or REJECTED")
    from datetime import datetime

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "UPDATE runs SET review_decision = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? "
            "WHERE run_id = ? AND status = 'NEEDS REVIEW' AND review_decision IS NULL",
            (decision, note.strip(), (reviewed_by or "").strip() or None, stamp, run_id),
        )
        conn.commit()
        return cur.rowcount == 1
