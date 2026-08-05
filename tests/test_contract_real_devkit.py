"""Runs against the REAL devkit. Skipped unless ASSIST_DEVKIT_URL is set.

Fixtures cannot catch server/client drift, because fixtures are what the client
already believes. This is the only test that can.
"""
import os

import pytest

from assist_desktop.client.transport import Transport

URL = os.environ.get("ASSIST_DEVKIT_URL")
pytestmark = pytest.mark.skipif(not URL, reason="ASSIST_DEVKIT_URL is not set")


def test_health_shape():
    health = Transport(URL).health()
    assert health["render_version"] == "v4.0"
    assert isinstance(health["chunk_count"], int)


def test_real_answer_deserialises_into_the_wire_models():
    turn = Transport(URL, timeout_s=60.0).ask("how do i fill the solution tank")
    assert turn.plan.kind in {"cached", "synthesize", "oos"}
    assert turn.timing["total_ms"] > 0
    if turn.answer:
        assert turn.answer.render_version == "v4.0"
        assert turn.answer.display_text


def test_safety_precedes_step_one_in_display_text():
    turn = Transport(URL, timeout_s=60.0).ask("how do i fill the solution tank")
    if turn.answer and turn.answer.safety and "Step 1:" in turn.answer.display_text:
        text = turn.answer.display_text
        assert text.index("**") < text.index("Step 1:")
