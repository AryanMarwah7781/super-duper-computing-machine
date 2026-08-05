from assist_desktop.client.health import ConnectionState, next_state

READY = {"ready": True, "render_version": "v4.0"}
WARMING = {"ready": False, "render_version": "v4.0"}


def test_healthy_service_becomes_ready():
    state, _ = next_state(ConnectionState.CONNECTING, READY, None)
    assert state is ConnectionState.READY


def test_not_yet_loaded_becomes_warming():
    state, detail = next_state(ConnectionState.CONNECTING, WARMING, None)
    assert state is ConnectionState.WARMING
    assert "warming" in detail.lower()


def test_error_becomes_offline_and_keeps_the_reason():
    state, detail = next_state(ConnectionState.READY, None, "connection refused")
    assert state is ConnectionState.OFFLINE
    assert "connection refused" in detail


def test_recovers_from_offline_to_ready():
    state, _ = next_state(ConnectionState.OFFLINE, READY, None)
    assert state is ConnectionState.READY


def test_version_mismatch_is_ready_but_warns():
    state, detail = next_state(ConnectionState.CONNECTING,
                               {"ready": True, "render_version": "v3.9"}, None)
    assert state is ConnectionState.READY
    assert "v3.9" in detail
