# Flow.io — Build Roadmap & Phase Tracker

AI orchestration platform. You state an outcome; Flow.io plans it, routes each step to a tool,
runs the work, validates it, and returns a result shaped to its type.

This file is the **live map of the build**. Each phase ships backend **and** frontend together so
you can see the progress on localhost every time. The checkbox is the source of truth for
"what phase are we in."

---

## 📍 Current phase: **All phases built** ✅ (only a live public deploy is left, and that needs your server)

| Phase | Goal | Backend | Frontend | You see on localhost | Status |
|-------|------|---------|----------|----------------------|--------|
| **0. Baseline** | Prove it boots end-to-end | Runs on SQLite, 58 tests green | Next.js dev server | App opens, a task plans → runs → validates | ✅ Done |
| **1. Image generation** ⭐ | Generate real images | Gemini image adapter + registry tool, 2 new tests | Results page already renders images | Ask for an image → get a real picture (needs Gemini key) | ✅ Done |
| **2. Speed** | Answers feel fast | Live token streaming over SSE (Groq + Gemini); fast steps routed to the fastest tool; understanding cached | Live-typing output panel ("Writing…") | Text appears as it generates, not after a long wait | ✅ Done |
| **3. Robustness** | Handle scale & failure | Real Celery worker (Redis, or a SQLite broker with no Redis); broker-down fallback to a thread; configurable provider timeout; tests for parallel steps, timeouts, 429s and API rate limits | Step cards pulse while running | Steps run side by side; failures shown clearly | ✅ Done |
| **4. Ship** | Production-ready build | Alembic migrations verified on a fresh DB; health check; Dockerfiles unchanged | `next build` standalone output verified | Same app, production build | ✅ Built · ⚠️ Docker images and public URL not run (no Docker here) |
| **5. Polish** | Professional, animated UI | — | Page-switch animation, route progress bar, click ripples, step pulse/pop, result reveal, sliding step panel, "Copied ✓" | Every click and page change animates; respects "reduce motion" | ✅ Done |
| **6. Complete workflow** | Every part of the ask gets done | New **Writing** step; numbers kept ("2 photos", "500 words"); AI planner (Groq, then Gemini) adds parts the word list misses; the check adds a missing part or redoes the weak one; essay and images run at the same time | Essay shown first, images under it | "write a 500 word essay on cars and give two photos" → Writing + 2 images + check | ✅ Done |

**Tests:** 101 backend tests pass · frontend typechecks · production build passes.

---

## Run it locally (no Docker needed)

Two terminals. Backend first, then frontend.

**Backend** (http://localhost:8000, SQLite dev DB):

    cd backend
    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt        # or the dev subset
    # first run only — create the SQLite tables:
    python -c "from app import db, models; e=db.init_engine(); models.Base.metadata.create_all(e)"
    uvicorn app.main:app --host 127.0.0.1 --port 8000

**Frontend** (http://localhost:3000):

    cd frontend
    npm install
    BACKEND_URL=http://localhost:8000 npm run dev

Open **http://localhost:3000**, register an account, then open **Tools** and save your Gemini and
Groq keys. API docs: http://localhost:8000/api/docs.

## Tests

    cd backend && . .venv/bin/activate && python -m pytest -q     # 101 passing
    cd frontend && npx tsc --noEmit                               # typecheck

---

## Image generation (Phase 1) — how it works

- **`gemini-image`** tool (provider `gemini`, adapter `gemini_images`) generates images with
  Google Gemini using **the same Gemini key you already saved** — no extra provider, no cost beyond
  Gemini. Model: `gemini-2.5-flash-image`.
- When your objective mentions *image, logo, poster, picture, illustration, visual, mockup, icon*,
  the understanding step tags it `image_generation`, the router picks `gemini-image`, and the
  Results panel shows the picture in a gallery.
- Alternatives already wired: `local-image` (free, local Stable Diffusion — set
  `LOCAL_IMAGE_API_URL`) and `openai-image` (paid). The router prefers whichever provider you have
  a key for.

To turn it on: save your Gemini key on the **Tools** page. The tool flips from `needs_key` to
`ready` and image tasks start generating real pictures.

---

## Speed (Phase 2) — how it works

Three changes make the app feel fast, biggest perceived win first:

- **Live token streaming.** Text steps (reasoning, code, research, documents) now stream the
  model's reply as it is written. The engine calls the adapter's `stream()` first and pushes each
  chunk as a `step.token` SSE event; the frontend shows it in a live **"Writing…"** panel with a
  blinking cursor. The authoritative result (and token counts) still comes from `run()` right
  after — so a dropped stream only skips the preview, never the answer. Groq, Gemini and Hugging
  Face stream natively; any other adapter falls back to a single `run()`.
- **Fast steps to the fastest tool.** Latency-sensitive steps (validation) get a routing bias
  toward the fastest, cheapest available tool, so a quick check never waits on a slow model while
  the heavy thinking still goes to the best model for its step.
- **Cached understanding.** The keyword understanding step is memoized (`lru_cache`), so repeated
  or near-duplicate objectives skip the re-scan. Each call still returns a fresh, independently
  mutable object.

No new keys or config needed — streaming works with the Groq and Gemini keys you already save.

---

## Robustness (Phase 3) — the real job queue

By default runs happen in a background thread (`EXECUTION_BACKEND=thread`). To use the real
Celery queue, add to `backend/.env`:

    EXECUTION_BACKEND=celery
    # with Redis running:
    REDIS_URL=redis://localhost:6379/0
    # or, with no Redis on your machine, a SQLite broker:
    CELERY_BROKER_URL=sqla+sqlite:///./celery_broker.db

Then start a third terminal next to the backend:

    cd backend && . .venv/bin/activate
    celery -A app.worker.celery_app worker --loglevel=info --concurrency=2 --pool=threads

If the broker is down, the backend runs the task in a thread instead of leaving it stuck.
`PROVIDER_TIMEOUT` (seconds, default 120) caps each provider call; timeouts and 429s are retried,
then the next tool takes over.

## Ship (Phase 4)

    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

See `DEPLOY.md`. Checked here: migrations on a fresh DB, `next build` standalone output, health
check. Not run here: the Docker images, Postgres, Caddy TLS, a public URL. These need Docker
and a server.

---

## How to test every objective (click by click)

Start: backend + frontend running, open http://localhost:3000.

| # | Objective | Do this | You should see |
|---|-----------|---------|----------------|
| 1 | Page switching (Phase 5) | Click Login → Register → back | Thin bar runs across the top; each page fades and rises in |
| 2 | Auth (FR-16) | Register, sign out, open `/app` | You are sent to `/login` |
| 3 | Save keys | Tools → paste Gemini key, then Groq key | Tools flip from `needs_key` to `ready` |
| 4 | Plan (FR-01–03) | Type *"Compare three competitors in the EU e-bike market and write a one-page brief"* → Run | Step cards cascade in, each shows its tool |
| 5 | Live typing (Phase 2) | Watch while it runs | "Writing…" panel types the answer; running card pulses |
| 6 | Parallel steps (Phase 3) | Same task | Research and Document reading run at the same time |
| 7 | Validate (FR-08) | Wait for the end | Result card slides in: "Checked … passed" |
| 8 | Step details (FR-12) | Click any step card | Panel slides in from the side; Esc closes it |
| 9 | Images (Phase 1) ⭐ | Run *"Design a logo for a streetwear brand called storkk"* | A real picture in the gallery |
| 10 | Code (FR-07) | Run *"Build a Python script that cleans a sales CSV and charts monthly revenue"* | File tabs; Copy → "Copied ✓" |
| 11 | Chart | Run *"Compare pricing options for our launch and recommend one"* | A bar chart, when the model adds numbers (not every answer has one) |
| 12 | Export (FR-13) | Click "Download as Markdown" | A `.md` file downloads |
| 13 | History (FR-11) | Click an old task in the left rail | It opens, with its result |
| 14 | Failure (FR-10, FR-15) | Tools → replace Groq key with a wrong one, run task 4 | A retry/fallback line, or a plain error with "View details" |
| 15 | Rate limit | Sign out, log in with a wrong password 11 times | 11th try: "Too many attempts. Wait 60 seconds" |
| 16 | Queue (Phase 3) | Set Celery in `.env` (above), restart, start worker, run task 4 | Worker log: `Task conduit.run_task[...] succeeded` |
| 17 | Reduce motion | Turn on your OS "Reduce motion", reload | No animations, everything still works |
| 18 | Phones (FR-14) | Make the window narrow | No sideways scroll; step panel comes up from the bottom |
| 19 | Continue chat | After a result, type *"make the background blue"* in "Continue this task" → Enter | Your bubble appears, the task runs again, a new result replaces the old one |
| 20 | Add a step by chat | Type *"now build a simple website that shows this logo"* | A new Code writing step appears before Validation |
| 21 | Idea chips | Click a chip like "Make it shorter" | It fills the box; press Send |

Automated: `cd backend && python -m pytest -q` (101 pass) and `cd frontend && npx tsc --noEmit`.

---

## What is real vs not (carried from the original build)

- **Tested:** auth, tasks, registry, routing (incl. fast-step bias), context handoffs,
  retry/fallback/revision, adapters against mocked HTTP (incl. Gemini images and token streaming),
  result shaping, SSE, files, usage, admin.
- **Not yet run for real:** Celery worker, Postgres migrations, Docker images, Caddy — these are
  Phase 3 and Phase 4.
- **Not built:** Python sandbox (code is delivered unrun), cost calculation, embeddings, PDF/binary
  uploads, email verification, password reset.
