# DEERE ASSIST — desktop client

A desktop client for the v4 RAG pipeline running on the SiMa Modalix devkit.

Python owns the process, the window, the network and all state. The UI is React
+ shadcn served from a local HTTP server on `127.0.0.1`; it never calls the
devkit directly. Node is a build-time tool only.

Design: `../docs/superpowers/specs/2026-08-05-assist-desktop-design.md`
Plan: `../docs/superpowers/plans/2026-08-05-assist-desktop-phase1.md`

## Run against the fake devkit (no hardware needed)

```powershell
# terminal 1 — replays fixtures on port 8100
.venv\Scripts\python tools\fake_devkit.py

# terminal 2
cd ui; npm run build; cd ..
.venv\Scripts\python -m assist_desktop --devkit http://127.0.0.1:8100
```

## Run against the real devkit

Start the service on the devkit first:

```bash
ssh <devkit> 'cd /media/nvme/ari_jd && \
  venv/bin/python -m uvicorn v4.service:app --host 0.0.0.0 --port 8090'
```

Nothing else may hold the milvus index while it runs — a stray `ask.py` will
make startup fail with `DataDirLockedError`. `/health` reports `ready: false`
for roughly 26 seconds while the index loads, then `ready: true`.

```powershell
.venv\Scripts\python -m assist_desktop --devkit http://192.168.1.128:8090
```

## Develop the UI with hot reload

```powershell
cd ui; npm run dev                                   # terminal 1
.venv\Scripts\python -m assist_desktop --dev --devkit http://127.0.0.1:8100
```

## Tests

```powershell
.venv\Scripts\python -m pytest                       # host — 39 tests
cd ui; npx vitest run                                # ui — 23 tests
```

The contract test against the real devkit is skipped unless you point it at one:

```powershell
$env:ASSIST_DEVKIT_URL="http://192.168.1.128:8090"
.venv\Scripts\python -m pytest tests/test_contract_real_devkit.py
```

## Deploying the service

`service/service.py` is deployed to the devkit as `/media/nvme/ari_jd/v4/service.py`:

```bash
scp service/service.py <devkit>:/media/nvme/ari_jd/v4/service.py
```

Verify `IMAGES_ROOT` at the top of that file points at the directory containing
the `image_path` values in `v4/data/chunks.json` before relying on photos.

## Turn log

Every turn appends a line to `turns.jsonl`: the question, which chunk won, the
routing reason, every candidate with its rerank score, and timings. Retrieval
accuracy is still unmeasured, and this is the evidence base for fixing it.

## Phase status

- **Phase 1 — typed path.** Complete.
- **Phase 2 — voice.** Not started. Push-to-talk, local `faster-whisper` STT,
  streaming Piper TTS, all in this Python process.
- **Phase 3 — wake word.** Blocked: `hey_deere.onnx` does not exist yet.
