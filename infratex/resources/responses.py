"""Responses resource (streaming AI answers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from .._scope import validate_scope
from .._types import StreamEvent

if TYPE_CHECKING:
    from .._http import HTTPClient


class Responses:
    """Interact with the ``/api/v1/responses`` endpoint."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(
        self,
        *,
        message: str,
        method: str = "vector",
        model: str = "fast",
        reasoning: bool = False,
        limit: int = 5,
        document_ids: Optional[List[str]] = None,
        collection_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """Generate a streamed AI response grounded in your documents.

        Yields :class:`StreamEvent` objects with ``type`` and ``content``.
        Event types:

        - ``"sources"`` -- retrieved source chunks (list of dicts)
        - ``"thinking"`` -- reasoning content (when reasoning=True)
        - ``"text"`` -- a chunk of generated text
        - ``"done"`` -- stream complete
        - ``"error"`` -- an error occurred

        Parameters
        ----------
        message:
            The user message / question.
        method:
            ``"vector"`` or ``"hybrid"``.
        model:
            ``"fast"`` (default) or ``"pro"`` (more intelligent, higher cost).
        reasoning:
            Enable extended reasoning. Default ``False``.
        limit:
            How many source chunks to retrieve (1--20).
        document_ids:
            Restrict to these document IDs.
        collection_id:
            Restrict to this collection.
        conversation_id:
            Continue an existing conversation thread. When set, the conversation's
            persisted document scope is used and request-level scope selectors must
            be omitted.
        """
        normalized_document_ids = validate_scope(
            document_ids=document_ids,
            collection_id=collection_id,
            conversation_id=conversation_id,
        )
        body: Dict[str, Any] = {
            "message": message,
            "method": method,
            "model": model,
            "limit": limit,
        }
        if reasoning:
            body["reasoning"] = True
        if normalized_document_ids is not None:
            body["document_ids"] = normalized_document_ids
        if collection_id is not None:
            body["collection_id"] = collection_id
        if conversation_id is not None:
            body["conversation_id"] = conversation_id

        for event_data in self._client.stream_sse("POST", "/api/v1/responses", json_body=body):
            event_type = event_data.get("type", "unknown")
            content = event_data.get("content")
            yield StreamEvent(type=event_type, content=content)
