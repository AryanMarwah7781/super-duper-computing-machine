"""Audio runs here, in the desktop host.

The devkit has no working sound hardware — `arecord -l` finds no soundcards and
PulseAudio sits on a null sink — so the microphone is on this machine and the
whole voice path follows it. This is the reason the host is Python rather than
Node or Rust: openwakeword, faster-whisper and sounddevice are all pip installs
that run in-process, with no sidecar to bundle, launch or supervise.
"""
