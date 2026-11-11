from pathlib import Path
import tempfile
import unittest

from database import initialize_database
from processor import process_invoice

ROOT = Path(__file__).resolve().parents[1]


class ClearMatchProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        initialize_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_sample(self, name):
        file_path = ROOT / "samples" / name
        return process_invoice(file_path.read_bytes(), name, str(self.db_path))

    def test_happy_path_auto_clears(self):
        result = self.run_sample("happy_path_invoice.pdf")
        self.assertEqual(result["status"], "AUTO-CLEAR")
        self.assertEqual(result["fields"]["po_number"], "PO-1001")

    def test_same_invoice_is_blocked_as_duplicate(self):
        self.run_sample("happy_path_invoice.pdf")
        result = self.run_sample("happy_path_invoice.pdf")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("Duplicate invoice detected", result["decision_reason"])

    def test_split_invoices_trigger_cumulative_review(self):
        self.run_sample("split_01_invoice.pdf")
        self.run_sample("split_02_invoice.pdf")
        result = self.run_sample("split_03_invoice.pdf")
        self.assertEqual(result["status"], "NEEDS REVIEW")
        self.assertIn("Cumulative invoices", result["decision_reason"])

    def test_missing_date_requires_review(self):
        result = self.run_sample("missing_date_invoice.pdf")
        self.assertEqual(result["status"], "NEEDS REVIEW")
        self.assertIn("Invoice date", result["decision_reason"])

    def test_closed_po_is_blocked(self):
        result = self.run_sample("closed_po_invoice.pdf")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("not active", result["decision_reason"])


if __name__ == "__main__":
    unittest.main()
