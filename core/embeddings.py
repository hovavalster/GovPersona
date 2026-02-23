"""
Singleton for multilingual HuggingFace embeddings.
Model: paraphrase-multilingual-MiniLM-L12-v2
Excellent Hebrew support, ~120 MB, downloaded once and cached.
"""
from __future__ import annotations
from langchain_huggingface import HuggingFaceEmbeddings
from chromadb import EmbeddingFunction, Documents, Embeddings

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_embeddings_instance: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Return the singleton HuggingFaceEmbeddings instance (cached after first call)."""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name=_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings_instance


class _HFEmbeddingFunction(EmbeddingFunction):
    """Simple ChromaDB EmbeddingFunction that calls HuggingFace embed_documents directly.
    Avoids the ChromaLangchainEmbeddingFunction adapter which breaks on LangChain 1.x."""

    def __call__(self, input: Documents) -> Embeddings:
        return get_embeddings().embed_documents(list(input))


_ef_instance: _HFEmbeddingFunction | None = None


def get_chroma_embedding_function() -> _HFEmbeddingFunction:
    """Return a ChromaDB-compatible embedding function."""
    global _ef_instance
    if _ef_instance is None:
        _ef_instance = _HFEmbeddingFunction()
    return _ef_instance
