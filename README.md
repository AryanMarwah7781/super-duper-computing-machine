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

## Screens

```
login  ──▶  home  ──┬──▶  chat        working RAG answers + this user's history
                    ├──▶  lesson      placeholder, navigation wired
                    └──▶  simulator   placeholder, navigation wired
```

Back and forward sit in the top bar and behave like a browser: navigating
somewhere new truncates the forward branch. Signing out clears the whole trail,
so the next person cannot walk back into the previous operator's session.

## Users and history

Sign in by typing a name, or pick one of the seeded profiles. There is no
password — one screen, one operator, and a name is only there to load the right
history.

`data/profiles.json` holds the roster and each person's questions. It seeds
three mock users with history on first run (Priya Sharma, Marcus Chen, Dan
Whitfield); delete the file to reseed. History is capped at 100 turns per
person.

Each recorded turn stores the **whole answer**, so re-opening a past question
re-renders exactly what was said at the time rather than re-asking a corpus that
may since have changed.

## Turn log

Every turn appends a line to `turns.jsonl`: the question, which chunk won, the
routing reason, every candidate with its rerank score, and timings. Retrieval
accuracy is still unmeasured, and this is the evidence base for fixing it.

## Phase status

- **Phase 1 — typed path.** Complete.
- **Phase 1b — welcome flow.** Complete: login, three-tile menu, back/forward,
  per-user chat history.
- **Phase 2 — voice.** Not started. Push-to-talk, local `faster-whisper` STT,
  streaming Piper TTS, all in this Python process. The history model already
  records `source: "voice"`, so the sidebar is ready for it.
- **Phase 3 — wake word.** Blocked. Neither `hey_deere.onnx` nor
  `hey_chris.onnx` exists — `wake_word/` holds only `hey_deere_config.yaml`,
  `train_hey_deere.ipynb` and `train_hey_deere.py`. `openwakeword` runs fine on
  Windows, so this needs a model trained (retarget the config to "hey chris"
  and run the notebook), not new architecture.

## Branding

The UI is deliberately brand-neutral. `https://www.ltts.com/media-kit` returns
HTTP 403 to automated fetches, so the logo, colours and typography could not be
retrieved and have **not** been guessed at. Drop the real assets in and the
theme variables in `ui/src/index.css` are where they belong.

## Running it, with the logs visible

```powershell
.\run.ps1                # check the board, then start — logs stream here
.\run.ps1 -Check         # preflight only, changes nothing
.\run.ps1 -Fake          # fixture replayer, no devkit needed
.\run.ps1 -Build         # rebuild the interface first
.\run.ps1 -Sensitive     # lower the wake-word threshold for this run
```

It runs in the **foreground**. Ctrl-C, or closing the window, stops everything —
nothing is detached.

In a second window:

```powershell
.\logs.ps1               # follow the application log, colour-coded
.\logs.ps1 -Voice        # only wake word, transcripts and audio
.\logs.ps1 -Board        # follow the board's manual service instead
```

`logs/app.log` survives restarts, so a problem from five minutes ago is still
there when you go looking.

### When "hey chris" does nothing

Run `.\logs.ps1 -Voice` and say it. The log distinguishes the cases:

| Line | Meaning |
|---|---|
| `microphone open, listening` | the audio path is up |
| `near miss: peak=0.52 ran=2` | heard, but short of the gate — lower it |
| `WAKE score=0.83 frames=4` | fired |
| *(nothing at all)* | no audio arriving — wrong device, or something else holds the microphone |

Tune without editing code:

```powershell
$env:ASSIST_WAKE_THRESHOLD = "0.45"   # default 0.6
$env:ASSIST_WAKE_FRAMES    = "2"      # default 3
```

`tools\voice_debug.py` shows the score live with sliders. It opens its own
microphone, so close the main app first — Windows will not share one.
