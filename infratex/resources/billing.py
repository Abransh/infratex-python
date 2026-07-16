"""Billing resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._types import BillingSummary

if TYPE_CHECKING:
    from .._http import HTTPClient


class Billing:
    """Interact with the ``/api/v1/billing`` endpoint."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self) -> BillingSummary:
        """Retrieve the billing summary for the current account."""
        resp = self._client.request("GET", "/api/v1/billing")
        return BillingSummary(resp)
