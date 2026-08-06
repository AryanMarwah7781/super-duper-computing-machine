# Running this on another machine

Everything the application needs is in this branch. You need a Windows machine
on the same network as the SiMa devkit, with a microphone.

## 1. Clone and set up

```powershell
git clone -b deploy https://github.com/AryanMarwah7781/super-duper-computing-machine.git assist
cd assist
.\setup.ps1 -Devkit http://<board-ip>:8090 -Trigger http://<simulator-ip>:5000/trigger
```

`setup.ps1` creates the virtual environment, installs everything, downloads the
speech voice (~60 MB), builds the interface, and writes both addresses to
`.env`. Re-running it is safe.

**Two machines, and they are easy to confuse.** The devkit answers questions
from the manual; the simulator receives spoken orders like "fold the boom".
Copy `.env.example` to `.env` and edit it, or pass the flags above. `run.ps1`
prints both addresses as it starts, so a wrong one shows before you speak.

| If this moves | Change | Symptom when wrong |
|---|---|---|
| the SiMa board | `ASSIST_DEVKIT_URL` | questions fail, offline banner |
| the simulator PC | `ASSIST_TRIGGER_URL` | "I could not reach the machine" |

Needs **Python 3.11+** and **Node 20+** on PATH. It checks and tells you if they
are missing.

## 2. Start it

```powershell
.\run.ps1
```

Foreground, logs streaming, Ctrl-C stops everything. In a second window:

```powershell
.\logs.ps1            # colour-coded
.\logs.ps1 -Voice     # only wake word, transcripts, audio
```

## 3. If the board is not running

`run.ps1` checks first and prints the exact command if it is down. On the board:

```bash
cd /media/nvme/ari_assist/v3
setsid nohup /media/nvme/ari_jd/venv/bin/python -m uvicorn service_v3:app \
  --host 0.0.0.0 --port 8090 --app-dir /media/nvme/ari_assist \
  > ../rag_v3.log 2>&1 &
```

To run with no devkit at all — fixtures instead of the real manual:

```powershell
.\run.ps1 -Fake
```

---

## What ships here, and what does not

| In the repo | |
|---|---|
| `assets/wakeword/` | the three wake models, 3.7 MB — the app cannot listen without them |
| `assist_desktop/` | the host: bridge, transport, audio, users |
| `ui/` | the interface (built by setup) |
| `service/service_v3.py` | the board service, for redeploying it |
| `tools/` | preflight, fixture replayer, voice debugger |

| Not in the repo | Why |
|---|---|
| Piper voice, 60 MB | freely downloadable; `setup.ps1` fetches it |
| the manual corpus, 1.4 GB | lives on the board |
| manual images, 33 MB | lives on the board |
| `.venv`, `node_modules`, `ui/dist` | built by setup |

**The board is assumed to be already set up.** This branch runs the *client*.
Standing a new board up from scratch is a separate job — the corpus, the index
and the models all have to be copied and the index repacked.

## Settings

All optional; `.env` or the environment.

| Variable | Default | |
|---|---|---|
| `ASSIST_DEVKIT_URL` | `http://192.168.94.180:8090` | the board that answers questions |
| `ASSIST_TRIGGER_URL` | `http://192.168.94.11:5000/trigger` | the simulator that spoken orders act on |
| `ASSIST_TIMEOUT_S` | `20` | give up on a question after this long |
| `ASSIST_TRIGGER_TIMEOUT_S` | `5` | give up on an order after this long |
| `ASSIST_WAKE_THRESHOLD` | `0.6` | how confident before "hey chris" fires |
| `ASSIST_WAKE_FRAMES` | `3` | consecutive 80 ms frames needed |
| `ASSIST_WAKE_DIR` | `assets/wakeword` | different wake models |
| `ASSIST_VOICE` | `assets/voice/...onnx` | a different speech voice |
| `ASSIST_BOARD_PASSWORD` | — | only for `preflight.py` and `logs.ps1 -Board` |

## Checking it before you trust it

```powershell
.\run.ps1 -Check                     # board, microphone, models — changes nothing
.\.venv\Scripts\python tools\preflight.py    # 21 checks across both machines
```

## When the wake word does nothing

```powershell
.\logs.ps1 -Voice
```

| Line | Meaning |
|---|---|
| `microphone open, listening` | the audio path is up |
| `near miss: peak=0.52 ran=2` | heard, but short of the gate — lower it |
| `WAKE score=0.83 frames=4` | fired |
| nothing at all | no audio — wrong device, or something else holds the microphone |

`.\run.ps1 -Sensitive` loosens the gate for one run. `tools\voice_debug.py`
shows the score live with sliders, but opens its own microphone, so close the
app first.

**Expect to tune this per machine.** The defaults came from measurement, but on
synthetic speech — a different voice, microphone and room will want different
numbers. The wake model also has a known weakness: it fires on "pressure" and
"christmas", which is why detection needs a sustained run rather than a single
high score. See `assist_desktop/audio/wake.py`.

## Tests

```powershell
.\.venv\Scripts\python -m pytest      # 97
cd ui; npx vitest run                 # 42
```

Three more run only against a live board:

```powershell
$env:ASSIST_DEVKIT_URL="http://<board-ip>:8090"
.\.venv\Scripts\python -m pytest tests\test_contract_real_devkit.py
```
