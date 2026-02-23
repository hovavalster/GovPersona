"""
Singleton for multilingual HuggingFace embeddings.
Model: paraphrase-multilingual-MiniLM-L12-v2
Excellent Hebrew support, ~120 MB, downloaded once and cached.
"""
from __future__ import annotations
from langchain_huggingface import HuggingFaceEmbeddings
from chromadb.utils.embedding_functions import ChromaLangchainEmbeddingFunction

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


def get_chroma_embedding_function() -> ChromaLangchainEmbeddingFunction:
    """Return a ChromaDB-compatible embedding function wrapping the LangChain embeddings."""
    lc_embeddings = get_embeddings()
    return ChromaLangchainEmbeddingFunction(embedding_function=lc_embeddings)
