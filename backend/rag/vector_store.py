import json
import logging
import hashlib
import os
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from config.settings import settings
from services.account_lifecycle import account_mutation

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_INDEX_DIR = BACKEND_DIR / "storage" / "index"
DOCUMENT_EMBEDDING_PREFIX = "search_document:"
QUERY_EMBEDDING_PREFIX = "search_query:"

ACRONYM_MAP = {
    "rag": "retrieval augmented generation",
    "qa": "question answering",
    "nlp": "natural language processing",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "nn": "neural network",
    "cnn": "convolutional neural network",
    "rnn": "recurrent neural network",
    "lstm": "long short term memory",
    "gpt": "generative pre trained transformer",
    "bert": "bidirectional encoder representations from transformers",
    "tf": "tensorflow",
    "svm": "support vector machine",
    "pca": "principal component analysis",
    "ir": "information retrieval",
    "ner": "named entity recognition",
    "pos": "part of speech",
    "tfidf": "term frequency inverse document frequency",
    "llm": "large language model",
    "sota": "state of the art",
    "db": "database",
    "ui": "user interface",
    "api": "application programming interface",
    "sse": "server sent events",
}


def dense_retrieval_enabled() -> bool:
    """Return whether the explicitly opt-in hybrid retrieval path is usable."""
    return settings.RETRIEVAL_MODE == "hybrid" and bool(settings.EMBEDDING_BASE_URL)


def embedding_identity() -> dict[str, str]:
    """Configured embedding space, without exposing URLs/credentials in artifacts.

    This identifies requested model/endpoint/prefixes, not provider weight bytes.
    A provider silently changing weights under the same ID still requires an
    operator-managed model revision and explicit reindex.
    """
    return {"model": settings.EMBEDDING_MODEL,
            "endpoint_sha256": hashlib.sha256(settings.EMBEDDING_BASE_URL.rstrip("/").encode()).hexdigest(),
            "document_prefix": DOCUMENT_EMBEDDING_PREFIX, "query_prefix": QUERY_EMBEDDING_PREFIX}


def document_scope_indices(documents, scope: str) -> set[int]:
    """Prefer a storage ID to display-name fallback, including legacy filenames."""
    normalized = (scope or "").strip().casefold()
    if not normalized:
        return set(range(len(documents)))
    stored = {index for index, document in enumerate(documents)
              if str(document.get("metadata", {}).get("storage_name")
                     or document.get("metadata", {}).get("file_name", "")).strip().casefold() == normalized}
    return stored or {index for index, document in enumerate(documents)
                      if str(document.get("metadata", {}).get("file_name", "")).strip().casefold() == normalized}


def expand_query(query: str) -> str:
    words = re.findall(r"[a-zA-Z]\w*", query.lower())
    expanded = set(words)
    for w in words:
        wl = w.lower()
        if wl in ACRONYM_MAP:
            expanded.update(ACRONYM_MAP[wl].split())
    if len(expanded) > len(words):
        return query + " " + " ".join(sorted(expanded - set(words)))
    return query


def _index_dir(user_id: str) -> Path:
    d = BASE_INDEX_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _remote_enabled() -> bool:
    return bool(settings.REDIS_URL or (settings.B2_KEY_ID and settings.B2_APP_KEY))


def _pointer_file(user_id: str) -> Path:
    return _index_dir(user_id) / "current.json"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_manifest(user_id: str) -> dict | None:
    if _remote_enabled():
        from services.remote_storage import download_bytes
        data = download_bytes(f"index/{user_id}/current.json", required=True)
    else:
        path = _pointer_file(user_id)
        data = path.read_bytes() if path.exists() else None
    if data is None:
        return None
    manifest = json.loads(data)
    if not re.fullmatch(r"[0-9a-f]{32}", manifest.get("revision", "")):
        raise ValueError("Invalid index revision")
    files = manifest.get("files", {})
    if "metadata.jsonl" not in files or set(files) - {"metadata.jsonl", "embeddings.npy", "faiss.index"}:
        raise ValueError("Invalid index snapshot")
    if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in files.values()):
        raise ValueError("Invalid snapshot checksum")
    return manifest


def index_revision(user_id: str) -> str:
    manifest = _read_manifest(user_id)
    if manifest:
        return manifest["revision"]
    # Legacy indexes remain readable until an explicit reindex migrates them.
    if _remote_enabled():
        return "legacy-remote"
    legacy = _index_dir(user_id) / "metadata.jsonl"
    return f"legacy-{legacy.stat().st_mtime_ns}" if legacy.exists() else "missing"


def _snapshot_dir(user_id: str) -> Path:
    pointer = _pointer_file(user_id)
    if pointer.exists():
        revision = json.loads(pointer.read_bytes())["revision"]
        if not re.fullmatch(r"[0-9a-f]{32}", revision):
            raise ValueError("Invalid local index revision")
        return _index_dir(user_id) / "revisions" / revision
    return _index_dir(user_id)


def _metadata_file(user_id: str) -> Path:
    return _snapshot_dir(user_id) / "metadata.jsonl"


def _embeddings_file(user_id: str) -> Path:
    return _snapshot_dir(user_id) / "embeddings.npy"


def _faiss_file(user_id: str) -> Path:
    return _snapshot_dir(user_id) / "faiss.index"


def _bm25_file(user_id: str) -> Path:
    return _snapshot_dir(user_id) / "bm25.pkl"


def _hydrate_snapshot(user_id: str, manifest: dict) -> Path:
    directory = _index_dir(user_id) / "revisions" / manifest["revision"]
    directory.mkdir(parents=True, exist_ok=True)
    for name, digest in manifest["files"].items():
        path = directory / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        if not _remote_enabled():
            raise RuntimeError("Local index snapshot is incomplete")
        from services.remote_storage import download_bytes
        data = download_bytes(f"index/{user_id}/revisions/{manifest['revision']}/{name}", required=True)
        if data is None or hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError("Index snapshot is incomplete or corrupt")
        _atomic_write(path, data)
    return directory


class HybridVectorStore:
    def __init__(
        self,
        user_id: str = "",
        documents: list[Dict[str, Any]] | None = None,
        bm25=None,
        embeddings: np.ndarray | None = None,
        faiss_index=None,
    ):
        self.user_id = user_id
        self.revision = ""
        self.documents = documents or []
        self.bm25 = bm25
        self.embeddings = embeddings
        self.faiss_index = faiss_index
        self.embedding_profile = embedding_identity() if embeddings is not None else None

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _build_bm25(self) -> None:
        from rank_bm25 import BM25Okapi
        tokenized = [self._tokenize(d.get("content", "")) for d in self.documents]
        # A valid text upload can contain only punctuation. rank_bm25 divides
        # by the average length for an all-empty token corpus.
        self.bm25 = BM25Okapi(tokenized) if any(tokenized) else None

    def _build_faiss(self) -> None:
        import faiss
        if self.embeddings is None or len(self.embeddings) == 0:
            self.faiss_index = None
            return
        dim = self.embeddings.shape[1]
        normalized = self.embeddings.copy()
        faiss.normalize_L2(normalized)
        self.faiss_index = faiss.IndexFlatIP(dim)
        self.faiss_index.add(normalized)

    def _get_query_embedding(self, query: str) -> np.ndarray | None:
        from rag.embeddings import get_embedding
        emb = get_embedding(query, prefix=QUERY_EMBEDDING_PREFIX)
        if emb is None:
            return None
        try:
            vector = np.asarray([emb], dtype=np.float32)
        except (TypeError, ValueError):
            return None
        if vector.ndim != 2 or not vector.shape[1] or not np.isfinite(vector).all():
            return None
        return vector

    def add_nodes(self, nodes: list[Dict[str, Any]]) -> int:
        if not nodes:
            return 0
        texts = [n.get("content", "") for n in nodes]
        if dense_retrieval_enabled():
            from rag.embeddings import get_embeddings_batch
            rebuild_dense = bool(self.documents) and (
                self.embeddings is None or self.embeddings.ndim != 2
                or len(self.embeddings) != len(self.documents)
                or self.embedding_profile != embedding_identity()
            )
            embedding_texts = ([document.get("content", "") for document in self.documents] + texts
                               if rebuild_dense else texts)
            new_embeddings = get_embeddings_batch(embedding_texts, prefix=DOCUMENT_EMBEDDING_PREFIX)
            valid_batch = (isinstance(new_embeddings, np.ndarray) and new_embeddings.ndim == 2
                           and len(new_embeddings) == len(embedding_texts)
                           and new_embeddings.shape[1] > 0 and np.isfinite(new_embeddings).all())
            if valid_batch:
                if rebuild_dense or self.embeddings is None or len(self.embeddings) == 0:
                    self.embeddings = new_embeddings
                elif self.embeddings.shape[1] == new_embeddings.shape[1]:
                    self.embeddings = np.vstack([self.embeddings, new_embeddings])
                else:
                    self.embeddings = None
                    self.faiss_index = None
            else:
                # Never keep a partial dense index whose rows no longer align
                # with the document list. BM25 remains fully functional.
                self.embeddings = None
                self.faiss_index = None
        else:
            # BM25 production mode does not pay embedding/indexing cost. Drop
            # any previously loaded dense state before appending documents so
            # persisted rows cannot become misaligned.
            self.embeddings = None
            self.faiss_index = None
        self.embedding_profile = embedding_identity() if self.embeddings is not None else None
        self.documents.extend(nodes)
        self._build_bm25()
        if self.embeddings is not None and len(self.embeddings) > 0:
            self._build_faiss()
        return len(nodes)

    def remove_by_file_name(self, file_name: str) -> int:
        if not file_name or not self.documents:
            return 0
        before = len(self.documents)
        mask = [
            d.get("metadata", {}).get("storage_name", d.get("metadata", {}).get("file_name")) != file_name
            for d in self.documents
        ]
        self.documents = [d for d, m in zip(self.documents, mask) if m]
        removed = before - len(self.documents)
        if removed and self.embeddings is not None and len(self.embeddings) > 0:
            if len(self.embeddings) == len(mask):
                self.embeddings = self.embeddings[mask]
            else:
                self.embeddings = None
                self.faiss_index = None
        if self.documents:
            self._build_bm25()
            if self.embeddings is not None and len(self.embeddings) > 0:
                self._build_faiss()
            else:
                self.faiss_index = None
        else:
            self.bm25 = None
            self.embeddings = None
            self.faiss_index = None
        return removed

    def persist(self) -> None:
        # Callers serialize mutations per user. Reject an accidentally reused
        # stale store as an additional guard against lost updates.
        if self.revision and self.revision != index_revision(self.user_id):
            raise RuntimeError("Index changed; reload before applying this mutation")
        if self.embeddings is not None and self.embedding_profile != embedding_identity():
            self.embeddings = None
            self.faiss_index = None
            self.embedding_profile = None
        from services.document_lifecycle import deleted_documents
        for name in deleted_documents(self.user_id):
            self.remove_by_file_name(name)
        revision = uuid.uuid4().hex
        directory = _index_dir(self.user_id) / "revisions" / revision
        directory.mkdir(parents=True)
        metadata = directory / "metadata.jsonl"
        metadata.write_text("".join(json.dumps(node, ensure_ascii=False) + "\n" for node in self.documents), encoding="utf-8")
        files = {"metadata.jsonl": metadata}
        if self.embeddings is not None and len(self.embeddings):
            np.save(directory / "embeddings.npy", self.embeddings)
            files["embeddings.npy"] = directory / "embeddings.npy"
        if self.faiss_index is not None:
            import faiss
            faiss.write_index(self.faiss_index, str(directory / "faiss.index"))
            files["faiss.index"] = directory / "faiss.index"
        manifest = {"revision": revision, "files": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()
        }, "ingestion_version": 2,
            "embedding_profile": self.embedding_profile if self.embeddings is not None else None}
        encoded = json.dumps(manifest).encode()
        if _remote_enabled():
            from services.remote_storage import upload_file, upload_bytes
            for name, path in files.items():
                if not upload_file(f"index/{self.user_id}/revisions/{revision}/{name}", path):
                    raise RuntimeError("Could not persist the complete index snapshot")
            # Publish only after every immutable artifact is durable. Readers
            # resolve one manifest and never combine artifacts from revisions.
            if not upload_bytes(f"index/{self.user_id}/current.json", encoded):
                raise RuntimeError("Could not publish the index revision")
        _atomic_write(_pointer_file(self.user_id), encoded)
        self.revision = revision

    @classmethod
    def load(cls, user_id: str):
        return load_vector_store(user_id)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        file_name: str | None = None,
    ) -> list[Dict[str, Any]]:
        n = len(self.documents)
        if n == 0 or top_k <= 0:
            return []
        normalized_file_name = (file_name or "").strip().casefold()
        eligible_indices = document_scope_indices(self.documents, normalized_file_name)
        if not eligible_indices:
            return []
        expanded = expand_query(query)
        tokenized_query = self._tokenize(expanded)

        bm25_scores = np.zeros(n, dtype=np.float64)
        if self.bm25 is not None:
            bm25_scores = np.array(self.bm25.get_scores(tokenized_query), dtype=np.float64)

        dense_scores = np.zeros(n, dtype=np.float32)
        if (dense_retrieval_enabled() and self.faiss_index is not None and self.faiss_index.ntotal > 0
                and self.embedding_profile == embedding_identity()):
            query_emb = self._get_query_embedding(expanded)
            if query_emb is not None and query_emb.shape[1] == self.faiss_index.d:
                import faiss
                faiss.normalize_L2(query_emb)
                # A global candidate cap can discard every passage from the
                # selected document before the scope filter is applied.
                search_k = n if normalized_file_name else min(top_k * 4, n)
                faiss_scores, faiss_indices = self.faiss_index.search(query_emb, search_k)
                for idx, score in zip(faiss_indices[0], faiss_scores[0]):
                    if idx in eligible_indices:
                        dense_scores[idx] = float(score)

        rrf_k = settings.RRF_K
        rrf_scores: dict[int, float] = {}
        bm25_order = [idx for idx in np.argsort(-bm25_scores) if idx in eligible_indices]
        for rank, idx in enumerate(bm25_order):
            if bm25_scores[idx] > 0:
                rrf_scores[idx] = 1.0 / (rrf_k + rank + 1)
        dense_order = [idx for idx in np.argsort(-dense_scores) if idx in eligible_indices]
        for rank, idx in enumerate(dense_order):
            if dense_scores[idx] > 0:
                rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)

        # rank_bm25 can produce a non-positive IDF when the corpus contains a
        # single document. Preserve useful retrieval for a user's first upload
        # with a deterministic token-overlap fallback.
        if not rrf_scores and tokenized_query:
            query_token_set = set(tokenized_query)
            overlap_scores = [
                len(query_token_set.intersection(self._tokenize(document.get("content", ""))))
                for document in self.documents
            ]
            overlap_order = [idx for idx in np.argsort(-np.asarray(overlap_scores)) if idx in eligible_indices]
            for rank, idx in enumerate(overlap_order):
                if overlap_scores[idx] > 0:
                    rrf_scores[int(idx)] = 1.0 / (rrf_k + rank + 1)

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        max_rrf = ranked[0][1] if ranked else 0.0
        candidates = [
            (idx, rrf_score)
            for idx, rrf_score in ranked
            if idx in eligible_indices
            if min_score <= 0 or (max_rrf > 0 and rrf_score / max_rrf >= min_score)
        ]

        # Return at most K passages, diversifying PDF evidence by page. This
        # same ranking policy runs in the application and in its evaluation.
        top_indices = []
        seen_pages = set()
        for idx, _ in candidates:
            metadata = self.documents[idx].get("metadata", {})
            page = metadata.get("page")
            page_key = (metadata.get("storage_name", metadata.get("file_name", "")), page) if page else (idx,)
            if page_key in seen_pages:
                continue
            seen_pages.add(page_key)
            top_indices.append(idx)
            if len(top_indices) >= top_k:
                break

        results = []
        for idx in top_indices:
            if 0 <= idx < len(self.documents):
                node = dict(self.documents[idx])
                raw = rrf_scores.get(idx, 0.0)
                node["_score"] = raw / max_rrf if max_rrf > 0 else 0.0
                results.append(node)
        return results

    def as_retriever(self, similarity_top_k: int = 5):
        return self


def build_vector_store(nodes: list[Dict[str, Any]], user_id: str = "") -> HybridVectorStore:
    store = HybridVectorStore(user_id=user_id)
    store.add_nodes(nodes)
    store.persist()
    return store


@account_mutation
def load_vector_store(user_id: str = "") -> HybridVectorStore:
    manifest = _read_manifest(user_id)
    if manifest:
        directory = _hydrate_snapshot(user_id, manifest)
        revision = manifest["revision"]
    else:
        directory = _index_dir(user_id)
        revision = index_revision(user_id)
        if _remote_enabled():
            # Legacy compatibility. A new reindex publishes a revisioned snapshot.
            from services.remote_storage import download_bytes
            data = download_bytes(f"index/{user_id}/metadata.jsonl", required=True)
            if data is None:
                raise FileNotFoundError(f"Vector store not found for user {user_id}")
            _atomic_write(directory / "metadata.jsonl", data)
            if dense_retrieval_enabled():
                for name in ("embeddings.npy", "faiss.index"):
                    data = download_bytes(f"index/{user_id}/{name}", required=True)
                    if data is not None:
                        _atomic_write(directory / name, data)
                    else:
                        (directory / name).unlink(missing_ok=True)
    metadata = directory / "metadata.jsonl"
    if not metadata.exists():
        raise FileNotFoundError(f"Vector store not found for user {user_id}")
    documents = [json.loads(line) for line in metadata.read_text(encoding="utf-8").splitlines() if line.strip()]
    embeddings = None
    if (dense_retrieval_enabled() and (directory / "embeddings.npy").exists()
            and manifest and manifest.get("embedding_profile") == embedding_identity()):
        embeddings = np.load(directory / "embeddings.npy", allow_pickle=False)
        if embeddings.ndim != 2 or len(embeddings) != len(documents) or not embeddings.shape[1] or not np.isfinite(embeddings).all():
            embeddings = None
    elif dense_retrieval_enabled() and (directory / "embeddings.npy").exists():
        logger.warning("Dense index identity is missing or differs from current configuration; using BM25 until reindex")
    store = HybridVectorStore(user_id=user_id, documents=documents, embeddings=embeddings)
    # Rebuild the inexpensive BM25 index rather than deserializing pickle.
    store._build_bm25()
    if embeddings is not None and len(embeddings):
        store._build_faiss()
    store.revision = revision
    from services.document_lifecycle import deleted_documents
    deleted = deleted_documents(user_id)
    for name in deleted:
        store.remove_by_file_name(name)
    store.deletion_revision = tuple(sorted(deleted))
    if manifest:
        _atomic_write(_pointer_file(user_id), json.dumps(manifest).encode())
    return store


def delete_vector_store(user_id: str = "") -> None:
    # An empty revision is a tombstone visible to other hosts; removing the
    # pointer would allow a cached/legacy index to reappear.
    store = HybridVectorStore(user_id=user_id)
    store.persist()
