from __future__ import annotations

import html
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import fitz

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import (  # noqa: E402
    DB_PATH,
    clear_demo_history,
    get_connection,
    get_exception_queue,
    get_po,
    get_purchase_orders,
    get_review_queue,
    get_reviewed,
    get_run,
    get_runs,
    initialize_database,
    set_review,
)
from processor import process_invoice, get_llm_settings, llm_health_check  # noqa: E402
from batch_processing import process_batch  # noqa: E402

st.set_page_config(
    page_title="ClearMatch | AP Control Tower",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit Cloud secrets and local environment variables are both supported.
try:
    for _name in [
        "GROQ_API_KEY", "GROQ_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
        "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER_NAME",
    ]:
        if _name in st.secrets:
            os.environ[_name] = str(st.secrets[_name])
except Exception:
    pass

initialize_database()

# -----------------------------------------------------------------------------
# Design system — a finance-operations workspace, not a generic Streamlit demo.
# -----------------------------------------------------------------------------
CUSTOM_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root {
  --ink:#17243b; --muted:#708097; --line:#e5eaf2; --canvas:#f4f6fa;
  --navy:#101d33; --navy2:#172945; --blue:#4263eb; --blue-soft:#edf1ff;
  --teal:#0f9b83; --teal-soft:#e8f7f3; --amber:#b7791f; --amber-soft:#fff5e5;
  --red:#c2413a; --red-soft:#fff0ef; --white:#fff;
}
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--canvas); color:var(--ink); }
[data-testid="stAppViewContainer"] { background:var(--canvas); }
.block-container { max-width:1540px; padding-top:1.65rem; padding-bottom:3rem; }
h1,h2,h3,h4 { font-family:'Manrope',sans-serif !important; letter-spacing:-.035em; color:var(--ink); }
h1 { font-size:2rem !important; font-weight:800 !important; }
h2 { font-size:1.5rem !important; font-weight:800 !important; }
h3 { font-size:1.12rem !important; font-weight:750 !important; }
p,li { color:#45546a; }
[data-testid="stHeader"] { background:rgba(244,246,250,.86); }
[data-testid="stSidebar"] { background:linear-gradient(180deg,var(--navy) 0%,#142640 100%); border-right:1px solid #253955; }
[data-testid="stSidebar"] > div { background:transparent; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] label { color:#dbe5f5 !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#9fb0c8 !important; }
[data-testid="stSidebar"] hr { border-color:#2b3e5b; }
[data-testid="stSidebar"] div[role="radiogroup"] { gap:5px; }
[data-testid="stSidebar"] div[role="radiogroup"] label {
  border-radius:10px; padding:9px 11px; margin:1px 0; border:1px solid transparent;
  background:transparent; transition:all .15s ease;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background:#203653; border-color:#304765; }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
  background:#263d61; border-color:#45638e; box-shadow:inset 3px 0 0 #7c9cff;
}
[data-testid="stSidebar"] div[role="radiogroup"] label p { color:#eaf0fa !important; font-weight:650; }
[data-testid="stSidebar"] [data-testid="stMetric"] { background:#1a2d49; border:1px solid #314764; border-radius:12px; padding:10px 12px; }
[data-testid="stSidebar"] [data-testid="stMetricLabel"] p { color:#9fb0c8 !important; font-size:.75rem; }
[data-testid="stSidebar"] [data-testid="stMetricValue"] { color:#fff !important; font-family:'Manrope',sans-serif; }
div[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:15px; padding:14px 16px; box-shadow:0 2px 8px rgba(20,39,69,.025); }
div[data-testid="stMetricLabel"] p { color:var(--muted); font-size:.78rem; font-weight:650; }
div[data-testid="stMetricValue"] { color:var(--ink); font-family:'Manrope',sans-serif; font-weight:800; }
.stButton > button, .stDownloadButton > button { border-radius:10px; min-height:2.55rem; font-weight:700; border:1px solid #dbe2ec; transition:all .15s ease; }
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"],
button[data-testid="baseButton-primary"] {
  background:var(--blue) !important; border-color:var(--blue) !important; color:#fff !important;
  box-shadow:0 4px 10px rgba(66,99,235,.16); font-weight:750 !important;
}
.stButton > button[kind="primary"] *,
.stButton > button[data-testid="stBaseButton-primary"] *,
button[data-testid="baseButton-primary"] * { color:#fff !important; }
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
  background:#3454d1 !important; border-color:#3454d1 !important;
  box-shadow:0 7px 16px rgba(66,99,235,.22);
}
.stDownloadButton > button { background:#fff; color:#34445b; }
[data-testid="stFileUploader"] section { background:#fbfcfe; border:1.5px dashed #cbd5e3; border-radius:14px; }
[data-testid="stFileUploader"] section:hover { border-color:#8098e8; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; overflow:hidden; }
[data-testid="stTabs"] button { font-weight:700; }
[data-testid="stExpander"] { border:1px solid var(--line); border-radius:11px; background:#fff; }
[data-testid="stAlert"] { border-radius:12px; }
hr { border-color:var(--line); }
.small-muted { color:var(--muted); font-size:.82rem; }
.eyebrow { color:#6479bb; font-size:.68rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; margin-bottom:.38rem; }
.page-title { font-family:'Manrope',sans-serif; font-size:2.08rem; line-height:1.08; letter-spacing:-.055em; font-weight:800; color:var(--ink); }
.page-subtitle { color:#718096; margin-top:.45rem; font-size:.92rem; max-width:850px; }
.topline { display:flex; justify-content:space-between; align-items:center; margin-bottom:1.2rem; gap:1rem; }
.live-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#16a37a; margin-right:7px; box-shadow:0 0 0 4px rgba(22,163,122,.10); }
.surface { background:#fff; border:1px solid var(--line); border-radius:16px; padding:17px 19px; box-shadow:0 2px 10px rgba(27,45,75,.025); }
.surface-tight { background:#fff; border:1px solid var(--line); border-radius:13px; padding:13px 15px; }
.hero { background:linear-gradient(115deg,#142844 0%,#1f3b62 62%,#31558a 100%); color:#fff; border-radius:20px; padding:25px 27px; position:relative; overflow:hidden; box-shadow:0 10px 24px rgba(18,39,69,.12); }
.hero:after { content:''; position:absolute; right:-46px; top:-110px; width:320px; height:320px; border:1px solid rgba(255,255,255,.12); border-radius:50%; box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025); }
.hero-kicker { color:#adbfeb; font-weight:800; font-size:.68rem; letter-spacing:.16em; text-transform:uppercase; }
.hero-title { font-family:'Manrope',sans-serif; font-size:1.9rem; color:#fff; font-weight:800; letter-spacing:-.05em; line-height:1.1; margin-top:8px; }
.hero-copy { color:#d5e0f1; font-size:.9rem; max-width:650px; margin-top:9px; }
.hero-stat { color:#fff; font-family:'Manrope',sans-serif; font-size:1.65rem; font-weight:800; }
.hero-stat-label { color:#bdcce0; font-size:.73rem; }
.kpi { background:#fff; border:1px solid var(--line); border-radius:15px; padding:15px 17px; height:100%; }
.kpi-label { color:#78869a; font-size:.74rem; font-weight:700; }
.kpi-value { color:var(--ink); font-family:'Manrope',sans-serif; font-size:1.65rem; font-weight:800; letter-spacing:-.045em; margin-top:4px; }
.kpi-foot { color:#8995a6; font-size:.72rem; margin-top:3px; }
.kpi-accent { width:27px; height:3px; border-radius:5px; margin-bottom:12px; }
.kpi-blue .kpi-accent { background:#5574ed; } .kpi-green .kpi-accent { background:#13a27e; }
.kpi-amber .kpi-accent { background:#e6a23c; } .kpi-red .kpi-accent { background:#d65b56; }
.section-head { display:flex; align-items:center; justify-content:space-between; margin:20px 0 10px; }
.section-head-title { font-family:'Manrope',sans-serif; font-size:1.02rem; color:var(--ink); font-weight:800; }
.section-head-note { color:#8a96a7; font-size:.75rem; }
.chip { display:inline-flex; align-items:center; padding:4px 9px; border-radius:99px; font-size:.68rem; font-weight:800; letter-spacing:.02em; white-space:nowrap; }
.chip-green { color:#11785d; background:#e5f6ef; } .chip-amber { color:#95610e; background:#fff2d9; }
.chip-red { color:#b83f39; background:#ffebea; } .chip-blue { color:#3f5dc8; background:#edf1ff; }
.chip-slate { color:#67758a; background:#eef1f5; }
.run-id { font-family:ui-monospace,Consolas,monospace; font-size:.75rem; color:#68778c; }
.field-card { border:1px solid #e8edf4; border-radius:11px; padding:10px 12px; background:#fff; margin-bottom:8px; }
.field-label { color:#7c899b; font-size:.69rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; }
.field-value { color:#1b2940; font-weight:750; font-size:.93rem; margin-top:3px; word-break:break-word; }
.evidence-line { color:#8190a4; font-size:.73rem; margin-top:5px; }
.stage-row { display:flex; gap:12px; align-items:flex-start; padding:11px 12px; border:1px solid #e7ecf3; border-radius:11px; background:#fff; margin:6px 0; }
.stage-node { width:24px; height:24px; flex:0 0 24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:.72rem; font-weight:800; background:#eef1f5; color:#7c899a; }
.stage-node.done { background:#e5f6ef; color:#148367; } .stage-node.active { background:#edf1ff; color:#4263eb; }
.stage-title { font-weight:750; color:#29384e; font-size:.82rem; }
.stage-detail { color:#8491a3; font-size:.73rem; margin-top:2px; }
.exposure-track { height:8px; background:#edf0f5; border-radius:99px; overflow:hidden; margin-top:7px; }
.exposure-fill { height:100%; border-radius:99px; }
.empty-state { border:1px dashed #cbd5e1; background:#fbfcfe; border-radius:15px; padding:28px; text-align:center; color:#7d8ba0; }
.footer-note { color:#95a0af; font-size:.72rem; text-align:center; padding-top:10px; }
@media (max-width: 850px) { .page-title{font-size:1.65rem;} .hero-title{font-size:1.5rem;} .block-container{padding-left:1rem;padding-right:1rem;} }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------
def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def money(value: Any, currency: str | None = None) -> str:
    if value is None or pd.isna(value):
        return "Not extracted"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{float(value):,.2f}"


def chip(status: str) -> str:
    cls = {
        "AUTO-CLEAR": "chip-green", "APPROVED": "chip-green", "PASS": "chip-green",
        "NEEDS REVIEW": "chip-amber", "REVIEW": "chip-amber", "PENDING": "chip-amber",
        "BLOCKED": "chip-red", "REJECTED": "chip-red", "FAIL": "chip-red",
        "INFO": "chip-blue", "ERROR": "chip-slate",
    }.get(str(status).upper(), "chip-slate")
    return f'<span class="chip {cls}">{esc(status)}</span>'


def section_head(title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="section-head"><div class="section-head-title">{esc(title)}</div>'
        f'<div class="section-head-note">{esc(note)}</div></div>',
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, subtitle: str, tag: str = "LIVE WORKSPACE") -> None:
    now = datetime.now().astimezone().strftime("%d %b %Y · %I:%M %p")
    st.markdown(
        f'<div class="topline"><div><div class="eyebrow">{esc(kicker)}</div>'
        f'<div class="page-title">{esc(title)}</div><div class="page-subtitle">{esc(subtitle)}</div></div>'
        f'<div style="text-align:right;min-width:150px"><div style="font-size:.7rem;color:#8290a3;font-weight:800;letter-spacing:.1em"><span class="live-dot"></span>{esc(tag)}</div>'
        f'<div style="font-size:.76rem;color:#8b97a8;margin-top:8px">{esc(now)}</div></div></div>',
        unsafe_allow_html=True,
    )


def kpi_grid(items: list[tuple[str, str, str, str]]) -> None:
    cols = st.columns(len(items), gap="medium")
    for col, (label, value, foot, accent) in zip(cols, items):
        with col:
            st.markdown(
                f'<div class="kpi kpi-{esc(accent)}"><div class="kpi-accent"></div>'
                f'<div class="kpi-label">{esc(label)}</div><div class="kpi-value">{esc(value)}</div>'
                f'<div class="kpi-foot">{esc(foot)}</div></div>', unsafe_allow_html=True,
            )


def brand() -> None:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin:4px 0 3px">'
        '<div style="width:34px;height:34px;border-radius:11px;background:linear-gradient(145deg,#6f8cff,#3d5ed7);display:flex;align-items:center;justify-content:center;color:white;font-size:19px;font-weight:900;box-shadow:0 5px 15px #08172c">◈</div>'
        '<div><div style="font-family:Manrope;font-size:1.36rem;font-weight:850;letter-spacing:-.06em;color:#fff">ClearMatch</div>'
        '<div style="font-size:.65rem;color:#9fb0c8;letter-spacing:.13em;text-transform:uppercase;font-weight:800">AP CONTROL TOWER</div></div></div>',
        unsafe_allow_html=True,
    )


def _field_display_value(key: str, value: Any, currency: str | None) -> str:
    if value in (None, ""):
        return "Not found"
    if key in {"subtotal", "tax", "total"}:
        return money(value, currency)
    return str(value)


def load_document_bytes(record: dict) -> bytes | None:
    raw_path = record.get("document_path")
    if not raw_path:
        return None
    try:
        root = (BASE_DIR / "data" / "documents").resolve()
        path = Path(raw_path).resolve()
        if root not in path.parents or not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def render_pdf_preview(pdf_bytes: bytes) -> None:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if not doc.page_count:
                st.warning("This PDF contains no pages.")
                return
            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            st.image(pix.tobytes("png"), caption=f"Source document · page 1 of {doc.page_count}", use_container_width=True)
            if doc.page_count > 1:
                st.caption(f"{doc.page_count} pages · preview shows the first page")
    except Exception:
        st.warning("Preview unavailable. The source PDF remains available for download.")


def render_field_cards(fields: dict, compact: bool = False) -> None:
    provenance = fields.get("_provenance", {})
    currency = fields.get("currency")
    items = [
        ("Vendor name", "vendor_name"), ("Invoice number", "invoice_number"),
        ("Invoice date", "invoice_date"), ("Purchase order", "po_number"),
        ("Subtotal", "subtotal"), ("Tax", "tax"), ("Invoice total", "total"),
    ]
    cols = st.columns(2 if not compact else 1, gap="small")
    for index, (label, key) in enumerate(items):
        p = provenance.get(key, {})
        value = _field_display_value(key, fields.get(key), currency)
        source = {"llm": "AI", "rule": "RULES", "none": "NOT FOUND"}.get(p.get("source"), "UNKNOWN")
        verified = bool(p.get("verified"))
        status_text = "Verified" if verified else ("Unverified" if fields.get(key) not in (None, "") else "Missing")
        status_color = "#148367" if verified else ("#b7791f" if fields.get(key) not in (None, "") else "#c2413a")
        evidence = p.get("evidence") or p.get("note") or "No supporting source snippet recorded."
        with cols[index % len(cols)]:
            st.markdown(
                f'<div class="field-card"><div style="display:flex;justify-content:space-between;gap:8px">'
                f'<div class="field-label">{esc(label)}</div><div style="font-size:.63rem;font-weight:800;color:{status_color}">{esc(source)} · {esc(status_text)}</div></div>'
                f'<div class="field-value">{esc(value)}</div><div class="evidence-line">{esc(evidence[:180])}</div></div>',
                unsafe_allow_html=True,
            )
    currency_p = provenance.get("currency", {})
    st.caption(f"Currency: {currency or 'Unknown / ambiguous'} · {currency_p.get('evidence') or 'No currency evidence recorded'}")


def render_run_details(record: dict, document_bytes: bytes | None = None) -> None:
    status = record.get("status", "NEEDS REVIEW")
    fields = record.get("fields", {})
    checks = record.get("checks", [])
    provenance = fields.get("_provenance", {})
    required = ["vendor_name", "invoice_number", "invoice_date", "po_number", "subtotal", "tax", "total"]
    present = sum(fields.get(k) not in (None, "") for k in required)
    grounded = sum(bool(provenance.get(k, {}).get("verified")) for k in required)
    currency = fields.get("currency")
    status_desc = {
        "AUTO-CLEAR": "All configured controls passed. This invoice is ready for AP approval; no payment has been released.",
        "NEEDS REVIEW": "One or more controls require a human decision before this invoice can proceed.",
        "BLOCKED": "A critical policy violation was found. This case is read-only until the underlying issue is corrected.",
    }.get(status, "Review the recorded checks before taking action.")
    color = {"AUTO-CLEAR": "#148367", "NEEDS REVIEW": "#ad7419", "BLOCKED": "#bd4c46"}.get(status, "#64748b")
    st.markdown(
        f'<div class="surface" style="border-left:4px solid {color};margin-bottom:13px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">'
        f'<div><div class="eyebrow">DECISION RECORD</div><div style="font-family:Manrope;font-size:1.55rem;font-weight:850;color:{color};letter-spacing:-.04em">{esc(status)}</div>'
        f'<div style="color:#708097;font-size:.82rem;margin-top:4px">{esc(status_desc)}</div></div>'
        f'<div style="text-align:right"><div class="run-id">{esc(record.get("run_id"))}</div><div style="color:#8794a6;font-size:.7rem;margin-top:4px">{esc(record.get("processing_ms",0))} ms processing</div></div></div>'
        f'<div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:15px;font-size:.78rem;color:#637187">'
        f'<span><b style="color:#1c2a41">{esc(money(record.get("invoice_total"), currency))}</b> · invoice value</span>'
        f'<span><b style="color:#1c2a41">{present}/7</b> · fields present</span><span><b style="color:#1c2a41">{grounded}/7</b> · source grounded</span>'
        f'<span>{esc(record.get("created_at"))}</span></div></div>', unsafe_allow_html=True,
    )
    st.markdown(f"**Decision rationale:** {record.get('decision_reason') or 'No rationale recorded.'}")
    if record.get("review_decision"):
        st.info(f"Human resolution: {record.get('review_decision')} · {record.get('reviewed_by') or 'Reviewer not recorded'} · {record.get('reviewed_at') or ''}. {record.get('review_note') or ''}")
    pdf = document_bytes if document_bytes is not None else load_document_bytes(record)
    if pdf:
        doc_col, fields_col = st.columns([.95, 1.05], gap="large")
        with doc_col:
            section_head("Source document", "Original PDF · retained locally")
            render_pdf_preview(pdf)
            st.download_button("Download original PDF", data=pdf, file_name=record.get("file_name") or "invoice.pdf", mime="application/pdf", key=f"pdf_{record.get('run_id')}")
        with fields_col:
            section_head("Extracted fields", "Provenance and field evidence")
            render_field_cards(fields)
    else:
        section_head("Extracted fields", "Provenance and field evidence")
        render_field_cards(fields)
        st.caption("Original PDF is not available for this historical run.")
    with st.expander(f"Decision controls · {len(checks)} checks", expanded=True):
        if checks:
            check_df = pd.DataFrame(checks)
            st.dataframe(check_df, hide_index=True, use_container_width=True, column_config={
                "check": st.column_config.TextColumn("Control", width="medium"),
                "result": st.column_config.TextColumn("Outcome", width="small"),
                "detail": st.column_config.TextColumn("Evidence and rationale", width="large"),
            })
        else:
            st.caption("No control evidence was recorded.")
    extraction = fields.get("_extraction", {})
    with st.expander("Extraction diagnostics and source text"):
        st.json({k: v for k, v in extraction.items() if k != "completeness_is_not_confidence"})
        st.text(record.get("extracted_text") or "No extracted text stored.")


def exception_category(record: dict) -> str:
    checks = record.get("checks", [])
    flagged = [c.get("check", "") for c in checks if c.get("result") in {"REVIEW", "BLOCK"}]
    mapping = [
        ("Cumulative PO exposure", "PO overexposure"), ("Currency consistency", "Currency mismatch"),
        ("Currency detection", "Currency not verified"), ("Arithmetic integrity", "Arithmetic mismatch"),
        ("PO vendor ownership", "Vendor / PO mismatch"), ("PO status", "PO status"),
        ("PO match", "PO not found"), ("Required fields", "Missing information"),
        ("Document readability", "Unreadable document"),
    ]
    for key, category in mapping:
        if key in flagged:
            return category
    reason = (record.get("decision_reason") or "").lower()
    return "Duplicate invoice" if "duplicate" in reason else "Other exception"


def exception_priority(category: str) -> str:
    if category in {"PO overexposure", "Currency mismatch", "Arithmetic mismatch", "Vendor / PO mismatch", "Duplicate invoice"}:
        return "HIGH"
    if category in {"PO status", "PO not found", "Unreadable document"}:
        return "MEDIUM"
    return "STANDARD"


def exposure_frame() -> pd.DataFrame:
    pos = get_purchase_orders()
    runs = get_runs()
    if pos.empty:
        return pos
    if runs.empty:
        pos["invoiced"] = 0.0
    else:
        counted = runs[
            runs["status"].isin(["AUTO-CLEAR", "NEEDS REVIEW"])
            & (runs["review_decision"].fillna("") != "REJECTED")
        ].copy()
        counted["invoice_total"] = pd.to_numeric(counted["invoice_total"], errors="coerce").fillna(0)
        counted["currency"] = counted["currency"].fillna("").astype(str).str.upper()
        pos_currency = pos[["po_number", "currency"]].copy()
        pos_currency["currency"] = pos_currency["currency"].fillna("").astype(str).str.upper()
        counted = counted.merge(pos_currency, on="po_number", how="inner", suffixes=("_invoice", "_po"))
        counted = counted[counted["currency_invoice"] == counted["currency_po"]]
        totals = counted.groupby("po_number")["invoice_total"].sum().to_dict()
        pos["invoiced"] = pos["po_number"].map(totals).fillna(0.0)
    pos["allowed_cap"] = pos["po_amount"] * (1 + pos["tolerance_pct"] / 100)
    pos["utilisation"] = pos.apply(lambda r: (r["invoiced"] / r["allowed_cap"] * 100) if r["allowed_cap"] else 0, axis=1)
    pos["po_utilisation"] = pos.apply(lambda r: (r["invoiced"] / r["po_amount"] * 100) if r["po_amount"] else 0, axis=1)
    def classify(row):
        if row["invoiced"] > row["allowed_cap"]:
            return "OVER TOLERANCE"
        if row["utilisation"] >= 80:
            return "WATCH"
        return "WITHIN RANGE"
    pos["exposure_status"] = pos.apply(classify, axis=1)
    return pos


def format_plot(fig, height: int = 300) -> None:
    fig.update_layout(
        height=height, margin=dict(t=18, b=12, l=8, r=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color="#637187", size=11),
        legend_title=None,
    )


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
def dashboard_page() -> None:
    runs = get_runs()
    queue = get_review_queue()
    resolved = get_reviewed()
    pos = exposure_frame()
    total = len(runs)
    auto = int((runs["status"] == "AUTO-CLEAR").sum()) if total else 0
    needs_review = int((runs["status"] == "NEEDS REVIEW").sum()) if total else 0
    blocked = int((runs["status"] == "BLOCKED").sum()) if total else 0
    auto_rate = auto / total * 100 if total else 0
    watch = int(pos["exposure_status"].isin(["WATCH", "OVER TOLERANCE"]).sum()) if not pos.empty else 0
    high_priority = 0
    if not queue.empty:
        for row in queue.to_dict("records"):
            rec = get_run(row["run_id"])
            if rec and exception_priority(exception_category(rec)) == "HIGH":
                high_priority += 1

    page_header("ACCOUNTS PAYABLE · CONTROL TOWER", "Accounts payable, under control.",
                "One workspace to intake invoices, understand exceptions and monitor purchase-order exposure.")
    st.markdown(
        f'<div class="hero"><div class="hero-kicker">CLEARMatch · OPERATIONS SNAPSHOT</div>'
        f'<div class="hero-title">From invoice arrival<br>to an explainable decision.</div>'
        f'<div class="hero-copy">AI-assisted document understanding. Deterministic finance controls. Human ownership for every exception.</div>'
        f'<div style="display:flex;gap:34px;flex-wrap:wrap;margin-top:20px">'
        f'<div><div class="hero-stat">{total:,}</div><div class="hero-stat-label">Recorded runs</div></div>'
        f'<div><div class="hero-stat">{len(queue):,}</div><div class="hero-stat-label">Awaiting human review</div></div>'
        f'<div><div class="hero-stat">{watch:,}</div><div class="hero-stat-label">PO exposure signals</div></div></div></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    kpi_grid([
        ("AUTO-CLEAR RATE", f"{auto_rate:.1f}%", f"{auto:,} of {total:,} recorded invoices", "green"),
        ("AWAITING REVIEW", f"{len(queue):,}", f"{high_priority} high-priority cases", "amber"),
        ("BLOCKED", f"{blocked:,}", "Critical controls triggered", "red"),
        ("REVIEW RESOLUTIONS", f"{len(resolved):,}", "Human decisions recorded", "blue"),
    ])

    section_head("Portfolio signals", "Derived from current PO register and recorded runs")
    if not pos.empty:
        p1, p2, p3 = st.columns(3, gap="medium")
        over = pos[pos["exposure_status"] == "OVER TOLERANCE"]
        watch_df = pos[pos["exposure_status"] == "WATCH"]
        p1.metric("Purchase orders monitored", f"{len(pos):,}")
        p2.metric("Near tolerance", f"{len(watch_df):,}")
        p3.metric("Over tolerance", f"{len(over):,}")
        if not over.empty:
            st.error("PO exposure has exceeded configured tolerance: " + ", ".join(over["po_number"].astype(str).tolist()))
        top_pos = pos.sort_values("utilisation", ascending=False).head(5).copy()
        with st.container(border=True):
            section_head("PO exposure watch", "Utilisation of PO value plus configured tolerance")
            for _, row in top_pos.iterrows():
                pct = min(100.0, max(0.0, float(row["utilisation"])))
                color = "#c44d48" if row["exposure_status"] == "OVER TOLERANCE" else ("#d59a3a" if row["exposure_status"] == "WATCH" else "#16a085")
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;gap:12px;align-items:end">'
                    f'<div><b style="color:#24344c">{esc(row["po_number"])}</b> <span style="color:#7d8ba0;font-size:.77rem">· {esc(row["vendor_name"])}</span></div>'
                    f'<div style="font-size:.75rem;color:#718096">{float(row["utilisation"]):.1f}% of allowed cap</div></div>'
                    f'<div class="exposure-track"><div class="exposure-fill" style="width:{pct}%;background:{color}"></div></div>'
                    f'<div style="display:flex;justify-content:space-between;margin:4px 0 12px;font-size:.7rem;color:#8b97a8">'
                    f'<span>{esc(money(row["invoiced"], row["currency"]))} invoiced</span><span>{esc(row["exposure_status"])}</span></div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("The PO register has no rows yet.")

    section_head("Decision intelligence", "Recorded outcomes, not simulated activity")
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        with st.container(border=True):
            section_head("Decision mix", "All recorded runs")
            if total:
                dist = pd.DataFrame({"Decision": ["AUTO-CLEAR", "NEEDS REVIEW", "BLOCKED"], "Runs": [auto, needs_review, blocked]})
                dist = dist[dist["Runs"] > 0]
                fig = px.pie(dist, names="Decision", values="Runs", hole=.72,
                             color="Decision", color_discrete_map={"AUTO-CLEAR": "#16a085", "NEEDS REVIEW": "#e0a13b", "BLOCKED": "#ca5b54"})
                fig.update_traces(textinfo="none", hovertemplate="%{label}: %{value}<extra></extra>")
                format_plot(fig, 250)
                fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-.08, x=0))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                st.markdown('<div class="empty-state">No invoice runs yet.<br>Start with a sample or upload a PDF.</div>', unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            section_head("Needs attention", "Oldest unresolved cases first")
            if queue.empty:
                st.markdown('<div class="empty-state">Exception desk is clear.<br>No invoices are awaiting a human decision.</div>', unsafe_allow_html=True)
            else:
                display_rows = []
                for row in queue.head(6).to_dict("records"):
                    record = get_run(row["run_id"]) or {}
                    category = exception_category(record)
                    display_rows.append({
                        "Vendor": row.get("vendor_name") or "Unknown vendor",
                        "Invoice": row.get("invoice_number") or "Not extracted",
                        "Issue": category,
                        "Priority": exception_priority(category),
                        "Amount": money(row.get("invoice_total"), row.get("currency")),
                    })
                st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True, height=260)
                st.caption("Blocked cases are visible in the Exception Desk but cannot be overridden in this MVP.")

    section_head("Latest decisions", "Most recent processing activity")
    if total:
        recent = runs.head(8).copy()
        recent["Invoice value"] = recent.apply(lambda r: money(r["invoice_total"], r.get("currency")), axis=1)
        recent = recent.rename(columns={"created_at": "Processed at", "vendor_name": "Vendor", "invoice_number": "Invoice", "po_number": "Purchase order", "status": "Decision", "run_id": "Run ID"})
        st.dataframe(recent[["Processed at", "Vendor", "Invoice", "Purchase order", "Invoice value", "Decision", "Run ID"]], hide_index=True, use_container_width=True)
    else:
        st.caption("Your decision ledger will populate as invoices are processed.")


def run_single_invoice(file_bytes: bytes, file_name: str, key_prefix: str = "single") -> None:
    st.markdown("#### Execution trace")
    stage_names = ["Document ingestion", "Text extraction", "Field extraction", "Duplicate screening", "Purchase order matching", "Policy evaluation", "Audit trail"]
    slots = {name: st.empty() for name in stage_names}
    progress = st.progress(0, text="Preparing document…")
    states = {name: "waiting" for name in stage_names}
    details = {name: "Queued" for name in stage_names}

    def update(stage: str, stage_state: str, detail: str) -> None:
        if stage in states:
            states[stage] = stage_state
            details[stage] = detail
        done = sum(v == "complete" for v in states.values())
        progress.progress(done / len(stage_names), text=f"{done} of {len(stage_names)} controls complete")
        for name in stage_names:
            state = states[name]
            node_class = "done" if state == "complete" else ("active" if state == "running" else "")
            glyph = "✓" if state == "complete" else ("•" if state == "running" else "○")
            slots[name].markdown(
                f'<div class="stage-row"><div class="stage-node {node_class}">{glyph}</div><div style="flex:1"><div class="stage-title">{esc(name)}</div><div class="stage-detail">{esc(details[name])}</div></div></div>',
                unsafe_allow_html=True,
            )

    for name in stage_names:
        update(name, "waiting", "Queued")
    record = process_invoice(file_bytes, file_name, str(DB_PATH), update, str(BASE_DIR / "data" / "documents"))
    progress.progress(1.0, text="Decision saved to the run ledger")
    st.session_state["last_run_id"] = record["run_id"]
    st.success("Processing complete. The decision, control evidence and source document have been recorded.")
    render_run_details(record, document_bytes=file_bytes)


def process_page() -> None:
    page_header("WORKFLOW · DOCUMENT INTAKE", "Process invoices", "Turn individual PDFs or a batch of supplier invoices into traceable AP decisions.")
    single_tab, batch_tab = st.tabs(["Single invoice", "Batch intake"])
    samples = {
        "Happy path · Northstar / PO-1001": "happy_path_invoice.pdf",
        "Split invoice · part 1 of 3 · ₹40,000": "split_01_invoice.pdf",
        "Split invoice · part 2 of 3 · ₹35,000": "split_02_invoice.pdf",
        "Split invoice · part 3 of 3 · ₹30,000": "split_03_invoice.pdf",
        "Missing invoice date · needs review": "missing_date_invoice.pdf",
        "Closed PO · blocked": "closed_po_invoice.pdf",
        "Scanned PDF · OCR test": "scanned_missing_date_invoice.pdf",
        "Wrong vendor for PO · blocked": "wrong_vendor_invoice.pdf",
        "Arithmetic mismatch · needs review": "arithmetic_mismatch_invoice.pdf",
        "Alternative layout · Northstar": "alternative_layout_invoice.pdf",
        "Table layout · Bluepeak": "bluepeak_layout_table_invoice.pdf",
        "Currency mismatch · USD vs INR PO": "currency_mismatch_invoice.pdf",
        "Compact pipe layout · Greenfield": "compact_pipe_layout_invoice.pdf",
    }
    with single_tab:
        left, right = st.columns([1, 1], gap="large")
        with left:
            with st.container(border=True):
                section_head("01 · Select source", "PDF input")
                source = st.radio("Input source", ["Sample scenario", "Upload a PDF"], horizontal=True, key="single_source")
                file_bytes = None
                file_name = None
                if source == "Sample scenario":
                    label = st.selectbox("Choose a test scenario", list(samples.keys()), key="single_sample")
                    file_name = samples[label]
                    path = BASE_DIR / "samples" / file_name
                    file_bytes = path.read_bytes() if path.exists() else None
                    if file_bytes:
                        st.caption(f"Synthetic test document · {len(file_bytes)/1024:.1f} KB")
                        st.download_button("Download source PDF", file_bytes, file_name=file_name, mime="application/pdf", key="download_sample")
                else:
                    uploaded = st.file_uploader("Drop a supplier invoice PDF", type=["pdf"], key="single_upload", help="PDF only · maximum 15 MB")
                    if uploaded:
                        file_bytes, file_name = uploaded.getvalue(), uploaded.name
                        st.caption(f"Selected: {file_name} · {len(file_bytes)/1024:.1f} KB")
                run = st.button("Run invoice controls", type="primary", use_container_width=True, disabled=not bool(file_bytes), key="run_single")
        with right:
            with st.container(border=True):
                section_head("02 · What happens next", "Live workflow")
                steps = [
                    ("01", "Read the source", "Extract embedded PDF text or invoke OCR for image-based scans."),
                    ("02", "Ground every field", "Check AI proposals against field-labelled source evidence; use deterministic fallback."),
                    ("03", "Apply finance controls", "Check arithmetic, duplicate risk, PO ownership, status, currency and cumulative exposure."),
                    ("04", "Record the decision", "Persist the outcome, evidence, timing and source PDF in the local audit ledger."),
                ]
                for n, title, desc in steps:
                    st.markdown(f'<div style="display:flex;gap:11px;padding:10px 0;border-bottom:1px solid #edf0f5"><div class="stage-node active">{n}</div><div><div class="stage-title">{esc(title)}</div><div class="stage-detail">{esc(desc)}</div></div></div>', unsafe_allow_html=True)
                st.caption("AI extraction is optional. Deterministic controls remain responsible for the final decision.")
        if run and file_bytes and file_name:
            try:
                run_single_invoice(file_bytes, file_name)
            except Exception as exc:
                st.error(f"Processing failed before a decision was saved: {exc}")
                st.caption("Check that the PDF is valid and within the 15 MB limit. No success is reported unless a run is saved.")
        elif st.session_state.get("last_run_id"):
            last = get_run(st.session_state["last_run_id"])
            if last:
                with st.expander("Most recent completed run", expanded=False):
                    render_run_details(last)

    with batch_tab:
        st.markdown(
            '<div class="surface" style="margin-bottom:14px"><div class="eyebrow">BATCH OPERATIONS</div>'
            '<div style="font-family:Manrope;font-size:1.2rem;font-weight:800;color:#1a2a42">Process a supplier drop in one pass.</div>'
            '<div style="font-size:.82rem;color:#738198;margin-top:5px">Each PDF is processed independently and receives its own run ID, decision, source evidence and audit record. Duplicate and PO-exposure checks see earlier files in the same batch.</div></div>',
            unsafe_allow_html=True,
        )
        files = st.file_uploader("Add multiple invoice PDFs", type=["pdf"], accept_multiple_files=True, key="batch_upload", help="Maximum 10 PDFs per batch · each file must be 15 MB or smaller")
        if files:
            total_size = sum(f.size for f in files)
            st.caption(f"{len(files)} document(s) selected · {total_size/1024/1024:.2f} MB total")
            if len(files) > 10:
                st.error("A batch can contain at most 10 PDFs. Remove files and try again.")
            elif total_size > 50 * 1024 * 1024:
                st.error("The combined batch size must not exceed 50 MB. Remove some files and try again.")
            else:
                batch_run = st.button("Process batch", type="primary", disabled=False, key="run_batch")
                if batch_run:
                    stage_names = ["Document ingestion", "Text extraction", "Field extraction", "Duplicate screening", "Purchase order matching", "Policy evaluation", "Audit trail"]
                    global_progress = st.progress(0, text="Starting batch intake…")
                    current_status = st.empty()
                    stage_view = st.empty()
                    active_index = {"value": None}
                    current_states: dict[str, str] = {}

                    def batch_progress(index: int, total: int, name: str, stage: str, state: str, detail: str) -> None:
                        if active_index["value"] != index:
                            active_index["value"] = index
                            current_states.clear()
                            current_states.update({s: "waiting" for s in stage_names})
                        if stage in current_states:
                            current_states[stage] = state
                        done = sum(v == "complete" for v in current_states.values())
                        overall = ((index - 1) + done / len(stage_names)) / total
                        global_progress.progress(min(overall, 1.0), text=f"Batch progress · {index}/{total} documents · {done}/{len(stage_names)} current stages")
                        current_status.info(f"Processing {index} of {total} · {name} · {detail}")
                        stage_html = []
                        for stage_name in stage_names:
                            stage_state = current_states[stage_name]
                            node_class = "done" if stage_state == "complete" else ("active" if stage_state == "running" else "")
                            glyph = "✓" if stage_state == "complete" else ("•" if stage_state == "running" else "○")
                            stage_html.append(f'<div class="stage-row"><div class="stage-node {node_class}">{glyph}</div><div class="stage-title">{esc(stage_name)}</div></div>')
                        stage_view.markdown("".join(stage_html), unsafe_allow_html=True)

                    documents = [(uploaded.name, uploaded.getvalue()) for uploaded in files]
                    results = process_batch(
                        documents,
                        str(DB_PATH),
                        str(BASE_DIR / "data" / "documents"),
                        batch_progress,
                    )
                    global_progress.progress(1.0, text="Batch intake complete")
                    result_rows = []
                    for item in results:
                        if item["ok"]:
                            record = item["record"]
                            result_rows.append({
                                "File": item["file_name"],
                                "Vendor": record.get("vendor_name") or "Unknown",
                                "Invoice": record.get("invoice_number") or "Not extracted",
                                "PO": record.get("po_number") or "—",
                                "Amount": money(record.get("invoice_total"), record.get("currency")),
                                "Decision": record.get("status"),
                                "Run ID": record.get("run_id"),
                                "Processing ms": record.get("processing_ms", 0),
                                "Error": "",
                            })
                        else:
                            result_rows.append({
                                "File": item["file_name"], "Vendor": "—", "Invoice": "—", "PO": "—",
                                "Amount": "—", "Decision": "ERROR", "Run ID": "Not recorded",
                                "Processing ms": 0, "Error": item["error"],
                            })
                    result_df = pd.DataFrame(result_rows)
                    st.session_state["last_batch_results"] = result_df
                    successful = sum(1 for r in results if r["ok"])
                    current_status.success(f"Batch finished · {successful} of {len(results)} documents successfully recorded. Each successful file has an independent run ID and audit record.")
                    st.dataframe(result_df, hide_index=True, use_container_width=True)
                    st.download_button("Download batch results CSV", result_df.to_csv(index=False).encode("utf-8-sig"), file_name=f"clearmatch_batch_{datetime.now():%Y%m%d_%H%M}.csv", mime="text/csv", key="download_batch_results")
                    st.caption("Files are processed sequentially so duplicate checks and cumulative PO exposure for later documents include earlier successful documents in this same batch. A single file error does not roll back successful runs.")
        else:
            st.markdown('<div class="empty-state">No batch selected yet.<br>Choose a set of invoice PDFs to begin intake.</div>', unsafe_allow_html=True)


def history_page() -> None:
    page_header("AUDIT · RUN LEDGER", "Run ledger", "A searchable record of every processed invoice, its decision and the evidence captured at runtime.")
    runs = get_runs()
    if runs.empty:
        st.markdown('<div class="empty-state">The ledger is empty.<br>Process an invoice to create the first decision record.</div>', unsafe_allow_html=True)
        return
    c1, c2, c3 = st.columns([1.5, 1, 1])
    with c1:
        query = st.text_input("Search records", placeholder="Vendor, invoice number, PO or run ID", key="ledger_search")
    with c2:
        statuses = ["All decisions"] + sorted(runs["status"].dropna().unique().tolist())
        status = st.selectbox("Decision", statuses, key="ledger_status")
    with c3:
        review_filter = st.selectbox("Human review", ["All", "Pending", "Approved", "Rejected"], key="ledger_review")
    filtered = runs.copy()
    if query:
        mask = filtered.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    if status != "All decisions":
        filtered = filtered[filtered["status"] == status]
    if review_filter == "Pending":
        filtered = filtered[(filtered["status"] == "NEEDS REVIEW") & filtered["review_decision"].isna()]
    elif review_filter == "Approved":
        filtered = filtered[filtered["review_decision"] == "APPROVED"]
    elif review_filter == "Rejected":
        filtered = filtered[filtered["review_decision"] == "REJECTED"]
    st.caption(f"Showing {len(filtered):,} of {len(runs):,} recorded runs")
    if filtered.empty:
        st.info("No run records match the current search and filters. Clear a filter or try a different search term.")
        return
    export = filtered.copy()
    export["invoice_value"] = export.apply(lambda r: money(r["invoice_total"], r.get("currency")), axis=1)
    st.download_button("Export filtered ledger · CSV", export.to_csv(index=False).encode("utf-8-sig"), file_name="clearmatch_run_ledger.csv", mime="text/csv")
    view = filtered.copy()
    view["Invoice value"] = view.apply(lambda r: money(r["invoice_total"], r.get("currency")), axis=1)
    view["Processed"] = view["created_at"].fillna("").astype(str).str.replace("T", " ", regex=False).str.slice(0, 16)
    view = view.rename(columns={"run_id": "Run ID", "vendor_name": "Vendor", "invoice_number": "Invoice", "po_number": "PO", "status": "Decision", "review_decision": "Human review"})
    # Keep the scan-friendly ledger narrow; the selected record below contains the complete audit detail.
    columns = ["Run ID", "Processed", "Vendor", "Invoice", "PO", "Invoice value", "Decision", "Human review"]
    ledger_height = min(430, max(112, 40 * len(view) + 48))
    st.dataframe(view[columns], hide_index=True, use_container_width=True, height=ledger_height)
    if not filtered.empty:
        st.caption("Select a row's run ID below to inspect the original PDF, extracted-field provenance, control evidence and any human resolution.")
        selected_id = st.selectbox("Open decision record", filtered["run_id"].tolist(), format_func=lambda x: f"{x} · {filtered.loc[filtered['run_id']==x, 'file_name'].iloc[0]}")
        record = get_run(selected_id)
        if record:
            st.divider()
            section_head("Selected decision record", "Full source evidence and audit trail")
            render_run_details(record)


def review_page() -> None:
    page_header("HUMAN-IN-THE-LOOP · EXCEPTION DESK", "Exception desk", "Resolve reviewable invoices with source evidence, a named reviewer and a recorded rationale.")
    queue = get_exception_queue()
    actionable = queue[queue["status"] == "NEEDS REVIEW"].copy() if not queue.empty else queue.copy()
    blocked = queue[queue["status"] == "BLOCKED"].copy() if not queue.empty else queue.copy()
    resolved = get_reviewed()
    kpi_grid([
        ("UNRESOLVED RECORDS", str(len(queue)), "Actionable reviews + policy blocks", "amber"),
        ("AWAITING HUMAN REVIEW", str(len(actionable)), "Eligible for reviewer resolution", "blue"),
        ("BLOCKED BY POLICY", str(len(blocked)), "Critical controls; not overridable", "red"),
        ("HUMAN RESOLUTIONS", str(len(resolved)), "Reviewer decisions recorded", "green"),
    ])
    tabs = st.tabs([f"Action required · {len(actionable)}", f"Blocked · {len(blocked)}", f"Resolved · {len(resolved)}"])
    with tabs[0]:
        if actionable.empty:
            st.markdown(
                '<div class="surface" style="padding:20px 22px;margin-bottom:12px">'
                '<div style="font-family:Manrope;font-weight:800;color:#1b2940;font-size:1.03rem">No actionable reviews are waiting.</div>'
                '<div style="color:#718096;font-size:.82rem;margin-top:5px">The review queue is clear. Policy-blocked invoices remain visible in the Blocked tab and cannot be manually overridden.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            a, b, c = st.columns(3, gap="medium")
            a.metric("Actionable reviews", len(actionable))
            b.metric("Policy-blocked records", len(blocked))
            c.metric("Resolved reviews", len(resolved))
        else:
            records = []
            for row in actionable.to_dict("records"):
                rec = get_run(row["run_id"]) or {}
                category = exception_category(rec)
                records.append({"Run ID": row["run_id"], "Vendor": row.get("vendor_name") or "Unknown", "Invoice": row.get("invoice_number") or "Not extracted", "PO": row.get("po_number") or "—", "Amount": money(row.get("invoice_total"), row.get("currency")), "Exception": category, "Priority": exception_priority(category), "Created": row.get("created_at")})
            table = pd.DataFrame(records)
            left, right = st.columns([1.05, 1], gap="large")
            with left:
                query = st.text_input("Find a case", placeholder="Search vendor, invoice or PO", key="exception_search")
                priority = st.selectbox("Priority filter", ["All", "HIGH", "MEDIUM", "STANDARD"], key="exception_priority")
                filtered = table.copy()
                if query:
                    m = filtered.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
                    filtered = filtered[m]
                if priority != "All":
                    filtered = filtered[filtered["Priority"] == priority]
                review_height = min(360, max(112, 42 * len(filtered) + 48))
                st.dataframe(filtered.drop(columns=["Run ID"]), hide_index=True, use_container_width=True, height=review_height)
                if filtered.empty:
                    selected_id = None
                else:
                    selected_id = st.selectbox("Select an exception", filtered["Run ID"].tolist(), format_func=lambda x: f"{x} · {filtered.loc[filtered['Run ID']==x, 'Vendor'].iloc[0]}", key="selected_exception")
            with right:
                section_head("Resolution workspace", "A human decision is required")
                if selected_id:
                    rec = get_run(selected_id)
                    if rec:
                        st.markdown(f"**{rec.get('vendor_name') or 'Unknown vendor'}** · {rec.get('invoice_number') or 'Invoice not extracted'}")
                        a, b = st.columns(2)
                        a.metric("Invoice value", money(rec.get("invoice_total"), rec.get("currency")))
                        b.metric("Exception type", exception_category(rec))
                        st.warning(rec.get("decision_reason") or "No decision rationale recorded.")
                        failed = [x for x in rec.get("checks", []) if x.get("result") in {"REVIEW", "BLOCK"}]
                        if failed:
                            st.dataframe(pd.DataFrame(failed), hide_index=True, use_container_width=True)
                        with st.expander("Inspect source and full decision evidence"):
                            render_run_details(rec)
                        reviewer = st.text_input("Reviewer name", key=f"reviewer_{selected_id}", placeholder="Your name")
                        note = st.text_area("Resolution rationale", key=f"note_{selected_id}", placeholder="What did you verify? Why is this invoice safe to approve or why should it be rejected?", height=100)
                        approve, reject = st.columns(2)
                        if approve.button("Approve exception", type="primary", use_container_width=True, key=f"approve_{selected_id}"):
                            if not reviewer.strip() or not note.strip():
                                st.error("Reviewer name and rationale are required.")
                            elif set_review(selected_id, "APPROVED", note, reviewed_by=reviewer):
                                st.success("Human approval recorded.")
                                st.rerun()
                        if reject.button("Reject invoice", use_container_width=True, key=f"reject_{selected_id}"):
                            if not reviewer.strip() or not note.strip():
                                st.error("Reviewer name and rationale are required.")
                            elif set_review(selected_id, "REJECTED", note, reviewed_by=reviewer):
                                st.success("Rejection recorded. This invoice is excluded from subsequent PO exposure calculations.")
                                st.rerun()
                else:
                    st.info("Select an exception to inspect its evidence and record a decision.")
    with tabs[1]:
        if blocked.empty:
            st.success("No unresolved blocked cases.")
        else:
            st.caption("Blocked outcomes are deliberately read-only. Resolve the underlying duplicate, vendor or PO issue and submit a corrected document.")
            blocked_view = blocked[["run_id", "created_at", "file_name", "vendor_name", "invoice_number", "po_number", "invoice_total", "currency", "decision_reason"]].copy()
            blocked_height = min(360, max(112, 42 * len(blocked_view) + 48))
            st.dataframe(blocked_view, hide_index=True, use_container_width=True, height=blocked_height)
            chosen = st.selectbox("Inspect blocked case", blocked["run_id"].tolist(), key="blocked_case")
            if chosen:
                rec = get_run(chosen)
                if rec:
                    render_run_details(rec)
    with tabs[2]:
        if resolved.empty:
            st.info("Resolved cases will appear here once a reviewer makes a decision.")
        else:
            resolved_view = resolved[["run_id", "vendor_name", "invoice_number", "po_number", "invoice_total", "currency", "review_decision", "reviewed_by", "review_note", "reviewed_at"]]
            resolved_height = min(420, max(112, 42 * len(resolved_view) + 48))
            st.dataframe(resolved_view, hide_index=True, use_container_width=True, height=resolved_height)


def po_page() -> None:
    page_header("PROCUREMENT · EXPOSURE MONITOR", "PO exposure monitor", "See what has been invoiced against each purchase order, including cumulative exposure and configured tolerance.")
    pos = exposure_frame()
    if pos.empty:
        st.info("No purchase orders found in the register.")
        return
    over = pos[pos["exposure_status"] == "OVER TOLERANCE"]
    watch = pos[pos["exposure_status"] == "WATCH"]
    kpi_grid([
        ("REGISTERED POs", str(len(pos)), "Synthetic procurement master data", "blue"),
        ("WITH RECORDED INVOICES", str(int((pos["invoiced"] > 0).sum())), "Eligible invoice exposure", "green"),
        ("APPROACHING TOLERANCE", str(len(watch)), "At least 80% of allowed cap", "amber"),
        ("OVER TOLERANCE", str(len(over)), "Requires AP attention", "red"),
    ])
    if not over.empty:
        st.error("Over-tolerance purchase orders: " + ", ".join(over["po_number"].astype(str).tolist()))
    section_head("Exposure by purchase order", "Active invoice exposure · watch at 80% · tolerance cap at 100%")
    plot = pos[pos["invoiced"] > 0].sort_values("utilisation", ascending=True).copy()
    if plot.empty:
        st.markdown('<div class="empty-state">No eligible invoices have been recorded against the PO register yet.<br>All purchase orders remain visible in the register below.</div>', unsafe_allow_html=True)
    else:
        plot["PO"] = plot["po_number"].astype(str) + " · " + plot["vendor_name"].astype(str)
        fig = px.bar(plot, x="utilisation", y="PO", orientation="h", color="exposure_status",
                     color_discrete_map={"WITHIN RANGE": "#16a085", "WATCH": "#e0a13b", "OVER TOLERANCE": "#ca5b54"},
                     hover_data={"invoiced": ":,.2f", "po_amount": ":,.2f", "allowed_cap": ":,.2f", "utilisation": ":.1f"})
        fig.add_vline(x=80, line_dash="dot", line_color="#d5a24a", annotation_text="Watch · 80%", annotation_position="top")
        fig.add_vline(x=100, line_dash="dash", line_color="#c65d56", annotation_text="Tolerance cap", annotation_position="top")
        fig.update_layout(xaxis_title="% of allowed exposure cap", yaxis_title=None, showlegend=True)
        format_plot(fig, min(480, max(230, 78 * len(plot) + 95)))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    section_head("PO register", "All registered POs · currency values remain native; no FX conversion")
    view = pos.copy()
    view["PO amount"] = view.apply(lambda r: money(r["po_amount"], r["currency"]), axis=1)
    view["Invoiced to date"] = view.apply(lambda r: money(r["invoiced"], r["currency"]), axis=1)
    view["Remaining to PO value"] = view.apply(lambda r: money(r["po_amount"] - r["invoiced"], r["currency"]), axis=1)
    view["Allowed cap"] = view.apply(lambda r: money(r["allowed_cap"], r["currency"]), axis=1)
    view["Remaining to allowed cap"] = view.apply(lambda r: money(r["allowed_cap"] - r["invoiced"], r["currency"]), axis=1)
    view["Utilisation"] = view["utilisation"].map(lambda x: f"{x:.1f}%")
    po_columns = ["po_number", "vendor_name", "status", "PO amount", "Invoiced to date", "Remaining to PO value", "Allowed cap", "Remaining to allowed cap", "Utilisation", "exposure_status"]
    po_height = min(430, max(150, 39 * len(view) + 48))
    st.dataframe(view[po_columns], hide_index=True, use_container_width=True, height=po_height)
    st.download_button("Export PO exposure · CSV", view.to_csv(index=False).encode("utf-8-sig"), file_name="clearmatch_po_exposure.csv", mime="text/csv")
    st.caption("Exposure includes recorded AUTO-CLEAR and NEEDS REVIEW invoices whose currency matches the PO, except rejected human reviews. Blocked duplicates and currency mismatches are excluded.")


def controls_page() -> None:
    page_header("GOVERNANCE · SYSTEM CONFIGURATION", "Policy & system health", "Understand the controls behind every decision and verify which services are actually available.")
    left, right = st.columns([1.05, .95], gap="large")
    with left:
        with st.container(border=True):
            section_head("Decision policy", "Deterministic rules own the outcome")
            policies = [
                ("AUTO-CLEAR", "All mandatory fields are present, arithmetic reconciles, no duplicate exists, and the PO is active, vendor-matched, currency-matched and within cumulative tolerance.", "#148367"),
                ("NEEDS REVIEW", "Information is missing or ambiguous, arithmetic does not reconcile, the PO cannot be found, currency is not verified or cumulative exposure exceeds tolerance.", "#ad7419"),
                ("BLOCKED", "A duplicate, vendor/PO ownership mismatch or closed PO triggers a critical policy block. Blocked outcomes cannot be overridden in this MVP.", "#bd4c46"),
            ]
            for label, description, color in policies:
                st.markdown(f'<div style="border:1px solid #e8edf4;border-left:4px solid {color};border-radius:11px;padding:12px 14px;margin:9px 0"><div style="font-weight:850;color:{color};font-family:Manrope">{esc(label)}</div><div style="font-size:.79rem;color:#718096;margin-top:5px">{esc(description)}</div></div>', unsafe_allow_html=True)
            st.markdown("**Configured assumptions**")
            assumptions = [
                "Arithmetic tolerance is the greater of one currency unit or 1% of invoice total.",
                "Cumulative PO tolerance is configured per PO and applies across recorded eligible invoices.",
                "Currency mismatches are not converted; they are routed to human review and excluded from exposure totals.",
                "AI output is a proposal. Field-level evidence must be grounded in the expected labelled source context.",
                "AUTO-CLEAR means ready for AP approval; it does not mean paid or released for payment.",
            ]
            for item in assumptions:
                st.markdown(f"- {item}")
    with right:
        with st.container(border=True):
            section_head("AI extraction service", "Configuration is not connectivity")
            settings = get_llm_settings()
            if settings:
                st.info(f"Configured · not yet verified  |  {settings['provider']} · {settings['model']}")
                st.caption("Credentials are detected. Only a successful live request can confirm that the provider is reachable and has available quota.")
                if st.button("Run live connection test", type="primary", use_container_width=True):
                    with st.spinner("Testing provider connection…"):
                        ok, message = llm_health_check()
                    (st.success if ok else st.error)(message)
            else:
                st.warning("No provider API key detected. Deterministic label-based extraction remains available.")
                st.caption("Configure a key in .streamlit/secrets.toml or an environment variable. Never put keys in source code or release ZIPs.")
        with st.container(border=True):
            section_head("Runtime diagnostics", "Local environment checks")
            tesseract = shutil.which("tesseract")
            if not tesseract and os.name == "nt":
                candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
                if candidate.exists():
                    tesseract = str(candidate)
            st.markdown(f"**OCR engine:** {chip('AVAILABLE' if tesseract else 'NOT FOUND')}", unsafe_allow_html=True)
            st.caption("System OCR executable detected." if tesseract else "Tesseract was not found. Image-only PDFs may require local OCR setup.")
            try:
                with get_connection() as conn:
                    conn.execute("SELECT 1").fetchone()
                st.markdown(f"**SQLite:** {chip('CONNECTED')}", unsafe_allow_html=True)
                st.caption("Local persistent database is responding to queries.")
            except sqlite3.Error:
                st.error("Database health check failed. Inspect local application logs for the underlying SQLite diagnostic.")
            st.markdown(f"**LLM configuration:** {chip('CONFIGURED' if settings else 'RULE-BASED MODE')}", unsafe_allow_html=True)
            st.caption("These checks report configuration and availability separately. No credentials are displayed.")
    st.divider()
    with st.container(border=True):
        section_head("Demo workspace maintenance", "Reset test runs before a clean rehearsal")
        st.warning("Clearing history permanently deletes recorded demo runs and PDFs inside data/documents. The PO register is retained.")
        confirm = st.checkbox("I understand this deletes all local run history and retained source PDFs.", key="confirm_reset")
        if st.button("Clear demo history", disabled=not confirm):
            clear_demo_history()
            st.session_state.pop("last_run_id", None)
            st.session_state.pop("last_batch_results", None)
            st.success("Demo history cleared. Purchase-order master data is unchanged.")
            st.rerun()


# -----------------------------------------------------------------------------
# Navigation shell
# -----------------------------------------------------------------------------
with st.sidebar:
    brand()
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.65rem;font-weight:850;letter-spacing:.15em;color:#8095b4;padding:8px 10px'>WORKSPACE</div>", unsafe_allow_html=True)
    page = st.radio(
        "WORKSPACE",
        ["Control tower", "Invoice intake", "Exception desk", "Run ledger", "PO exposure", "Policy & system"],
        label_visibility="collapsed",
        key="main_navigation",
        format_func=lambda x: {
            "Control tower": "◫   Control tower",
            "Invoice intake": "＋   Invoice intake",
            "Exception desk": "◉   Exception desk",
            "Run ledger": "▤   Run ledger",
            "PO exposure": "▥   PO exposure",
            "Policy & system": "⚙   Policy & system",
        }[x],
    )
    st.divider()
    runs_count = len(get_runs())
    review_count = len(get_review_queue())
    st.metric("Recorded runs", f"{runs_count:,}")
    st.metric("Awaiting review", f"{review_count:,}")
    st.markdown("<div style='height:12px'></div><div style='border:1px solid #304662;border-radius:11px;padding:11px 12px;background:#172b47'><div style='color:#9eb2d0;font-size:.62rem;font-weight:850;letter-spacing:.13em'>CASE STUDY BUILD</div><div style='color:#fff;font-weight:750;font-size:.8rem;margin-top:5px'>PS-1 · FINANCE / AP</div><div style='color:#9eb2d0;font-size:.68rem;margin-top:3px'>AI-assisted · Human-governed</div></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:20px'></div><div style='color:#7188a8;font-size:.65rem'>CLEARMATCH · LOCAL WORKSPACE</div>", unsafe_allow_html=True)

if page == "Control tower":
    dashboard_page()
elif page == "Invoice intake":
    process_page()
elif page == "Exception desk":
    review_page()
elif page == "Run ledger":
    history_page()
elif page == "PO exposure":
    po_page()
else:
    controls_page()

st.markdown('<div class="footer-note">ClearMatch is a case-study prototype. Bundled vendors, invoices and purchase orders are synthetic. Decisions support AP review; they do not release payments.</div>', unsafe_allow_html=True)
