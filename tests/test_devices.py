"""Microphone identity, and the two ways it went wrong.

Both bugs here were found on 2026-08-06 by plugging a Yeti GX into a running
app. Neither raised an error; the app simply carried on being wrong, which is
why they are pinned here.
"""
from __future__ import annotations

import sys
import types

import pytest

from assist_desktop.audio import mic as micmod


class FakePortAudio:
    """Stands in for sounddevice, including its refresh-on-reinit behaviour.

    PortAudio snapshots the device list when it initialises and serves that
    snapshot until it is re-initialised. `pending` is what Windows would
    report after the next re-init -- i.e. a microphone plugged in since.
    """

    def __init__(self, devices, pending=None, default=0):
        self._devices = list(devices)
        self.pending = list(pending) if pending is not None else None
        self.default = default
        self.reinits = 0

    # -- the sounddevice surface mic.py uses --
    def query_devices(self):
        return list(self._devices)

    def _terminate(self):
        pass

    def _initialize(self):
        self.reinits += 1
        if self.pending is not None:
            self._devices = list(self.pending)
            self.pending = None

    class _Default:
        device = (0, 1)

    @property
    def default_device(self):
        return self._Default


def install(monkeypatch, fake):
    module = types.SimpleNamespace(
        query_devices=fake.query_devices,
        _terminate=fake._terminate,
        _initialize=fake._initialize,
        default=types.SimpleNamespace(device=(fake.default, 1)),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", module)
    return fake


def dev(name, inputs=1):
    return {"name": name, "max_input_channels": inputs, "max_output_channels": 0}


REALTEK = dev("Microphone Array (Realtek(R) Audio)", 2)
YETI = dev("Microphone (Yeti GX)")
SPEAKERS = {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2}


# -- a microphone plugged in while the app runs must appear ----------------

def test_a_microphone_plugged_in_after_startup_is_listed(monkeypatch):
    """The Yeti GX bug. PortAudio hands out the device list it captured at
    startup, so the picker kept showing a world without the new microphone
    however many times it was reopened. Only a restart helped."""
    fake = install(monkeypatch, FakePortAudio([REALTEK], pending=[REALTEK, YETI]))
    names = [d["name"] for d in micmod.list_input_devices()]
    assert "Microphone (Yeti GX)" in names, "must ask Windows again, not use the snapshot"
    assert fake.reinits == 1


def test_listing_devices_does_not_invent_outputs(monkeypatch):
    install(monkeypatch, FakePortAudio([REALTEK, SPEAKERS, YETI]))
    names = [d["name"] for d in micmod.list_input_devices()]
    assert names == ["Microphone Array (Realtek(R) Audio)", "Microphone (Yeti GX)"]


def test_a_missing_sounddevice_is_not_an_error(monkeypatch):
    """No audio stack must degrade to 'no microphones', not a crash."""
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    assert micmod.list_input_devices() == []


# -- indices shift; names do not -------------------------------------------

def test_a_device_is_found_again_after_indices_shift(monkeypatch):
    """Plugging the Yeti in pushed the Realtek array from index 0 to 1. A
    stored index would now silently select a different microphone."""
    install(monkeypatch, FakePortAudio([YETI, REALTEK]))
    assert micmod.resolve_device(
        name="Microphone Array (Realtek(R) Audio)", index=0) == 1


def test_the_name_is_trusted_over_a_stale_index(monkeypatch):
    install(monkeypatch, FakePortAudio([YETI, REALTEK]))
    resolved = micmod.resolve_device(name="Microphone (Yeti GX)", index=1)
    assert resolved == 0, "the name wins; the index was captured before the shift"


def test_an_unplugged_device_falls_back_to_the_default(monkeypatch):
    """Unplug the Yeti and its index may now be another microphone entirely.
    Recording from whatever happens to be there is worse than the default."""
    install(monkeypatch, FakePortAudio([REALTEK]))
    assert micmod.resolve_device(name="Microphone (Yeti GX)", index=5) is None


def test_an_index_still_works_when_no_name_is_known(monkeypatch):
    """Old callers, and anyone who picked before names were recorded."""
    install(monkeypatch, FakePortAudio([YETI, REALTEK]))
    assert micmod.resolve_device(name=None, index=1) == 1


def test_no_name_and_no_index_means_the_system_default(monkeypatch):
    install(monkeypatch, FakePortAudio([YETI, REALTEK]))
    assert micmod.resolve_device(name=None, index=None) is None


# -- the microphone re-resolves at the moment it opens ---------------------

def test_the_microphone_re_resolves_its_device_when_it_opens(monkeypatch):
    """Between choosing a microphone and opening the stream, another device
    can be plugged in and shift every index. The name is re-checked at open."""
    install(monkeypatch, FakePortAudio([REALTEK, YETI]))
    m = micmod.Microphone(device=1, device_name="Microphone (Yeti GX)")

    install(monkeypatch, FakePortAudio([YETI, REALTEK]))
    assert m.resolved_device() == 0


def test_a_microphone_without_a_name_keeps_its_index(monkeypatch):
    install(monkeypatch, FakePortAudio([REALTEK, YETI]))
    assert micmod.Microphone(device=1).resolved_device() == 1


# -- refreshing must never leave the audio stack switched off --------------

class BreakableFake(FakePortAudio):
    """A PortAudio whose re-init can fail, and which refuses to answer while
    it is terminated -- exactly what the real one does."""

    def __init__(self, devices, fail_initialize=False):
        super().__init__(devices)
        self.fail_initialize = fail_initialize
        self.live = True

    def _terminate(self):
        self.live = False

    def _initialize(self):
        self.reinits += 1
        if self.fail_initialize:
            raise RuntimeError("cannot initialise")
        self.live = True

    def query_devices(self):
        if not self.live:
            raise RuntimeError("PortAudio not initialized [PaErrorCode -10000]")
        return list(self._devices)


def test_a_failed_reinit_does_not_kill_device_listing(monkeypatch):
    """Found by opening the picker on 2026-08-06. _terminate() succeeded,
    _initialize() failed, and one try/except around both left PortAudio off
    for the rest of the session -- every later query raised -10000."""
    fake = BreakableFake([REALTEK, YETI], fail_initialize=True)
    install(monkeypatch, fake)
    micmod.list_input_devices()          # trips the failure
    fake.fail_initialize = False
    names = [d["name"] for d in micmod.list_input_devices()]
    assert names, "the audio stack must recover, not stay dead"


def test_listing_devices_never_terminates_a_live_stream(monkeypatch):
    """PortAudio must not be torn down underneath an open stream. The
    microphone stays open while the picker is read."""
    fake = install(monkeypatch, FakePortAudio([REALTEK, YETI]))
    micmod.note_stream_opened()
    try:
        micmod.list_input_devices()
        assert fake.reinits == 0, "must not re-init while a stream is open"
    finally:
        micmod.note_stream_closed()


def test_the_refresh_resumes_once_the_stream_closes(monkeypatch):
    fake = install(monkeypatch, FakePortAudio([REALTEK], pending=[REALTEK, YETI]))
    micmod.note_stream_opened()
    micmod.list_input_devices()
    micmod.note_stream_closed()
    names = [d["name"] for d in micmod.list_input_devices()]
    assert "Microphone (Yeti GX)" in names
