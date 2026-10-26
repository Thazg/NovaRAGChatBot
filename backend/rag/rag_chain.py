import re

from rag.vector_store import load_vector_store, index_revision, embedding_identity, document_scope_indices
from config.settings import settings
from rag.cache import SimpleCache
from services.account_lifecycle import account_mutation

retrieval_cache = SimpleCache(max_entries=256)
_vector_store_instances: dict[str, object] = {}


def _ensure_user_id(user_id: str) -> str:
    return user_id or "__anonymous__"


def get_retriever(user_id: str = ""):
    return _get_retriever_locked(_ensure_user_id(user_id))


@account_mutation
def _get_retriever_locked(user_id: str):
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
    _reload_vector_store_locked(_ensure_user_id(user_id))


@account_mutation
def _reload_vector_store_locked(user_id: str) -> None:
    uid = _ensure_user_id(user_id)
    try:
        _vector_store_instances[uid] = load_vector_store(uid)
    except FileNotFoundError:
        _vector_store_instances.pop(uid, None)
    retrieval_cache.clear()


def unload_vector_store(user_id: str = "") -> None:
    uid = _ensure_user_id(user_id)
    from services.index_jobs import _user_index_lock
    # Cleanup must remain possible after the account deletion barrier exists.
    with _user_index_lock(uid):
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
        eligible = document_scope_indices(retriever.documents, scope)
        documents = [document for index, document in enumerate(retriever.documents) if index in eligible]
        nodes = _representative_nodes(documents, count)
    return nodes


def retrieve_context(
    query: str, user_id: str = "", top_k: int | None = None,
    allow_broad: bool = True, document_name: str = "",
):
    return _retrieve_context_locked(query, _ensure_user_id(user_id), top_k, allow_broad, document_name)


@account_mutation
def _retrieve_context_locked(
    query: str, user_id: str, top_k: int | None,
    allow_broad: bool, document_name: str,
):
    uid = _ensure_user_id(user_id)
    # Resolve the current revision before looking up a query result: an old
    # retrieval-cache hit must not bypass cross-process invalidation.
    retriever = get_retriever(uid)
    if retriever is None:
        return []
    cache_key = repr((uid, getattr(retriever, "revision", ""), getattr(retriever, "deletion_revision", ()),
                      settings.RETRIEVAL_MODE, embedding_identity(), document_name.strip().casefold(),
                      query.strip(), top_k or settings.TOP_K, allow_broad))
    cached = retrieval_cache.get(cache_key)
    if cached is not None:
        return cached
    nodes = retrieve_from_store(query, retriever, top_k, allow_broad, document_name)
    retrieval_cache.set(cache_key, nodes)
    return nodes


def rewrite_question(question, history):
    """Expand referential follow-ups with bounded user questions, never model output.

    This is a lexical heuristic, not a model-based standalone-question rewriter.
    Short standalone topics and document overviews must remain independent of
    previous answers, which are not a source of verified document facts.
    """
    question = (question or "").strip()
    if not question:
        return ""
    if not history or _is_document_overview_query(question):
        return question
    question_lower = question.lower()
    trigger_words = [
        "it", "this", "that", "those", "they", "them", "its", "their", "these",
        "nó", "cái này", "cái đó", "những cái này", "những cái đó", "chúng", "chúng nó",
        "cụ thể", "chi tiết", "cụ thể hơn", "rõ hơn", "kể tiếp", "tiếp theo", "nói rõ",
    ]
    referential = any(
        (word in question_lower if " " in word else re.search(rf"\b{re.escape(word)}\b", question_lower))
        for word in trigger_words
    )
    elliptical = question_lower.rstrip(".!?") in {
        "why", "how so", "explain more", "continue", "vì sao", "tại sao", "tiếp", "nói tiếp", "giải thích thêm",
    } or question_lower.startswith(("what about ", "how about ", "còn "))
    if not (referential or elliptical):
        return question
    user_questions = []
    for message in reversed(history):
        content = str(message.get("content", "")).strip()
        if message.get("role") == "user" and content and content.casefold() != question.casefold():
            user_questions.append(re.sub(r"\s+", " ", content)[:200])
            if len(user_questions) == 2:
                break
    if not user_questions:
        return question
    return f"{question}\nPrevious user questions: {' | '.join(reversed(user_questions))}"
