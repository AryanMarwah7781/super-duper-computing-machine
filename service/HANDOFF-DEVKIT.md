# Devkit handoff — stand up the v4 RAG service

**For the Claude session running ON the SiMa Modalix board.**
Written 2026-08-05. Everything below marked *verified* was checked over SSH
from the Windows host on that date.

---

## 1. Your job in one sentence

Get `service.py` running on this board so it answers `POST /ask` from the v4
RAG pipeline, and a desktop client on the LAN can reach it at
`http://192.168.94.180:8090`.

The client half is **already built, tested and working** — it just has nothing
real to talk to. It currently runs against a fixture replayer. Your job is to
replace the fixtures with the actual corpus.

---

## 2. State of this board — verified, not assumed

| Fact | Value |
|---|---|
| Host | `192.168.94.180`, user `sima` |
| OS | eLxr 12 (aria), Linux 6.18.3-modalix, **aarch64** |
| Project root | `/media/nvme/ari_jd` — exists |
| Free space | 180 GB on `/media/nvme` — plenty |
| venv | `/media/nvme/ari_jd/venv`, **Python 3.11.2** |
| Nothing on :8080, :8090, :5000, :8081 | no service is running |

**The venv already has every dependency you need — do not reinstall:**

```
fastapi 0.136.1   uvicorn 0.46.0    pydantic 2.13.4
pymilvus 2.5.18   bm25s 0.3.8       sentence-transformers 5.4.1
torch 2.11.0      transformers 5.8.0
```

### The blocker you must solve first

**`/media/nvme/ari_jd/v4` DOES NOT EXIST on this board. Neither does
`jd-chatbot-v3`.** Verified by listing the directory.

This board is at the **v2.2 era**. It has `jd-chatbot-v2.0`, `jd-chatbot-v2.2`,
`rag.py`, `rag_og.py`, `server.py`. All the v3 and v4 work lives **only on the
Windows host**, under `C:\Users\user\Desktop\jd\archive\`.

So nothing here can run until the code and data are copied over. See §3.

---

## 3. What has to be copied here, and from where

Everything is on the Windows host at `192.168.94.x` under
`C:\Users\user\Desktop\jd\`.

| Copy this (Windows) | To here (board) | Size |
|---|---|---|
| `archive\v4\` | `/media/nvme/ari_jd/v4/` | 75 MB |
| `archive\jd-chatbot-v3\bge-large-local\` | `/media/nvme/ari_jd/jd-chatbot-v3/bge-large-local/` | 1.28 GB |
| `archive\jd-chatbot-v3\cross-encoder-fast-local\` | `/media/nvme/ari_jd/jd-chatbot-v3/cross-encoder-fast-local/` | 88 MB |
| `assist\service\service.py` | `/media/nvme/ari_jd/v4/service.py` | 5 KB |

Total ≈ **1.44 GB**. From the Windows side:

```powershell
$B = "sima@192.168.94.180:/media/nvme/ari_jd"
scp -r C:\Users\user\Desktop\jd\archive\v4 "${B}/v4"
ssh sima@192.168.94.180 "mkdir -p /media/nvme/ari_jd/jd-chatbot-v3"
scp -r C:\Users\user\Desktop\jd\archive\jd-chatbot-v3\bge-large-local "${B}/jd-chatbot-v3/bge-large-local"
scp -r C:\Users\user\Desktop\jd\archive\jd-chatbot-v3\cross-encoder-fast-local "${B}/jd-chatbot-v3/cross-encoder-fast-local"
scp C:\Users\user\Desktop\jd\assist\service\service.py "${B}/v4/service.py"
```

**Why those two model directories specifically:** `v4/assist/retrieve/search.py`
hardcodes them —

```python
MODEL    = f"{ROOT}/jd-chatbot-v3/bge-large-local"
RERANKER = f"{ROOT}/jd-chatbot-v3/cross-encoder-fast-local"
```

Do **not** copy the whole of `jd-chatbot-v3` — it also contains
`bge-reranker-local`, 2.2 GB that v4 never loads.

### Verify the copy landed

```bash
ls /media/nvme/ari_jd/v4/assist/retrieve/search.py          # the pipeline
ls /media/nvme/ari_jd/v4/data/chunks.json                   # ~4 MB corpus
ls /media/nvme/ari_jd/v4/data/index/                        # bm25/ + jd_manuals_v4.db/
ls /media/nvme/ari_jd/jd-chatbot-v3/bge-large-local/        # embedder
ls /media/nvme/ari_jd/jd-chatbot-v3/cross-encoder-fast-local/
```

### Prove the pipeline works before wrapping it in HTTP

```bash
cd /media/nvme/ari_jd
venv/bin/python v4/ask.py --debug "how do i fill the solution tank"
```

Expect a rendered procedure and roughly **26s cold / 5s warm**. If this fails,
stop — the service cannot work either, and you will debug it far more easily
here than through HTTP.

---

## 4. The endpoint contract

The client is already written against this. **Do not change the shapes** — if
you must, say so explicitly, because the Windows-side wire models and the
display parser both depend on them.

### `GET /ready`

Liveness only. Answers *before* the index has loaded. Used to tell "still
warming" apart from "host is down".

```json
{ "alive": true }
```

### `GET /health`

Polled every 3 seconds by the client; it drives the connection indicator.

```json
{
  "ready": true,
  "error": null,
  "render_version": "v4.0",
  "corpus_hash": "7f3a9c21",
  "chunk_count": 2995,
  "uptime_s": 128
}
```

- `ready` is **false** for ~26s while the index loads. The client shows
  "warming up" and disables input. It must not be `true` before `search()` can
  actually serve.
- `error` carries the warm-up failure verbatim when there is one — most likely
  `DataDirLockedError` (see §5).
- `render_version` **must be `"v4.0"`**. The client warns on a mismatch.

### `POST /ask`

Request:

```json
{ "query": "how do i fill the solution tank", "top_k": 5 }
```

Response — this is the whole contract:

```json
{
  "plan":   { "kind": "cached", "chunk_ids": [412],
              "reason": "top=procedure score=8.14" },
  "answer": {
    "display_text":    "**WARNING:** ...\nStep 1: ...\n[PHOTO: Fill cap]\n\n_Manual page 472._",
    "spoken_segments": ["Warning. ...", "Step 1. ...", "See page 472."],
    "safety":    [ { "level": "WARNING", "text": "...",
                     "source_chunk_id": 88, "page": 472 } ],
    "citations": [ { "page": 472, "procedure_name": "Fill Solution Tank",
                     "chunk_id": 412, "method": "image" } ],
    "images":    [ { "id_code": "N136007—UN—05MAR18",
                     "image_path": "images/fill_cap.png",
                     "caption": "Fill cap location", "step_num": 2 } ],
    "render_version": "v4.0",
    "source_hash":    "a1b2c3d4e5f60718"
  },
  "candidates": [ { "chunk_id": 412, "score": 8.14, "content_type": "procedure",
                    "procedure_name": "Fill Solution Tank", "page": 472 } ],
  "timing": { "search_ms": 4510, "render_ms": 3, "total_ms": 4520 }
}
```

Rules the client depends on:

1. **`plan.kind` is one of `cached` | `synthesize` | `oos`.** `cached` renders
   plainly; `synthesize` is badged "excerpt, not a composed answer"; `oos`
   renders "I don't know".
2. **When `plan.kind == "oos"`, `answer` MUST be `null`.** Never send a
   best-guess chunk with an oos plan. A confidently wrong answer read to
   someone standing next to a machine is the worst failure this product has.
3. **`candidates` is always present**, even for `oos`, with every rerank score.
   The client logs it to `turns.jsonl`; it is the evidence base for the
   unmeasured retrieval accuracy problem. Do not trim it.
4. **`timing` keys are exactly `search_ms`, `render_ms`, `total_ms`.** Not
   `retrieval_ms`/`rerank_ms` — `search()` does BM25, vector, RRF and rerank
   behind one call and does not expose the split, so reporting them separately
   would be fabricated.
5. **`display_text` grammar is fixed.** The client parses exactly these line
   forms and nothing else:

   | Line | Meaning |
   |---|---|
   | `**LEVEL:** text` | safety banner (DANGER/WARNING/CAUTION/NOTE/IMPORTANT) |
   | `Step N: text` | numbered step |
   | `[PHOTO: caption]` | image whose **`caption`** matches — matched on caption, then `id_code` |
   | `cell \| cell \| cell` | table row |
   | `_Manual page N._` | citation footer |
   | `**name**` | heading |

   This is whatever `render.py` already emits. Do not post-process it.
6. **Safety renders above step 1.** A structural guarantee from `render.py`,
   asserted on both sides. Do not reorder.
7. Return **503** when `ready` is false. Never answer from a half-loaded index.

### `GET /images/{path}`

Serves manual images. The client's local server proxies and disk-caches these,
so `<img>` tags only ever address `127.0.0.1`.

`IMAGES_ROOT` at the top of `service.py` currently reads:

```python
IMAGES_ROOT = Path("/media/nvme/ari_jd/jd-chatbot-v3/static")
```

**This is a guess and needs verifying.** Find where the `image_path` values in
`v4/data/chunks.json` actually resolve, and correct it:

```bash
venv/bin/python - <<'PY'
import json
c = json.load(open('/media/nvme/ari_jd/v4/data/chunks.json'))
paths = {i['image_path'] for ch in c for s in (ch.get('steps') or [])
         for i in (s.get('images') or []) if i.get('image_path')}
print(len(paths), 'distinct image paths; samples:')
for p in list(paths)[:5]: print('  ', p)
PY
find /media/nvme/ari_jd -name "*.png" -path "*static*" 2>/dev/null | head -5
```

Path traversal is already refused (`/images/../../etc/passwd` → 404); there is a
test for it. Keep that.

---

## 5. Two operational constraints that will bite you

**Milvus-lite is single-process.** The service holds an exclusive lock on
`v4/data/index/jd_manuals_v4.db` for its whole lifetime. Nothing else may search
while it runs — including `ask.py`. If startup reports `DataDirLockedError`, a
stray `ask.py` is holding it:

```bash
pgrep -af "ask.py|service"       # find it
```

Startup surfaces this through `/health.error` rather than dying silently, and
`/ask` returns 503 with the same text, so the client can say something useful.

**Cold load is ~26s.** It happens on a background thread at startup so the port
answers immediately. Queries are then **serialised behind a lock** — one at a
time. This is a single-operator appliance; concurrent milvus-lite access buys
nothing and risks the store. Leave the lock in.

---

## 6. Run it

```bash
cd /media/nvme/ari_jd
venv/bin/python -m uvicorn v4.service:app --host 0.0.0.0 --port 8090
```

`--host 0.0.0.0` matters — the client is on another machine. Bind to localhost
and it will look like the board is down.

Then, from the board:

```bash
curl -s localhost:8090/health            # ready:false for ~26s, then true
curl -s localhost:8090/ask -H 'content-type: application/json' \
     -d '{"query":"how do i fill the solution tank"}' | head -c 800
```

If the board has a firewall, open the port. Verify from the Windows host:

```powershell
curl http://192.168.94.180:8090/health
```

### Then hand back

Tell the Windows side it is up. They run:

```powershell
$env:ASSIST_DEVKIT_URL="http://192.168.94.180:8090"
.venv\Scripts\python -m pytest tests\test_contract_real_devkit.py   # 3 tests, currently skipped
.venv\Scripts\python -m assist_desktop --devkit http://192.168.94.180:8090
```

Those three tests are the acceptance gate. They are the only thing that can
catch server/client drift, because the fixtures are what the client already
believes.

---

## 7. What is already proven, so you don't redo it

`service.py` has **never run**, but its logic is covered by nine tests on the
Windows side (`tests/test_service_contract.py`), which import the real module
against stubbed v4 modules. Already verified:

- `/health` shape, and `render_version == "v4.0"`
- `/ask` output deserialises into the client's wire models
- `candidates` carry rerank scores; `timing` keys are the three above
- `oos` returns a **null** answer
- 503 before the index is loaded
- a warm-up failure is reported verbatim, not swallowed
- an unreadable `chunks.json` does **not** brick an otherwise loaded index
  (the corpus hash is cosmetic — this was a real bug, found and fixed)
- image path traversal is refused

**What those tests cannot tell you:** whether retrieval actually works, whether
the models load on aarch64, whether `IMAGES_ROOT` is right, or how slow it is.
That is exactly your job.

---

## 8. Known problem you will meet, and should not try to fix here

**Retrieval accuracy is unmeasured, and the failure mode is known and bad.**
From `v4/HANDOFF.md`: "how do i start spraying" resolves to one of three
different chunks and **flips on a question mark**. v4 dropped v3's 14 corrective
regexes and never built the replacement. This is a v4 corpus/index problem, not
a service problem — do not paper over it in `service.py`.

The client already logs every turn's `plan.reason` and full candidate list to
`turns.jsonl` precisely so this becomes measurable. Leave `candidates` intact
and that work gets an evidence base.

---

## 9. Out of scope

- **LLiMa / the `synthesize` path.** Nothing has been on `:5000` since Jul 2 —
  confirmed still closed today. Procedures and tables need no LLM at all;
  passage questions fall back to the retrieved passage verbatim, badged in the
  UI. If LLiMa returns, `synthesize` slots in behind the existing `plan.kind`
  without the client changing.
- **Voice.** Runs entirely on the Windows client (`faster-whisper` + Piper
  in-process). The board has no working sound hardware and does not need any.
- **Wake word.** Neither `hey_deere.onnx` nor `hey_chris.onnx` exists — only
  `wake_word/train_hey_deere.py` and its notebook. Needs a Colab training run,
  not board work.
- **`server.py`, face auth, tool commands.** The old v2.2 stack. Leave it alone;
  `service.py` is deliberately separate so v4 stays uncoupled from it.
