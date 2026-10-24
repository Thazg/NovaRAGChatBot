import re

from rag.vector_store import load_vector_store, index_revision
from config.settings import settings
from rag.cache import SimpleCache

retrieval_cache = SimpleCache(max_entries=256)
_vector_store_instances: dict[str, object] = {}


def _ensure_user_id(user_id: str) -> str:
    return user_id or "__anonymous__"


def get_retriever(user_id: str = ""):
    uid = _ensure_user_id(user_id)
    current_revision = index_revision(uid)
    from services.document_lifecycle import deleted_documents
    deletion_revision = tuple(sorted(deleted_documents(uid)))
    cached = _vector_store_instances.get(uid)
    if cached is not None and (getattr(cached, "revision", None) != current_revision
                              or getattr(cached, "deletion_revision", ()) != deletion_revision):
        _vector_store_instances.pop(uid, None)
    if uid not in _vector_store_instances:
        try:
            _vector_store_instances[uid] = load_vector_store(uid)
        except FileNotFoundError:
            return None
    return _vector_store_instances.get(uid)


def reload_vector_store(user_id: str = "") -> None:
    uid = _ensure_user_id(user_id)
    try:
        _vector_store_instances[uid] = load_vector_store(uid)
    except FileNotFoundError:
        _vector_store_instances.pop(uid, None)
    retrieval_cache.clear()


def unload_vector_store(user_id: str = "") -> None:
    uid = _ensure_user_id(user_id)
    _vector_store_instances.pop(uid, None)
    retrieval_cache.clear()


def _is_document_overview_query(query: str) -> bool:
    normalized = re.sub(r"\s+", " ", (query or "").strip().lower())
    overview_phrases = (
        "summarize", "summary", "main points", "key points", "overview",
        "document about", "file about", "this document", "this file",
        "tóm tắt", "tổng quan", "ý chính", "điểm chính", "nội dung chính",
        "tài liệu này", "file này",
    )
    return any(phrase in normalized for phrase in overview_phrases)


def _representative_nodes(documents: list[dict], top_k: int) -> list[dict]:
    if not documents:
        return []
    count = min(max(1, top_k), len(documents))
    if count == 1:
        indices = [0]
    else:
        indices = [round(position * (len(documents) - 1) / (count - 1)) for position in range(count)]
    nodes = []
    for index in dict.fromkeys(indices):
        node = dict(documents[index])
        node["_score"] = 1.0
        nodes.append(node)
    return nodes


def retrieve_from_store(
    query: str, retriever, top_k: int | None = None,
    allow_broad: bool = True, document_name: str = "",
):
    """The production query path, also used by offline regression evaluation."""
    count = max(1, min(top_k or settings.TOP_K, 15))
    scope = document_name.strip()
    nodes = retriever.retrieve(query.strip(), top_k=count, file_name=scope or None)
    if not nodes and allow_broad and _is_document_overview_query(query):
        documents = [document for document in retriever.documents if not scope or scope.casefold() in {
            str(document.get("metadata", {}).get("file_name", "")).casefold(),
            str(document.get("metadata", {}).get("storage_name", "")).casefold(),
        }]
        nodes = _representative_nodes(documents, count)
    return nodes


def retrieve_context(
    query: str, user_id: str = "", top_k: int | None = None,
    allow_broad: bool = True, document_name: str = "",
):
    uid = _ensure_user_id(user_id)
    # Resolve the current revision before looking up a query result: an old
    # retrieval-cache hit must not bypass cross-process invalidation.
    retriever = get_retriever(uid)
    if retriever is None:
        return []
    cache_key = repr((uid, getattr(retriever, "revision", ""), getattr(retriever, "deletion_revision", ()), document_name.strip().casefold(),
                      query.strip(), top_k or settings.TOP_K, allow_broad))
    cached = retrieval_cache.get(cache_key)
    if cached is not None:
        return cached
    nodes = retrieve_from_store(query, retriever, top_k, allow_broad, document_name)
    retrieval_cache.set(cache_key, nodes)
    return nodes


def rewrite_question(question, history):
    question = (question or "").strip()
    if not question:
        return ""
    if not history or len(history) < 2:
        return question
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    question_lower = question.lower()
    trigger_words = [
        "it", "this", "that", "those", "they", "them", "he", "she", "the",
        "nó", "cái này", "cái đó", "những cái này", "những cái đó", "chúng", "chúng nó",
        "cụ thể", "chi tiết", "cụ thể hơn", "rõ hơn", "kể tiếp", "tiếp theo", "nói rõ",
    ]
    if any(
        (word in question_lower if " " in word else re.search(rf"\b{re.escape(word)}\b", question_lower))
        for word in trigger_words
    ):
        return f"{question} (Context: {history_text})"
    if len(question.split()) <= 3:
        return f"{question} (Context: {history_text})"
    return question
