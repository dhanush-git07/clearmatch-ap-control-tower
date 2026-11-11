from pathlib import Path
import tempfile
import unittest
from unittest import mock
import os

from batch_processing import process_batch
from database import get_runs, get_prior_po_total, initialize_database

ROOT = Path(__file__).resolve().parents[1]


class BatchIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "batch.db")
        self.documents = str(Path(self.tmp.name) / "documents")
        initialize_database(self.db)
        self.env = mock.patch.dict(os.environ, {"GROQ_API_KEY": "", "OPENAI_API_KEY": "", "LLM_API_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def read(self, name):
        return (ROOT / "samples" / name).read_bytes()

    def test_split_invoices_in_batch_respect_sequence_and_cumulative_exposure(self):
        docs = [
            ("part-1.pdf", self.read("split_01_invoice.pdf")),
            ("part-2.pdf", self.read("split_02_invoice.pdf")),
            ("part-3.pdf", self.read("split_03_invoice.pdf")),
        ]
        results = process_batch(docs, self.db, self.documents)
        self.assertEqual([x["record"]["status"] for x in results], ["AUTO-CLEAR", "AUTO-CLEAR", "NEEDS REVIEW"])
        self.assertEqual(len(get_runs(self.db)), 3)
        self.assertEqual(get_prior_po_total("PO-1002", self.db), 105000.0)

    def test_bad_file_does_not_prevent_later_invoice_processing(self):
        docs = [
            ("broken.pdf", b"not a pdf"),
            ("good.pdf", self.read("happy_path_invoice.pdf")),
        ]
        results = process_batch(docs, self.db, self.documents)
        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[1]["record"]["status"], "AUTO-CLEAR")
        self.assertEqual(len(get_runs(self.db)), 1)

    def test_duplicate_in_same_batch_is_detected(self):
        payload = self.read("happy_path_invoice.pdf")
        results = process_batch([("one.pdf", payload), ("copy.pdf", payload)], self.db, self.documents)
        self.assertEqual(results[0]["record"]["status"], "AUTO-CLEAR")
        self.assertEqual(results[1]["record"]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
