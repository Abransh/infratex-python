"""Main Infratex client."""

from __future__ import annotations

import os
from typing import Optional

import httpx

from ._http import HTTPClient
from .resources.documents import Documents
from .resources.searches import Searches
from .resources.responses import Responses
from .resources.collections import Collections
from .resources.conversations import Conversations
from .resources.account import AccountResource
from .resources.billing import Billing

__all__ = ["Infratex"]


class Infratex:
    """Infratex API client.

    Parameters
    ----------
    api_key:
        Your Infratex API key (``infratex_sk_...``).  Falls back to the
        ``INFRATEX_API_KEY`` environment variable when not provided.
    base_url:
        Override the API base URL (default ``https://api.infratex.io``).
    timeout:
        Request timeout in seconds (default 300).
    httpx_client:
        Optionally provide your own ``httpx.Client`` instance.
    """

    documents: Documents
    searches: Searches
    responses: Responses
    collections: Collections
    conversations: Conversations
    account: AccountResource
    billing: Billing

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        httpx_client: Optional[httpx.Client] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("INFRATEX_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "An API key is required. Pass api_key= or set the INFRATEX_API_KEY "
                "environment variable."
            )

        self._http = HTTPClient(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout,
            httpx_client=httpx_client,
        )

        self.documents = Documents(self._http)
        self.searches = Searches(self._http)
        self.responses = Responses(self._http)
        self.collections = Collections(self._http)
        self.conversations = Conversations(self._http)
        self.account = AccountResource(self._http)
        self.billing = Billing(self._http)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> Infratex:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
