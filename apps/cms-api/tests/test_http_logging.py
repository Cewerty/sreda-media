import asyncio
import json
import logging
from io import StringIO
from unittest.mock import patch
from uuid import UUID

import pytest
from django.http import HttpResponse
from django.test import AsyncClient, Client, override_settings
from django.urls import path
from structlog.contextvars import get_contextvars

CANARY = "private-canary-value"
INCOMING = "12345678-1234-4234-8234-123456789012"


async def success(request):
    before = get_contextvars()["correlation_id"]
    await asyncio.sleep(0)
    assert before == get_contextvars()["correlation_id"]
    return HttpResponse(before)


def failure(request):
    raise RuntimeError(CANARY)


urlpatterns = [path("ok/", success), path("error/", failure)]


@pytest.fixture
def stream():
    output = StringIO()
    handler = logging.getLogger("cms").handlers[0]
    with patch.object(handler, "stream", output):
        yield output


@override_settings(ROOT_URLCONF=__name__, DEBUG=False)
def test_responses(stream, capfd, caplog):
    client = Client(raise_request_exception=False)
    for url, code, outcome in [
        ("/ok/", 200, "success"),
        (f"/{CANARY}/", 404, "client_error"),
        ("/error/", 500, "server_error"),
    ]:
        response = client.post(
            f"{url}?query={CANARY}",
            CANARY,
            content_type="text/plain",
            headers={"Authorization": CANARY, "X-Correlation-ID": INCOMING},
        )
        assert response.status_code == code
        event = json.loads(stream.getvalue())
        assert set(event) == {
            "event",
            "component",
            "operation",
            "outcome",
            "correlation_id",
            "status_code",
            "elapsed_ms",
            "environment",
            "timestamp",
            "release",
        }
        assert event["event"] == "request_finished"
        assert event["component"] == "cms-api"
        assert event["operation"] == "http_request"
        assert event["outcome"] == outcome
        assert event["status_code"] == code
        assert event["elapsed_ms"] >= 0
        assert event["timestamp"].endswith("Z")
        assert event["correlation_id"] == response["X-Correlation-ID"] != INCOMING
        assert UUID(event["correlation_id"]).version == 4
        assert CANARY not in stream.getvalue()
        stream.seek(0)
        stream.truncate()
    captured = capfd.readouterr()
    assert CANARY not in captured.out + captured.err + caplog.text


@override_settings(ROOT_URLCONF=__name__)
def test_concurrent_requests(stream):
    async def run():
        client = AsyncClient()
        return await asyncio.gather(client.get("/ok/"), client.get("/ok/"))

    responses = asyncio.run(run())
    ids = {response["X-Correlation-ID"] for response in responses}
    assert len(ids) == 2
    assert ids == {response.content.decode() for response in responses}
    assert ids == {json.loads(line)["correlation_id"] for line in stream.getvalue().splitlines()}
    assert "correlation_id" not in get_contextvars()
