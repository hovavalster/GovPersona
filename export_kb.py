# -*- coding: utf-8 -*-
"""
export_kb.py — Run ONCE on your home laptop to export ChromaDB to portable JSON.

The JSON files are then placed inside GovPersona-CLI/ and zipped for the work computer.
No embeddings are re-computed; this just reads what's already stored in ChromaDB.

Usage:
  python export_kb.py
  python export_kb.py --out-dir C:\\path\\to\\GovPersona-CLI
"""
import sys
import io
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="Export GovPersona ChromaDB to JSON files.")
    parser.add_argument(
        "--out-dir",
        default=os.path.join(SCRIPT_DIR, "GovPersona-CLI"),
        help="Output directory for JSON files (default: GovPersona-CLI/ next to this script)",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # ── Check chromadb ────────────────────────────────────────────────────────
    try:
        import chromadb
        from chromadb import Settings
    except ImportError:
        print("ERROR: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)

    # ── Load agent configs ────────────────────────────────────────────────────
    agents_json = os.path.join(SCRIPT_DIR, "config", "agents.json")
    if not os.path.exists(agents_json):
        print(f"ERROR: agents.json not found at {agents_json}")
        sys.exit(1)

    with open(agents_json, encoding="utf-8") as f:
        agents = json.load(f)

    # Copy agents_config.json to output dir
    out_agents = os.path.join(out_dir, "agents_config.json")
    with open(out_agents, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)
    print(f"  Saved agents_config.json  ({len(agents)} agents)")

    # ── Connect to ChromaDB ───────────────────────────────────────────────────
    db_path = os.path.join(SCRIPT_DIR, "data", "chroma_db")
    if not os.path.exists(db_path):
        print(f"ERROR: ChromaDB not found at {db_path}")
        print("  Run the GovPersona app and ingest documents first.")
        sys.exit(1)

    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False),
    )

    # ── Export each org ───────────────────────────────────────────────────────
    total_chunks = 0
    BATCH = 5000

    for org_id, cfg in agents.items():
        print(f"\n  Exporting '{org_id}'...")

        try:
            collection = client.get_collection(name=org_id)
        except Exception as e:
            print(f"  WARNING: Collection '{org_id}' not found ({e}). Skipping.")
            continue

        count = collection.count()
        if count == 0:
            print(f"  WARNING: Collection '{org_id}' is empty. Skipping.")
            continue

        all_chunks = []
        offset = 0
        while offset < count:
            result = collection.get(
                include=["documents", "metadatas"],
                limit=BATCH,
                offset=offset,
            )
            for doc_id, doc, meta in zip(
                result["ids"], result["documents"], result["metadatas"]
            ):
                all_chunks.append({
                    "id": doc_id,
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "org_id": meta.get("org_id", org_id),
                    "doc_type": meta.get("doc_type", "document"),
                    "chunk_index": meta.get("chunk_index", 0),
                })
            offset += BATCH
            print(f"    ...{min(offset, count)}/{count}", end="\r", flush=True)

        out_file = os.path.join(out_dir, f"kb_{org_id}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            # Compact JSON: no indent, saves ~30% vs pretty-print
            json.dump(all_chunks, f, ensure_ascii=False, separators=(",", ":"))

        size_mb = os.path.getsize(out_file) / (1024 * 1024)
        print(f"  Saved {count:,} chunks  ->  kb_{org_id}.json  ({size_mb:.1f} MB)")
        total_chunks += count

    print(f"\n{'='*55}")
    print(f"  Total exported: {total_chunks:,} chunks")
    print(f"  Output folder : {out_dir}")
    print()
    print("  NEXT STEPS:")
    print("  1. Copy the contents of GovPersona-CLI/ to a USB or email")
    print("  2. On the work computer, run  install.bat  once")
    print("  3. Then run  ask.bat  to ask questions")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
