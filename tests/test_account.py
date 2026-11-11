from __future__ import annotations

import json

import httpx

from infratex import AccountSettings

from .conftest import ClientFactory

_SETTINGS = {
    "allow_overage": False,
    "monthly_spend_cap_micros": None,
    "low_balance_threshold_micros": 2500000,
    "has_payment_method": False,
    "data_residency": "eu_only",
}


def test_settings_report_data_residency(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_SETTINGS))

    settings = client.account.settings()

    assert recorder.last.url.path == "/api/v1/account/settings"
    assert settings.data_residency == "eu_only"


def test_update_settings_sends_only_data_residency(make_client: ClientFactory) -> None:
    client, recorder = make_client(lambda request: httpx.Response(200, json=_SETTINGS))

    settings = client.account.update_settings(data_residency="eu_only")

    assert recorder.last.method == "PATCH"
    assert recorder.last.url.path == "/api/v1/account/settings"
    assert json.loads(recorder.last.content) == {"data_residency": "eu_only"}
    assert isinstance(settings, AccountSettings)
