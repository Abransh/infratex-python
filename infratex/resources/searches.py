"""Searches resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .._scope import validate_scope
from .._types import SearchResponse

if TYPE_CHECKING:
    from .._http import HTTPClient


class Searches:
    """Interact with the ``/api/v1/searches`` endpoint."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(
        self,
        *,
        query: str,
        method: str = "vector",
        limit: int = 5,
        document_ids: Optional[List[str]] = None,
        collection_id: Optional[str] = None,
    ) -> SearchResponse:
        """Run a semantic or hybrid search across indexed documents.

        Parameters
        ----------
        query:
            The natural-language search query.
        method:
            ``"vector"`` or ``"hybrid"``.
        limit:
            Maximum number of results to return (1--50).
        document_ids:
            Restrict search to these document IDs.
        collection_id:
            Restrict search to this collection.
        """
        normalized_document_ids = validate_scope(
            document_ids=document_ids,
            collection_id=collection_id,
        )
        body: Dict[str, Any] = {
            "query": query,
            "method": method,
            "limit": limit,
        }
        if normalized_document_ids is not None:
            body["document_ids"] = normalized_document_ids
        if collection_id is not None:
            body["collection_id"] = collection_id

        resp = self._client.request("POST", "/api/v1/searches", json_body=body)
        return SearchResponse(resp)
