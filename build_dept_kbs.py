"""
build_dept_kbs.py — Build department-level knowledge bases for:
  - finance_chief_economist   (Chief Economist Division)
  - finance_budget_dept       (Budget Department)

Sources used:
  1. Existing finance_ministry KB chunks — filtered by PDF type
  2. ALL 4,000+ knesset_cache .doc files — re-parsed with dept-specific keywords
  3. New PDFs downloaded from gov.il Chief Economist & Budget Dept pages

Run:
  python build_dept_kbs.py
"""

import sys
import io
import json
import time
import ssl
import requests
import urllib3
from pathlib import Path
from docx import Document
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
urllib3.disable_warnings()

BASE    = Path(__file__).parent
CACHE   = BASE / "knesset_cache"
CLI     = BASE / "GovPersona-CLI"
KB_DIR  = BASE / "knowledge_base"
PDF_CE  = KB_DIR / "finance_chief_economist"   # new PDF downloads
PDF_BD  = KB_DIR / "finance_budget_dept"
PDF_CE.mkdir(parents=True, exist_ok=True)
PDF_BD.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
}


# =============================================================================
# SSL adapter (needed for many gov.il servers)
# =============================================================================
class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.mount("https://", LegacySSLAdapter())
    return s


# =============================================================================
# 1. PDF document categorization
# =============================================================================
# PDFs that belong to the Chief Economist's division
CHIEF_ECON_PDF_PATTERNS = [
    "macroeconomics-trends-forecast",
    "economic-analysis-forecast",
    "consensus-forecast",
    "oecd-economic-survey",
    "annual-debt-report",
    "digital-asset-regulation",
    "chief-economist",
    "macro-economic",
    "economic-review",
    "economic-outlook",
    "growth-forecast",
]

# PDFs that belong to the Budget Department
BUDGET_PDF_PATTERNS = [
    "state-budget",
    "budget-plan",
    "budget-execution",
    "economic-plan",
    "bank-tax-team-report",
    "budget-department",
    "budget-framework",
    "multi-year-budget",
    "fiscal-plan",
]

def classify_pdf(source):
    s = source.lower()
    for p in CHIEF_ECON_PDF_PATTERNS:
        if p in s:
            return "chief_econ"
    for p in BUDGET_PDF_PATTERNS:
        if p in s:
            return "budget"
    return None


# =============================================================================
# 2. Knesset keyword sets — broader than just speaker attribution
# =============================================================================
# Chief Economist — macroeconomics, forecasting, growth/inflation
CHIEF_ECON_KW = [
    "כלכלן ראשי",
    "אגף הכלכלן",
    "אגף כלכלה",
    "תחזית מקרו",
    "תחזית כלכלית",
    "תחזית צמיחה",
    "סקירה כלכלית",
    "סיכום כלכלי",
    "ניתוח כלכלי",
    "מדד המחירים",
    "שוק העבודה",
    "תוצר מקומי גולמי",
    "תמג",
    "מדיניות פיסקלית",
    "ריבית בנק ישראל",
    "אינפלציה",
    "פריון",
    "צמיחה כלכלית",
    "הפקר הכלכלי",
    "מחקר כלכלי",
    "chief economist",
    "macro forecast",
    "economic forecast",
    "gdp growth",
    "fiscal policy",
]

# Budget Department — state budget, expenditure, deficit
BUDGET_KW = [
    "אגף התקציבים",
    "ממונה על התקציבים",
    "מנהל התקציבים",
    "מנהל אגף",
    "הצעת תקציב",
    "תקציב המדינה",
    "תקציב הממשלה",
    "סעיף תקציבי",
    "קיצוץ תקציבי",
    "הרחבת תקציב",
    "גירעון תקציבי",
    "גירעון המדינה",
    "חוק התקציב",
    "חוק ההסדרים",
    "מסגרת תקציבית",
    "הוצאות הממשלה",
    "הכנסות המדינה",
    "פיקוח תקציבי",
    "ביצוע תקציבי",
    "תוספת תקציב",
    "העברת תקציב",
    "budget department",
    "budget director",
    "state budget",
    "budget deficit",
    "budget cut",
    "budget framework",
]

def score_text(text, keywords):
    """Count how many unique keywords appear in text."""
    tl = text.lower()
    return sum(1 for kw in keywords if kw.lower() in tl)


# =============================================================================
# 3. Load existing finance_ministry KB and split by department
# =============================================================================
def split_existing_chunks():
    fm_path = CLI / "kb_finance_ministry.json"
    print(f"\nLoading finance_ministry KB from {fm_path.name}...", end=" ")
    with open(fm_path, "r", encoding="utf-8") as f:
        all_chunks = json.load(f)
    print(f"{len(all_chunks):,} chunks")

    ce_chunks, bd_chunks = [], []

    for chunk in all_chunks:
        src = chunk.get("source", "")
        if src.startswith("knesset_"):
            # Score against both department keyword sets
            text = chunk.get("text", "")
            cs = score_text(text, CHIEF_ECON_KW)
            bs = score_text(text, BUDGET_KW)
            if cs > 0:
                ce_chunks.append(dict(chunk, dept="chief_econ"))
            if bs > 0:
                bd_chunks.append(dict(chunk, dept="budget"))
        else:
            cat = classify_pdf(src)
            if cat == "chief_econ":
                ce_chunks.append(dict(chunk, dept="chief_econ"))
            elif cat == "budget":
                bd_chunks.append(dict(chunk, dept="budget"))

    print(f"  Chief Economist from existing KB: {len(ce_chunks):,} chunks")
    print(f"  Budget Dept from existing KB:     {len(bd_chunks):,} chunks")
    return ce_chunks, bd_chunks


# =============================================================================
# 4. Re-parse ALL knesset_cache .doc files for dept-specific content
# =============================================================================
def extract_window(paragraphs, hit_idx, window=4):
    """Return a window of paragraphs around a keyword hit."""
    start = max(0, hit_idx - 1)
    end   = min(len(paragraphs), hit_idx + window)
    return "\n".join(p.strip() for p in paragraphs[start:end] if p.strip())

def mine_knesset_cache():
    """Re-parse all cached .doc files, extract dept-relevant passages."""
    doc_files = sorted(CACHE.glob("*.doc"))
    print(f"\nMining {len(doc_files):,} Knesset .doc files...")

    ce_passages, bd_passages = [], []
    errors = 0

    for i, doc_path in enumerate(doc_files):
        if i % 500 == 0:
            print(f"  {i:,}/{len(doc_files):,}  "
                  f"CE:{len(ce_passages):,}  BD:{len(bd_passages):,}")
        try:
            doc   = Document(str(doc_path))
            paras = [p.text for p in doc.paragraphs]
            full  = "\n".join(paras)

            # Derive a readable source label
            parts = doc_path.stem.split("_")
            doc_id = parts[1] if len(parts) > 1 else doc_path.stem
            src_label = f"knesset_cache_{doc_id}"

            # Chief Economist hits
            ce_hits = [j for j, p in enumerate(paras)
                       if score_text(p, CHIEF_ECON_KW) > 0]
            seen_ce = set()
            for h in ce_hits:
                window_text = extract_window(paras, h, window=5)
                key = window_text[:80]
                if key not in seen_ce and len(window_text) > 50:
                    seen_ce.add(key)
                    ce_passages.append({
                        "text": window_text,
                        "source": src_label,
                        "chunk_index": h,
                        "dept": "chief_econ",
                    })

            # Budget Dept hits
            bd_hits = [j for j, p in enumerate(paras)
                       if score_text(p, BUDGET_KW) > 0]
            seen_bd = set()
            for h in bd_hits:
                window_text = extract_window(paras, h, window=5)
                key = window_text[:80]
                if key not in seen_bd and len(window_text) > 50:
                    seen_bd.add(key)
                    bd_passages.append({
                        "text": window_text,
                        "source": src_label,
                        "chunk_index": h,
                        "dept": "budget",
                    })

        except Exception:
            errors += 1

    print(f"  Done. CE passages: {len(ce_passages):,}  "
          f"BD passages: {len(bd_passages):,}  errors: {errors}")
    return ce_passages, bd_passages


# =============================================================================
# 5. Download additional PDFs from gov.il for each department
# =============================================================================

# Chief Economist — curated publication URLs from the MoF website
CHIEF_ECON_PDFS = [
    # Macroeconomic forecasts (additional rounds not yet in KB)
    ("https://www.gov.il/BlobFolder/reports/macro-economic-forecast-round1-2024/he/forecast-round1-2024.pdf",
     "macro-forecast-round1-2024.pdf"),
    ("https://www.gov.il/BlobFolder/reports/macro-economic-forecast-round2-2024/he/forecast-round2-2024.pdf",
     "macro-forecast-round2-2024.pdf"),
    # Economic overview 2023
    ("https://www.gov.il/BlobFolder/reports/economic-analysis-forecast-2023-2024-jan/he/economic-analysis-forecast-2023-2024-jan.pdf",
     "economic-analysis-jan-2024.pdf"),
    # Debt strategy
    ("https://www.gov.il/BlobFolder/reports/debt-management-annual-report-2022/he/debt-report-2022-en.pdf",
     "annual-debt-report-2022-en.pdf"),
]

# Budget Department — curated URLs
BUDGET_DEPT_PDFS = [
    # Budget circulars / instructions
    ("https://www.gov.il/BlobFolder/reports/budget-circular-2024/he/budget-circular-2024.pdf",
     "budget-circular-2024.pdf"),
    ("https://www.gov.il/BlobFolder/reports/budget-execution-2023/he/budget-execution-report-2023.pdf",
     "budget-execution-report-2023.pdf"),
    # Multi-year framework documents
    ("https://www.gov.il/BlobFolder/reports/economic-plan-2025/he/economic-plan-2025.pdf",
     "economic-plan-2025.pdf"),
]

def try_download_pdfs(session, url_pairs, dest_dir, label):
    """Try each (url, filename) pair; skip silently if unavailable."""
    print(f"\nDownloading {label} PDFs...")
    downloaded = []
    for url, fname in url_pairs:
        dest = dest_dir / fname
        if dest.exists():
            print(f"  [skip]  {fname} (already on disk)")
            downloaded.append(dest)
            continue
        try:
            r = session.get(url, timeout=30, verify=False, stream=True)
            if r.status_code == 200:
                data = r.content
                if len(data) > 5_000:
                    dest.write_bytes(data)
                    print(f"  [ok]    {fname}  ({len(data)//1024} KB)")
                    downloaded.append(dest)
                    time.sleep(0.5)
                else:
                    print(f"  [skip]  {fname}  (too small — URL may have moved)")
            else:
                print(f"  [skip]  {fname}  (HTTP {r.status_code})")
        except Exception as e:
            print(f"  [skip]  {fname}  ({str(e)[:60]})")
    return downloaded


# =============================================================================
# 6. Ingest a PDF file into chunks (200-word blocks)
# =============================================================================
def pdf_to_chunks(pdf_path, chunk_words=200):
    """Extract text from PDF and chunk it."""
    try:
        import pdfplumber
        chunks = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            all_text = "\n".join(
                p.extract_text() or "" for p in pdf.pages)
        words = all_text.split()
        fname = pdf_path.name
        for i in range(0, len(words), chunk_words):
            block = " ".join(words[i:i + chunk_words])
            if len(block) > 50:
                chunks.append({
                    "text": block,
                    "source": fname,
                    "chunk_index": i // chunk_words,
                })
        return chunks
    except ImportError:
        # pdfplumber not installed — try PyMuPDF
        try:
            import fitz
            chunks = []
            doc = fitz.open(str(pdf_path))
            all_text = "\n".join(page.get_text() for page in doc)
            words = all_text.split()
            fname = pdf_path.name
            for i in range(0, len(words), chunk_words):
                block = " ".join(words[i:i + chunk_words])
                if len(block) > 50:
                    chunks.append({
                        "text": block,
                        "source": fname,
                        "chunk_index": i // chunk_words,
                    })
            return chunks
        except Exception as e:
            print(f"    [warn] Could not parse {pdf_path.name}: {e}")
            return []
    except Exception as e:
        print(f"    [warn] Could not parse {pdf_path.name}: {e}")
        return []


# =============================================================================
# 7. Deduplicate chunks by text fingerprint
# =============================================================================
def dedup(chunks):
    seen = set()
    out  = []
    for c in chunks:
        key = c["text"][:120].strip()
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


# =============================================================================
# 8. Save KB JSON
# =============================================================================
def save_kb(chunks, name):
    path = CLI / f"kb_{name}.json"
    clean = [{k: v for k, v in c.items() if k != "dept"} for c in chunks]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False)
    size_mb = path.stat().st_size / 1_048_576
    print(f"\n  Saved {path.name}  ({len(clean):,} chunks, {size_mb:.1f} MB)")
    return path


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 60)
    print("GovPersona — Department KB Builder")
    print("=" * 60)

    session = make_session()

    # Step 1: split existing finance_ministry KB
    ce_chunks, bd_chunks = split_existing_chunks()

    # Step 2: mine all knesset_cache .doc files for dept content
    ce_knesset, bd_knesset = mine_knesset_cache()
    ce_chunks.extend(ce_knesset)
    bd_chunks.extend(bd_knesset)

    # Step 3: try to download new PDFs
    ce_pdfs = try_download_pdfs(session, CHIEF_ECON_PDFS, PDF_CE, "Chief Economist")
    bd_pdfs = try_download_pdfs(session, BUDGET_DEPT_PDFS, PDF_BD, "Budget Dept")

    # Ingest any successfully downloaded PDFs
    print("\nIngesting downloaded PDFs...")
    for pdf in ce_pdfs:
        new_chunks = pdf_to_chunks(pdf)
        if new_chunks:
            print(f"  {pdf.name}: {len(new_chunks)} chunks")
            ce_chunks.extend(new_chunks)

    for pdf in bd_pdfs:
        new_chunks = pdf_to_chunks(pdf)
        if new_chunks:
            print(f"  {pdf.name}: {len(new_chunks)} chunks")
            bd_chunks.extend(new_chunks)

    # Step 4: ingest existing PDFs from knowledge_base that weren't in the KB yet
    # (e.g., files in knowledge_base/finance_ministry/ subfolders)
    print("\nChecking for additional PDFs in knowledge_base/finance_ministry/...")
    fm_kb_dir = KB_DIR / "finance_ministry"
    if fm_kb_dir.exists():
        for pdf_path in fm_kb_dir.rglob("*.pdf"):
            cat = classify_pdf(pdf_path.name)
            if cat == "chief_econ":
                new_c = pdf_to_chunks(pdf_path)
                if new_c:
                    already = {c["source"] for c in ce_chunks}
                    if pdf_path.name not in already:
                        print(f"  CE: {pdf_path.name} — {len(new_c)} chunks")
                        ce_chunks.extend(new_c)
            elif cat == "budget":
                new_c = pdf_to_chunks(pdf_path)
                if new_c:
                    already = {c["source"] for c in bd_chunks}
                    if pdf_path.name not in already:
                        print(f"  BD: {pdf_path.name} — {len(new_c)} chunks")
                        bd_chunks.extend(new_c)

    # Step 5: dedup + save
    ce_chunks = dedup(ce_chunks)
    bd_chunks = dedup(bd_chunks)

    print("\nFinal chunk counts before save:")
    print(f"  Chief Economist : {len(ce_chunks):,}")
    print(f"  Budget Dept     : {len(bd_chunks):,}")

    save_kb(ce_chunks, "finance_chief_economist")
    save_kb(bd_chunks, "finance_budget_dept")

    print("\nDone. Next step: add agents to agents_config.json and commit.")


if __name__ == "__main__":
    main()
