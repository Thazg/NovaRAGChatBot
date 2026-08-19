import json
import logging
import pickle
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from config.settings import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_INDEX_DIR = BACKEND_DIR / "storage" / "index"

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


def expand_query(query: str) -> str:
    words = re.findall(r"[a-zA-Z]\w*", query)
    expanded = set(words)
    for w in words:
        wl = w.lower()
        if wl in ACRONYM_MAP:
            expanded.update(ACRONYM_MAP[wl].split())
    if len(expanded) > len(words):
        return query + " " + " ".join(sorted(expanded - set(w.lower() for w in words)))
    return query


def _index_dir(user_id: str) -> Path:
    d = BASE_INDEX_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _metadata_file(user_id: str) -> Path:
    return _index_dir(user_id) / "metadata.jsonl"


def _embeddings_file(user_id: str) -> Path:
    return _index_dir(user_id) / "embeddings.npy"


def _faiss_file(user_id: str) -> Path:
    return _index_dir(user_id) / "faiss.index"


def _bm25_file(user_id: str) -> Path:
    return _index_dir(user_id) / "bm25.pkl"


def _b2_metadata_path(user_id: str) -> str:
    return f"index/{user_id}/metadata.jsonl"


def _b2_embeddings_path(user_id: str) -> str:
    return f"index/{user_id}/embeddings.npy"


def _b2_faiss_path(user_id: str) -> str:
    return f"index/{user_id}/faiss.index"


def _b2_bm25_path(user_id: str) -> str:
    return f"index/{user_id}/bm25.pkl"


def _b2_backup_paths(user_id: str) -> list[str]:
    return [
        _b2_metadata_path(user_id),
        _b2_embeddings_path(user_id),
        _b2_faiss_path(user_id),
        _b2_bm25_path(user_id),
    ]


def _upload_to_b2(user_id: str, local_files: dict[str, Path]) -> None:
    try:
        from services.remote_storage import upload_file
        for remote_key, local_path in local_files.items():
            upload_file(remote_key, local_path)
    except Exception:
        pass


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
        self.documents = documents or []
        self.bm25 = bm25
        self.embeddings = embeddings
        self.faiss_index = faiss_index

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _build_bm25(self) -> None:
        from rank_bm25 import BM25Okapi
        tokenized = [self._tokenize(d.get("content", "")) for d in self.documents]
        self.bm25 = BM25Okapi(tokenized) if tokenized else None

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
        emb = get_embedding(query, prefix="search_query:")
        if emb is None:
            return None
        return np.array([emb], dtype=np.float32)

    def add_nodes(self, nodes: list[Dict[str, Any]]) -> int:
        if not nodes:
            return 0
        texts = [n.get("content", "") for n in nodes]
        if dense_retrieval_enabled():
            from rag.embeddings import get_embeddings_batch
            new_embeddings = get_embeddings_batch(texts, prefix="search_document:")
            if new_embeddings is not None and len(new_embeddings) == len(nodes):
                if self.embeddings is None or len(self.embeddings) == 0:
                    self.embeddings = new_embeddings
                else:
                    self.embeddings = np.vstack([self.embeddings, new_embeddings])
            elif self.embeddings is not None:
                # Never keep a partial dense index whose rows no longer align
                # with the document list. BM25 remains fully functional.
                self.embeddings = None
                self.faiss_index = None
            else:
                self.faiss_index = None
        else:
            # BM25 production mode does not pay embedding/indexing cost. Drop
            # any previously loaded dense state before appending documents so
            # persisted rows cannot become misaligned.
            self.embeddings = None
            self.faiss_index = None
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
        with _metadata_file(self.user_id).open("w", encoding="utf-8") as f:
            for node in self.documents:
                json.dump(node, f, ensure_ascii=False)
                f.write("\n")
        if self.embeddings is not None and len(self.embeddings) > 0:
            np.save(_embeddings_file(self.user_id), self.embeddings)
        else:
            _embeddings_file(self.user_id).unlink(missing_ok=True)
        if self.faiss_index is not None:
            import faiss
            faiss.write_index(self.faiss_index, str(_faiss_file(self.user_id)))
        else:
            _faiss_file(self.user_id).unlink(missing_ok=True)
        if self.bm25 is not None:
            with _bm25_file(self.user_id).open("wb") as f:
                pickle.dump(self.bm25, f)
        else:
            _bm25_file(self.user_id).unlink(missing_ok=True)
        b2_files = {}
        if _metadata_file(self.user_id).exists():
            b2_files[_b2_metadata_path(self.user_id)] = _metadata_file(self.user_id)
        if _embeddings_file(self.user_id).exists():
            b2_files[_b2_embeddings_path(self.user_id)] = _embeddings_file(self.user_id)
        if _faiss_file(self.user_id).exists():
            b2_files[_b2_faiss_path(self.user_id)] = _faiss_file(self.user_id)
        if _bm25_file(self.user_id).exists():
            b2_files[_b2_bm25_path(self.user_id)] = _bm25_file(self.user_id)
        if b2_files:
            _upload_to_b2(self.user_id, b2_files)

    @classmethod
    def load(cls, user_id: str):
        mf = _metadata_file(user_id)
        ef = _embeddings_file(user_id)
        ff = _faiss_file(user_id)
        bf = _bm25_file(user_id)
        if not mf.exists():
            raise FileNotFoundError(f"Vector store not found for user {user_id}.")
        documents: list[Dict[str, Any]] = []
        with mf.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    documents.append(json.loads(line))
        embeddings = None
        if dense_retrieval_enabled() and ef.exists():
            embeddings = np.load(ef)
            if len(embeddings) != len(documents):
                logger.warning("Ignoring misaligned embeddings for user %s", user_id)
                embeddings = None
        faiss_index = None
        if dense_retrieval_enabled() and ff.exists() and embeddings is not None:
            import faiss
            faiss_index = faiss.read_index(str(ff))
            if faiss_index.ntotal != len(documents):
                logger.warning("Ignoring misaligned FAISS index for user %s", user_id)
                faiss_index = None
        bm25 = None
        if bf.exists():
            with bf.open("rb") as f:
                bm25 = pickle.load(f)
        return cls(
            user_id=user_id,
            documents=documents,
            bm25=bm25,
            embeddings=embeddings,
            faiss_index=faiss_index,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        file_name: str | None = None,
    ) -> list[Dict[str, Any]]:
        n = len(self.documents)
        if n == 0:
            return []
        normalized_file_name = (file_name or "").strip().casefold()
        eligible_indices = {
            index
            for index, document in enumerate(self.documents)
            if not normalized_file_name
            or normalized_file_name in {
                str(document.get("metadata", {}).get("file_name", "")).strip().casefold(),
                str(document.get("metadata", {}).get("storage_name", "")).strip().casefold(),
            }
        }
        if not eligible_indices:
            return []
        expanded = expand_query(query)
        tokenized_query = self._tokenize(expanded)

        bm25_scores = np.zeros(n, dtype=np.float64)
        if self.bm25 is not None:
            bm25_scores = np.array(self.bm25.get_scores(tokenized_query), dtype=np.float64)

        dense_scores = np.zeros(n, dtype=np.float32)
        if dense_retrieval_enabled() and self.faiss_index is not None and self.faiss_index.ntotal > 0:
            query_emb = self._get_query_embedding(expanded)
            if query_emb is not None:
                import faiss
                faiss.normalize_L2(query_emb)
                search_k = min(top_k * 4, n)
                faiss_scores, faiss_indices = self.faiss_index.search(query_emb, search_k)
                for idx, score in zip(faiss_indices[0], faiss_scores[0]):
                    if idx != -1 and idx < n:
                        dense_scores[idx] = float(score)

        rrf_k = settings.RRF_K
        rrf_scores: dict[int, float] = {}
        bm25_order = np.argsort(-bm25_scores)
        for rank, idx in enumerate(bm25_order):
            if bm25_scores[idx] > 0:
                rrf_scores[idx] = 1.0 / (rrf_k + rank + 1)
        dense_order = np.argsort(-dense_scores)
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
            overlap_order = np.argsort(-np.asarray(overlap_scores))
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

        query_terms = {w.lower() for w in re.findall(r"[a-zA-Z]\w+", expanded) if len(w) > 3}
        candidate_count = min(top_k * 4, len(candidates))
        top_indices = [idx for idx, _ in candidates[:candidate_count]]
        top_indices = top_indices[:top_k]
        seen = set(top_indices)
        upload_candidates = [
            (idx, rrf_score)
            for idx, rrf_score in candidates
            if "uploads" in str(self.documents[idx].get("metadata", {}).get("file_path", "")).lower()
            or "upload" in str(self.documents[idx].get("metadata", {}).get("file_path", "")).lower()
        ]

        if query_terms and candidates:
            missing_terms = set(query_terms)
            for idx in top_indices:
                content = self.documents[idx].get("content", "").lower()
                missing_terms -= {t for t in missing_terms if t in content}
            for idx, _ in candidates[candidate_count:]:
                if not missing_terms:
                    break
                if idx in seen:
                    continue
                content = self.documents[idx].get("content", "").lower()
                found = {t for t in missing_terms if t in content}
                if found:
                    top_indices.append(idx)
                    seen.add(idx)
                    missing_terms -= found

        seen_upload_files = set()
        for idx in top_indices:
            fn = self.documents[idx].get("metadata", {}).get("file_name", "")
            if fn:
                seen_upload_files.add(fn)
        if upload_candidates and min_score > 0:
            upload_candidates.sort(key=lambda item: item[1], reverse=True)
            added = 0
            for idx, rrf_score in upload_candidates:
                if rrf_score < min_score:
                    continue
                if idx in seen:
                    continue
                fn = self.documents[idx].get("metadata", {}).get("file_name", "")
                if fn and fn not in seen_upload_files:
                    top_indices.append(idx)
                    seen.add(idx)
                    seen_upload_files.add(fn)
                    added += 1
                    if added >= 2:
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


def load_vector_store(user_id: str = "") -> HybridVectorStore:
    mf = _metadata_file(user_id)
    ef = _embeddings_file(user_id)
    ff = _faiss_file(user_id)
    bf = _bm25_file(user_id)
    if not mf.exists():
        try:
            from services.remote_storage import download_file
            download_file(_b2_metadata_path(user_id), mf)
            if dense_retrieval_enabled():
                download_file(_b2_embeddings_path(user_id), ef)
                download_file(_b2_faiss_path(user_id), ff)
            download_file(_b2_bm25_path(user_id), bf)
        except ImportError:
            pass
        if not mf.exists():
            raise FileNotFoundError(f"Vector store not found for user {user_id}.")
    return HybridVectorStore.load(user_id)


def delete_vector_store(user_id: str = "") -> None:
    """Remove local and remote index artifacts for a user."""
    index_dir = BASE_INDEX_DIR / user_id
    if index_dir.exists():
        shutil.rmtree(index_dir)
    try:
        from services.remote_storage import delete_file
        for remote_path in _b2_backup_paths(user_id):
            delete_file(remote_path)
    except Exception:
        pass
