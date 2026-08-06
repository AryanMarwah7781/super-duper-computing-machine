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


def test_unknown_version_is_ready_but_warns():
    state, detail = next_state(ConnectionState.CONNECTING,
                               {"ready": True, "render_version": "v9.9"}, None)
    assert state is ConnectionState.READY
    assert "v9.9" in detail


def test_v3_is_supported_and_named_not_warned_about():
    """Both pipelines emit the same display grammar, so v3 is a normal state,
    not a mismatch — it must not nag on every poll."""
    state, detail = next_state(ConnectionState.CONNECTING,
                               {"ready": True, "render_version": "v3"}, None)
    assert state is ConnectionState.READY
    assert "expects" not in detail and "supports" not in detail
    assert "v3" in detail
