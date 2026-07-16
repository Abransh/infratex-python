"""Shared scope validation helpers for SDK resource methods."""

from __future__ import annotations

from typing import Iterable, List, Optional


def normalize_document_ids(document_ids: Optional[Iterable[str]]) -> Optional[List[str]]:
    if document_ids is None:
        return None

    normalized = [document_id for document_id in document_ids if document_id]
    return normalized or None


def validate_scope(
    *,
    document_ids: Optional[Iterable[str]] = None,
    collection_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Optional[List[str]]:
    normalized_document_ids = normalize_document_ids(document_ids)

    if normalized_document_ids is not None and collection_id is not None:
        raise ValueError("document_ids and collection_id cannot be used together")

    if conversation_id is not None and (
        normalized_document_ids is not None or collection_id is not None
    ):
        raise ValueError(
            "document_ids and collection_id must be omitted when conversation_id is provided"
        )

    return normalized_document_ids
