"""
Document loading and chunking — Hebrew/RTL aware.
Supports PDF (PyMuPDF primary, pypdf fallback), TXT, JSON.
"""
from __future__ import annotations
import json
import os
import warnings
from typing import List, Tuple, Dict, Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.vector_store import VectorStoreManager

# Hebrew-aware separators (standard + Hebrew punctuation)
_HEBREW_SEPARATORS = ["\n\n", "\n", ".", "!", "?", "׃", "׀", " ", ""]

_splitter = RecursiveCharacterTextSplitter(
    separators=_HEBREW_SEPARATORS,
    chunk_size=800,
    chunk_overlap=150,
    strip_whitespace=True,
)


def extract_text(file_path: str) -> Tuple[str, str]:
    """
    Extract raw text from file_path.
    Returns (text, warning_message). warning_message is empty string on success.
    Supports: .pdf, .txt, .json
    """
    ext = os.path.splitext(file_path)[1].lower()
    warning = ""

    if ext == ".pdf":
        text = _extract_pdf(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    elif ext == ".json":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    if len(text.strip()) < 50:
        warning = (
            "⚠️ Very little text extracted — this may be a scanned image PDF with no "
            "text layer. Consider running OCR on the file before uploading."
        )

    return text, warning


def _extract_pdf(file_path: str) -> str:
    """Try PyMuPDF first (better RTL/Hebrew), fall back to pypdf."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text("text", sort=True))
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        warnings.warn(f"PyMuPDF failed ({e}), falling back to pypdf")

    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(pages)
    except Exception as e:
        raise RuntimeError(f"Both PDF parsers failed: {e}") from e


def chunk_text(
    text: str,
    source: str,
    org_id: str,
    doc_type: str = "document",
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Split text into chunks and generate metadata for each.
    Returns (chunks, metadatas).
    """
    raw_chunks = _splitter.split_text(text)

    chunks, metadatas = [], []
    for i, chunk in enumerate(raw_chunks):
        if len(chunk.strip()) < 30:
            continue
        chunks.append(chunk)
        metadatas.append(
            {
                "source": os.path.basename(source),
                "org_id": org_id,
                "doc_type": doc_type,
                "chunk_index": i,
            }
        )

    return chunks, metadatas


def ingest_file(
    file_path: str,
    org_id: str,
    vsm: VectorStoreManager,
    doc_type: str = "document",
) -> Tuple[int, int, str]:
    """
    Full pipeline: extract → chunk → add to vector store.
    Returns (added, total_chunks, warning_message).
    """
    text, warning = extract_text(file_path)
    chunks, metadatas = chunk_text(text, source=file_path, org_id=org_id, doc_type=doc_type)
    added, total = vsm.add_chunks(org_id, chunks, metadatas)
    return added, total, warning
