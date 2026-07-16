"""Account resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._types import Account as AccountModel

if TYPE_CHECKING:
    from .._http import HTTPClient


class AccountResource:
    """Interact with the ``/api/v1/account`` endpoint."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self) -> AccountModel:
        """Retrieve the current account details."""
        resp = self._client.request("GET", "/api/v1/account")
        return AccountModel(resp)
