# -*- coding: utf-8 -*-
"""
Bank of Israel document downloader.
Scrapes boi.org.il and saves PDFs to knowledge_base/central_bank/<category>/

Usage:
  python download_boi.py                          # download all categories
  python download_boi.py --category financial_stability
  python download_boi.py --category monetary_policy
  python download_boi.py --list                   # list available categories
  python download_boi.py --max-per-category 5     # limit downloads per category
"""
import sys, io
# Force UTF-8 output on Windows so status lines print correctly
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import os
import re
import sys
import time
import json

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.boi.org.il"
OUTPUT_ROOT = os.path.join(os.path.dirname(__file__), "knowledge_base", "central_bank")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Publication categories — add more here as needed
CATEGORIES = {
    "financial_stability": {
        "name": "Financial Stability Reports (דוחות יציבות פיננסית)",
        "url": "https://www.boi.org.il/en/communication-and-publications/regular-publications/financial-stability/",
        "subfolder": "financial_stability",
    },
    "monetary_policy": {
        "name": "Monetary Policy Reports (דוחות מדיניות מוניטרית)",
        "url": "https://www.boi.org.il/en/communication-and-publications/regular-publications/monetary-policy-reports/",
        "subfolder": "monetary_policy",
    },
    "annual_report": {
        "name": "Annual Reports (דוחות שנתיים)",
        "url": "https://www.boi.org.il/en/communication-and-publications/regular-publications/annual-report/",
        "subfolder": "annual_reports",
    },
    "interest_rate": {
        "name": "Interest Rate Decisions (החלטות ריבית)",
        "url": "https://www.boi.org.il/en/communication-and-publications/press-releases/?type=interest-rate",
        "subfolder": "interest_rate_decisions",
    },
    "research_papers": {
        "name": "Discussion Papers / Research (מסמכי דיון)",
        "url": "https://www.boi.org.il/en/research-and-publications/working-papers/",
        "subfolder": "research_papers",
    },
}


# ── HTTP Session ───────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ── Page fetching ──────────────────────────────────────────────────────────────

def fetch_html(session: requests.Session, url: str, retries: int = 3) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"  WARNING: Could not fetch {url}: {e}")
                return None


def _extract_links_from_container(soup: BeautifulSoup, listing_url: str) -> list[str]:
    """
    Extract publication detail-page links from #itemsContainer only.
    Falls back to the whole page if #itemsContainer is absent.
    Excludes the listing page itself to avoid infinite loops.
    """
    container = soup.find(id="itemsContainer") or soup
    listing_path = listing_url.replace(BASE_URL, "").rstrip("/")

    links = []
    for a in container.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]  # strip query + fragment
        if not href or href == listing_path or href == listing_url:
            continue
        # Must be a sub-page of this listing (deeper path)
        if href.startswith(listing_path + "/") and len(href) > len(listing_path) + 2:
            full = BASE_URL + href if href.startswith("/") else href
            if full not in links:
                links.append(full)
    return links


def try_ajax_pagination(
    session: requests.Session,
    listing_url: str,
    initial_soup: BeautifulSoup,
    max_pages: int = 10,
) -> list[str]:
    """
    Use the Bank of Israel AJAX filter endpoint to retrieve additional pages.
    """
    # The BOI filter endpoint needs a PageId (the Umbraco node id of the listing page).
    # It's stored as data-page-id on the items container or a nearby element.
    page_id = None
    for tag in initial_soup.find_all(True, attrs={"data-page-id": True}):
        page_id = tag["data-page-id"]
        break
    if not page_id:
        for inp in initial_soup.find_all("input", {"type": "hidden"}):
            name = (inp.get("name") or "").lower()
            if "pageid" in name or "nodeid" in name or "currentpage" in name:
                page_id = inp.get("value")
                break

    links = []
    for page_idx in range(1, max_pages + 1):
        payload = {"PageIndex": page_idx, "PageSize": 10}
        if page_id:
            payload["PageId"] = page_id

        try:
            resp = session.post(
                BASE_URL + "/BoiControllers/Publications/Filter",
                data=payload,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": listing_url,
                },
                timeout=30,
            )
            if resp.status_code != 200 or len(resp.text.strip()) < 50:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            new_links = _extract_links_from_container(soup, listing_url)
            if not new_links:
                break
            links.extend(new_links)
            time.sleep(0.5)
        except Exception:
            break

    return links


def get_all_publication_links(
    session: requests.Session,
    listing_url: str,
    max_pages: int = 10,
) -> list[str]:
    """Load listing page + paginate via AJAX to get all publication detail links."""
    print(f"  Fetching listing page...")
    soup = fetch_html(session, listing_url)
    if not soup:
        return []

    links = _extract_links_from_container(soup, listing_url)
    print(f"  Found {len(links)} publications on first page.")

    more = try_ajax_pagination(session, listing_url, soup, max_pages=max_pages)
    if more:
        before = len(links)
        for link in more:
            if link not in links:
                links.append(link)
        if len(links) > before:
            print(f"  Got {len(links) - before} more via pagination (total: {len(links)}).")

    return links


# ── PDF extraction & download ──────────────────────────────────────────────────

def get_pdf_links(session: requests.Session, page_url: str) -> list[str]:
    """Visit a publication detail page and return all PDF URLs found."""
    soup = fetch_html(session, page_url)
    if not soup:
        return []

    pdfs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0].split("?")[0]
        if ".pdf" in href.lower() and "/media/" in href:
            full = BASE_URL + href if href.startswith("/") else href
            pdfs.add(full)

    return list(pdfs)


def safe_filename(url: str) -> str:
    """Convert a URL to a safe Windows filename."""
    name = url.split("/")[-1].split("?")[0].split("#")[0]
    # Decode percent-encoded Hebrew chars
    try:
        from urllib.parse import unquote
        name = unquote(name)
    except Exception:
        pass
    # Replace illegal Windows filename characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name or "document.pdf"


def download_pdf(
    session: requests.Session,
    url: str,
    output_dir: str,
) -> str:
    """Download a single PDF. Returns a status string."""
    os.makedirs(output_dir, exist_ok=True)
    filename = safe_filename(url)
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        return f"SKIP  {filename} (already downloaded)"

    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)

        size_kb = os.path.getsize(output_path) // 1024
        return f"SAVED {filename} ({size_kb} KB)"
    except Exception as e:
        return f"ERROR {url}: {e}"


# ── Main download flow ─────────────────────────────────────────────────────────

def download_category(
    session: requests.Session,
    cat_id: str,
    cat: dict,
    max_items: int | None,
    max_pages: int = 10,
) -> dict:
    """Download all PDFs for a single category. Returns stats dict."""
    print(f"\n{'='*60}")
    print(f">> {cat['name']}")
    print(f"{'='*60}")

    output_dir = os.path.join(OUTPUT_ROOT, cat["subfolder"])
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: get publication page links
    pub_links = get_all_publication_links(session, cat["url"], max_pages=max_pages)

    if not pub_links:
        print("  No publication links found.")
        return {"downloaded": 0, "skipped": 0, "errors": 0}

    if max_items:
        pub_links = pub_links[:max_items]

    print(f"  Processing {len(pub_links)} publication(s)...")

    # Step 2: for each publication, find and download PDFs
    stats = {"downloaded": 0, "skipped": 0, "errors": 0}
    all_pdfs = []

    for pub_url in pub_links:
        pdfs = get_pdf_links(session, pub_url)
        all_pdfs.extend(pdfs)
        time.sleep(0.3)  # polite delay between page requests

    # Deduplicate
    all_pdfs = list(dict.fromkeys(all_pdfs))
    print(f"  Found {len(all_pdfs)} PDF(s) to download.")

    for pdf_url in all_pdfs:
        status = download_pdf(session, pdf_url, output_dir)
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
        description="Download Bank of Israel documents to knowledge_base/central_bank/"
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
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of publications to process per category",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        metavar="N",
        help="Maximum pagination pages to scrape per category (default 10)",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable categories:")
        for cat_id, cat in CATEGORIES.items():
            print(f"  {cat_id:<25} {cat['name']}")
        return

    cats_to_run = (
        {args.category: CATEGORIES[args.category]}
        if args.category
        else CATEGORIES
    )

    print(f"\nBank of Israel Document Downloader")
    print(f"Output: {OUTPUT_ROOT}")
    print(f"Categories: {', '.join(cats_to_run.keys())}")

    session = make_session()
    total_stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    for cat_id, cat in cats_to_run.items():
        stats = download_category(
            session,
            cat_id,
            cat,
            max_items=args.max_per_category,
            max_pages=args.max_pages,
        )
        for k in total_stats:
            total_stats[k] += stats[k]

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"   Downloaded : {total_stats['downloaded']} new file(s)")
    print(f"   Skipped    : {total_stats['skipped']} (already had them)")
    print(f"   Errors     : {total_stats['errors']}")
    print(f"\nFiles saved to: {OUTPUT_ROOT}")
    print(
        f"\nNext step: go to GovPersona → Train Agent tab → select Bank of Israel → "
        f"upload the files, OR run:\n"
        f"  python ingest.py --org central_bank"
    )


if __name__ == "__main__":
    main()
