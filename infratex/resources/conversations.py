"""Conversations resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from .._scope import validate_scope
from .._types import Conversation

if TYPE_CHECKING:
    from .._http import HTTPClient


class Conversations:
    """Interact with the ``/api/v1/conversations`` endpoints."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(
        self,
        *,
        title: str = "New Chat",
        document_ids: Optional[List[str]] = None,
        collection_id: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation thread with an optional persisted scope."""
        normalized_document_ids = validate_scope(
            document_ids=document_ids,
            collection_id=collection_id,
        )
        body = {"title": title}
        if normalized_document_ids is not None:
            body["document_ids"] = normalized_document_ids
        if collection_id is not None:
            body["collection_id"] = collection_id
        resp = self._client.request(
            "POST", "/api/v1/conversations", json_body=body
        )
        return Conversation(resp)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """List conversations.

        Parameters
        ----------
        limit:
            Maximum number of conversations to return (1--100).
        offset:
            Pagination offset.
        """
        params = {"limit": limit, "offset": offset}
        resp = self._client.request("GET", "/api/v1/conversations", params=params)
        return [Conversation(c) for c in resp]

    def get(self, conversation_id: str) -> Conversation:
        """Retrieve a conversation and its messages."""
        resp = self._client.request("GET", "/api/v1/conversations/{}".format(conversation_id))
        return Conversation(resp)

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation."""
        self._client.request_no_content("DELETE", "/api/v1/conversations/{}".format(conversation_id))
