import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from database import initialize_database
from processor import process_invoice, get_llm_settings, _safe_error

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "gsk_FAKE_SECRET_KEY_123"


def fake_openai(content=None, exc=None):
    """Build a stand-in 'openai' module so no real API call is made."""
    class Completions:
        def create(self, **kwargs):
            if exc:
                raise exc
            msg = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class OpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    return types.SimpleNamespace(OpenAI=OpenAI)


def item(value, evidence=None):
    return {"value": value, "evidence": evidence}


GOOD_EVIDENCE = {
    "vendor_name": "Vendor:\nNorthstar Supplies",
    "invoice_number": "Invoice Number:\nNS-INV-1001",
    "invoice_date": "Invoice Date:\n04-Nov-2026",
    "po_number": "PO Number:\nPO-1001",
    "subtotal": "Subtotal:\nINR 50,000.00",
    "tax": "Tax:\nINR 9,000.00",
    "total": "Grand Total:\nINR 59,000.00",
}


class QuotaError(Exception):
    status_code = 429
    body = {"error": {"code": "insufficient_quota"}}


class LlmExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "t.db")
        initialize_database(self.db)
        self.env = mock.patch.dict(os.environ, {"GROQ_API_KEY": FAKE_KEY, "OPENAI_API_KEY": ""}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_with(self, sample, module):
        with mock.patch.dict(sys.modules, {"openai": module}):
            return process_invoice((ROOT / "samples" / sample).read_bytes(), sample, self.db)

    def test_groq_is_selected_when_key_present(self):
        s = get_llm_settings()
        self.assertEqual(s["provider"], "Groq")
        self.assertIn("groq.com", s["base_url"])

    def test_good_llm_output_is_accepted_and_grounded(self):
        payload = {
            "vendor_name": item("Northstar Supplies", GOOD_EVIDENCE["vendor_name"]),
            "invoice_number": item("NS-INV-1001", GOOD_EVIDENCE["invoice_number"]),
            "invoice_date": item("04-Nov-2026", GOOD_EVIDENCE["invoice_date"]),
            "po_number": item("PO-1001", GOOD_EVIDENCE["po_number"]),
            "subtotal": item(50000, GOOD_EVIDENCE["subtotal"]),
            "tax": item(9000, GOOD_EVIDENCE["tax"]),
            "total": item(59000, GOOD_EVIDENCE["total"]), "currency": "INR",
        }
        r = self.run_with("happy_path_invoice.pdf", fake_openai(json.dumps(payload)))
        self.assertEqual(r["status"], "AUTO-CLEAR")
        self.assertTrue(r["extraction_method"].startswith("LLM extraction (Groq"))
        self.assertEqual(r["fields"]["_extraction"]["grounded_fields"], 7)

    def test_hallucinated_date_is_discarded_not_trusted(self):
        payload = {
            "vendor_name": item("Bluepeak Technologies", "Vendor:\nBluepeak Technologies"),
            "invoice_number": item("BP-INV-3001", "Invoice Number:\nBP-INV-3001"),
            "invoice_date": item("15-Oct-2026", "Invoice Date:\n15-Oct-2026"),
            "po_number": item("PO-1003", "PO Number:\nPO-1003"),
            "subtotal": item(None), "tax": item(None), "total": item(None), "currency": "INR",
        }
        r = self.run_with("missing_date_invoice.pdf", fake_openai(json.dumps(payload)))
        self.assertIsNone(r["fields"]["invoice_date"])
        self.assertIn("invoice_date", r["fields"]["_extraction"]["rejected_fields"])
        self.assertEqual(r["status"], "NEEDS REVIEW")

    def test_invoice_number_digits_cannot_be_reused_as_missing_invoice_date(self):
        payload = {
            "vendor_name": item("Bluepeak Technologies", "Vendor:\nBluepeak Technologies"),
            "invoice_number": item("BP-INV-3001", "Invoice Number:\nBP-INV-3001"),
            # Deliberately malicious/mistaken model output: 3001 occurs in the invoice ID,
            # but there is no invoice-date label or date in this PDF.
            "invoice_date": item("3001", "Invoice Number:\nBP-INV-3001"),
            "po_number": item("PO-1003", "PO Number:\nPO-1003"),
            "subtotal": item(50000, "Subtotal:\nINR 50,000.00"),
            "tax": item(9000, "Tax:\nINR 9,000.00"),
            "total": item(59000, "Grand Total:\nINR 59,000.00"),
            "currency": "INR",
        }
        r = self.run_with("missing_date_invoice.pdf", fake_openai(json.dumps(payload)))
        self.assertIsNone(r["fields"]["invoice_date"])
        self.assertIn("invoice_date", r["fields"]["_extraction"]["rejected_fields"])
        self.assertEqual(r["status"], "NEEDS REVIEW")
        self.assertIn("Invoice date", r["decision_reason"])


    def test_vendor_tax_id_cannot_be_accepted_as_vendor_name(self):
        payload = {
            "vendor_name": item("TAX-998812", "Vendor Tax ID: TAX-998812"),
            "invoice_number": item("NS-INV-1001", GOOD_EVIDENCE["invoice_number"]),
            "invoice_date": item("04-Nov-2026", GOOD_EVIDENCE["invoice_date"]),
            "po_number": item("PO-1001", GOOD_EVIDENCE["po_number"]),
            "subtotal": item(50000, GOOD_EVIDENCE["subtotal"]),
            "tax": item(9000, GOOD_EVIDENCE["tax"]),
            "total": item(59000, GOOD_EVIDENCE["total"]),
            "currency": "INR",
        }
        result = self.run_with("happy_path_invoice.pdf", fake_openai(json.dumps(payload)))
        self.assertEqual(result["fields"]["vendor_name"], "Northstar Supplies")
        self.assertEqual(result["fields"]["_provenance"]["vendor_name"]["source"], "rule")
        self.assertIn("vendor_name", result["fields"]["_extraction"]["rejected_fields"])

    def test_llm_value_without_verbatim_field_evidence_is_rejected(self):
        payload = {
            "vendor_name": item("Northstar Supplies", "Vendor: Northstar Supplies"),
            "invoice_number": item("NS-INV-1001", "Invoice Number: NS-INV-1001"),
            "invoice_date": item("04-Nov-2026", "Due Date: 04-Nov-2026"),
            "po_number": item("PO-1001", "PO Number: PO-1001"),
            "subtotal": item(50000, "Subtotal: INR 50,000.00"),
            "tax": item(9000, "Tax: INR 9,000.00"),
            "total": item(59000, "Grand Total: INR 59,000.00"),
            "currency": "INR",
        }
        r = self.run_with("happy_path_invoice.pdf", fake_openai(json.dumps(payload)))
        self.assertEqual(r["fields"]["invoice_date"], "04-Nov-2026")
        self.assertEqual(r["fields"]["_provenance"]["invoice_date"]["source"], "rule")
        self.assertIn("invoice_date", r["fields"]["_extraction"]["rejected_fields"])

    def test_api_error_falls_back_safely_without_leaking_key(self):
        r = self.run_with("happy_path_invoice.pdf", fake_openai(exc=QuotaError(f"denied for {FAKE_KEY}")))
        self.assertEqual(r["status"], "AUTO-CLEAR")
        self.assertTrue(r["extraction_method"].startswith("Rule-based fallback"))
        self.assertIn("429", r["fields"]["_extraction"]["message"])
        self.assertNotIn(FAKE_KEY, json.dumps(r, default=str))

    def test_garbage_llm_output_falls_back(self):
        r = self.run_with("happy_path_invoice.pdf", fake_openai("this is not json"))
        self.assertEqual(r["status"], "AUTO-CLEAR")
        self.assertTrue(r["extraction_method"].startswith("Rule-based fallback"))

    def test_fenced_json_is_parsed(self):
        payload = {"vendor_name": item("Northstar Supplies", GOOD_EVIDENCE["vendor_name"]),
                   "invoice_number": item("NS-INV-1001", GOOD_EVIDENCE["invoice_number"]),
                   "invoice_date": item("04-Nov-2026", GOOD_EVIDENCE["invoice_date"]),
                   "po_number": item("PO-1001", GOOD_EVIDENCE["po_number"]),
                   "subtotal": item("50,000", GOOD_EVIDENCE["subtotal"]),
                   "tax": item("9,000", GOOD_EVIDENCE["tax"]),
                   "total": item("59,000", GOOD_EVIDENCE["total"]), "currency": "INR"}
        r = self.run_with("happy_path_invoice.pdf", fake_openai("```json\n" + json.dumps(payload) + "\n```"))
        self.assertEqual(r["fields"]["total"], 59000.0)


if __name__ == "__main__":
    unittest.main()
