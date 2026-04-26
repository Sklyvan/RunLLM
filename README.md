# 🏃 RunLLM

> A personal AI running coach that wraps your Garmin Connect data with
> Claude (Anthropic) for natural, conversational training analysis.

Ask things like *"how was my last long run?"*, *"am I overtraining?"*,
*"compare my pace zones across the last three tempo workouts"* — and get
answers grounded in your actual telemetry, not generic advice.

---

## ✨ What it does

- 🔗 **Links your Garmin account** (with 2FA support) and pulls every
  activity from the last 12 months.
- 🗂️ **Normalizes the data** to metric units and stores per-second
  GPS/HR/cadence/speed as Parquet files keyed by user.
- 💬 **Talks to Claude** with a compact, evidence-based coach persona.
  The system prompt holds one-line summaries of every activity; full
  splits and time-series load **only when Claude needs them** via tool
  use — so context stays small and costs stay low.
- 🧰 **Four specialist tools** Claude can call: full activity detail,
  downsampled time-series, HR-zone breakdown, and a structured filter
  to recover activities that didn't fit in the prompt.
- 🌐 **Multi-tenant from day one** — every query is filtered by
  `user_id`, third-party credentials are encrypted at rest with Fernet.

---

## 🏗️ Architecture at a glance

```
SvelteKit SPA  ──JWT──▶  FastAPI  ──tool use──▶  Claude (Anthropic)
   (Vercel)              (Render)
                            │
                            ├── Postgres (Supabase)   ◀ summary rows
                            ├── Storage  (Supabase)   ◀ Parquet time-series
                            └── garminconnect (lib)   ◀ isolated behind a Protocol
```

Detailed diagram in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🧱 Stack

| Layer        | Tech |
| ------------ | ---- |
| 🐍 Backend   | Python 3.12 · FastAPI · SQLModel · Alembic · Anthropic SDK · `garminconnect` · `pyarrow` · `cryptography` (Fernet) |
| 🎨 Frontend  | SvelteKit (Svelte 5 runes) · TypeScript · Tailwind CSS · `@supabase/supabase-js` · `marked` + `dompurify` |
| 🗄️ Data     | Supabase Postgres (via `asyncpg`) · Supabase Storage (private bucket) · Supabase Auth (JWT) |
| ☁️ Hosting   | Backend on Render (Docker, free plan) · Frontend on Vercel (`adapter-vercel`) |
| 🔧 Tooling   | `pytest` + `pytest-asyncio` · `mypy --strict` · `ruff` · `black` · `pre-commit` · GitHub Actions CI |

---

## 📁 Repository layout

```
backend/    🐍 FastAPI app, domain models, Garmin + LLM services, Alembic migrations, Dockerfile
frontend/   🎨 SvelteKit SPA — login, chat, settings
docs/       📚 SETUP, RUNBOOK, ARCHITECTURE, coding standards
scripts/    🛠️ smoke_test.sh and other ops helpers
render.yaml ☁️ Render Blueprint for the backend service
```

---

## 🚀 Running locally

> 📝 First time? Read [`docs/SETUP.md`](docs/SETUP.md) for the full
> walkthrough (Supabase project, Fernet key, Anthropic key, etc.).

### 🐍 Backend

```bash
cd backend
uv venv --python 3.12 && source .venv/bin/activate   # or: python3.12 -m venv .venv
pip install -e ".[dev]"
cp .env.example .env                                  # then fill in real values
alembic upgrade head
uvicorn runllm.api.main:app --reload
```

The server boots at <http://localhost:8000>. Swagger UI at `/docs`.

### 🎨 Frontend

```bash
cd frontend
npm install
cp .env.example .env                                  # PUBLIC_* vars
npm run dev
```

The SPA boots at <http://localhost:5173>.

---

## 🔌 API surface

All endpoints under `/api/v1` require a Supabase JWT in
`Authorization: Bearer <token>`.

| Method | Path                              | Purpose |
| ------ | --------------------------------- | ------- |
| `POST` | `/api/v1/garmin/credentials`      | Save Garmin email/password (returns `mfa_required` if 2FA). |
| `POST` | `/api/v1/garmin/mfa`              | Submit the 2FA code to complete login. |
| `POST` | `/api/v1/garmin/sync`             | Pull new activities, persist + upload Parquet. |
| `GET`  | `/api/v1/garmin/status`           | Last sync, activity count, has-credentials flag. |
| `POST` | `/api/v1/chat`                    | Send a message, get Claude's grounded reply. |
| `GET`  | `/healthz` · `/readyz`            | Liveness / readiness probes. |

---

## 🧪 Tests

```bash
cd backend
pytest                  # 76 tests, ~90% line coverage
mypy runllm             # strict
ruff check runllm tests
black --check runllm tests
```

> ⚠️ Tests **never** hit real Anthropic, real Garmin or real
> Supabase. Every external dependency is injected via a `Protocol` or
> a factory and substituted with a fake.

---

## 🔐 Security model

- 🛡️ **Auth**: Supabase Auth on the client; backend validates the JWT
  on every request and resolves a local `User` row keyed on the
  Supabase `sub` claim.
- 🗝️ **Garmin credentials at rest**: encrypted with `Fernet` using a
  server-side key (`FERNET_KEY`). Plaintext never touches the database.
- 🧱 **Multi-tenant isolation**: every SQL query and every Storage path
  carries the `user_id`.
- 🚫 **No secrets in git**: see `.env.example` files; production values
  go in Render and Vercel dashboards.

---

## 🤝 Contributing

- 🧭 Read [`docs/LLM.md`](docs/LLM.md) — those are the coding
  standards every PR follows.
- ✅ Use Conventional Commits (`feat:`, `fix:`, `chore:`, …).
- 🧪 Add tests next to the code you touch.
- 🌳 All work happens on `main`; small, frequent commits.

---

## 📄 License

MIT.

