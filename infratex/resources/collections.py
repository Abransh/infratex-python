"""Collections resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .._types import Collection

if TYPE_CHECKING:
    from .._http import HTTPClient


class Collections:
    """Interact with the ``/api/v1/collections`` endpoints."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def create(self, *, name: str) -> Collection:
        """Create a new collection."""
        resp = self._client.request(
            "POST", "/api/v1/collections", json_body={"name": name}
        )
        return Collection(resp)

    def list(self) -> List[Collection]:
        """List all collections."""
        resp = self._client.request("GET", "/api/v1/collections")
        return [Collection(c) for c in resp]

    def get(self, collection_id: str) -> Collection:
        """Retrieve a single collection by ID."""
        resp = self._client.request("GET", "/api/v1/collections/{}".format(collection_id))
        return Collection(resp)

    def update(self, collection_id: str, *, name: str) -> Collection:
        """Rename a collection."""
        resp = self._client.request(
            "PATCH",
            "/api/v1/collections/{}".format(collection_id),
            json_body={"name": name},
        )
        return Collection(resp)

    def delete(self, collection_id: str) -> None:
        """Delete a collection."""
        self._client.request_no_content("DELETE", "/api/v1/collections/{}".format(collection_id))
