from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import fitz

from database import find_duplicate, get_po, get_prior_po_total, insert_run

StageCallback = Callable[[str, str, str], None]


def _emit(callback: StageCallback | None, stage: str, state: str, detail: str) -> None:
    if callback:
        callback(stage, state, detail)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_text(pdf_bytes: bytes) -> tuple[str, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = [page.get_text("text") for page in doc]
    text = "\n".join(text_parts).strip()
    if len(re.sub(r"\s", "", text)) >= 35:
        return text, "PDF text extraction"

    # Scanned PDFs need OCR. The deployment includes Tesseract through packages.txt.
    try:
        import pytesseract
        from PIL import Image
        import shutil

        if not shutil.which("tesseract"):
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(win_path):
                pytesseract.pytesseract.tesseract_cmd = win_path

        ocr_parts: list[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_parts.append(pytesseract.image_to_string(image))
        ocr_text = "\n".join(ocr_parts).strip()
        if ocr_text:
            return ocr_text, "OCR (Tesseract)"
    except Exception:
        pass
    return text, "PDF text extraction (limited text)"


def _label_value(text: str, labels: list[str]) -> str | None:
    """Read a value after an explicit label separator or directly below a label-only line."""
    lines = text.splitlines()
    for label in labels:
        same_line = re.compile(rf"^\s*(?:{label})\s*[:#|–—-]\s*(.*?)\s*$", re.I)
        label_only = re.compile(rf"^\s*(?:{label})\s*[:#|–—-]?\s*$", re.I)
        for index, line in enumerate(lines):
            match = same_line.match(line)
            if match:
                value = match.group(1).strip().strip("|;")
                if value:
                    return value
            if label_only.match(line):
                for next_line in lines[index + 1:index + 3]:
                    candidate = next_line.strip()
                    if not candidate:
                        continue
                    if re.match(r"(?i)^(?:vendor(?:\s+name)?|supplier(?:\s+name)?|invoice\s+(?:number|no\.?|date|id)|inv\.?\s*(?:no\.?|number)|date\s+of\s+invoice|issue\s+date|date\s+issued|due\s+date|po\s+(?:number|no\.?|ref)|p\.?o\.?\s+(?:number|no\.?|ref)|purchase\s+order|subtotal|sub\s+total|taxable|tax|gst|igst|cgst|sgst|grand\s+total|amount\s+due|amount\s+payable|total\s+due|currency)\b", candidate):
                        break
                    return candidate.strip("|;")
    return None


def _amount_after_label(text: str, labels: list[str]) -> float | None:
    lines = text.splitlines()
    for label in labels:
        same_line = re.compile(rf"^\s*(?:{label})\s*[:#|–—-]\s*(.*?)\s*$", re.I)
        label_only = re.compile(rf"^\s*(?:{label})\s*[:#|–—-]?\s*$", re.I)
        for index, line in enumerate(lines):
            match = same_line.match(line)
            candidates = [match.group(1)] if match else []
            if label_only.match(line):
                candidates.extend(lines[index + 1:index + 3])
            for candidate in candidates:
                amount = _parse_amount(candidate)
                if amount is not None:
                    return amount
    return None


_FIELD_KEYS = ["vendor_name", "invoice_number", "invoice_date", "po_number", "subtotal", "tax", "total"]
_AMOUNT_KEYS = {"subtotal", "tax", "total"}
_FIELD_LABELS = {
    # Anchored labels prevent values from being borrowed from nearby metadata such
    # as Vendor Tax ID, Due Date, or an invoice identifier containing digits.
    "vendor_name": [r"^\s*(?:vendor(?:\s+name)?|supplier(?:\s+name)?|billed\s+from|seller|issued\s+by)\s*(?:[:#|–—-]|$)"],
    "invoice_number": [r"^\s*(?:invoice\s*(?:number|no\.?|#|id)|inv\.?\s*(?:number|no\.?|#)|document\s+id)\s*(?:[:#|–—-]|$)"],
    "invoice_date": [r"^\s*(?:invoice\s+date|date\s+of\s+invoice|issue\s+date|date\s+issued|issued\s+on|billing\s+date)\s*(?:[:#|–—-]|$)"],
    "po_number": [r"^\s*(?:p\.?\s*o\.?\s*(?:number|no\.?|#|ref(?:erence)?)|customer\s+po|client\s+po|purchase\s+order(?:\s*(?:number|no\.?|ref(?:erence)?))?)\s*(?:[:#|–—-]|$)"],
    "subtotal": [r"^\s*(?:subtotal|sub\s+total|taxable\s+(?:value|amount)|net\s+taxable\s+value)\s*(?:[:#|–—-]|$)"],
    "tax": [r"^\s*(?:tax(?:\s+amount)?|gst(?:\s+amount)?|igst(?:\s+amount)?|cgst(?:\s+amount)?|sgst(?:\s+amount)?|vat(?:\s+amount)?|sales\s+tax)\s*(?:[:#|–—-]|$)"],
    "total": [r"^\s*(?:grand\s+total|invoice\s+total|total\s+amount|total\s+payable|amount\s+payable|amount\s+due|total\s+due|balance\s+due|total)\s*(?:[:#|–—-]|$)"],
}
_LABEL_HINTS = {
    "subtotal": ["subtotal", "sub total", "taxable"],
    "tax": ["tax", "gst", "igst", "cgst", "sgst", "vat"],
    "total": ["grand total", "invoice total", "total amount", "total payable", "amount payable", "amount due", "total due", "balance due", "total"],
}


def _field_label_pattern(key: str) -> re.Pattern[str]:
    return re.compile("(?:" + "|".join(_FIELD_LABELS[key]) + ")", re.I)


def _all_field_labels_pattern(exclude: str | None = None) -> re.Pattern[str]:
    pieces = [p for key, patterns in _FIELD_LABELS.items() if key != exclude for p in patterns]
    return re.compile("(?:" + "|".join(pieces) + ")", re.I)


def _looks_like_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    patterns = [
        r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:20\d{2}|\d{2})\b",
        r"\b20\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b",
        r"\b(?:0?[1-9]|[12]\d|3[01])[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-,\s]+20\d{2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}\b",
    ]
    return any(re.search(pattern, value, re.I) for pattern in patterns)


def _value_in_context(key: str, value: Any, context: str) -> bool:
    if value in (None, ""):
        return False
    if key == "invoice_date" and not _looks_like_date(str(value)):
        return False
    if key in _AMOUNT_KEYS:
        amount = _parse_amount(value)
        return amount is not None and _amount_in_text(amount, context)
    token = _alnum(str(value))
    return bool(token) and token in _alnum(context)


def _context_for_field(text: str, key: str, value: Any) -> str | None:
    """Find a value only inside a nearby, field-labelled source context."""
    lines = text.splitlines()
    label_pattern = _field_label_pattern(key)
    other_labels = _all_field_labels_pattern(exclude=key)
    for index, line in enumerate(lines):
        if not label_pattern.search(line):
            continue
        context_lines = [line.strip()]
        for candidate in lines[index + 1:index + 4]:
            candidate = candidate.strip()
            if not candidate:
                continue
            if other_labels.search(candidate):
                break
            context_lines.append(candidate)
            if _value_in_context(key, value, "\n".join(context_lines)):
                break
        context = "\n".join(part for part in context_lines if part)
        if _value_in_context(key, value, context):
            return context[:240]
        # Same-line layouts may have content after an adjacent label; do not
        # scan indefinitely across subsequent fields.
    return None


def _normalise_evidence(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip().casefold()


def _verify_llm_evidence(text: str, key: str, value: Any, evidence: Any) -> tuple[bool, str]:
    """Require verbatim source evidence, the correct field label, and local value association."""
    if not isinstance(evidence, str) or not evidence.strip():
        return False, "The model did not provide source evidence."
    if _normalise_evidence(evidence) not in _normalise_evidence(text):
        return False, "The cited evidence is not a verbatim excerpt from the source document."
    if not _field_label_pattern(key).search(evidence):
        return False, "The cited evidence does not contain the expected field label."
    if not _value_in_context(key, value, evidence):
        return False, "The cited evidence does not contain a valid value for this field."
    source_context = _context_for_field(text, key, value)
    if not source_context:
        return False, "The value was not found next to the expected field label in the source document."
    return True, source_context


def _detect_currency(text: str) -> tuple[str | None, str]:
    """Detect only unambiguous currency indicators in a monetary context; bare '$' is unknown."""
    explicit = re.search(r"(?im)^\s*currency\s*[:#|–—-]?\s*([A-Z]{3})\b", text)
    if explicit:
        code = explicit.group(1).upper()
        if code in {"INR", "USD", "EUR", "GBP", "CAD", "AUD", "SGD", "JPY"}:
            return code, explicit.group(0).strip()[:120]
        return None, f"Unsupported or unrecognised currency code: {code}."

    # Clear symbols are reliable. A bare dollar sign is not, because it is used by
    # USD, CAD, AUD and several other currencies.
    symbol_patterns = [("INR", "₹"), ("EUR", "€"), ("GBP", "£")]
    symbol_hits = [(code, symbol) for code, symbol in symbol_patterns if symbol in text]
    if len(symbol_hits) == 1:
        return symbol_hits[0][0], symbol_hits[0][1]
    if len(symbol_hits) > 1:
        return None, "Conflicting currency symbols found."
    if re.search(r"(?i)\bRs\.?\s*\d", text):
        return "INR", re.search(r"(?i)\bRs\.?\s*\d[\d,]*(?:\.\d{1,2})?", text).group(0)[:120]

    codes = ["INR", "USD", "EUR", "GBP", "CAD", "AUD", "SGD", "JPY"]
    hits: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        for code in codes:
            # A code must stand alone, appear beside a monetary amount, or be in
            # an explicit amount/currency heading. Digits inside IDs are not enough.
            if stripped.upper() == code:
                hits.append((code, stripped))
                continue
            match = re.search(rf"(?i)\b{code}\b(?=\s*[\d,]+(?:\.\d{{1,2}})?|\s*[)])", line)
            heading = re.search(rf"(?i)\b(?:amount|total|subtotal|taxable|tax|payable|due)\s*\([^)]*\b{code}\b[^)]*\)", line)
            if match or heading:
                hits.append((code, (match or heading).group(0)[:120]))
    unique = {code for code, _ in hits}
    if len(unique) == 1:
        code = next(iter(unique))
        evidence = next(value for found_code, value in hits if found_code == code)
        return code, evidence
    if len(unique) > 1:
        return None, "Conflicting currency indicators found in monetary context."
    return None, "No unambiguous currency code or symbol found. A bare '$' is treated as ambiguous."


def _regex_extract(text: str) -> dict[str, Any]:
    vendor = _label_value(text, [r"Vendor(?: Name)?", r"Supplier(?: Name)?", r"Billed From", r"Seller", r"Issued By"])
    invoice_number = _label_value(text, [r"Invoice(?: Number| No\.?| #| ID)", r"Inv(?:oice)? No\.?", r"Document ID"])
    invoice_date = _label_value(text, [r"Invoice Date", r"Date of Invoice", r"Issue Date", r"Date Issued", r"Issued On", r"Billing Date"])
    po_number = _label_value(text, [r"P\.?\s*O\.?(?: Number| No\.?| Ref(?:erence)?| #)?", r"Customer PO", r"Client PO", r"Purchase Order(?: Number| No\.?| Ref(?:erence)?)?"])
    subtotal = _amount_after_label(text, [r"Subtotal", r"Sub Total", r"Taxable (?:Value|Amount)", r"Net Taxable Value"])
    tax = _amount_after_label(text, [r"Tax(?: Amount)?\b", r"GST(?: Amount)?\b", r"IGST(?: Amount)?\b", r"VAT(?: Amount)?\b", r"Sales Tax\b"])
    total = _amount_after_label(text, [r"Grand Total", r"Invoice Total", r"Total Amount", r"Amount Payable", r"Amount Due", r"Total Due", r"Total Payable", r"Balance Due", r"Total"])
    currency, _ = _detect_currency(text)
    return {
        "vendor_name": vendor,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "po_number": po_number,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": currency,
    }


def _ground_rule_fields(text: str, proposed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    fields = dict(proposed)
    provenance: dict[str, dict[str, Any]] = {}
    for key in _FIELD_KEYS:
        value = fields.get(key)
        evidence = _context_for_field(text, key, value) if value not in (None, "") else None
        if evidence:
            provenance[key] = {"source": "rule", "verified": True, "evidence": evidence, "note": ""}
        else:
            fields[key] = None
            provenance[key] = {"source": "none", "verified": False, "evidence": "", "note": "Not found in the correct labelled context."}
    currency, currency_evidence = _detect_currency(text)
    fields["currency"] = currency
    provenance["currency"] = {
        "source": "rule" if currency else "none", "verified": bool(currency),
        "evidence": currency_evidence, "note": "" if currency else currency_evidence,
    }
    return fields, provenance


def get_llm_settings() -> dict[str, Any] | None:
    """Pick the first configured provider. Groq and Gemini are free, OpenAI-compatible options."""
    generic_key = os.getenv("LLM_API_KEY", "").strip()
    generic_url = os.getenv("LLM_BASE_URL", "").strip()
    if generic_key and generic_url:
        return {"provider": os.getenv("LLM_PROVIDER_NAME", "Custom"), "api_key": generic_key,
                "base_url": generic_url, "model": os.getenv("LLM_MODEL", "").strip() or "unspecified"}
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        return {"provider": "Groq", "api_key": groq_key, "base_url": "https://api.groq.com/openai/v1",
                "model": os.getenv("GROQ_MODEL", "").strip() or "llama-3.3-70b-versatile"}
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        return {"provider": "OpenAI", "api_key": openai_key, "base_url": None,
                "model": os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"}
    return None


def _safe_error(exc: Exception, api_key: str) -> str:
    """Readable diagnostic that never includes the API key."""
    status = getattr(exc, "status_code", None)
    code = None
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            code = err.get("code") or err.get("type")
    message = type(exc).__name__
    if status:
        message += f" (HTTP {status})"
    if code:
        message += f" · {code}"
    hints = {401: "API key rejected", 403: "access denied", 404: "model name not found",
             429: "rate limit or quota exhausted"}
    if status in hints:
        message += f" · {hints[status]}"
    return message.replace(api_key, "***") if api_key else message


def _norm_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _parse_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def _amount_in_text(amount: float, text: str) -> bool:
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            if abs(float(token.replace(",", "")) - amount) < 0.005:
                return True
        except ValueError:
            continue
    return False


def _parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.I | re.M).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object")
    return data


_SYSTEM_PROMPT = (
    "You extract fields from invoice text. Return ONE JSON object with exactly these keys: "
    "vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, currency. "
    "Each of the first seven keys must be an object {\"value\": ..., \"evidence\": ...}. "
    "Evidence MUST be an exact, contiguous excerpt copied verbatim from the source text. "
    "It MUST include the field's own label and its value together; do not cite a value from another field. "
    "For example, never use digits from an invoice number as an invoice date. "
    "Copy text values exactly as written (do not reformat dates). Amounts are plain numbers without commas or symbols. "
    "If a value is absent or ambiguous, use {\"value\": null, \"evidence\": null}. "
    "NEVER guess, infer, or calculate a missing value. "
    "Currency must be explicitly supported by a currency code or unambiguous symbol in the text; otherwise null. "
    "Return only JSON."
)


def _llm_extract(text: str, fallback: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, dict[str, Any]]]:
    """LLM proposes; field-specific source grounding and deterministic rules dispose."""
    grounded_fallback, fallback_provenance = _ground_rule_fields(text, fallback)
    settings = get_llm_settings()
    if settings is None:
        diag = {"status": "not_configured", "message": "No LLM API key configured."}
        return grounded_fallback, "Rule-based extraction", diag, fallback_provenance
    started = time.perf_counter()
    try:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": settings["api_key"], "timeout": 45.0, "max_retries": 1}
        if settings["base_url"]:
            kwargs["base_url"] = settings["base_url"]
        client = OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=settings["model"],
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": text[:18000]}],
        )
        data = _parse_llm_json(response.choices[0].message.content or "{}")
    except Exception as exc:
        diag = {"status": "error", "provider": settings["provider"], "model": settings["model"],
                "message": _safe_error(exc, settings["api_key"])}
        return grounded_fallback, "Rule-based fallback (AI unavailable)", diag, fallback_provenance

    fields: dict[str, Any] = {}
    provenance: dict[str, dict[str, Any]] = {}
    rejected: list[str] = []
    gap_filled: list[str] = []
    rejection_reasons: dict[str, str] = {}
    for key in _FIELD_KEYS:
        item = data.get(key)
        value = item.get("value") if isinstance(item, dict) else None
        evidence = item.get("evidence") if isinstance(item, dict) else None
        if value in (None, ""):
            value = None
        if value is not None and key in _AMOUNT_KEYS:
            value = _parse_amount(value)
        elif value is not None:
            value = str(value).strip()
        verified, source_context = _verify_llm_evidence(text, key, value, evidence) if value is not None else (False, "")
        if value is not None and verified:
            fields[key] = value
            provenance[key] = {"source": "llm", "verified": True, "evidence": source_context, "note": ""}
            continue
        if value is not None:
            rejected.append(key)
            _, reason = _verify_llm_evidence(text, key, value, evidence)
            rejection_reasons[key] = reason
        fallback_value = grounded_fallback.get(key)
        fallback_prov = fallback_provenance.get(key, {})
        if fallback_value not in (None, "") and fallback_prov.get("verified"):
            fields[key] = fallback_value
            note = "AI value rejected: " + rejection_reasons.get(key, "no valid evidence") if value is not None else "AI returned no value; verified rule-based value used."
            provenance[key] = {**fallback_prov, "note": note}
            gap_filled.append(key)
        else:
            fields[key] = None
            note = rejection_reasons.get(key, "Not found in the correct labelled context.") if value is not None else "Not found in document."
            provenance[key] = {"source": "none", "verified": False, "evidence": "", "note": note}

    # Currency is not trusted from the LLM: only deterministic document indicators are used.
    currency, currency_evidence = _detect_currency(text)
    fields["currency"] = currency
    provenance["currency"] = {
        "source": "rule" if currency else "none", "verified": bool(currency),
        "evidence": currency_evidence, "note": "" if currency else currency_evidence,
    }
    proposed_currency = str(data.get("currency") or "").strip().upper()
    if proposed_currency and currency and proposed_currency != currency:
        rejected.append("currency")
        rejection_reasons["currency"] = f"Model currency {proposed_currency} conflicts with document-detected currency {currency}."

    diag = {"status": "ok", "provider": settings["provider"], "model": settings["model"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "rejected_fields": rejected, "rejection_reasons": rejection_reasons,
            "gap_filled_fields": gap_filled, "message": "AI extraction succeeded; field evidence was checked against labelled source context."}
    return fields, f"LLM extraction ({settings['provider']} · {settings['model']})", diag, provenance


def llm_health_check() -> tuple[bool, str]:
    """Tiny real API call used by the Controls page and test_llm_connection.py."""
    settings = get_llm_settings()
    if settings is None:
        return False, "No LLM API key configured."
    try:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": settings["api_key"], "timeout": 30.0, "max_retries": 0}
        if settings["base_url"]:
            kwargs["base_url"] = settings["base_url"]
        started = time.perf_counter()
        OpenAI(**kwargs).chat.completions.create(
            model=settings["model"], max_tokens=5,
            messages=[{"role": "user", "content": "Reply with the word OK."}],
        )
        return True, f"{settings['provider']} · {settings['model']} responded in {int((time.perf_counter() - started) * 1000)} ms."
    except Exception as exc:
        return False, f"{settings['provider']} · {settings['model']}: {_safe_error(exc, settings['api_key'])}"


def _normalise_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _format_money(value: float, currency: str | None = None) -> str:
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{value:,.2f}"


def process_invoice(
    pdf_bytes: bytes,
    file_name: str,
    db_path: str,
    stage_callback: StageCallback | None = None,
    document_dir: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = f"CM-{datetime.now(timezone.utc):%y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    file_hash = sha256_bytes(pdf_bytes)

    _emit(stage_callback, "Document ingestion", "running", "Checking file integrity and opening the PDF.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("The uploaded file does not appear to be a valid PDF.")
    if len(pdf_bytes) > 15 * 1024 * 1024:
        raise ValueError("File is larger than the 15 MB limit. Please upload a smaller PDF.")
    _emit(stage_callback, "Document ingestion", "complete", f"PDF accepted · {len(pdf_bytes) / 1024:.1f} KB")

    _emit(stage_callback, "Text extraction", "running", "Reading embedded PDF text; OCR is used when the PDF is image-based.")
    extracted_text, extraction_mode = _extract_text(pdf_bytes)
    _emit(stage_callback, "Text extraction", "complete", f"{extraction_mode} · {len(extracted_text)} characters extracted")

    unreadable = len(re.sub(r"\s", "", extracted_text)) < 35
    _emit(stage_callback, "Field extraction", "running", "Extracting vendor, invoice identifiers, PO reference and amounts.")
    if unreadable:
        fields = {key: None for key in _FIELD_KEYS}
        fields["currency"] = None
        extraction_method = "Unreadable document"
        llm_diag = {"status": "skipped", "message": "No readable text, so AI extraction was skipped."}
        provenance = {key: {"source": "none", "verified": False, "evidence": "", "note": "Document unreadable."} for key in _FIELD_KEYS}
        provenance["currency"] = {"source": "none", "verified": False, "evidence": "", "note": "Currency unavailable."}
    else:
        fallback_fields = _regex_extract(extracted_text)
        fields, extraction_method, llm_diag, provenance = _llm_extract(extracted_text, fallback_fields)
    field_keys = _FIELD_KEYS
    present_count = sum(fields.get(key) not in (None, "") for key in field_keys)
    grounded_count = sum(1 for key in field_keys if provenance.get(key, {}).get("verified"))
    extraction_completeness = round(present_count / len(field_keys), 2)
    fields["_provenance"] = provenance
    fields["_extraction"] = {**llm_diag, "text_extraction_mode": extraction_mode,
                             "grounded_fields": grounded_count, "required_fields": len(field_keys),
                             "present_fields": present_count, "completeness_is_not_confidence": True}
    detail = f"{present_count}/{len(field_keys)} required fields found · {grounded_count} source-grounded · {extraction_method}"
    if llm_diag.get("status") in ("error", "skipped"):
        detail += f" · {llm_diag['message']}"
    _emit(stage_callback, "Field extraction", "complete", detail)

    _emit(stage_callback, "Duplicate screening", "running", "Checking file fingerprint and previously processed vendor invoice IDs.")
    duplicate = None if unreadable else find_duplicate(fields.get("vendor_name"), fields.get("invoice_number"), file_hash, db_path)
    if duplicate:
        _emit(stage_callback, "Duplicate screening", "complete", f"Potential duplicate matches previous run {duplicate['run_id']}.")
    else:
        _emit(stage_callback, "Duplicate screening", "complete", "No previous matching file or vendor invoice ID found.")

    _emit(stage_callback, "Purchase order matching", "running", "Looking up the referenced PO and checking vendor ownership.")
    po = get_po(fields.get("po_number"), db_path)
    _emit(stage_callback, "Purchase order matching", "complete", "PO found and vendor matched." if po else "No exact PO match found.")

    _emit(stage_callback, "Policy evaluation", "running", "Applying deterministic finance controls and cumulative PO exposure checks.")
    checks: list[dict[str, str]] = []
    blocked_reasons: list[str] = []
    review_reasons: list[str] = []

    required_labels = {
        "vendor_name": "Vendor name",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
        "po_number": "PO number",
        "subtotal": "Subtotal",
        "tax": "Tax",
        "total": "Invoice total",
    }
    missing = [label for key, label in required_labels.items() if fields.get(key) in (None, "")]
    checks.append({"check": "Required fields", "result": "PASS" if not missing else "REVIEW", "detail": "All required fields found." if not missing else "Missing: " + ", ".join(missing)})
    if missing:
        review_reasons.append("Required invoice fields are missing or could not be extracted: " + ", ".join(missing) + ".")

    document_currency = fields.get("currency")
    if document_currency:
        checks.append({"check": "Currency detection", "result": "PASS", "detail": f"Document currency detected from source: {document_currency}."})
    else:
        checks.append({"check": "Currency detection", "result": "REVIEW", "detail": "No unambiguous currency code or symbol was found. A bare '$' is treated as ambiguous."})
        review_reasons.append("Invoice currency could not be verified from the document.")

    arithmetic_ok = False
    if all(isinstance(fields.get(k), (int, float)) for k in ["subtotal", "tax", "total"]):
        delta = abs(float(fields["subtotal"]) + float(fields["tax"]) - float(fields["total"]))
        arithmetic_ok = delta <= max(1.0, abs(float(fields["total"])) * 0.01)
        checks.append({"check": "Arithmetic integrity", "result": "PASS" if arithmetic_ok else "REVIEW", "detail": f"Subtotal + tax differs from total by {_format_money(delta, fields.get('currency'))}." if not arithmetic_ok else "Subtotal + tax reconciles to invoice total within 1%."})
        if not arithmetic_ok:
            review_reasons.append("Subtotal plus tax does not reconcile with the stated invoice total.")
    else:
        checks.append({"check": "Arithmetic integrity", "result": "REVIEW", "detail": "Cannot validate arithmetic because one or more amounts are missing."})

    if duplicate:
        checks.append({"check": "Duplicate detection", "result": "BLOCK", "detail": f"Matches prior run {duplicate['run_id']} ({duplicate['file_name']})."})
        blocked_reasons.append(f"Duplicate invoice detected. It was previously processed as {duplicate['run_id']}.")
    else:
        checks.append({"check": "Duplicate detection", "result": "PASS", "detail": "No duplicate found in recorded run history."})

    if po is None:
        checks.append({"check": "PO match", "result": "REVIEW", "detail": f"PO {fields.get('po_number') or 'not provided'} was not found in the PO register."})
        review_reasons.append("No matching purchase order was found in the procurement register.")
    else:
        vendor_match = _normalise_name(fields.get("vendor_name")) == _normalise_name(po["vendor_name"])
        if not vendor_match:
            checks.append({"check": "PO vendor ownership", "result": "BLOCK", "detail": f"Invoice vendor '{fields.get('vendor_name')}' does not match PO vendor '{po['vendor_name']}'."})
            blocked_reasons.append("The invoice vendor does not match the vendor assigned to the purchase order.")
        else:
            checks.append({"check": "PO vendor ownership", "result": "PASS", "detail": f"Vendor matches PO register: {po['vendor_name']} ({po['vendor_id']})."})

        po_active = str(po["status"]).upper() == "ACTIVE"
        checks.append({"check": "PO status", "result": "PASS" if po_active else "BLOCK", "detail": f"PO status is {po['status']}."})
        if not po_active:
            blocked_reasons.append(f"Purchase order is not active (status: {po['status']}).")

        po_currency = str(po.get("currency") or "").upper()
        currency_matches = bool(document_currency and po_currency and document_currency == po_currency)
        if not document_currency:
            checks.append({"check": "Currency consistency", "result": "REVIEW", "detail": f"Invoice currency is unknown; PO is denominated in {po_currency or 'an unspecified currency'}."})
            if "Invoice currency could not be verified from the document." not in review_reasons:
                review_reasons.append("Invoice currency could not be verified against the purchase order.")
        elif not po_currency or document_currency != po_currency:
            checks.append({"check": "Currency consistency", "result": "REVIEW", "detail": f"Invoice currency {document_currency} does not match PO currency {po_currency or 'not configured'}. No FX conversion is configured."})
            review_reasons.append(f"Invoice currency ({document_currency}) does not match PO currency ({po_currency or 'not configured'}); manual review is required.")
        else:
            checks.append({"check": "Currency consistency", "result": "PASS", "detail": f"Invoice and PO currencies both use {document_currency}."})

        if duplicate:
            checks.append({"check": "Cumulative PO exposure", "result": "INFO", "detail": "Not added to cumulative exposure because this invoice was already recorded and is blocked as a duplicate."})
        elif not currency_matches:
            checks.append({"check": "Cumulative PO exposure", "result": "INFO", "detail": "Skipped because invoice and PO currencies are not verified as matching."})
        elif fields.get("total") is not None:
            prior_total = get_prior_po_total(fields.get("po_number"), db_path)
            cumulative = prior_total + float(fields["total"])
            po_amount = float(po["po_amount"])
            tolerance = po_amount * float(po["tolerance_pct"]) / 100.0
            excess = cumulative - po_amount
            detail = (
                f"Previously recorded: {_format_money(prior_total, po_currency)}; this invoice: "
                f"{_format_money(float(fields['total']), po_currency)}; cumulative: "
                f"{_format_money(cumulative, po_currency)} against PO {_format_money(po_amount, po_currency)}."
            )
            if excess > tolerance:
                checks.append({"check": "Cumulative PO exposure", "result": "REVIEW", "detail": detail + f" Exceeds PO by {_format_money(excess, po_currency)}, above tolerance of {_format_money(tolerance, po_currency)}."})
                review_reasons.append("Cumulative invoices against this PO exceed its value beyond the configured tolerance.")
            else:
                checks.append({"check": "Cumulative PO exposure", "result": "PASS", "detail": detail + (f" Within configured tolerance ({po['tolerance_pct']}%)." if excess > 0 else " Within PO value." )})
        else:
            checks.append({"check": "Cumulative PO exposure", "result": "REVIEW", "detail": "Cannot calculate PO exposure because invoice total is missing."})

    if unreadable:
        checks = [{"check": "Document readability", "result": "REVIEW", "detail": "No readable text could be extracted, even after OCR. Other controls were not applied because there is nothing reliable to check."}]
        blocked_reasons = []
        review_reasons = ["No readable text could be extracted from this document. Ask the vendor for a clearer copy or upload a higher-quality scan."]

    if extraction_method.startswith("Rule-based fallback"):
        checks.append({"check": "Extraction service", "result": "INFO", "detail": f"AI extraction was unavailable ({llm_diag.get('message', 'unknown reason')}); deterministic label-based extraction was used."})
    else:
        checks.append({"check": "Extraction service", "result": "INFO", "detail": extraction_method + "."})
    rejected = llm_diag.get("rejected_fields") or []
    checks.append({"check": "Source grounding", "result": "INFO", "detail": f"{grounded_count}/{len(field_keys)} required fields matched a field-specific labelled context. Evidence must be verbatim and adjacent to the correct label." + (f" AI values discarded: {', '.join(rejected)}." if rejected else "")})

    if blocked_reasons:
        status = "BLOCKED"
        reasons = blocked_reasons + review_reasons
    elif review_reasons:
        status = "NEEDS REVIEW"
        reasons = review_reasons
    else:
        status = "AUTO-CLEAR"
        reasons = ["All configured checks passed. Invoice is ready for AP approval."]

    decision_reason = " ".join(reasons)
    _emit(stage_callback, "Policy evaluation", "complete", f"Decision: {status} · {len(checks)} checks recorded")

    processing_ms = int((time.perf_counter() - started) * 1000)
    created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    document_path = None
    if document_dir:
        from pathlib import Path
        target_dir = Path(document_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        document_path = str((target_dir / f"{run_id}.pdf").resolve())
        (target_dir / f"{run_id}.pdf").write_bytes(pdf_bytes)

    record = {
        "run_id": run_id,
        "created_at": created_at,
        "file_name": file_name,
        "file_sha256": file_hash,
        "vendor_name": fields.get("vendor_name"),
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "po_number": fields.get("po_number"),
        "invoice_total": fields.get("total"),
        "currency": fields.get("currency"),
        "status": status,
        "decision_reason": decision_reason,
        "extraction_method": extraction_method,
        "confidence": None,  # Deprecated legacy field; completeness is stored separately.
        "extraction_completeness": extraction_completeness,
        "document_path": document_path,
        "fields": fields,
        "checks": checks,
        "extracted_text": extracted_text[:20000],
        "processing_ms": processing_ms,
    }
    insert_run(record, db_path)
    _emit(stage_callback, "Audit trail", "complete", f"Saved decision, checks and extracted evidence as {run_id}.")
    return record
