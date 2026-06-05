# Autonomous News Reel Generator (MVP)

End-to-end pipeline that turns a topic into a vertical short-form video (TikTok / Reels / Shorts).

**Stack:** Next.js + Tailwind + SWR (frontend) · FastAPI + SQLAlchemy + Alembic + Supabase Postgres (backend) · Make.com (Gemini + Pexels automation) · edge-tts + MoviePy (local render) · Supabase Storage (delivery)

## Architecture

```
User → Next.js → POST /api/campaigns (FastAPI)
                  ↓
                  write pending row
                  ↓
                  fire Make.com webhook
                  ↓
                  return 202 Accepted
                                 ↓
              Make.com: Gemini → Pexels (per scene)
                                 ↓
              POST /api/campaigns/{id}/script  (HMAC-signed)
                  ↓
                  status = ready_to_render
                  ↓
                  background task: edge-tts → MoviePy → Supabase upload
                  ↓
                  status = completed, video_url set
                                 ↓
User ← polls GET /api/campaigns/{id} ← plays video
```

## Repository layout

```
.
├── backend/                FastAPI service + worker + Alembic
├── frontend/               Next.js dashboard
├── implementation.md       Original technical spec
├── make-com-flow.md        Make.com scenario config (module-by-module)
└── tools/                  Reference repos cloned for inspiration
```

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | FastAPI / edge-tts / MoviePy |
| pip | latest | Install backend deps |
| Node.js | 18+ | Build / run the Next.js frontend |
| PostgreSQL | 13+ | Supabase's hosted Postgres is fine |
| ffmpeg | latest | MoviePy needs it on PATH |
| Supabase project | free tier OK | Postgres + Storage bucket |
| Make.com account | free tier OK (cap ~140 reels/mo) | Gemini + Pexels orchestration |
| Google AI Studio key | — | Gemini (also paste into Make.com connection) |
| Pexels API key | — | (paste into Make.com scenario variable) |

## Backend setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — fill in:
#   DATABASE_URL, GEMINI_API_KEY, PEXELS_API_KEY,
#   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_BUCKET,
#   MAKE_COM_WEBHOOK_URL, MAKE_COM_CALLBACK_SECRET, APP_BASE_URL
```

### Create the schema

Two options. Pick one:

**A. Auto-create on startup (dev only):** the app calls `Base.metadata.create_all()` on startup. Just run it.

**B. Alembic migration (recommended once you have a real DB):**
```bash
alembic upgrade head
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Healthcheck: `curl http://localhost:8000/health` → `{"status":"ok"}`
OpenAPI docs: http://localhost:8000/docs

## Frontend setup

```bash
cd frontend
npm install

cp .env.example .env.local
# Edit .env.local — fill in:
#   NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_SUPABASE_URL,
#   NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_BUCKET
```

### Run

```bash
npm run dev
```

Open http://localhost:3000.

## Make.com scenario

See **`make-com-flow.md`** for the full module-by-module config. The single thing FastAPI needs from Make.com is the **Custom Webhook trigger URL** — paste it into `MAKE_COM_WEBHOOK_URL` in `backend/.env`. The HMAC secret must match `MAKE_COM_CALLBACK_SECRET` in both `.env` files.

In the Make.com scenario, also set:
- `APP_BASE_URL` = `http://localhost:8000` (or your deployed URL)
- `PEXELS_API_KEY` = your Pexels key
- Add a **Google Gemini** connection with your `GEMINI_API_KEY`

## Mock mode (test without Make.com)

For local development or quick demos, you can bypass Make.com entirely. Already enabled by default in `backend/.env`:

```ini
MOCK_MODE=true
```

**What mock mode does:**

- Skips the Make.com webhook fire
- Simulates the callback inline with a hardcoded script that mentions your topic
- Queries Pexels directly using safe generic search terms (`technology`, `city`, `people`, `business`, `nature`) — these always return clips, so the rest of the pipeline never starves
- Kicks off the render worker immediately

**What you get to test in mock mode:** the full backend — state machine, edge-tts, MoviePy, Supabase upload, frontend polling. The only thing not exercised is the Make.com scenario itself (the Gemini call and the Pexels loop in Make.com).

**To switch to real Make.com mode later:** set `MOCK_MODE=false` in `backend/.env` and fill in `MAKE_COM_WEBHOOK_URL` + `MAKE_COM_CALLBACK_SECRET`. The same campaign endpoint then fires the real Make.com webhook.

## End-to-end test (mock mode)

1. Backend running (`uvicorn`) — `MOCK_MODE=true` already set in `.env`
2. Frontend running (`npm run dev`)
3. Open http://localhost:3000, enter a topic, click **Generate Reel**
4. Backend writes a `pending` row → flips to `processing` → simulates Make.com callback → status = `ready_to_render` → kicks off the render worker → returns 202
5. Worker runs edge-tts → MoviePy → Supabase upload
6. Status flips to `completed` with `video_url` set
7. Frontend (polling every 3s) shows the video player

### End-to-end test (real Make.com)

1. Set `MOCK_MODE=false` in `backend/.env`
2. Build the Make.com scenario per `make-com-flow.md`, turn it ON
3. Make.com scenario is the same as above from step 4, but Make.com does the Gemini + Pexels work in step 4 before calling back

## API endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/api/campaigns` | Create campaign, fire Make.com webhook, return **202** | open (MVP) |
| `GET` | `/api/campaigns` | List campaigns (newest first) | open (MVP) |
| `GET` | `/api/campaigns/{id}` | Get one campaign (the polling endpoint) | open (MVP) |
| `POST` | `/api/campaigns/{id}/script` | Make.com success callback | HMAC via `X-Webhook-Secret` |
| `POST` | `/api/campaigns/{id}/fail` | Make.com error callback | HMAC via `X-Webhook-Secret` |
| `GET` | `/health` | Liveness | open |

## State machine

```
pending → processing → ready_to_render → rendering → completed
                                                  └──→ failed
```

| Status | Set by |
|---|---|
| `pending` | `POST /api/campaigns` (initial) |
| `processing` | `POST /api/campaigns` (right before firing Make.com webhook) |
| `ready_to_render` | `POST /api/campaigns/{id}/script` (Make.com callback) |
| `rendering` | Render worker (start of edge-tts) |
| `completed` | Render worker (after Supabase upload) |
| `failed` | Render worker (caught exception) **or** `POST /api/campaigns/{id}/fail` (Make.com error) |

## Notes & follow-ups

- `implementation.md` originally said "no Make.com" — that was overridden. The Make.com scenario in `make-com-flow.md` is the source of truth for the automation layer.
- Free Make.com tier caps you at ~140 reels/mo (~1,000 ops). Bump to Core ($10.59/mo, 10k ops) for ~1,400/mo.
- MoviePy rendering is CPU-bound. For a single-machine MVP demo, this is fine. For production: push the render to a worker queue (Arq + Redis, or Celery) and run multiple workers.
- If Supabase Storage isn't configured, the worker still produces a local MP4 and stores the local path; the frontend will just show no video. The campaign row's `video_path` will be set even if `video_url` is `null`.
- The `make_com_callback_secret` check in `core/security.py` is a no-op when the secret still has the placeholder value — set it in `.env` for production.
- Edge cases handled: missing `video_url` per scene (skipped, not fatal), worker exception (status → failed with message), Make.com webhook fire failure (logged, doesn't fail the request).
