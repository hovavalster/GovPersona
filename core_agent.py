"""
core_agent.py — RAG pipeline template for Government Organizational Persona.

Demonstrates the full cycle:
  1. Load & chunk a text or PDF document
  2. Store chunks in a local ChromaDB vector store
  3. Retrieve relevant context for a query
  4. Build a persona-aligned system prompt (zero hallucination policy)
  5. Call Claude and return a cited answer

Run:
    python core_agent.py --org finance_ministry --question "What is Israel's deficit target?"
    python core_agent.py --org finance_ministry --file path/to/document.pdf --ingest-only
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from typing import Any

import anthropic
import chromadb
from chromadb import Settings
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2000
TEMPERATURE = 0.3
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
N_RESULTS = 7
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "chroma_db")

# Zero-hallucination persona prompt template
SYSTEM_TEMPLATE = """\
You are a senior official and institutional spokesperson for {org_name}.

STRICT RULES:
- Answer ONLY from the retrieved context below.
- If the answer is not found in the context, say exactly:
  "The available documents do not address this specific point."
- Never fabricate statistics, dates, names, or policy positions.
- Cite the source document for every factual claim using [Source N].
- Respond in the SAME LANGUAGE as the question.

MANDATE: {org_mandate}

RETRIEVED CONTEXT:
{context}
"""


# ── Document loading & chunking ────────────────────────────────────────────────

def load_pdf(path: str) -> str:
    """Extract plain text from a PDF file.

    Args:
        path: Absolute or relative path to the PDF.

    Returns:
        Full extracted text as a single string.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a PDF or yields no text.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise ValueError(f"No text extracted from {path} (may be a scanned image).")
    return text


def load_txt(path: str) -> str:
    """Load plain text from a .txt file.

    Args:
        path: Path to the text file.

    Returns:
        File contents as a string.
    """
    with open(path, encoding="utf-8") as f:
        return f.read()


def chunk_text(
    text: str,
    source: str,
    org_id: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Split text into overlapping chunks with metadata.

    Args:
        text: Full document text.
        source: Source filename (used in citations).
        org_id: Organisation identifier.
        chunk_size: Target character count per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        Tuple of (chunks, metadatas) where metadatas[i] describes chunks[i].
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    chunks: list[str] = []
    metadatas: list[dict[str, Any]] = []

    current = ""
    idx = 0
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append(current.strip())
            metadatas.append({"source": source, "org_id": org_id, "chunk_index": idx})
            idx += 1
            # Keep overlap
            current = current[-overlap:] + "\n\n" + para
        else:
            current += ("\n\n" if current else "") + para

    if current.strip():
        chunks.append(current.strip())
        metadatas.append({"source": source, "org_id": org_id, "chunk_index": idx})

    return chunks, metadatas


# ── Vector store ───────────────────────────────────────────────────────────────

def get_collection(org_id: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection for the given org.

    Args:
        org_id: Organisation identifier (e.g. "finance_ministry").

    Returns:
        A ChromaDB Collection ready for add/query operations.
    """
    os.makedirs(DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(
        path=DB_PATH,
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=org_id,
        metadata={"hnsw:space": "cosine"},
    )


def store_chunks(
    org_id: str,
    chunks: list[str],
    metadatas: list[dict[str, Any]],
) -> tuple[int, int]:
    """Add text chunks to the vector store, skipping duplicates.

    Args:
        org_id: Organisation identifier.
        chunks: List of text chunks.
        metadatas: Parallel list of metadata dicts.

    Returns:
        Tuple of (newly_added, total_submitted).
    """
    collection = get_collection(org_id)
    ids = [hashlib.md5(c.encode()).hexdigest() for c in chunks]

    existing_set = set(collection.get(ids=ids, include=[])["ids"])
    new = [(i, c, m) for i, c, m in zip(ids, chunks, metadatas) if i not in existing_set]

    if new:
        new_ids, new_chunks, new_metas = zip(*new)
        collection.add(
            ids=list(new_ids),
            documents=list(new_chunks),
            metadatas=list(new_metas),
        )
    return len(new), len(chunks)


def ingest_file(path: str, org_id: str) -> tuple[int, int]:
    """Full ingestion pipeline: load → chunk → store.

    Args:
        path: Path to PDF or TXT file.
        org_id: Target organisation collection.

    Returns:
        Tuple of (chunks_added, total_chunks).
    """
    ext = os.path.splitext(path)[1].lower()
    text = load_pdf(path) if ext == ".pdf" else load_txt(path)
    source = os.path.basename(path)
    chunks, metadatas = chunk_text(text, source, org_id)
    return store_chunks(org_id, chunks, metadatas)


# ── Retrieval ──────────────────────────────────────────────────────────────────

def retrieve(
    org_id: str,
    query: str,
    n_results: int = N_RESULTS,
) -> list[dict[str, Any]]:
    """Semantic similarity search over the org's collection.

    Args:
        org_id: Organisation identifier.
        query: Natural language query.
        n_results: Number of chunks to return.

    Returns:
        List of dicts with keys: text, source, distance.
    """
    collection = get_collection(org_id)
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "text": doc,
            "source": meta.get("source", "unknown"),
            "distance": dist,
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


def build_context(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved chunks as numbered source blocks.

    Args:
        chunks: Output of retrieve().

    Returns:
        Formatted string ready to insert into the system prompt.
    """
    if not chunks:
        return "[No documents have been ingested for this organisation yet.]"
    parts = [f"[Source {i}: {c['source']}]\n{c['text']}" for i, c in enumerate(chunks, 1)]
    return "\n\n---\n\n".join(parts)


# ── LLM call with retry ────────────────────────────────────────────────────────

def call_claude(
    client: anthropic.Anthropic,
    system: str,
    question: str,
) -> str:
    """Call Claude with automatic retry on rate-limit and timeout errors.

    Args:
        client: Authenticated Anthropic client.
        system: System prompt string.
        question: User question.

    Returns:
        Claude's response text.

    Raises:
        RuntimeError: If all 3 attempts fail.
    """
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=system,
                messages=[{"role": "user", "content": question}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            wait = 2 ** attempt
            print(f"  Rate limit hit — waiting {wait}s (attempt {attempt + 1}/3)...")
            time.sleep(wait)
        except anthropic.APITimeoutError:
            print(f"  Timeout — waiting 5s (attempt {attempt + 1}/3)...")
            time.sleep(5)
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}") from e
    raise RuntimeError("Claude API unavailable after 3 attempts.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point for ingestion and querying."""
    parser = argparse.ArgumentParser(
        description="GovPersona core RAG agent — ingest documents and query them."
    )
    parser.add_argument("--org", required=True, help="Organisation ID (e.g. finance_ministry)")
    parser.add_argument("--file", help="Path to PDF or TXT file to ingest")
    parser.add_argument("--question", "-q", help="Question to ask the agent")
    parser.add_argument("--ingest-only", action="store_true", help="Ingest without querying")
    args = parser.parse_args()

    # Ingest
    if args.file:
        print(f"\n  Ingesting {args.file} into '{args.org}'...")
        added, total = ingest_file(args.file, args.org)
        print(f"  Added {added}/{total} chunks (duplicates skipped)")

    if args.ingest_only:
        return

    # Query
    if not args.question:
        parser.error("Provide --question (or --ingest-only to skip querying)")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set in .env")

    print(f"\n  Retrieving context for: {args.question}")
    chunks = retrieve(args.org, args.question)
    print(f"  Found {len(chunks)} relevant chunks")

    context = build_context(chunks)
    org_mandate = f"Official spokesperson for {args.org}"  # Replace with real mandate
    system = SYSTEM_TEMPLATE.format(
        org_name=args.org,
        org_mandate=org_mandate,
        context=context,
    )

    client = anthropic.Anthropic(api_key=api_key)
    print("\n  Calling Claude...\n")
    answer = call_claude(client, system, args.question)
    print(answer)


if __name__ == "__main__":
    main()
