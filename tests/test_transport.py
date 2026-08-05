import threading
import time
from pathlib import Path

import pytest
import uvicorn

from assist_desktop.client.transport import StaleResponse, Transport, TransportError
from tools.fake_devkit import make_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="module")
def devkit_url():
    config = uvicorn.Config(make_app(FIXTURES), host="127.0.0.1", port=8123,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "fake devkit failed to start"
    yield "http://127.0.0.1:8123"
    server.should_exit = True
    thread.join(timeout=5)


def test_health_returns_payload(devkit_url):
    assert Transport(devkit_url).health()["ready"] is True


def test_ask_returns_a_parsed_turn(devkit_url):
    turn = Transport(devkit_url).ask("how do i fill the tank")
    assert turn.plan.kind == "cached"
    assert turn.answer is not None
    assert turn.answer.safety[0].level == "WARNING"


def test_unreachable_devkit_raises_transport_error():
    t = Transport("http://127.0.0.1:9", timeout_s=1.0)
    with pytest.raises(TransportError) as exc:
        t.health()
    assert exc.value.detail


def test_refused_connection_does_not_claim_a_timeout():
    """A refused port is not a slow devkit, and must not say it was."""
    t = Transport("http://127.0.0.1:9", timeout_s=20.0)
    with pytest.raises(TransportError) as exc:
        t.ask("anything")
    assert "cannot reach" in exc.value.detail
    assert "20s" not in exc.value.detail


def test_a_superseded_generation_is_stale(devkit_url):
    t = Transport(devkit_url)
    generation = t._current_generation()
    t.cancel()
    with pytest.raises(StaleResponse):
        t._check_generation(generation)
