from pathlib import Path

import httpx
import pytest

from maritime.sources import Fetcher, SourceError
from maritime.store import Store


def test_raw_retention_retry_and_idempotency(tmp_path):
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(503 if len(attempts) == 1 else 200, json={"real": "response"})

    fetch = Fetcher(
        tmp_path, httpx.Client(transport=httpx.MockTransport(handle)), sleep=lambda _: None
    )
    _, first = fetch.get("test", "https://example.org")
    _, second = fetch.get("test", "https://example.org")
    assert first["checksum"] == second["checksum"]
    assert len(list((tmp_path / "bronze/test").glob("*.raw"))) == 1
    assert Path(first["raw_path"]).read_bytes()
    assert fetch.retries == 1


def test_failure_loud(tmp_path):
    fetch = Fetcher(
        tmp_path, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403)))
    )
    with pytest.raises(SourceError):
        fetch.get("test", "https://example.org")
    assert fetch.events[-1]["status"] == "FAILED"


def test_store_atomic_publication(tmp_path):
    store = Store(tmp_path)
    store.write("a", "ports", [{"id": 1}])
    assert store.read("ports") == []
    with pytest.raises(ValueError, match="approved release"):
        store.set_metadata("published_run", "a")
    assert store.read("ports") == []
