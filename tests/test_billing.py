from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import pytest

from infratex import BillingTransaction

from .conftest import ClientFactory


def _transaction(tx_id: str, created_at: str) -> Dict[str, Any]:
    return {
        "id": tx_id,
        "transaction_type": "usage_charge",
        "status": "posted",
        "amount_micros": -15000,
        "balance_after_micros": 985000,
        "currency": "EUR",
        "source_type": "document",
        "source_id": "doc-1",
        "description": "Parsing Standard: report.pdf (3 pages)",
        "created_at": created_at,
        "metadata": {"pages": 3},
    }


def _page(*tx_ids: str, next_before: Optional[str] = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "transactions": [_transaction(tx_id, "2026-10-1{}T10:00:00Z".format(i)) for i, tx_id in enumerate(tx_ids)],
            "next_before": next_before,
        },
    )


def test_list_transactions_sends_filters(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: _page("tx-1", next_before="2026-10-10T10:00:00Z"))

    page = client.billing.list_transactions(
        since=datetime(2026, 10, 1, tzinfo=timezone.utc),
        until="2026-10-15T00:00:00Z",
        before="2026-10-12T08:30:00+02:00",
        limit=500,
    )

    assert recorder.last.url.path == "/api/v1/billing/transactions"
    assert dict(recorder.last.url.params) == {
        "since": "2026-10-01T00:00:00+00:00",
        "until": "2026-10-15T00:00:00Z",
        "before": "2026-10-12T08:30:00+02:00",
        "limit": "500",
    }
    # "+" in an offset must be percent-encoded, or the server reads a space.
    assert b"%2B00%3A00" in recorder.last.url.query
    assert page.next_before == "2026-10-10T10:00:00Z"
    (transaction,) = list(page)
    assert isinstance(transaction, BillingTransaction)
    assert transaction.amount_micros == -15000
    assert transaction.source_id == "doc-1"
    assert transaction.metadata == {"pages": 3}


def test_list_transactions_sends_no_query_by_default(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: _page())

    page = client.billing.list_transactions()

    assert recorder.last.url.query == b""
    assert len(page) == 0
    assert page.next_before is None


@pytest.mark.parametrize("limit", [0, 501])
def test_list_transactions_rejects_out_of_range_limit(make_client: ClientFactory, limit: int) -> None:
    client, recorder = make_client(lambda request: _page())

    with pytest.raises(ValueError, match="between 1 and 500"):
        client.billing.list_transactions(limit=limit)
    assert recorder.requests == []


def test_iter_transactions_follows_next_before(make_client: ClientFactory) -> None:
    pages = {
        None: _page("tx-3", "tx-2", next_before="2026-10-11T10:00:00Z"),
        "2026-10-11T10:00:00Z": _page("tx-1", next_before=None),
    }
    client, recorder = make_client(lambda request: pages[request.url.params.get("before")])

    transactions = list(client.billing.iter_transactions(since="2026-10-01T00:00:00Z", page_size=2))

    assert [t.id for t in transactions] == ["tx-3", "tx-2", "tx-1"]
    assert [dict(r.url.params) for r in recorder.requests] == [
        {"since": "2026-10-01T00:00:00Z", "limit": "2"},
        {"since": "2026-10-01T00:00:00Z", "before": "2026-10-11T10:00:00Z", "limit": "2"},
    ]


def test_iter_transactions_is_lazy(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: _page("tx-2", "tx-1", next_before="2026-10-10T10:00:00Z"))

    iterator = client.billing.iter_transactions()
    assert recorder.requests == []

    assert next(iterator).id == "tx-2"
    assert len(recorder.requests) == 1
    assert recorder.last.url.params["limit"] == "500"


def test_iter_transactions_validates_page_size_eagerly(make_client: ClientFactory) -> None:
    client, _ = make_client(lambda request: _page())

    with pytest.raises(ValueError, match="page_size"):
        client.billing.iter_transactions(page_size=1000)
