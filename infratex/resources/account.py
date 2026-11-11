"""Account resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .._types import Account as AccountModel, AccountSettings

if TYPE_CHECKING:
    from .._http import HTTPClient

#: ``"default"``: every parse method and model is available. ``"eu_only"``: a
#: request that would be processed outside the EU is refused with 422.
DataResidency = Literal["default", "eu_only"]


class AccountResource:
    """Interact with the ``/api/v1/account`` endpoints."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self) -> AccountModel:
        """Retrieve the current account details (tenant + credit balance)."""
        resp = self._client.request("GET", "/api/v1/account")
        return AccountModel(resp)

    def settings(self) -> AccountSettings:
        """Retrieve account settings (overage, spend cap, thresholds, data residency)."""
        resp = self._client.request("GET", "/api/v1/account/settings")
        return AccountSettings(resp)

    def update_settings(self, *, data_residency: DataResidency) -> AccountSettings:
        """Set where the account's requests may be processed.

        An API key may change only ``data_residency`` (the billing settings
        are dashboard-only). It may switch the account to ``"eu_only"``, but
        switching an EU-only account back to ``"default"`` is dashboard-only:
        the API answers 403 ``dashboard_only``. A change applies from the next
        request.
        """
        resp = self._client.request(
            "PATCH",
            "/api/v1/account/settings",
            json_body={"data_residency": data_residency},
        )
        return AccountSettings(resp)
