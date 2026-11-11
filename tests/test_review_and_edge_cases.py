import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

from database import (find_duplicate, get_prior_po_total, get_review_queue, get_reviewed,
                      get_exception_queue, get_run, initialize_database, set_review)
from processor import process_invoice

ROOT = Path(__file__).resolve().parents[1]


class EdgeCaseAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        initialize_database(self.db)
        # Rule-based path only: no LLM keys in the test environment.
        self.env = mock.patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENAI_API_KEY": "", "LLM_API_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_sample(self, name):
        return process_invoice((ROOT / "samples" / name).read_bytes(), name, self.db)

    def test_currency_mismatch_with_po_requires_review_and_skips_exposure(self):
        r = self.run_sample("currency_mismatch_invoice.pdf")
        self.assertEqual(r["fields"]["currency"], "USD")
        self.assertEqual(r["status"], "NEEDS REVIEW")
        currency_check = next(c for c in r["checks"] if c["check"] == "Currency consistency")
        self.assertEqual(currency_check["result"], "REVIEW")
        exposure_check = next(c for c in r["checks"] if c["check"] == "Cumulative PO exposure")
        self.assertEqual(exposure_check["result"], "INFO")
        self.assertIn("Skipped", exposure_check["detail"])
        # A wrong-currency run must not contaminate later INR exposure calculations.
        self.assertEqual(get_prior_po_total("PO-1001", self.db), 0.0)
        valid = self.run_sample("alternative_layout_invoice.pdf")
        self.assertEqual(valid["status"], "AUTO-CLEAR")
        self.assertEqual(get_prior_po_total("PO-1001", self.db), 531.0)

    def test_alternative_invoice_layouts_extract_with_rule_fallback(self):
        first = self.run_sample("alternative_layout_invoice.pdf")
        second = self.run_sample("bluepeak_layout_table_invoice.pdf")
        self.assertEqual(first["status"], "AUTO-CLEAR")
        self.assertEqual(first["fields"]["invoice_number"], "NS-INV-1002")
        self.assertEqual(second["status"], "AUTO-CLEAR")
        self.assertEqual(second["fields"]["invoice_number"], "BP-INV-3002")
        self.assertEqual(second["fields"]["total"], 23600.0)
        third = self.run_sample("compact_pipe_layout_invoice.pdf")
        self.assertEqual(third["status"], "AUTO-CLEAR")
        self.assertEqual(third["fields"]["vendor_name"], "Greenfield Packaging")
        self.assertEqual(third["fields"]["invoice_number"], "GFP-INV-5002")
        self.assertEqual(third["fields"]["po_number"], "PO-1005")
        self.assertEqual(third["fields"]["total"], 11800.0)

    def test_currency_is_not_assumed_from_ambiguous_dollar_symbol(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 550, 400),
            "Vendor: Northstar Supplies\nInvoice Number: NS-USD-9002\nInvoice Date: 06-Nov-2026\n"
            "PO Number: PO-1001\nSubtotal: $450.00\nTax: $81.00\nGrand Total: $531.00", fontsize=12)
        pdf_bytes = doc.tobytes()
        result = process_invoice(pdf_bytes, "ambiguous_currency.pdf", self.db)
        self.assertIsNone(result["fields"]["currency"])
        self.assertEqual(result["status"], "NEEDS REVIEW")
        self.assertIn("currency", result["decision_reason"].lower())

    def test_wrong_vendor_for_po_is_blocked(self):
        r = self.run_sample("wrong_vendor_invoice.pdf")
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("vendor", r["decision_reason"].lower())

    def test_arithmetic_mismatch_needs_review(self):
        r = self.run_sample("arithmetic_mismatch_invoice.pdf")
        self.assertEqual(r["status"], "NEEDS REVIEW")
        self.assertIn("reconcile", r["decision_reason"].lower())

    def test_unreadable_pdf_needs_review_and_does_not_poison_duplicates(self):
        doc = fitz.open()
        doc.new_page()
        blank = doc.tobytes()
        first = process_invoice(blank, "blank.pdf", self.db)
        self.assertEqual(first["status"], "NEEDS REVIEW")
        self.assertEqual(first["checks"][0]["check"], "Document readability")
        second = process_invoice(blank, "blank_again.pdf", self.db)
        self.assertNotIn("Duplicate", second["decision_reason"])
        self.assertIsNone(find_duplicate(None, None, first["file_sha256"], self.db))

    def test_review_queue_approve_and_reject(self):
        self.run_sample("split_01_invoice.pdf")
        self.run_sample("split_02_invoice.pdf")
        third = self.run_sample("split_03_invoice.pdf")
        self.assertEqual(third["status"], "NEEDS REVIEW")
        self.assertEqual(len(get_review_queue(self.db)), 1)
        self.assertEqual(get_prior_po_total("PO-1002", self.db), 105000.0)
        self.assertTrue(set_review(third["run_id"], "REJECTED", "Over-billed", self.db, reviewed_by="AP Reviewer"))
        self.assertFalse(set_review(third["run_id"], "APPROVED", "", self.db))  # already decided
        self.assertEqual(len(get_review_queue(self.db)), 0)
        self.assertEqual(len(get_reviewed(self.db)), 1)
        reviewed = get_run(third["run_id"], self.db)
        self.assertEqual(reviewed["reviewed_by"], "AP Reviewer")
        # Rejected invoice no longer counts toward PO exposure.
        self.assertEqual(get_prior_po_total("PO-1002", self.db), 75000.0)

    def test_approved_invoice_still_counts_toward_exposure(self):
        for n in ("split_01_invoice.pdf", "split_02_invoice.pdf"):
            self.run_sample(n)
        third = self.run_sample("split_03_invoice.pdf")
        set_review(third["run_id"], "APPROVED", "Verified with vendor", self.db)
        self.assertEqual(get_prior_po_total("PO-1002", self.db), 105000.0)


    def test_exception_queue_includes_blocked_and_review_but_only_review_is_actionable(self):
        blocked = self.run_sample("closed_po_invoice.pdf")
        review = self.run_sample("missing_date_invoice.pdf")
        rows = get_exception_queue(self.db)
        self.assertEqual(set(rows["status"].tolist()), {"BLOCKED", "NEEDS REVIEW"})
        self.assertFalse(set_review(blocked["run_id"], "APPROVED", "Should not override", self.db))
        self.assertTrue(set_review(review["run_id"], "APPROVED", "Checked against source", self.db, reviewed_by="Demo reviewer"))
        remaining = get_exception_queue(self.db)
        self.assertEqual(remaining["run_id"].tolist(), [blocked["run_id"]])

    def test_scanned_invoice_uses_ocr_when_tesseract_is_available(self):
        import shutil
        if not shutil.which("tesseract"):
            self.skipTest("Tesseract executable is not installed in this environment")
        result = self.run_sample("scanned_missing_date_invoice.pdf")
        self.assertEqual(result["status"], "NEEDS REVIEW")
        self.assertEqual(result["fields"]["_extraction"]["text_extraction_mode"], "OCR (Tesseract)")
        self.assertIsNone(result["fields"]["invoice_date"])


    def test_original_pdf_is_retained_for_later_source_review(self):
        import fitz
        from database import get_run
        documents = Path(self.tmp.name) / "documents"
        result = process_invoice(
            (ROOT / "samples" / "happy_path_invoice.pdf").read_bytes(),
            "happy_path_invoice.pdf", self.db, document_dir=str(documents)
        )
        stored = Path(result["document_path"])
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_bytes(), (ROOT / "samples" / "happy_path_invoice.pdf").read_bytes())
        persisted = get_run(result["run_id"], self.db)
        self.assertEqual(persisted["document_path"], str(stored))
        self.assertEqual(persisted["extraction_completeness"], 1.0)

    def test_auto_clear_runs_cannot_be_reviewed(self):
        r = self.run_sample("happy_path_invoice.pdf")
        self.assertFalse(set_review(r["run_id"], "APPROVED", "", self.db))

    def test_old_database_is_migrated(self):
        old = str(Path(self.tmp.name) / "old.db")
        conn = sqlite3.connect(old)
        conn.execute("""CREATE TABLE runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, file_name TEXT NOT NULL,
            file_sha256 TEXT NOT NULL, vendor_name TEXT, invoice_number TEXT, invoice_date TEXT, po_number TEXT,
            invoice_total REAL, currency TEXT, status TEXT NOT NULL, decision_reason TEXT NOT NULL,
            extraction_method TEXT NOT NULL, confidence REAL, fields_json TEXT NOT NULL, checks_json TEXT NOT NULL,
            extracted_text TEXT, processing_ms INTEGER NOT NULL DEFAULT 0)""")
        conn.commit(); conn.close()
        initialize_database(old)
        conn = sqlite3.connect(old)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
        conn.close()
        self.assertTrue({"review_decision", "review_note", "reviewed_at", "reviewed_by", "document_path", "extraction_completeness"} <= cols)


if __name__ == "__main__":
    unittest.main()
