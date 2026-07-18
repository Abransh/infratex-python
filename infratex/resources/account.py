"""Account resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._types import Account as AccountModel, AccountSettings

if TYPE_CHECKING:
    from .._http import HTTPClient


class AccountResource:
    """Interact with the ``/api/v1/account`` endpoints."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self) -> AccountModel:
        """Retrieve the current account details (tenant + credit balance)."""
        resp = self._client.request("GET", "/api/v1/account")
        return AccountModel(resp)

    def settings(self) -> AccountSettings:
        """Retrieve account billing settings (overage, spend cap, thresholds)."""
        resp = self._client.request("GET", "/api/v1/account/settings")
        return AccountSettings(resp)
