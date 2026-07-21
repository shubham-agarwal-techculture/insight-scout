# Insight Scout

A Python Cursor SDK project that runs a local agent to research **five highly technical, unexpectedly astonishing insights** about new technologies — then streams them into a web UI you can follow live.

Each insight must feel mind-blowing in a **positive, unexpected** way, and must be cross-checked against **at least two independent legitimate sources**.

---

## What it does

1. Launches a **local Cursor agent** (`composer-2.5`) via the Python SDK (`cursor-sdk`).
2. Instructs the agent to search widely, prefer primary sources, and discard single-source or rumor-only claims.
3. Streams progress and assistant text over **Server-Sent Events (SSE)**.
4. Renders a **web UI** that tracks:
   - run phase (starting → researching → writing → done)
   - live tool / activity log
   - insight tracker `01`–`05`
   - readable cards: optional **image**, **In short**, **How it works**, **Proof**, **Easy to miss because**

A CLI entrypoint is also included for terminal-only runs.

---

## Requirements

| Item | Notes |
| --- | --- |
| Python | 3.10+ (developed with 3.12 / 3.13) |
| Cursor API key | User or team service-account key from [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations) |
| OS | Windows, macOS, or Linux. **Windows includes a local bridge workaround** (see below). |
| Network | Agent needs web access to research and verify sources |

---

## Project layout

```text
cursor-sdk-proj/
├── app.py                 # FastAPI web server + SSE stream
├── scout.py               # Shared prompt + agent event iterator
├── image_gen.py           # AI image generation (OpenAI / Pollinations)
├── insights_agent.py      # CLI runner (same agent as the UI)
├── win_bridge_patch.py    # Windows fix for cursor-sdk bridge discovery
├── static/
│   ├── index.html         # Insight Scout UI shell
│   ├── styles.css         # Layout and motion
│   ├── app.js             # Live stream client + insight parsing
│   └── generated/         # Cached AI visuals (gitignored)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup

### 1. Create a virtual environment

```powershell
cd D:\projects-shubham\02.06.2026\cursor_projects\cursor-sdk-proj
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure your API key

```powershell
copy .env.example .env
```

Edit `.env`:

```env
CURSOR_API_KEY=cursor_...
```

The app loads `.env` automatically via `python-dotenv`. You can also set the variable in the shell instead.

---

## Run the web UI

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open:

**http://127.0.0.1:8765**

Click **Start scout**. The left rail shows status and live activity; the main panel fills with insight cards as the agent writes them.

### API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | `{ ok, api_key_configured, image_provider }` |
| `GET` | `/api/scout/stream` | SSE stream of scout events (one run at a time) |
| `POST` | `/api/insights/image` | Generate/cache an AI image for an insight (`title`, optional `twist`, `insight_n`) |
| `GET` | `/static/*` | UI assets |

Only **one scout run** can be active at a time. A second request while a run is in progress returns `409`.

---

## Run the CLI

Same agent and prompt as the UI; prints assistant text to stdout:

```powershell
.\.venv\Scripts\python.exe insights_agent.py
```

**Exit codes**

| Code | Meaning |
| --- | --- |
| `0` | Run finished successfully |
| `1` | Startup / auth / config failure (`CursorAgentError`) |
| `2` | Run started but failed mid-flight |

---

## How the agent is prompted

The shared prompt in `scout.py` enforces:

- **Exactly 5 insights** about new / emerging tech
- **Unexpected + positive** astonishment (not doom or hype fluff)
- **Concrete technical** mechanisms, measurements, or architectural twists
- **Dual-source verification** — discard claims that lack a second independent confirmation
- Preference for papers, official technical blogs, standards, lab writeups, and reputable scientific press
- Structured markdown output:

```markdown
### Insight N: <plain title>
- **In short:** ...
- **How it works:**
  - ...
  - ...
  - ...
- **Proof:**
  - [Source title](https://…)
  - [Source title](https://…)
- **Easy to miss because:** ...
- **Image:** https://…/figure.png   # or `none`
```

The prompt also enforces plain, scannable writing (lead with the conclusion, short sentences, everyday words, bullets over walls of text) so the insight stays intact without dense jargon.

The UI parses that shape live as text streams in and shows the image on each card when a valid `http(s)` URL is present. If the image is missing or fails to load, the UI calls **`POST /api/insights/image`** to generate an AI visual from the title + twist (cached under `static/generated/`).

**Image providers**

| Priority | Provider | When |
| --- | --- | --- |
| 1 | OpenAI Images (`dall-e-3` by default) | `OPENAI_API_KEY` is set |
| 2 | [Pollinations](https://pollinations.ai) (Flux) | No OpenAI key — works out of the box |

---

## Event stream shape

`GET /api/scout/stream` emits SSE `data:` lines with JSON payloads:

| `type` | Purpose |
| --- | --- |
| `phase` | High-level phase + human detail |
| `started` | `agent_id`, `run_id` |
| `tool` | Tool name / status / call id |
| `thinking` | Truncated thinking snippet (if present) |
| `status` | Agent status updates |
| `text` | Assistant text chunks |
| `done` | Terminal success (`status`, `run_id`) |
| `error` | Failure (`kind`: `startup` \| `run` \| `internal`) |

The stream ends with:

```text
event: end
data: {}
```

---

## Windows bridge patch

On Windows, `cursor-sdk` local agents launch a Node bridge and wait for a discovery line on the process **stderr pipe**. The stock discovery path uses `selectors.DefaultSelector()` / `select()`, which on Windows only works with **sockets** — not pipes — and raises:

```text
OSError: [WinError 10038] An operation was attempted on something that is not a socket
```

`win_bridge_patch.py` is applied automatically from `scout.py` and:

1. Replaces bridge discovery with a **threaded stderr line reader**
2. Regenerates callback auth tokens that would start with `-` (rejected by the bridge argv parser)

No action is needed on macOS / Linux (the patch is a no-op there).

---

## Architecture

```text
Browser  --fetch SSE-->  FastAPI (app.py)
                              |
                              v
                     iter_scout_events (scout.py)
                              |
                              v
                     Agent.create + agent.send  (cursor-sdk, local)
                              |
                              v
                     Local Cursor agent runtime (cwd = project root)
```

- **Local runtime** is set explicitly via `LocalAgentOptions(cwd=...)`.
- Model is fixed to `composer-2.5`.
- Resources are disposed with the SDK `with Agent.create(...) as agent:` context manager.
- Startup failures (`CursorAgentError`) and mid-run failures (`result.status == "error"`) are reported as distinct stream errors.

---

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| UI says API key missing | `.env` has `CURSOR_API_KEY`, then restart `app.py` |
| `401` / auth errors | Key whitespace, wrong environment, or key without access |
| `WinError 10038` | Ensure you run through `scout.py` / `app.py` / `insights_agent.py` so the Windows patch loads |
| `409` from `/api/scout/stream` | Another scout is already running — wait or refresh after it finishes |
| Empty / thin insights | Agent needs network; try again — research quality varies by model access and search results |
| Bridge timeout | Antivirus / firewall blocking local Node bridge; retry; confirm `cursor-sdk` installed in the active venv |

---

## Development notes

- Prefer editing the prompt in **`scout.py`** only — both UI and CLI share it.
- UI insight parsing lives in **`static/app.js`** (`parseInsights`).
- Do not commit `.env` (ignored). Keep secrets out of the repo.
- SDK docs: [Python Cursor SDK](https://cursor.com/docs/sdk/python)

---

## License

Private project unless you add a license file.
