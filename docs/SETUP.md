# SETUP

First-time setup for RunLLM. Follow top to bottom.

## 1. Supabase project

1. Create a project at <https://supabase.com>.
2. From `Project Settings → API`, copy:
   - `URL` → `SUPABASE_URL`
   - `anon` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY`
3. From `Project Settings → Database`, copy the connection string and convert
   to async:

   ```
   postgresql+asyncpg://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres
   ```

   Save as `DATABASE_URL`.

## 2. Database migrations

```bash
cd backend
cp .env.example .env  # paste the values above
alembic upgrade head
```

## 3. Storage bucket

In `Storage`, create a private bucket named `activities`. The backend uses
the service-role key, so a private bucket is fine.

## 4. Fernet key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save the output as `FERNET_KEY`.

## 5. Anthropic API key

Get it from <https://console.anthropic.com>. Save as `ANTHROPIC_API_KEY`.

## 6. Render (backend)

1. Connect this repo at <https://dashboard.render.com>.
2. Use the included `render.yaml` blueprint.
3. Fill in the secret env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `FERNET_KEY`,
   `ALLOWED_ORIGINS`.

## 7. Vercel (frontend)

1. Import the `frontend/` directory.
2. Set the env vars:
   - `PUBLIC_SUPABASE_URL`
   - `PUBLIC_SUPABASE_ANON_KEY`
   - `PUBLIC_API_BASE_URL` (Render service URL)

## 8. GitHub Actions secrets

CI runs lint, type-check and tests against ephemeral environments — no
secrets required by default. If you later add deploy steps, add the
relevant tokens (Render API key, Vercel token) under
`Repo Settings → Secrets and variables → Actions`.

