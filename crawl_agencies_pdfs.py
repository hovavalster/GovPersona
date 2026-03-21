"""
crawl_agencies_pdfs.py  —  Crawl official agency websites and download all PDFs.

Strategy per agency:
  BOI          — server-rendered site; uses sitemap.xml (13,700 pages) to find publication pages
  ISA          — SPA (JS-rendered); uses direct known URL patterns
  CMISA        — gov.il SPA; uses gov.il BlobFolder URL pattern + known reports
  MOJ/Tax Auth — SSL legacy cipher issue; fixed with custom SSL adapter
  Finance Mnstry — gov.il SPA; uses BlobFolder pattern

Run: python crawl_agencies_pdfs.py
"""

import sys
import io
import time
import re
import ssl
import hashlib
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from html import unescape
from collections import deque

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4"])
    from bs4 import BeautifulSoup

import urllib3
urllib3.disable_warnings()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
KB   = BASE / "knowledge_base"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
}

MIN_PDF   = 5_000
MAX_PDF   = 50_000_000
DELAY     = 0.4
MAX_PAGES = 500
MAX_PDFS  = 300


# =============================================================================
# SSL-legacy adapter (fixes SSLV3_ALERT_HANDSHAKE_FAILURE on older gov servers)
# =============================================================================
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

def make_session(legacy_ssl=False):
    s = requests.Session()
    s.headers.update(HEADERS)
    if legacy_ssl:
        s.mount("https://", LegacySSLAdapter())
    return s


# =============================================================================
# Helpers
# =============================================================================
def slugify(url):
    path = urlparse(url).path
    name = Path(unquote(path)).name
    name = re.sub(r'[^\w\u0590-\u05FF._-]', '_', name)
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    if len(name) > 120:
        name = name[-100:] + '_' + hashlib.md5(url.encode()).hexdigest()[:6] + '.pdf'
    return name or 'doc.pdf'

def extract_pdf_hrefs(html, base_url):
    """Return absolute PDF URLs found anywhere in the page HTML."""
    pdfs = set()
    # Find raw href/src attributes with .pdf
    for m in re.finditer(r'(?:href|src|data-href|data-src)=["\']([^"\']*\.pdf[^"\']*)["\']',
                          html, re.IGNORECASE):
        url = unescape(m.group(1).strip())
        if url.startswith('//'):
            url = 'https:' + url
        if url.startswith('/') or url.startswith('http'):
            pdfs.add(urljoin(base_url, url).split('?')[0])
    return list(pdfs)

def extract_html_links(html, base_url, allowed_hosts):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(('#', 'javascript', 'mailto')):
            continue
        abs_url = urljoin(base_url, href).split('#')[0]
        p = urlparse(abs_url)
        if p.scheme not in ('http', 'https'):
            continue
        if abs_url.lower().endswith('.pdf'):
            continue
        if any(h in p.netloc for h in allowed_hosts):
            links.add(abs_url)
    return list(links)


def download_pdf(session, url, dest):
    """Download URL to dest. Returns (ok, size_or_reason)."""
    try:
        r = session.get(url, timeout=25, verify=False, stream=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > MAX_PDF:
                return False, "too large"
        if len(data) < MIN_PDF:
            return False, f"too small ({len(data)} B)"
        dest.write_bytes(data)
        return True, len(data)
    except Exception as e:
        return False, str(e)[:60]


# =============================================================================
# BOI: sitemap-based crawl
# =============================================================================
def crawl_boi(out_dir, session):
    print("  Strategy: sitemap-based crawl")

    # Fetch sitemap
    try:
        r = session.get("https://www.boi.org.il/sitemap.xml", timeout=30, verify=False)
        all_urls = re.findall(r'<loc>(.*?)</loc>', r.text)
    except Exception as e:
        print(f"  Sitemap error: {e}")
        return 0, 0

    # Publication-relevant URL patterns
    pub_keywords = [
        'boi-report', 'financial-stability', 'monetary-policy-report',
        'research-department-publications', 'working-paper', 'inflation-report',
        'banking-supervision', 'annual-report', 'foreign-currency',
        'payment-systems', 'budget', 'supervisor', 'discussion-paper',
        'economic-review', 'research-and-publications', 'bank-supervision-annual',
    ]
    skip_keywords = ['tenders', '/researchers/', '/tags/', '/news-archive/']
    candidates = [
        u for u in all_urls
        if any(kw in u.lower() for kw in pub_keywords)
        and not any(sk in u.lower() for sk in skip_keywords)
    ]
    print(f"  Found {len(candidates)} publication pages in sitemap")

    found_pdfs = set()
    downloaded = skipped = failed = 0

    for i, page_url in enumerate(candidates[:MAX_PAGES]):
        try:
            r = session.get(page_url, timeout=15, verify=False)
            if r.status_code != 200:
                continue
            page_pdfs = extract_pdf_hrefs(r.text, page_url)
            for pdf_url in page_pdfs:
                if pdf_url in found_pdfs:
                    continue
                found_pdfs.add(pdf_url)
                fname = slugify(pdf_url)
                dest = out_dir / fname
                if dest.exists() and dest.stat().st_size > MIN_PDF:
                    skipped += 1
                    continue
                print(f"    [{i+1}/{len(candidates)}] {fname[:65]} ...", end="", flush=True)
                ok, info = download_pdf(session, pdf_url, dest)
                if ok:
                    print(f" OK ({info:,} B)")
                    downloaded += 1
                else:
                    print(f" skip ({info})")
                    failed += 1
                time.sleep(DELAY)
                if downloaded >= MAX_PDFS:
                    break
        except Exception:
            pass
        time.sleep(0.2)
        if downloaded >= MAX_PDFS:
            break

    return downloaded, skipped


# =============================================================================
# Generic HTML crawler (for sites that are server-rendered)
# =============================================================================
def crawl_generic(seeds, allowed_hosts, out_dir, session, depth=2):
    queue = deque([(s, 0) for s in seeds])
    visited = set(seeds)
    found_pdfs = set()
    downloaded = skipped = failed = pages = 0

    while queue and pages < MAX_PAGES and downloaded < MAX_PDFS:
        url, d = queue.popleft()
        pages += 1
        try:
            r = session.get(url, timeout=15, verify=False)
            if r.status_code != 200:
                continue
            html = r.text
            # Extract PDFs
            for pdf_url in extract_pdf_hrefs(html, url):
                if pdf_url in found_pdfs:
                    continue
                found_pdfs.add(pdf_url)
                fname = slugify(pdf_url)
                dest = out_dir / fname
                if dest.exists() and dest.stat().st_size > MIN_PDF:
                    skipped += 1
                    continue
                print(f"    {fname[:65]} ...", end="", flush=True)
                ok, info = download_pdf(session, pdf_url, dest)
                if ok:
                    print(f" OK ({info:,} B)")
                    downloaded += 1
                else:
                    print(f" skip ({info})")
                    failed += 1
                time.sleep(DELAY)
                if downloaded >= MAX_PDFS:
                    break
            # Crawl deeper
            if d < depth:
                for link in extract_html_links(html, url, allowed_hosts):
                    if link not in visited:
                        visited.add(link)
                        queue.append((link, d + 1))
        except Exception:
            pass
        time.sleep(0.2)

    return downloaded, skipped


# =============================================================================
# ISA: mix of server-rendered pages + known URL patterns
# =============================================================================
ISA_SEEDS = [
    "https://www.new.isa.gov.il/he/publications/",
    "https://www.new.isa.gov.il/he/annual-reports/",
    "https://www.new.isa.gov.il/he/enforcement/",
    "https://www.new.isa.gov.il/he/supervision/",
    "https://www.new.isa.gov.il/he/research/",
    "https://www.new.isa.gov.il/he/regulation/",
    "https://www.new.isa.gov.il/he/investor-education/",
    # Old ISA site (static HTML)
    "https://www.isa.gov.il/sites/ISAHeb/About/Pages/default.aspx",
    "https://www.isa.gov.il/sites/ISAEng/About/Pages/default.aspx",
    "https://www.isa.gov.il/sites/ISAHeb/1502/Pages/default.aspx",
]

# =============================================================================
# CMISA / gov.il: try their publication BlobFolders + search
# =============================================================================
CMISA_SEEDS = [
    "https://www.gov.il/he/departments/capital_market/govil-landing-page",
    "https://www.gov.il/he/departments/publications/reports/capital_market",
    "https://www.gov.il/he/departments/topics/capital-market-insurance-savings/govil-landing-page",
]

# =============================================================================
# Tax Authority seeds (legacy SSL)
# =============================================================================
TAX_SEEDS = [
    "https://www.taxes.gov.il/IncomeTax/Pages/default.aspx",
    "https://www.taxes.gov.il/customs/Pages/default.aspx",
    "https://www.taxes.gov.il/RealEstateTaxation/Pages/default.aspx",
    "https://www.taxes.gov.il/VAT/Pages/default.aspx",
    "https://www.taxes.gov.il/Pages/TaxAuthorityPublications.aspx",
    "https://secapp.taxes.gov.il/",
]

# =============================================================================
# Ministry of Justice seeds (legacy SSL)
# =============================================================================
MOJ_SEEDS = [
    "https://www.justice.gov.il/Pubilcations/Pages/Publications.aspx",
    "https://www.justice.gov.il/Units/RashamHaptentim/about/Pages/default.aspx",
    "https://www.justice.gov.il/Units/MinheletHabira/Pages/default.aspx",
    "https://www.justice.gov.il/StateAttorney/Pages/default.aspx",
]

# =============================================================================
# Finance Ministry seeds
# =============================================================================
MOF_SEEDS = [
    "https://www.gov.il/he/departments/ministry_of_finance/govil-landing-page",
    "https://mof.gov.il/he/PublicationsAndReviews/Pages/default.aspx",
    "https://mof.gov.il/he/BudgetManagement/Pages/default.aspx",
]


# =============================================================================
# Main
# =============================================================================
print("=" * 65)
print("  GovPersona PDF Crawler  (v2)")
print("=" * 65)

JOBS = [
    {
        "org":      "central_bank",
        "label":    "Bank of Israel",
        "mode":     "boi",
        "ssl":      False,
    },
    {
        "org":      "securities_authority",
        "label":    "Israel Securities Authority",
        "mode":     "generic",
        "seeds":    ISA_SEEDS,
        "hosts":    ["isa.gov.il", "new.isa.gov.il"],
        "depth":    2,
        "ssl":      False,
    },
    {
        "org":      "capital_markets_authority",
        "label":    "Capital Markets, Insurance & Savings",
        "mode":     "generic",
        "seeds":    CMISA_SEEDS,
        "hosts":    ["gov.il"],
        "depth":    2,
        "ssl":      False,
    },
    {
        "org":      "ministry_of_justice",
        "label":    "Ministry of Justice",
        "mode":     "generic",
        "seeds":    MOJ_SEEDS,
        "hosts":    ["justice.gov.il"],
        "depth":    2,
        "ssl":      True,   # legacy SSL
    },
    {
        "org":      "tax_authority",
        "label":    "Israel Tax Authority",
        "mode":     "generic",
        "seeds":    TAX_SEEDS,
        "hosts":    ["taxes.gov.il", "secapp.taxes.gov.il"],
        "depth":    2,
        "ssl":      True,   # legacy SSL
    },
    {
        "org":      "finance_ministry",
        "label":    "Ministry of Finance",
        "mode":     "generic",
        "seeds":    MOF_SEEDS,
        "hosts":    ["gov.il", "mof.gov.il"],
        "depth":    2,
        "ssl":      False,
    },
]

total_new = 0
for job in JOBS:
    org   = job["org"]
    label = job["label"]
    out_dir = KB / org
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"  {label}  ({org})")
    print(f"{'='*65}")

    session = make_session(legacy_ssl=job["ssl"])

    if job["mode"] == "boi":
        dl, sk = crawl_boi(out_dir, session)
    else:
        dl, sk = crawl_generic(
            job["seeds"], job["hosts"], out_dir, session, depth=job.get("depth", 2)
        )

    print(f"\n  -> New PDFs: {dl}  |  Skipped (existing): {sk}")
    total_new += dl

print(f"\n{'='*65}")
print(f"  TOTAL new PDFs downloaded: {total_new}")
print(f"{'='*65}")
print("\nNext steps:")
for j in JOBS:
    print(f"  python ingest.py --org {j['org']}")
print("  python export_kb.py")
