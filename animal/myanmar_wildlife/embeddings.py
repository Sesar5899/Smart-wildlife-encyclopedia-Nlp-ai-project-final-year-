"""Administrator-built OpenAI embeddings with an offline SQLite index.

All published passages for animals, ecosystems, and protected areas are
embedded through OpenAI only when an administrator publishes or explicitly
rebuilds the index.  Member chat never makes an online embedding request.  It
loads passage vectors from SQLite and may use an exact question vector that an
administrator previously cached in the RAG console; otherwise retrieval falls
back to the Myanmar-aware lexical pipeline.

Passage vectors are deduplicated by ``(model, sha256(text))``.  A second table
maps every vector back to its content kind, stable record key, passage label,
and position, so index completeness and stale records are observable.
"""

from __future__ import annotations

import hashlib
import math

import requests

from config import Config
from db import (
    get_query_vectors, get_vectors, prune_vector_index, remove_vector_index,
    replace_vector_index, save_query_vectors, save_vectors, vector_index_stats,
    vector_store_stats,
)


class EmbeddingError(RuntimeError):
    """An administrator-triggered OpenAI embedding operation failed."""


def enabled() -> bool:
    """Whether local semantic retrieval is enabled for the configured model."""
    return bool(Config.EMBED_ENABLED and Config.OPENAI_EMBED_MODEL)


def online_enabled() -> bool:
    """Whether an administrator can currently create new OpenAI vectors."""
    return bool(enabled() and Config.OPENAI_API_KEY)


def index_model() -> str:
    """Storage namespace, including dimensions that change vector identity."""
    dimensions = Config.OPENAI_EMBED_DIMENSIONS or "default"
    return f"openai:{Config.OPENAI_EMBED_MODEL}:{dimensions}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize(vector):
    """Store unit vectors so cosine similarity is a plain dot product."""
    if not isinstance(vector, list):
        return None
    try:
        values = [float(value) for value in vector]
        length = math.sqrt(sum(value * value for value in values))
    except (TypeError, ValueError, OverflowError):
        return None
    if not length:
        return None
    return [value / length for value in values]


def _openai_embed(texts: list[str]):
    """Create one ordered batch of vectors through OpenAI's embeddings API."""
    if not texts:
        return []
    if not online_enabled():
        raise EmbeddingError(
            "OpenAI indexing is unavailable. Set OPENAI_API_KEY for the admin process."
        )

    payload = {
        "model": Config.OPENAI_EMBED_MODEL,
        "input": texts,
        "encoding_format": "float",
    }
    if Config.OPENAI_EMBED_DIMENSIONS > 0:
        payload["dimensions"] = Config.OPENAI_EMBED_DIMENSIONS

    try:
        response = requests.post(
            f"{Config.OPENAI_BASE_URL.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(5, Config.OPENAI_EMBED_TIMEOUT),
        )
    except requests.RequestException as exc:
        raise EmbeddingError(f"OpenAI embeddings request failed: {exc}") from exc

    if response.status_code != 200:
        try:
            detail = response.json().get("error", {}).get("message")
        except (TypeError, ValueError):
            detail = None
        raise EmbeddingError(
            f"OpenAI embeddings returned HTTP {response.status_code}: "
            f"{detail or response.text[:300]}"
        )

    try:
        data = response.json().get("data", [])
    except ValueError as exc:
        raise EmbeddingError("OpenAI embeddings returned invalid JSON") from exc
    if not isinstance(data, list) or len(data) != len(texts):
        raise EmbeddingError("OpenAI embeddings returned an incomplete batch")

    ordered = [None] * len(texts)
    for fallback_index, item in enumerate(data):
        if not isinstance(item, dict):
            raise EmbeddingError("OpenAI embeddings returned an invalid item")
        index = item.get("index", fallback_index)
        if not isinstance(index, int) or not 0 <= index < len(texts):
            raise EmbeddingError("OpenAI embeddings returned an invalid item index")
        ordered[index] = _normalize(item.get("embedding"))
    if any(vector is None for vector in ordered):
        raise EmbeddingError("OpenAI embeddings returned an invalid vector")

    dimensions = {len(vector) for vector in ordered}
    if len(dimensions) != 1:
        raise EmbeddingError("OpenAI embeddings returned inconsistent dimensions")
    return ordered


def cached_vectors(texts: list[str]):
    """Read passage vectors without making any network call."""
    if not texts or not enabled():
        return [None] * len(texts)
    hashes = [text_hash(text) for text in texts]
    try:
        cached = get_vectors(index_model(), set(hashes))
    except Exception:
        return [None] * len(texts)
    return [cached.get(digest) for digest in hashes]


def _ensure_vectors(texts: list[str]):
    """Create every missing vector and return them in input order."""
    hashes = [text_hash(text) for text in texts]
    cached = get_vectors(index_model(), set(hashes))

    missing = []
    seen = set()
    for text, digest in zip(texts, hashes):
        if digest not in cached and digest not in seen:
            seen.add(digest)
            missing.append((digest, text))

    batch_size = Config.OPENAI_EMBED_BATCH_SIZE
    for start in range(0, len(missing), batch_size):
        batch = missing[start:start + batch_size]
        vectors = _openai_embed([text for _, text in batch])
        fresh = [(digest, vector) for (digest, _), vector in zip(batch, vectors)]
        save_vectors(index_model(), fresh)
        cached.update(dict(fresh))

    vectors = [cached.get(digest) for digest in hashes]
    if any(vector is None for vector in vectors):
        raise EmbeddingError("The local vector store is incomplete after indexing")
    return vectors, len(missing)


def index_record(content_kind: str, record_key, passages):
    """Fully index one current record, including passage metadata."""
    passages = list(passages)
    texts = [passage.text for passage in passages]
    if not texts:
        remove_vector_index(
            index_model(), content_kind, str(record_key)
        )
        return {"passages": 0, "new_vectors": 0, "reused_vectors": 0}
    if not online_enabled():
        raise EmbeddingError(
            "Set OPENAI_API_KEY before publishing or rebuilding embeddings."
        )

    _, new_vectors = _ensure_vectors(texts)
    entries = [
        (position, passage.label, text_hash(passage.text))
        for position, passage in enumerate(passages)
    ]
    replace_vector_index(
        index_model(), content_kind, str(record_key), entries
    )
    return {
        "passages": len(passages),
        "new_vectors": new_vectors,
        "reused_vectors": len(set(text_hash(text) for text in texts)) - new_vectors,
    }


def remove_record(content_kind: str, record_key):
    """Remove a deleted or renamed record from the active local index."""
    if not enabled():
        return 0
    return remove_vector_index(
        index_model(), content_kind, str(record_key)
    )


def finish_full_index(valid_records):
    """Remove records and vectors not referenced by a completed full rebuild."""
    return prune_vector_index(index_model(), valid_records)


def cached_question_vector(question: str):
    """An exact admin-cached question vector, read entirely offline."""
    question = (question or "").strip()
    if not question or not enabled():
        return None
    digest = text_hash(question)
    try:
        return get_query_vectors(
            index_model(), {digest}
        ).get(digest)
    except Exception:
        return None


def admin_question_vector(question: str, *, cache=True):
    """Embed an admin console question online and optionally cache it locally."""
    question = (question or "").strip()
    if not question or not enabled():
        return None
    existing = cached_question_vector(question)
    if existing is not None:
        return existing
    vector = _openai_embed([question])[0]
    if cache:
        save_query_vectors(
            index_model(), [(text_hash(question), vector)]
        )
    return vector


def retrieval_vectors(question: str, passages, *, allow_online=False,
                      cache_question=False):
    """Return query and passage vectors without member-time network access.

    ``allow_online`` is reserved for administrator routes.  Member chat uses
    the default and therefore either finds an exact cached admin query vector
    or performs lexical retrieval with ``None`` as the query vector.
    """
    passages = list(passages)
    if not enabled() or not passages:
        return None, [None] * len(passages)
    passage_vectors = cached_vectors([passage.text for passage in passages])
    if not any(passage_vectors):
        return None, passage_vectors
    if allow_online:
        question_vector = admin_question_vector(
            question, cache=cache_question
        )
    else:
        question_vector = cached_question_vector(question)
    return question_vector, passage_vectors


def status():
    """Local index and administrator connectivity configuration."""
    model = Config.OPENAI_EMBED_MODEL
    storage_model = index_model()
    state = {
        "enabled": enabled(),
        "provider": "OpenAI",
        "model": model,
        "index_model": storage_model,
        "threshold": Config.EMBED_THRESHOLD,
        "api_configured": online_enabled(),
        "rows": 0,
        "dims": 0,
        "bytes": 0,
        "indexed_records": 0,
        "indexed_passages": 0,
        "cached_queries": 0,
        "by_kind": {},
    }
    try:
        state.update(vector_store_stats(storage_model))
        state.update(vector_index_stats(storage_model))
    except Exception:
        pass
    return state
