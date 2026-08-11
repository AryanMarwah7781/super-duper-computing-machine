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
.venv\Scripts\python -m pytest                       # host — 454 tests
cd ui; npx vitest run                                # ui — 87 tests
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
login  ──┬──▶  home  ──┬──▶  chat        working RAG answers + this user's history
         │             ├──▶  lesson      guided procedures, steps ticked by the machine
         │             └──▶  simulator   how to bring the simulator up, with video
         └──▶  admin              roster, lesson assignment, everyone's progress
```

A brand new operator does not land on the menu. Their first sign-in opens the
simulator walkthrough, because every tile on the menu assumes a machine that is
already running.

Back and forward sit in the top bar and behave like a browser: navigating
somewhere new truncates the forward branch. Signing out clears the whole trail,
so the next person cannot walk back into the previous operator's session.

## One app, several monitors

The rig has four panels and the app opens a window on two of them: the chatbot
on one, the lesson plan on another. The simulator gets a third, which this app
never draws on and only tidies. The fourth is left alone deliberately — that is
the desktop the demo is driven from.

Every window loads the same bundle with a different `?role=`, so there is one
UI, not three. Python decides which panel a role lands on; the UI decides what
a role shows. Events are broadcast to every window, because a turn that arrives
while somebody is reading the lesson plan still has to reach the lesson plan.

**Naming a monitor is the whole problem.** pywebview indexes its screens 0..n,
Windows names the devices DISPLAY1/2/3/5 with no DISPLAY4 at all, and the
Settings app shows a third set of numbers. None of them agree. So a panel is
named by where it is:

```powershell
.venv\Scripts\python tools\identify_screens.py     # prints a token on each panel
```

```
ASSIST_SCREEN_CHAT=1920x1080+1920+10
ASSIST_SCREEN_LESSON=1920x1080-1920+9
ASSIST_SCREEN_GAME=1920x1080+0+0
```

Geometry rather than an index, because an index reshuffles the moment a cable
moves and a layout pinned to indices then opens the lesson plan on top of the
game. Position identifies a panel and resolution is allowed to differ — a
monitor that changed mode is still the monitor on the left. A panel that is not
there at all falls back to a sensible screen and says so in the log rather than
refusing to start in front of a room.

Two roles resolving onto the same panel collapses to one window rather than
stacking two fullscreen windows where only one can be seen. One screen is a
legitimate way to demo this, which is also what `--single` and a plain browser
get.

```powershell
.venv\Scripts\python -m assist_desktop --windowed   # ordinary windows, for development
.venv\Scripts\python -m assist_desktop --single     # everything in one window
```

`--windowed` exists because a frameless fullscreen window on the wrong monitor
is genuinely hard to get rid of.

### The simulator's window

Left alone, Farming Simulator stretches across every monitor — it was found
5776 pixels wide, spanning the lesson plan's panel and the chatbot's with both
of ours underneath it. So it is moved onto its own panel and sized:

```
ASSIST_GAME_TITLE=Farming Simulator
ASSIST_GAME_SIZE=1600x900      # or `max` to fill the panel
```

Centred rather than pinned to a corner, and never given focus: moving the game
must not pull the operator away from the screen they are reading. The game is
never launched by this app, and it not running is the ordinary case rather than
an error.

**Exclusive fullscreen is the case this cannot fix.** A game that owns the
display mode either ignores the move or drops its swap chain, and it
re-minimises itself whenever it loses focus. Run it borderless windowed. The log
says which happened instead of claiming a move that did not take.

## The welcome

The screens stay black from the first painted frame — `background_color` on the
window, not CSS, because a window that paints white for two frames while the
bundle loads is exactly what "keep the screens black" was asking us not to do.

Then Chris rolls in and greets whoever signed in, and the two ways in are
offered: ask the sprayer something, or carry on with the lesson plan. Both
panels show the choice at once, so whichever monitor the operator is looking at
has the answer on it.

**"Welcome" and "Welcome back" are different sentences.** Being recognised is
the whole point of a returning greeting, and a machine that greets a ten-year
veteran as a stranger every morning is worse than one that says nothing. Which
one you get is decided before the profile is written — `login()` creates a
missing profile, and afterwards everybody looks like a returning operator.

The name is DOM text over a fixed recording rather than part of it. That is the
reason this is not a rendered video per operator: one recording greets
everybody, and the greeting is spoken by the voice that already reads answers.
Only the chat panel speaks, or the greeting arrives twice over.

A video that never fires `ended` — a missing file, a codec the webview will not
take, a blocked autoplay — cannot strand somebody on a black screen: a failsafe
timer ends the welcome regardless, and a click skips it.

### Who signed in

Sign-in happens somewhere else. There are two ways it reaches this app, and
neither has to be present — the app's own sign-in screen always works.

**The kiosk on the SiMa board.** An operator taps their ID card at the board
and it POSTs the sign-in here; when that session ends here, this app POSTs back
and the board returns to its card rail.

```
board 192.168.94.15:8080  --POST /login-->        this laptop :5000
this laptop               --POST /api/logout-->   board 192.168.94.15:8080
```

```json
{ "event": "operator_login", "new_user": false,
  "user": { "id": "priya-sharma", "name": "Priya Sharma" } }
```

Three things about that inbound message are load-bearing:

- **The 200 goes out before anything is done about it.** The board waits five
  seconds and then tells the person in front of it that the handoff failed.
  Signing somebody in and starting the voice takes longer than that cold, so
  the answer never waits for the work.
- **A repeat is not a second person.** The board re-sends the identical payload
  behind its "Try again" button. The same operator arriving twice is ignored
  rather than replaying the welcome over a session in progress.
- **`new_user` is the board's opinion of its own card roster**, not ours.
  "Welcome" or "Welcome back" is still decided by `data/assist.db`, which is
  the thing holding the history that makes the difference mean anything.

Both addresses live in `.env` (`ASSIST_KIOSK_URL`, `ASSIST_LOGIN_PORT`) and are
read per message, so moving the board needs no restart. The address of *this*
machine lives on the board, in `WELCOME_JD_URL`.

Windows Firewall has to let the board in, and a blocked inbound rule looks
exactly like a board that never sent anything. This laptop already carries an
"Edge Listener" rule that opens TCP 5000 to any program; on a machine that does
not, Windows prompts for Python on the first sign-in — Allow. To check:

```powershell
Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow |
  Where-Object { ($_ | Get-NetFirewallPortFilter).LocalPort -contains '5000' }
```

To prove the pipe before a demo, with both machines up:

```powershell
python tools/kiosk_check.py                        # both directions, read-only
python tools/kiosk_check.py --login "Priya Sharma" # a card tap, faked locally
python tools/kiosk_check.py --logout               # send the kiosk back to its rail
```

If port 5000 is already held — `window_listener.py` from the old stack is the
usual culprit — the app still starts, and the log says so in as many words.

**A file, for the older arrangement.** The other system writes the name to:

```
ASSIST_LOGIN_FILE=C:/simulator/current_user.json
{"name": "Priya Sharma"}
```

`username`, `user`, `operator`, `displayName` and a bare line of text all work
too — in the file and in the kiosk's JSON alike. Being generous costs a
dictionary lookup; being strict costs an operator standing in front of a black
screen while somebody reads the source to find out which key it wanted.

The file is polled, and a read landing mid-write is expected rather than
exceptional — there is no lock between the two processes. A half-written
`{"name": "Priya` is nobody, never a person called `{"name": "Priya`.

Until that file exists the app's own sign-in screen is the way in, so none of
this waits on another team being ready.

## Users and history

Sign in by typing a name, or pick one of the seeded profiles. There is no
password — one screen, one operator, and a name is only there to load the right
history.

`data/assist.db` — one SQLite file — holds the roster, each person's questions,
their lesson progress and which lessons they have been assigned. It seeds three
mock users with history on first run (Priya Sharma, Marcus Chen, Dan Whitfield);
delete the file to reseed. History is capped at 100 turns per person.

Each recorded turn stores the **whole answer**, so re-opening a past question
re-renders exactly what was said at the time rather than re-asking a corpus that
may since have changed.

The store used to be `data/profiles.json` plus `data/lesson_progress.json`. Both
are imported on the first run against a fresh database and then left untouched,
so upgrading loses nobody's history. Nothing writes to them any more.

```
users            id, name, created_at, last_seen, onboarded
history          one row per question, capped at 100 per person
lesson_state     per user and lesson: assigned, last_opened
lesson_progress  one row per completed step
```

Deleting an operator cascades through all four.

## Admin

The **Admin** button on the sign-in screen opens a username and password form —
`admin` / `admin` by default, checked in Python and overridable with
`ASSIST_ADMIN_USER` and `ASSIST_ADMIN_PASSWORD`. It is a shared trainer login,
not a role system: one shop floor, one person who sets up the training. No admin
call does anything until that sign-in has happened.

From there:

- **Add and remove operators.** Removing takes their history and every completed
  step with them, so it asks first and says what goes.
- **Assign lessons.** Every lesson is assigned to everyone by default —
  a lesson added to the catalog tomorrow must not be invisible to the people
  already on the roster. Switch one off and it disappears from that operator's
  lesson list, without touching progress they already made.
- **Read everyone's progress.** Per lesson, per operator, plus a cohort total.
  Withheld lessons do not count against anybody: someone held back from five
  lessons is not "behind".
- **Refresh progress.** One call re-reads the whole roster. Steps recorded while
  an operator is working the console land in the same database, so this is how
  the trainer sees them arrive.

## Getting started, for a new operator

Someone the admin added this morning has never started the simulator, so their
first sign-in opens the walkthrough rather than the menu: the recording, plus
the four steps beside it. Marked as seen once they say they are ready, and
reachable from the menu tile afterwards.

The recording stays where it was recorded and is streamed from there over
127.0.0.1 — a 220 MB screen capture has no business in the UI bundle or in git.
Point `ASSIST_STARTER_VIDEO` at a different file to change it.

That file's `moov` atom sits at the end, so the bundle server answers HTTP Range
requests: without `206` responses a player downloads all 220 MB before it can
show a frame, and seeking never works.

## Lessons

A lesson is a short procedure on the machine: press this, then that. Nobody is
asked to confirm they did it — the simulator's Connections App already writes
every signal that leaves the armrest to its `log.txt`, so the app tails that
file and the step completes when the machine says it happened. The Connections
App is only read from: never launched, never written to, never configured.

`data/lessons.json` is the whole content — categories, lessons, step copy, and
the signal rule behind each step. Console button photos live in
`ui/public/lesson-icons/`. Add a lesson by editing that one file.

```json
{"header": "Turn On Solution Pump",
 "body":   "Press the Solution Pump button…",
 "icon":   {"label": "SOLUTION PUMP", "image": "lesson-icons/solution-pump.jpeg"},
 "sync":   {"signals": ["PLT_AIC_SolutionPump"], "condition": "equals",
            "value": "1", "requires_step": null}}
```

| Condition | Completes when |
|---|---|
| `equals` | the signal reports exactly `value` |
| `nonzero` | the signal reports anything non-zero it can read as a number |
| `off_baseline` | the signal leaves a band of ±`value` around this session's resting median |
| `back_to_baseline` | …and comes back, but only after having left |

`requires_step` orders a lesson: *"move to Rate 2"* means nothing until Rate 1
was selected.

The hydro handle has no fixed neutral — two sessions on the same physical
handle rested at 174 and at 238 — so the baseline conditions measure it fresh
each time and deliberately never persist it.

Steps a lesson cannot see are still steps. The Farming Simulator lessons (drive,
harvest, fold the booms) send nothing to any log, so those tick off by hand, and
every step carries a **Mark done** button for a signal the log missed.

Progress lives in `data/assist.db`, per operator, and survives a restart. Set
`ASSIST_SIM_LOG` to point at a Connections App log somewhere other than the path
in the catalog.

## Spoken orders, and the listener you may not need

"Fold the boom" acts; "how do I fold the boom" gets answered. The acting half
ends up in `C:\simulator\voice_commands.json`, which the simulator reads.

How it gets there depends on where the simulator is:

| `ASSIST_TRIGGER_MODE` | What happens |
|---|---|
| `auto` (default) | Writes the file directly when `ASSIST_TRIGGER_URL` points at this machine; posts over HTTP when it does not |
| `local` | Always writes the file |
| `http` | Always posts, even on one machine |

`window_listener.py` is a Flask server whose entire job is to receive that POST
and append it to the file. Across a network it is necessary. On one machine it
is a socket and a second console window standing between a process and a file it
can already write — so `auto` skips it, and nothing needs to be started by hand.

```powershell
.\run.ps1 -Local          # simulator on this machine, no listener
```

The written entry is byte-for-byte what the listener would have produced — same
keys, same `received_at` stamp, same whole-array rewrite — because the simulator
side is unchanged and still reading it. `ASSIST_COMMAND_FILE` moves the file.

An address that will not resolve is treated as remote on purpose: writing a
local file nobody reads and reporting success is worse than a failed POST the
operator hears about.

## Answers already given

The board takes about six seconds to retrieve and fifteen to a hundred to
synthesise. A question asked twice should not be searched twice, so answers are
kept in `data/assist.db` and served from there.

```powershell
.venv\Scripts\python tools\warm_cache.py            # answer the common ones now
.venv\Scripts\python tools\warm_cache.py --from-log # what has actually been asked here
.venv\Scripts\python tools\warm_cache.py --list     # what is cached, with hit counts
.venv\Scripts\python tools\warm_cache.py --clear    # forget it all
```

The list lives in `data/common_questions.json`, generated from `QUESTIONS` in
the repo root — 30 questions hand-graded against the v4 index. Anything asked
live is cached too, so the list only matters for questions nobody has asked yet.

**Keyed by the pipeline, not just the question.** v3 and v4 answer the same
question differently, and switching between them is a one-line edit in `.env`;
an answer remembered from one is never served as though it came from the other.

**What is never kept:** commands, which must act on the machine every time;
Chris, because a conversation that repeats itself word for word is not one; and
`oos`, which is the corpus failing to match today and may match tomorrow.

Matching drops case, punctuation and articles, so `How do I fill the solution
tank?` and `how do i fill solution tank` share an answer. Nothing cleverer:
`how to start spraying` and `how do i start spraying` stay separate questions,
because a wrong hit serves the wrong procedure.

A hit is ready in about six milliseconds, which reads as though nothing
happened. `ASSIST_RECALL_DELAY_S` (default 2.5 s) holds it back to the pace of
a real answer; set it to 0 to hand answers back as fast as they are found. The
reported timing is the wait that actually happened — the original search time
is kept separately as `first_answered_ms`, and never claimed as this turn's.

The client cannot tell when the corpus on the board changes. **Run `--clear`
after any re-index.**

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

### Driving it from another machine

```powershell
# elevated, once, on the rig
.	ools\enable-ssh.ps1 -PublicKey "<the other laptop's id_ed25519.pub line>"
.	ools\enable-ssh.ps1 -Undo          # turn it off again
```

Starts the OpenSSH server, opens port 22 on every firewall profile (this Wi-Fi
is classified Public, where a default-profile rule would be enabled and still
not apply), and installs the key in
`C:\ProgramData\sshdministrators_authorized_keys` — which is where Windows
OpenSSH looks for a member of Administrators, rather than `~/.ssh`.

Key auth rather than a password because the rig's account has none, and Windows
OpenSSH refuses password logins for blank-password accounts.

SSH gives a terminal: start and stop the app, follow `logs/app.log`, run the
tests. The window itself still opens on the rig's screen — for that you want
Remote Desktop, which locks the rig's console and redirects its audio, so the
microphone stops working there while you are connected.

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
$env:ASSIST_WAKE_THRESHOLD = "0.7"    # default 0.8
$env:ASSIST_WAKE_FRAMES    = "2"      # default 3
```

`run.ps1` clears both unless you pass `-Sensitive`, because an environment
variable outlives the run that set it: one `-Sensitive` run used to gate every
later session in that window at 0.45, including ones started without the flag.
Put them in `.env` to make them stick.

The default is **3 frames above 0.8**, and both halves matter. 0.8 is the line
the wake models were measured at: "hey chris" holds 3-6 frames above it, and
the worst impostors -- "the pressure is fine", "christmas is coming" -- hold 2.
Gate lower and that separation is gone; at 0.6 an impostor holds five or six
frames and fires. That is an app that wakes on "start spraying" and keeps
listening for the rest of the session.

`tools\voice_debug.py` shows the score live with sliders. It opens its own
microphone, so close the main app first — Windows will not share one.

### When the app disappears on switching microphone

No traceback, no error line — the log simply stops and the app is gone. That is
a native crash, and Windows recorded it even though Python did not:

```powershell
Get-WinEvent -FilterHashtable @{LogName='Application'} -MaxEvents 20 |
  Where-Object { $_.Id -eq 1000 } | Select-Object TimeCreated, Message
```

Selecting a Bluetooth headset produced `libportaudio64bit.dll`, exception
`0xc0000005`, then `ntdll.dll` `0xc0000374` — an access violation followed by
heap corruption. PortAudio being used after it was freed.

Three things guard that path now: playback counts as a live stream (an output
stream was invisible to the guard that keeps PortAudio from being
re-initialised), opening a stream and re-initialising it are serialised, and a
device switch reuses the listing the picker already took instead of re-scanning
mid-switch.

A Bluetooth headset changing profile is still the hardest case, because Windows
tears the endpoints down underneath the process. The reliable way onto AirPods
is to make them the default input in Windows and then start the app, rather
than switching to them from inside it.

### When it starts listening by itself

Symptom: it answers, and immediately wakes again — sometimes cutting its own
answer off — and the history fills with transcripts nobody said ("Okay.",
"Next.", half a sentence from the room).

The microphone is hearing the speakers. Playback runs on its own thread, so
`say()` returns the moment it starts; the wake gate used to reopen right then,
with the answer still coming out of the speakers a foot away. The gate now stays
shut for as long as the app is talking, plus a short tail for the room:

```powershell
$env:ASSIST_ECHO_TAIL_S = "0.6"   # how long after the last word (default 0.6)
$env:ASSIST_BARGE_IN    = "1"     # keep the gate live while talking, so
                                  # "hey chris" can interrupt an answer.
                                  # Headsets and directional microphones only —
                                  # on open speakers it wakes itself again.
```

If a wake still fires within a second and a half of the app finishing, the log
says so outright:

```
WARNING  audio  wake fired 0.4s after the app stopped talking — if this
                repeats, the microphone is hearing the speakers
```

That means the tail is too short for the room, or the speakers are too close to
the microphone.
