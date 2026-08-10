"""The command layer, and the three bugs it inherited fixes for.

Every one of these was a real failure in the old stack. They are tests now so
the fixes cannot be lost in a rewrite.
"""
from __future__ import annotations

import pytest

from assist_desktop.commands import COMMANDS, execute, match, match_and_execute


def sent(record: list):
    def send(payload: str):
        record.append(payload)
        return True, ""
    return send


def failing(payload: str):
    return False, "ConnectError: simulator unreachable"


# -- asking about a command must never run it -----------------------------

@pytest.mark.parametrize("question", [
    "how do i start spraying",
    "how do i fold the boom",
    "what is the procedure to start spraying",
    "when should i fold the boom",
    "can you tell me how to unfold the boom",
    "should i stop spraying now",
    "why does the boom fold",
])
def test_questions_are_answered_not_executed(question):
    """The whole reason for the question-word guard: these all contain a
    command phrase, and substring matching would fire on every one."""
    assert match(question) is None


# -- but instructions must run --------------------------------------------

@pytest.mark.parametrize("order,expected", [
    ("start spraying", "start_spraying"),
    ("begin spraying", "start_spraying"),
    ("stop spraying", "stop_spraying"),
    ("fold the boom", "fold_boom"),
    ("unfold the boom", "unfold_boom"),
    ("please fold it", "fold_boom"),
    ("go ahead and unfold the boom", "unfold_boom"),
    ("just stop spraying", "stop_spraying"),
    ("unfold it for me", "unfold_boom"),
])
def test_instructions_are_executed(order, expected):
    assert match(order) == expected


def test_politeness_still_counts_as_an_order():
    """An operator with their hands full says 'could you fold the boom' and
    means it as an instruction."""
    assert match("could you fold the boom for me") == "fold_boom"


# -- the substring bug ----------------------------------------------------

@pytest.mark.parametrize("order", [
    "unfold boom",
    "unfold the boom",
    "please unfold the boom",
    "can you unfold it",
])
def test_unfold_is_never_mistaken_for_fold(order):
    """'fold boom' is a substring of 'unfold boom'. Declaring fold first made
    'unfold the boom' FOLD it — the machine did the opposite of what was
    asked. Longest phrase wins, so declaration order cannot matter."""
    assert match(order) == "unfold_boom"


# -- normalisation --------------------------------------------------------

@pytest.mark.parametrize("order", [
    "Start Spraying!",
    "  start   spraying  ",
    "START SPRAYING",
    "start spraying.",
])
def test_punctuation_and_case_do_not_matter(order):
    assert match(order) == "start_spraying"


def test_speech_to_text_phrasing_is_matched():
    """Transcripts arrive as full sentences with capitals and a full stop."""
    assert match("Unfold the boom.") == "unfold_boom"


# -- execution ------------------------------------------------------------

def test_executing_sends_the_payload_the_simulator_expects():
    record: list[str] = []
    result = execute("start_spraying", send=sent(record))
    assert result.ok is True
    assert record == ["Turn on Spraying"]
    assert "activated" in result.spoken.lower()


@pytest.mark.parametrize("name,payload", [
    ("start_spraying", "Turn on Spraying"),
    ("stop_spraying", "Turn off Spraying"),
    ("fold_boom", "Fold the Boom"),
    ("unfold_boom", "Unfold the boom"),
])
def test_payloads_match_the_original_scripts(name, payload):
    """The simulator matches on these strings; they are a wire contract."""
    record: list[str] = []
    execute(name, send=sent(record))
    assert record == [payload]


def test_an_unreachable_simulator_says_nothing_happened():
    """The operator must not be told the boom folded when it did not."""
    result = execute("fold_boom", send=failing)
    assert result.ok is False
    assert "not" in result.spoken.lower()
    assert "simulator unreachable" in result.detail


def test_match_and_execute_returns_none_for_a_question():
    record: list[str] = []
    assert match_and_execute("how do i fold the boom", send=sent(record)) is None
    assert record == [], "a question must not touch the machine"


def test_every_command_has_a_payload_and_something_to_say():
    for name, c in COMMANDS.items():
        assert c["payload"], name
        assert c["spoken"], name
        assert c["phrases"], name


# -- the polite-order versus polite-question distinction -------------------

@pytest.mark.parametrize("order", [
    "can you unfold the boom",
    "could you fold it",
    "would you stop spraying",
    "can you unfold it for me",
])
def test_polite_orders_run(order):
    """'can/could/would' open an instruction as often as a question, so they
    are not treated as question words."""
    assert match(order) is not None


@pytest.mark.parametrize("question", [
    "can you tell me how to unfold the boom",
    "could you explain how to fold the boom",
    "can you walk me through starting spraying",
    "would you show me how to stop spraying",
])
def test_polite_questions_do_not_run(question):
    """...which leaves these: questions that open with a polite-order word.
    They are separated by asking-phrases, not by the first word."""
    assert match(question) is None


# -- the simulator's address must be changeable ---------------------------

def test_the_trigger_url_follows_the_environment_at_send_time(monkeypatch):
    """It used to be read once, when the module was first imported. Since
    api.py imports commands before anything imports config -- and config is
    what loads .env -- the address in .env was captured too late and silently
    ignored. Changing the simulator's IP did nothing."""
    from assist_desktop import commands as c
    monkeypatch.setenv("ASSIST_TRIGGER_URL", "http://10.0.0.99:5000/trigger")
    assert c.trigger_url() == "http://10.0.0.99:5000/trigger"


def test_the_trigger_url_has_a_default(monkeypatch):
    from assist_desktop import commands as c
    monkeypatch.delenv("ASSIST_TRIGGER_URL", raising=False)
    assert c.trigger_url().startswith("http://")


def test_a_dotenv_trigger_url_reaches_the_command(monkeypatch, tmp_path):
    """The end-to-end version: what the operator actually edits is .env.

    config is imported before the variable is cleared, because importing it is
    what reads the real .env -- do it the other way round and this test only
    proves that the developer's own .env exists.
    """
    from assist_desktop import commands as c
    from assist_desktop.config import load_dotenv
    monkeypatch.delenv("ASSIST_TRIGGER_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("ASSIST_TRIGGER_URL=http://10.0.0.42:5000/trigger\n",
                   encoding="utf-8")
    load_dotenv(env)
    assert c.trigger_url() == "http://10.0.0.42:5000/trigger"


def test_a_real_environment_variable_beats_dotenv(monkeypatch, tmp_path):
    """.env fills gaps; it does not override what is already set. Otherwise
    run.ps1 -Trigger could not win over a stale file."""
    from assist_desktop import commands as c
    from assist_desktop.config import load_dotenv
    monkeypatch.setenv("ASSIST_TRIGGER_URL", "http://10.0.0.7:5000/trigger")
    env = tmp_path / ".env"
    env.write_text("ASSIST_TRIGGER_URL=http://10.0.0.42:5000/trigger\n",
                   encoding="utf-8")
    load_dotenv(env)
    assert c.trigger_url() == "http://10.0.0.7:5000/trigger"


# -- what the microphone actually produced ---------------------------------
#
# These are not hypothetical. Every phrase below was produced by Whisper on
# this machine, for an operator saying an ordinary command, and each one
# previously fell through to the manual: ten seconds of retrieval ending in
# "I don't know" while the sprayer did nothing.

@pytest.mark.parametrize("heard,expected", [
    ("Start spring.", "start_spraying"),          # logged 17:16:41, 17:17:18
    ("start spinning", "start_spraying"),         # recorded in stt.py
    ("start speaking", "start_spraying"),         # recorded in stt.py
    ("start solution bump", "start_spraying"),    # from the old tools.py
    ("start solution dump", "start_spraying"),
    ("start solution hump", "start_spraying"),
    ("stop spring", "stop_spraying"),
    ("stop spinning", "stop_spraying"),
])
def test_known_mishearings_still_reach_the_command(heard, expected):
    """stt.py already primes Whisper with the machine's vocabulary, and it is
    still wrong on these. Biasing the decoder is the first line of defence,
    not the only one."""
    assert match(heard) == expected


def test_a_misheard_question_is_still_a_question():
    """The mishearing table must not out-rank the question guard, or asking
    'how do i start spraying' starts the sprayer when it is misheard."""
    assert match("how do i start spring") is None
    assert match("can you tell me how to start spinning") is None


def test_mishearings_do_not_swallow_unrelated_speech():
    """'spring' has an ordinary meaning. Only the command-shaped phrases are
    repaired, never the bare word."""
    assert match("spring") is None
    assert match("check the spring tension") is None
    assert match("is it spring") is None


# -- one machine needs no listener -----------------------------------------
#
# window_listener.py is a Flask server whose entire job is to append the order
# to C:\simulator\voice_commands.json. When the app is on that same machine,
# the network hop, the server and its console window stand between a process
# and a file it can already write.

import json as _json

from assist_desktop import commands as c


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSIST_TRIGGER_MODE", "local")
    monkeypatch.setenv("ASSIST_COMMAND_FILE", str(tmp_path / "voice_commands.json"))
    c.is_this_machine.cache_clear()
    return tmp_path / "voice_commands.json"


def test_a_local_order_lands_in_the_file_the_simulator_reads(local):
    assert c.execute("start_spraying").ok is True
    entries = _json.loads(local.read_text(encoding="utf-8"))
    assert [e["command"] for e in entries] == ["Turn on Spraying"]


def test_a_local_order_is_shaped_exactly_like_the_listener_wrote_it(local):
    """The simulator side is unchanged and is still reading these keys."""
    c.execute("fold_boom")
    entry = _json.loads(local.read_text(encoding="utf-8"))[0]
    assert set(entry) == {"timestamp", "command", "received_at"}
    assert entry["command"] == "Fold the Boom"


def test_local_orders_append_rather_than_replace(local):
    local.write_text(_json.dumps([{"timestamp": "t", "command": "Turn on Spraying",
                                   "received_at": "r"}]), encoding="utf-8")
    c.execute("stop_spraying")
    entries = _json.loads(local.read_text(encoding="utf-8"))
    assert [e["command"] for e in entries] == ["Turn on Spraying", "Turn off Spraying"]


def test_a_missing_command_file_is_created(local):
    assert not local.exists()
    assert c.execute("fold_boom").ok is True
    assert local.is_file()


def test_a_corrupt_command_file_does_not_lose_the_order(local):
    local.write_text("{ half a write", encoding="utf-8")
    assert c.execute("fold_boom").ok is True
    assert _json.loads(local.read_text(encoding="utf-8"))[0]["command"] == "Fold the Boom"


def test_a_local_order_never_touches_the_network(local, monkeypatch):
    def explode(*a, **k):
        raise AssertionError("posted to a listener that does not need to exist")
    monkeypatch.setattr("httpx.post", explode)
    assert c.execute("start_spraying").ok is True


def test_an_unwritable_file_is_reported_not_claimed(local, monkeypatch):
    monkeypatch.setattr(c.Path, "write_text",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError("held")))
    result = c.execute("start_spraying")
    assert result.ok is False
    assert "not" in result.spoken.lower(), "must not claim the sprayer started"


# -- choosing the route ----------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5000/trigger",
    "http://localhost:5000/trigger",
])
def test_a_loopback_address_is_this_machine(url):
    c.is_this_machine.cache_clear()
    assert c.is_this_machine(url) is True


def test_this_machines_own_hostname_is_this_machine():
    import socket
    c.is_this_machine.cache_clear()
    assert c.is_this_machine(f"http://{socket.gethostname()}:5000/trigger") is True


def test_another_machine_is_not_this_machine():
    c.is_this_machine.cache_clear()
    assert c.is_this_machine("http://192.0.2.10:5000/trigger") is False


def test_an_address_that_will_not_resolve_stays_on_the_network(monkeypatch):
    """Guessing local would write a file nobody reads and report success."""
    c.is_this_machine.cache_clear()
    assert c.is_this_machine("http://no-such-host.invalid:5000/trigger") is False


def test_auto_sends_a_remote_address_over_the_network(monkeypatch):
    monkeypatch.delenv("ASSIST_TRIGGER_MODE", raising=False)
    monkeypatch.setenv("ASSIST_TRIGGER_URL", "http://192.0.2.10:5000/trigger")
    c.is_this_machine.cache_clear()
    assert c.delivery() == ("http", "http://192.0.2.10:5000/trigger")


def test_auto_writes_the_file_when_the_listener_would_be_on_this_machine(monkeypatch, tmp_path):
    monkeypatch.delenv("ASSIST_TRIGGER_MODE", raising=False)
    monkeypatch.setenv("ASSIST_TRIGGER_URL", "http://127.0.0.1:5000/trigger")
    monkeypatch.setenv("ASSIST_COMMAND_FILE", str(tmp_path / "voice_commands.json"))
    c.is_this_machine.cache_clear()
    assert c.delivery() == ("local", str(tmp_path / "voice_commands.json"))


def test_http_can_be_forced_even_on_one_machine(monkeypatch):
    """A listener already running locally stays usable — some setups want the
    server in the loop."""
    monkeypatch.setenv("ASSIST_TRIGGER_MODE", "http")
    monkeypatch.setenv("ASSIST_TRIGGER_URL", "http://127.0.0.1:5000/trigger")
    c.is_this_machine.cache_clear()
    assert c.delivery()[0] == "http"


def test_an_unknown_mode_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("ASSIST_TRIGGER_MODE", "sideways")
    assert c.trigger_mode() == "auto"
