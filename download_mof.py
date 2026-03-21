# -*- coding: utf-8 -*-
"""
Ministry of Finance – Chief Economist Division document downloader.
Downloads PDFs directly from gov.il BlobFolder URLs (HTML pages are WAF-blocked,
but direct PDF links are publicly accessible).

Saves to: knowledge_base/finance_ministry/<category>/

Usage:
  python download_mof.py                          # download all categories
  python download_mof.py --category forecasts
  python download_mof.py --category budget
  python download_mof.py --list                   # list available categories
"""
import sys
import io
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import os
import time

import requests

OUTPUT_ROOT = os.path.join(os.path.dirname(__file__), "knowledge_base", "finance_ministry")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "application/pdf,*/*;q=0.8",
    "Referer": "https://www.gov.il/",
}

# ── Curated PDF catalogue ──────────────────────────────────────────────────────
# gov.il BlobFolder direct PDF URLs — these are publicly accessible (200 OK).
# Organised by category → subfolder + list of (filename, url) tuples.

CATEGORIES = {
    "forecasts": {
        "name": "Macroeconomic Forecasts & Economic Analysis (תחזיות מאקרו-כלכליות)",
        "subfolder": "forecasts",
        "pdfs": [
            (
                "macroeconomics-trends-forecast-2025-2029-update.pdf",
                "https://www.gov.il/BlobFolder/reports/development-and-income-forecast-corona/he/"
                "Publishes_Reviews_macroeconomics-trends-and-forecast-2025-2029-update.pdf",
            ),
            (
                "consensus-forecast-round1-2025.pdf",
                "https://www.gov.il/BlobFolder/reports/review-03022025-main/he/"
                "reviews-and-publishes_review-03022025.pdf",
            ),
            (
                "consensus-forecast-round2-2025.pdf",
                "https://www.gov.il/BlobFolder/reports/review-29042025-main/he/"
                "reviews-and-publishes_review-29042025.pdf",
            ),
            (
                "macroeconomics-trends-forecast-2024-2025-update.pdf",
                "https://www.gov.il/BlobFolder/reports/development-and-income-forecast-corona/he/"
                "Publishes_Reviews_macroeconomics-trends-and-forecast-2024-2025-update.pdf",
            ),
            (
                "macroeconomics-trends-forecast-2023-2024.pdf",
                "https://www.gov.il/BlobFolder/reports/development-and-income-forecast-corona/he/"
                "Publishes_Reviews_macroeconomics-trends-and-forecast-2023-2024.pdf",
            ),
            (
                "macroeconomics-trends-forecast-2023-2027.pdf",
                "https://www.gov.il/BlobFolder/reports/macroeconomics-trends-and-forecast-2023-2027/he/"
                "Publishes_macroeconomic-forecast_macroeconomics-trends-and-forecast-2023-2027.pdf",
            ),
            (
                "economic-analysis-forecast-2023-2024-oct.pdf",
                "https://www.gov.il/BlobFolder/reports/development-and-income-forecast-corona/he/"
                "Publishes_Reviews_macroeconomics-econimic-analysis-and-forecast-2023-2024.pdf",
            ),
        ],
    },
    "budget": {
        "name": "State Budget Documents (תקציב המדינה)",
        "subfolder": "budget",
        "pdfs": [
            (
                "state-budget-2025-main.pdf",
                "https://www.gov.il/blobFolder/policy/state-budget-main-2025/he/"
                "state-budget_2025_state-budget-main-2025-file.pdf",
            ),
            (
                "state-budget-2023-2024-main.pdf",
                "https://www.gov.il/blobFolder/policy/state-budget-main-2023-2024/he/"
                "state-budget_2023-2024_state-budget-main-2023-2024-file.pdf",
            ),
            (
                "budget-plan-2026-2028.pdf",
                "https://www.gov.il/BlobFolder/reports/budget-plan-multi-years/he/"
                "budget-plan-multi-years_budgetplanupdate_2026-2028_publish-062025.pdf",
            ),
            (
                "economic-plan-2026.pdf",
                "https://www.gov.il/BlobFolder/reports/seder-gov031225/he/"
                "Seder_Gov_plan-eco2026.pdf",
            ),
        ],
    },
    "budget_execution": {
        "name": "Budget Execution Reports (ביצוע תקציב)",
        "subfolder": "budget_execution",
        "pdfs": [
            (
                "budget-execution-report-2024.pdf",
                "https://www.gov.il/BlobFolder/reports/budget-execution-reports-2024/he/"
                "files_budget-execution-reports_budget-execution-reports-2024-report.pdf",
            ),
            (
                "budget-execution-presentation-2024.pdf",
                "https://www.gov.il/BlobFolder/reports/budget-execution-reports-2024/he/"
                "files_budget-execution-reports_budget-execution-reports-2024-presentation.pdf",
            ),
        ],
    },
    "debt": {
        "name": "Annual Debt Reports (דוחות חוב שנתיים)",
        "subfolder": "debt_reports",
        "pdfs": [
            (
                "annual-debt-report-2024-en.pdf",
                "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/annual-debt-report-2024/en/"
                "files-eng_Annual-Debt-Reports_annual-debt-report-2024-accessible-version-en.pdf",
            ),
            (
                "annual-debt-report-2023-en.pdf",
                "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/annual-debt-report-2023/en/"
                "files-eng_Annual-Debt-Reports_annual-debt-report-2023-print-version-eng.pdf",
            ),
        ],
    },
    "oecd_surveys": {
        "name": "OECD Economic Surveys – Israel (סקרי OECD)",
        "subfolder": "oecd_surveys",
        "pdfs": [
            (
                "oecd-economic-survey-israel-2025.pdf",
                "https://www.gov.il/BlobFolder/news/press_02042025/he/"
                "PressReleases_files_press_02042025_file.pdf",
            ),
            (
                "oecd-economic-survey-israel-2020.pdf",
                "https://www.gov.il/blobfolder/news/press_23092020_b/he/"
                "pressreleases_files_press_23092020_b_file.pdf",
            ),
            (
                "oecd-economic-survey-israel-2018.pdf",
                "https://www.gov.il/BlobFolder/news/press_11032018_a/he/"
                "PressReleases_files_2018-oecd-economic-survey-Israel.pdf",
            ),
        ],
    },
    "research": {
        "name": "Research & Special Reports (מחקר ודוחות מיוחדים)",
        "subfolder": "research",
        "pdfs": [
            (
                "digital-asset-regulation-2022-en.pdf",
                "https://www.gov.il/BlobFolder/news/press_28112022/en/"
                "PressReleases_eng_Files_eng_Digital-Asset-Regulation.pdf",
            ),
            (
                "bank-tax-team-report.pdf",
                "https://www.gov.il/BlobFolder/reports/banks-tax-team-report/he/"
                "Publishes_banks-tax-team-report.pdf",
            ),
        ],
    },
}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def download_pdf(session: requests.Session, url: str, output_dir: str, filename: str) -> str:
    """Download a single PDF. Returns a status string."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        return f"SKIP  {filename} (already downloaded)"

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            return f"WARN  {filename} — unexpected content-type: {content_type[:60]}"

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)

        size_kb = os.path.getsize(output_path) // 1024
        return f"SAVED {filename} ({size_kb} KB)"
    except requests.HTTPError as e:
        return f"ERROR {filename}: HTTP {e.response.status_code}"
    except Exception as e:
        return f"ERROR {filename}: {e}"


# ── Main download flow ─────────────────────────────────────────────────────────

def download_category(session: requests.Session, cat_id: str, cat: dict) -> dict:
    """Download all PDFs for a single category. Returns stats dict."""
    print(f"\n{'='*60}")
    print(f">> {cat['name']}")
    print(f"{'='*60}")

    output_dir = os.path.join(OUTPUT_ROOT, cat["subfolder"])
    os.makedirs(output_dir, exist_ok=True)

    stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    for filename, url in cat["pdfs"]:
        status = download_pdf(session, url, output_dir, filename)
        print(f"  {status}")
        if status.startswith("SAVED"):
            stats["downloaded"] += 1
        elif status.startswith("SKIP"):
            stats["skipped"] += 1
        else:
            stats["errors"] += 1
        time.sleep(0.5)

    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download MoF Chief Economist documents to knowledge_base/finance_ministry/"
    )
    parser.add_argument(
        "--category",
        choices=list(CATEGORIES.keys()),
        default=None,
        help="Download a specific category (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available categories and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable categories:")
        for cat_id, cat in CATEGORIES.items():
            count = len(cat["pdfs"])
            print(f"  {cat_id:<20} ({count} PDFs)  {cat['name']}")
        return

    cats_to_run = (
        {args.category: CATEGORIES[args.category]}
        if args.category
        else CATEGORIES
    )

    total_pdfs = sum(len(c["pdfs"]) for c in cats_to_run.values())
    print("\nMoF Chief Economist Document Downloader")
    print(f"Output : {OUTPUT_ROOT}")
    print(f"Categories : {', '.join(cats_to_run.keys())}")
    print(f"Total PDFs : {total_pdfs}")

    session = make_session()
    total_stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    for cat_id, cat in cats_to_run.items():
        stats = download_category(session, cat_id, cat)
        for k in total_stats:
            total_stats[k] += stats[k]

    print(f"\n{'='*60}")
    print("Done!")
    print(f"   Downloaded : {total_stats['downloaded']} new file(s)")
    print(f"   Skipped    : {total_stats['skipped']} (already had them)")
    print(f"   Errors     : {total_stats['errors']}")
    print(f"\nFiles saved to: {OUTPUT_ROOT}")
    print(
        "\nNext step: run:\n"
        "  python ingest.py --org finance_ministry\n"
        "to load the PDFs into GovPersona's knowledge base."
    )


if __name__ == "__main__":
    main()
