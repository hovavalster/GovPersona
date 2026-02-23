"""
ChromaDB vector store manager — one collection per org (isolated).
"""
from __future__ import annotations
import hashlib
import os
from typing import List, Dict, Any

import chromadb
from chromadb import Settings

from core.embeddings import get_chroma_embedding_function

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_db")


class VectorStoreManager:
    def __init__(self):
        os.makedirs(_DB_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        self._ef = get_chroma_embedding_function()

    def _get_or_create_collection(self, org_id: str):
        return self.client.get_or_create_collection(
            name=org_id,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        org_id: str,
        chunks: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> tuple[int, int]:
        """
        Add text chunks to the org's collection.
        Uses MD5-based IDs to deduplicate — already-present chunks are skipped.
        Returns (added_count, total_submitted).
        """
        if not chunks:
            return 0, 0

        collection = self._get_or_create_collection(org_id)

        # Build MD5 IDs
        ids = [hashlib.md5(chunk.encode("utf-8")).hexdigest() for chunk in chunks]

        # Check which IDs already exist
        existing = collection.get(ids=ids, include=[])["ids"]
        existing_set = set(existing)

        new_ids, new_chunks, new_meta = [], [], []
        for i, (doc_id, chunk, meta) in enumerate(zip(ids, chunks, metadatas)):
            if doc_id not in existing_set:
                new_ids.append(doc_id)
                new_chunks.append(chunk)
                new_meta.append(meta)

        if new_ids:
            collection.add(ids=new_ids, documents=new_chunks, metadatas=new_meta)

        return len(new_ids), len(chunks)

    def search(
        self,
        org_id: str,
        query: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search within a single org's collection.
        Returns list of dicts with 'text', 'metadata', 'distance'.
        """
        collection = self._get_or_create_collection(org_id)
        count = collection.count()
        if count == 0:
            return []

        n = min(n_results, count)
        results = collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]
        for doc, meta, dist in zip(docs, metas, dists):
            output.append({"text": doc, "metadata": meta, "distance": dist})
        return output

    def get_doc_count(self, org_id: str) -> int:
        """Return number of chunks stored for the given org."""
        collection = self._get_or_create_collection(org_id)
        return collection.count()

    def clear_collection(self, org_id: str):
        """Delete and recreate the org's collection (wipes all data)."""
        try:
            self.client.delete_collection(org_id)
        except Exception:
            pass
        self._get_or_create_collection(org_id)


_vsm_instance: VectorStoreManager | None = None


def get_vsm() -> VectorStoreManager:
    """Module-level singleton."""
    global _vsm_instance
    if _vsm_instance is None:
        _vsm_instance = VectorStoreManager()
    return _vsm_instance
