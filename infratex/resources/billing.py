"""Billing resource."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Union

from .._types import BillingSummary, BillingTransaction, BillingTransactionPage

if TYPE_CHECKING:
    from .._http import HTTPClient

Timestamp = Union[datetime, str]

MAX_TRANSACTION_PAGE = 500


class Billing:
    """Interact with the ``/api/v1/billing`` endpoints."""

    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self) -> BillingSummary:
        """Retrieve the billing summary for the current account."""
        resp = self._client.request("GET", "/api/v1/billing")
        return BillingSummary(resp)

    def list_transactions(
        self,
        *,
        since: Optional[Timestamp] = None,
        until: Optional[Timestamp] = None,
        before: Optional[Timestamp] = None,
        limit: Optional[int] = None,
    ) -> BillingTransactionPage:
        """Fetch one page of the account's credit ledger, newest first.

        Parameters
        ----------
        since:
            Only transactions at or after this time. A ``datetime`` (use a
            timezone-aware one) or an ISO 8601 string.
        until:
            Only transactions before this time.
        before:
            Cursor: the ``next_before`` of the previous page.
        limit:
            Page size, 1 to 500. The server default is 100.
        """
        _check_page_size("limit", limit)
        params: Dict[str, Any] = {
            "since": _timestamp(since),
            "until": _timestamp(until),
            "before": _timestamp(before),
            "limit": limit,
        }
        resp = self._client.request("GET", "/api/v1/billing/transactions", params=params)
        return BillingTransactionPage(resp)

    def iter_transactions(
        self,
        *,
        since: Optional[Timestamp] = None,
        until: Optional[Timestamp] = None,
        page_size: int = MAX_TRANSACTION_PAGE,
    ) -> Iterator[BillingTransaction]:
        """Iterate over every transaction in the window, newest first.

        Follows ``next_before`` from page to page until the last one, fetching
        each page lazily as the iterator advances.
        """
        _check_page_size("page_size", page_size)
        return self._iter_transactions(since=since, until=until, page_size=page_size)

    def _iter_transactions(
        self,
        *,
        since: Optional[Timestamp],
        until: Optional[Timestamp],
        page_size: int,
    ) -> Iterator[BillingTransaction]:
        before: Optional[str] = None
        while True:
            page = self.list_transactions(since=since, until=until, before=before, limit=page_size)
            for transaction in page.transactions:
                yield transaction
            if not page.next_before or page.next_before == before:
                return
            before = page.next_before


def _timestamp(value: Optional[Timestamp]) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _check_page_size(name: str, value: Optional[int]) -> None:
    if value is not None and not 1 <= value <= MAX_TRANSACTION_PAGE:
        raise ValueError("{} must be between 1 and {}".format(name, MAX_TRANSACTION_PAGE))
