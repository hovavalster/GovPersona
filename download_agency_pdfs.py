"""
download_agency_pdfs.py — Download curated PDFs for ISA, CMISA, MOJ, Tax Authority.

These agencies have JS-SPA websites that can't be crawled; URLs sourced manually.
"""

import sys
import io
import time
import hashlib
import re
import ssl
import requests
from pathlib import Path
from urllib.parse import unquote, urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import urllib3
urllib3.disable_warnings()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE    = Path(__file__).parent
KB      = BASE / "knowledge_base"
MIN_PDF = 5_000
MAX_PDF = 60_000_000
DELAY   = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
}

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

def slugify(url):
    path = urlparse(url).path
    name = Path(unquote(path)).name
    name = re.sub(r'[^\w\u0590-\u05FF._-]', '_', name)
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    if len(name) > 120:
        name = name[-90:] + '_' + hashlib.md5(url.encode()).hexdigest()[:6] + '.pdf'
    return name or 'doc.pdf'

def download(session, url, dest):
    try:
        r = session.get(url, timeout=40, verify=False, stream=True)
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
        return False, str(e)[:80]


# =============================================================================
# Curated PDF lists per agency
# =============================================================================

PDFS = {
    "securities_authority": [
        # ISA Annual Reports
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f2c2bb1c37/report_2024.pdf",
         "ISA Annual Report 2024 (Hebrew)"),
        ("https://www.new.isa.gov.il/en/images/Fittings/isa-be/asset_library_pic/al_lobby/al_lobby-649135bbde875/ANNUALREPORT2023.pdf",
         "ISA Annual Report 2023 (English)"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f2c2bb1c37/isareport2023.pdf",
         "ISA Annual Report 2023 (Hebrew)"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637b90c7be39b/AnnualReport2022.pdf",
         "ISA Annual Report 2022 (English)"),
        # ISA Financial Statements & Highlights
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f2c2bb1c37/FinancialReport2022-M.pdf",
         "ISA Financial Statements 2022"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6253f4f00241c/Highlights_report25.pdf",
         "ISA Corporate Dept Highlights 2025"),
        # Regulatory Guidance
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6253f4f00241c/codexIndex.pdf",
         "ISA Investment Codex (index of regulations)"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-62bd445f910eb/MoneyMarketFundReg24.pdf",
         "ISA Money Market Fund Regulations 2024"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-637f62a916518/IXBRL170823.pdf",
         "ISA IXBRL Reporting Proposal 2023"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-628ce07f9490d/Exemption_regulations.pdf",
         "ISA Exemption Regulations"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/Foreign_Underwriters_Guide.pdf",
         "ISA Guide for Foreign Underwriters"),
        ("https://www.new.isa.gov.il/en/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-64fee64cb474c/13052021.pdf",
         "ISA ESG Disclosure Guidance 2021"),
        ("https://www.new.isa.gov.il/images/Fittings/isa-be/asset_library_pic/al_lobby/al_lobby-63a2db729e575/QA-Tashlum.pdf",
         "ISA Q&A Payment Service Providers 2024"),
        ("https://www.new.isa.gov.il/images/Fittings/isa/asset_library_pic/al_lobby/al_lobby-6547a86b2d6b6/report_en3625.pdf",
         "ISA Regulatory Report (English)"),
    ],

    "capital_markets_authority": [
        # Commissioner Annual Reports
        ("https://www.gov.il/BlobFolder/news/press_0083/he/Commisioner%20Report%20Design%20B_chapter3%20ver%206.0_digital.pdf",
         "CMISA Commissioner Report 2024 — Ch.3 Market Trends"),
        ("https://www.gov.il/BlobFolder/news/press_0083/he/Commisioner%20Report%20Design%20B_chapter4%20ver%206.0_digital.pdf",
         "CMISA Commissioner Report 2024 — Ch.4 Pension Savings Data"),
        ("https://www.gov.il/BlobFolder/reports/1_annual_report_2021/he/CMISA_AnnualReport_Chapter3.pdf",
         "CMISA Annual Report 2021 — Ch.3 Insurance Data"),
        # Public Complaints
        ("https://www.gov.il/BlobFolder/reports/report_0011/he/1766497697_%D7%93%D7%95%D7%97_%D7%A4%D7%A0%D7%99%D7%95%D7%AA_%D7%94%D7%A6%D7%99%D7%91%D7%95%D7%A8_2024_V10.pdf",
         "CMISA Public Complaints Report 2024 v10"),
        # Regulatory Circulars
        ("https://www.gov.il/BlobFolder/dynamiccollectorresultitem/notice-2023-019/he/DRlist%20_regulation_27082023_PDF.pdf",
         "CMISA Website Info Requirements 2023"),
        ("https://www.gov.il/BlobFolder/dynamiccollectorresultitem/notice-2023-052/he/Regulation_2024-10-3_P.pdf",
         "CMISA Cyber Risk Management Regulation 2024"),
        ("https://www.gov.il/BlobFolder/dynamiccollectorresultitem/notice-2024-118/he/questions_answers.pdf",
         "CMISA Q&A Institutional Reporting 2024"),
        ("https://www.gov.il/BlobFolder/dynamiccollectorresultitem/notice-2024-119/he/roadmap-update5-withchanges-PDF.pdf",
         "CMISA IFRS 17 Roadmap Update 2024"),
        # State Comptroller audits of CMISA
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2024/The-cost-of-living/2024-The-cost-of-living-104-Hon.pdf",
         "State Comptroller 2024 — CMISA Supervision of Savings"),
        ("https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.11/EN/2022.11-307-Pension-EN.pdf",
         "State Comptroller 2022 — Pension Aspects (English)"),
    ],

    "ministry_of_justice": [
        # Courts Administration
        ("https://www.gov.il/BlobFolder/reports/statistics_annual_2022/he/22%20JB.pdf",
         "Courts Administration Annual Statistics 2022"),
        # Freedom of Information
        ("https://www.gov.il/BlobFolder/generalpage/freedom-of-info-law/he/annual-report-freedom-of-info-2023.pdf",
         "Freedom of Information Annual Report 2023"),
        ("https://www.gov.il/BlobFolder/generalpage/freedom_information_law/he/foi-attorney-report-2022.pdf",
         "Freedom of Information — State Attorney 2022"),
        ("https://www.gov.il/BlobFolder/generalpage/freedom_information_act/he/annual-reports-publications_info-freedom-eca-report-2023.pdf",
         "Freedom of Information — Enforcement Authority 2023"),
        # Public Complaints Commissioner
        ("https://www.gov.il/BlobFolder/reports/annual_report_2014/he/reoport-2022.pdf",
         "Public Complaints Commissioner on Courts 2022"),
        ("https://www.gov.il/BlobFolder/reports/account/he/account-2023.pdf",
         "Public Complaints Commissioner on Judges 2023"),
        # Activity Summary
        ("https://www.gov.il/BlobFolder/reports/summary_2022_report/he/summary_2022.pdf",
         "Ministry of Justice Activity Summary 2022"),
        # State Attorney
        ("https://www.justice.gov.il/Units/StateAttorney/Documents/data-report-2017.pdf",
         "State Attorney Data Report 2017"),
        # Knesset — State Attorney data
        ("https://fs.knesset.gov.il/25/law/25_ls_bk_9695918.pdf",
         "State Attorney Office Data to Knesset 2025"),
    ],

    "tax_authority": [
        # Income Tax Circulars
        ("https://www.gov.il/BlobFolder/policy/inst-05-2024/he/IncomeTax_inst-05-2024.pdf",
         "Income Tax Instruction 05/2024"),
        # Tax Reform
        ("https://www.gov.il/BlobFolder/unit/tax-reforma-committee/he/Vaadot_ahchud_TaxReformaCommittee_Report_Chapter1.PDF",
         "Tax Reform Committee Report — Chapter 1"),
        # Open API docs
        ("https://www.gov.il/BlobFolder/service/connect-to-shaam/he/Service_Pages_shaam_Tax-Authority-Open-API.pdf",
         "Tax Authority SHAAM Open API Documentation"),
        # OECD Revenue Statistics
        ("https://www.oecd.org/content/dam/oecd/en/topics/policy-sub-issues/global-tax-revenues/revenue-statistics-israel.pdf",
         "OECD Revenue Statistics 2024 — Israel"),
        # Knesset Research — State Revenues Analysis
        ("https://fs.knesset.gov.il/globaldocs/MMM/6745f598-afce-ef11-a856-005056aa1f91/2_6745f598-afce-ef11-a856-005056aa1f91_11_20780.pdf",
         "Knesset Research — State Revenues 2024/2025"),
    ],
}

# =============================================================================
# Main
# =============================================================================
session = make_session()
total_new = 0

print("=" * 65)
print("  GovPersona — Targeted PDF Downloader (agency publications)")
print("=" * 65)

for org, urls in PDFS.items():
    out_dir = KB / org
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = failed = 0

    print(f"\n{'='*65}")
    print(f"  {org}  ({len(urls)} URLs)")
    print(f"{'='*65}")

    for url, label in urls:
        fname = slugify(url)
        dest  = out_dir / fname
        if dest.exists() and dest.stat().st_size > MIN_PDF:
            print(f"  skip (exists) {fname[:60]}")
            skipped += 1
            continue
        print(f"  {label[:55]}", end="", flush=True)
        ok, info = download(session, url, dest)
        if ok:
            print(f" — OK ({info:,} B)")
            downloaded += 1
        else:
            print(f" — FAIL ({info})")
            failed += 1
        time.sleep(DELAY)

    print(f"\n  -> New: {downloaded}  |  Skipped: {skipped}  |  Failed: {failed}")
    total_new += downloaded

print(f"\n{'='*65}")
print(f"  TOTAL new PDFs: {total_new}")
print(f"{'='*65}")
print("\nNext steps:")
for org in PDFS:
    print(f"  python ingest.py --org {org}")
print("  python export_kb.py")
