# RunLLM

A personal AI running coach that wraps Garmin Connect data with Claude
(Anthropic) for conversational analysis.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLModel, Alembic, Anthropic SDK,
  `garminconnect`, Supabase (Postgres + Storage + Auth).
- **Frontend**: SvelteKit (Svelte 5 + TypeScript), Tailwind CSS,
  deployed on Vercel.
- **Infra**: Backend on Render, database + storage + auth on Supabase.

## Repository layout

```
backend/    FastAPI app, domain models, Garmin + LLM services
frontend/   SvelteKit app (scaffolded in Phase 6)
docs/       Architecture, setup and runbook docs
```

## Running locally (placeholders)

Backend:

```bash
cd backend
uv venv && source .venv/bin/activate   # or python -m venv .venv
pip install -e ".[dev]"
cp .env.example .env                   # then fill in real values
alembic upgrade head
uvicorn runllm.api.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Coding standards

See [`LLM.md`](docs/LLM.md) at the repo root. Every contributor and every
AI agent working in this repo must follow it.

