"""Fault checks for cleanup of the live Q02 checker's own resources."""

import importlib.util
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "q02_checker", Path(__file__).resolve().parents[3] / "tests/e2e/check_q02_booking.py"
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def run_cleanup(monkeypatch, handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(
            checker,
            "cognito",
            lambda client, operation, **kwargs: client.post(
                "http://cognito.test/" + kwargs["Token"]
            ),
        )

        def request(method, base, path, actor=None, expected=200, **kwargs):
            response = http.request(method, base + path, **kwargs)
            response.raise_for_status()
            assert response.status_code == expected
            return response.json() if response.content else None

        return checker.cleanup(
            request,
            http,
            "client",
            {
                "patient": {"access_token": "access-one", "refresh_token": "refresh-one"},
                "clinic": {"access_token": "access-two", "refresh_token": "refresh-two"},
            },
            [("patient", "one"), ("clinic", "two")],
            {"slot_id": "slot"},
        )


def test_cleanup_continues_after_resource_and_token_failures(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/appointments/one":
            raise httpx.ReadTimeout("unavailable", request=request)
        if request.method == "DELETE" or request.url.path == "/refresh-one":
            return httpx.Response(503)
        if request.url.path == "/appointments/two":
            return httpx.Response(200, json={"status": "held"})
        return httpx.Response(200)

    errors = run_cleanup(monkeypatch, handler)

    assert len(errors) == 3
    assert ("POST", "/appointments/two/cancel") in calls
    assert ("DELETE", "/slots/slot") in calls
    assert ("POST", "/refresh-two") in calls


@pytest.mark.parametrize("current_status", ["expired", "held"])
def test_cancel_conflict_requires_confirmed_expiry(monkeypatch, current_status):
    reads = 0

    def handler(request):
        nonlocal reads
        if request.url.path == "/appointments/one":
            reads += 1
            return httpx.Response(200, json={"status": "held" if reads == 1 else current_status})
        if request.url.path == "/appointments/one/cancel":
            return httpx.Response(409)
        if request.url.path == "/appointments/two":
            return httpx.Response(200, json={"status": "expired"})
        return httpx.Response(204 if request.method == "DELETE" else 200)

    errors = run_cleanup(monkeypatch, handler)

    assert len(errors) == (0 if current_status == "expired" else 1)
