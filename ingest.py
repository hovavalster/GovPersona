"""
CLI batch ingestion script.

Usage:
  python ingest.py --org finance_ministry
  python ingest.py --org central_bank --file path/to/report.pdf
  python ingest.py --org securities_authority --clear

By default, ingests all PDF/TXT/JSON files from knowledge_base/<org>/.
"""
from dotenv import load_dotenv
load_dotenv()

import argparse
import os
import sys

from agents.registry import list_agents, get_agent
from core.document_loader import ingest_file
from core.vector_store import get_vsm

_KB_ROOT = os.path.join(os.path.dirname(__file__), "knowledge_base")
_SUPPORTED = {".pdf", ".txt", ".json"}


def main():
    parser = argparse.ArgumentParser(description="GovPersona batch document ingestor")
    parser.add_argument(
        "--org",
        required=True,
        help="Agent org_id (e.g. finance_ministry, central_bank, securities_authority)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Path to a single file to ingest (optional; defaults to all files in knowledge_base/<org>/)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the collection before ingesting",
    )
    args = parser.parse_args()

    # Validate org
    known = {oid for oid, _ in list_agents()}
    if args.org not in known:
        print(f"ERROR: Unknown org '{args.org}'. Known agents: {sorted(known)}")
        sys.exit(1)

    vsm = get_vsm()

    if args.clear:
        print(f"Clearing collection for '{args.org}'...")
        vsm.clear_collection(args.org)
        print("Collection cleared.")

    # Build file list
    if args.file:
        files = [args.file]
    else:
        kb_dir = os.path.join(_KB_ROOT, args.org)
        if not os.path.isdir(kb_dir):
            print(f"ERROR: Knowledge base directory not found: {kb_dir}")
            sys.exit(1)
        files = [
            os.path.join(kb_dir, f)
            for f in os.listdir(kb_dir)
            if os.path.splitext(f)[1].lower() in _SUPPORTED
        ]

    if not files:
        print(f"No supported files found for org '{args.org}'.")
        sys.exit(0)

    print(f"Ingesting {len(files)} file(s) into '{args.org}'...")
    total_added = 0
    total_chunks = 0

    for fp in files:
        fname = os.path.basename(fp)
        try:
            added, total, warning = ingest_file(
                file_path=fp,
                org_id=args.org,
                vsm=vsm,
            )
            total_added += added
            total_chunks += total
            status = f"  ✓ {fname}: {added} new chunks (of {total} total)"
            if warning:
                status += f"\n    ⚠ {warning}"
            print(status)
        except Exception as e:
            print(f"  ✗ {fname}: ERROR — {e}")

    print(f"\nDone. {total_added}/{total_chunks} chunks added to '{args.org}'.")
    print(f"Total indexed: {vsm.get_doc_count(args.org)} chunks.")


if __name__ == "__main__":
    main()
