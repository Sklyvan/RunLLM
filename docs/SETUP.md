# 🛠️ SETUP

First-time setup for RunLLM. Follow top to bottom. Every value you
collect goes into one (or both) of these two files for local
development:

- **`backend/.env`** — used by the FastAPI service and Alembic. Create
  it by copying `backend/.env.example`.
- **`frontend/.env`** — used by SvelteKit at build time. Create it by
  copying `frontend/.env.example`.

For production, the same values go into the **Render dashboard** (for
the backend) and the **Vercel dashboard** (for the frontend) — see
sections 6 and 7.

> 💡 Reference templates: [`backend/.env.example`](../backend/.env.example) ·
> [`frontend/.env.example`](../frontend/.env.example).

```bash
cp backend/.env.example  backend/.env
cp frontend/.env.example frontend/.env
```

---

## 1. 🗄️ Supabase project

1. Sign in at <https://supabase.com/dashboard> and click **New project**.
   Pick a project name, a strong database password (save it — you'll
   reuse it below), and a region close to you.
2. Wait for provisioning (~2 minutes), then open the project.
3. In the left sidebar go to **Project Settings → API**. Copy:

   | Source field (Supabase UI)         | Goes into                         | Variable name           |
   | ---------------------------------- | --------------------------------- | ----------------------- |
   | `Project URL`                      | `backend/.env`, `frontend/.env`   | `SUPABASE_URL` *(backend)* / `PUBLIC_SUPABASE_URL` *(frontend)* |
   | `Project API keys → anon public`   | `backend/.env`, `frontend/.env`   | `SUPABASE_ANON_KEY` *(backend)* / `PUBLIC_SUPABASE_ANON_KEY` *(frontend)* |
   | `Project API keys → service_role`  | `backend/.env` only — **never** the frontend | `SUPABASE_SERVICE_KEY`  |

4. In the left sidebar go to **Project Settings → Database →
   Connection string → URI**. Copy the connection string, replace the
   driver prefix and substitute your DB password:

   ```
   postgresql+asyncpg://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres
   ```

   Paste it into `backend/.env` as `DATABASE_URL`.

> ⚠️ The `service_role` key bypasses Row Level Security. Treat it like
> a root password — backend only, never in the SvelteKit app, never in
> git.

---

## 2. 🧬 Database migrations

Run Alembic against the Supabase Postgres you just configured:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or: uv venv --python 3.12 && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

This applies every migration in
[`backend/alembic/versions/`](../backend/alembic/versions/) and
creates the `user` and `activity` tables.

Verify in the Supabase dashboard at **Table Editor** → both tables
should be visible.

---

## 3. 📦 Storage bucket

1. In the Supabase dashboard, click **Storage** in the left sidebar.
2. Click **New bucket** (top right).
3. Name it exactly **`activities`** (this matches the default
   `SUPABASE_BUCKET` value in `backend/.env.example`; if you choose a
   different name, update `SUPABASE_BUCKET` in `backend/.env` and on
   Render to match).
4. **Public bucket**: leave **off**. The backend uses the
   `service_role` key, which can read/write private buckets directly.
5. Click **Create bucket**.

That's it — the storage path layout `{user_id}/{activity_id}.parquet`
is created automatically the first time the activity processor runs.

---

## 4. 🔑 Fernet key

This key encrypts each user's Garmin credentials at rest. Generate one
locally:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `backend/.env` as `FERNET_KEY=<value>`.

> ⚠️ If you ever lose this key, every stored Garmin token becomes
> unreadable — users would simply re-link from the Settings page. To
> rotate without losing data, follow the procedure in
> [`docs/RUNBOOK.md`](RUNBOOK.md#-rotate-the-fernet-key).

---

## 5. 🤖 Anthropic API key

1. Sign in at <https://console.anthropic.com>.
2. Go to **Settings → API Keys** and click **Create Key**.
3. Copy the value (you only see it once) into `backend/.env` as
   `ANTHROPIC_API_KEY`.
4. Optionally set a monthly budget alert in **Settings → Billing →
   Limits** to avoid surprises.

The model name lives in `backend/.env` as `ANTHROPIC_MODEL`
(default: `claude-sonnet-4-5`). Change it there if you want to use a
different Claude model.

---

## 6. ☁️ Render (backend, production)

1. Push your repo to GitHub if you haven't already.
2. Open <https://dashboard.render.com>, click **New → Blueprint**, and
   point it at your fork. Render reads
   [`render.yaml`](../render.yaml) and proposes one web service named
   `runllm-backend`.
3. Confirm. Render will then ask you to fill in every env var marked
   `sync: false` in the blueprint. Use the values you put in
   `backend/.env`:

   | Variable                | Where it came from           |
   | ----------------------- | ---------------------------- |
   | `SUPABASE_URL`          | Section 1                    |
   | `SUPABASE_ANON_KEY`     | Section 1                    |
   | `SUPABASE_SERVICE_KEY`  | Section 1                    |
   | `DATABASE_URL`          | Section 1                    |
   | `ANTHROPIC_API_KEY`     | Section 5                    |
   | `FERNET_KEY`            | Section 4                    |
   | `ALLOWED_ORIGINS`       | The Vercel URL from section 7 (e.g. `https://runllm.vercel.app`) |

4. Render builds the Docker image from
   [`backend/Dockerfile`](../backend/Dockerfile), runs
   `alembic upgrade head`, then starts uvicorn. Watch the **Logs** tab
   for `Application startup complete`.

> 💡 You'll need the Render service URL (e.g.
> `https://runllm-backend.onrender.com`) for `PUBLIC_API_BASE_URL` in
> the next step.

---

## 7. ▲ Vercel (frontend, production)

1. Sign in at <https://vercel.com> and click **Add New → Project**.
2. Import the same GitHub repo. In the **Configure Project** screen
   set **Root Directory** to `frontend/`. Vercel auto-detects
   SvelteKit because of [`frontend/vercel.json`](../frontend/vercel.json).
3. Expand **Environment Variables** and add:

   | Variable                    | Goes where             | Value                                             |
   | --------------------------- | ---------------------- | ------------------------------------------------- |
   | `PUBLIC_SUPABASE_URL`       | All environments       | Same as backend's `SUPABASE_URL` (section 1)      |
   | `PUBLIC_SUPABASE_ANON_KEY`  | All environments       | Same as backend's `SUPABASE_ANON_KEY` (section 1) |
   | `PUBLIC_API_BASE_URL`       | All environments       | Render service URL from section 6                 |

4. Click **Deploy**.
5. Once the first deploy succeeds, copy the resulting Vercel URL
   (e.g. `https://runllm.vercel.app`) and paste it into Render's
   `ALLOWED_ORIGINS` env var. Save & redeploy the backend so CORS
   accepts the frontend.

---

## 8. 🤫 GitHub Actions secrets

The CI workflow in
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) only runs
lint, type-check, tests, and a frontend build — **no secrets are
required** for green CI on a fresh fork.

You only need to add secrets here if you later add deploy steps:

| Use case                    | Secret name             | Where to obtain                                       |
| --------------------------- | ----------------------- | ----------------------------------------------------- |
| Auto-deploy backend         | `RENDER_API_KEY`        | Render dashboard → **Account Settings → API Keys**    |
| Auto-deploy frontend        | `VERCEL_TOKEN`          | Vercel dashboard → **Account Settings → Tokens**      |
| Run integration tests in CI | `SUPABASE_*`, `FERNET_KEY`, `ANTHROPIC_API_KEY` | Same values you configured locally |

Add them under **Repo Settings → Secrets and variables → Actions →
New repository secret**.

---

## ✅ Smoke test

Once both deploys are live, verify they can talk to each other:

```bash
./scripts/smoke_test.sh https://runllm-backend.onrender.com
```

Then open your Vercel URL, sign up with email/password, link your
Garmin account from **Settings**, click **Sync now**, and chat from
the home page.

