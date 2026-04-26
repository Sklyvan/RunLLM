# 🏗️ ARCHITECTURE

```
                         +-----------------+
                         | 🎨 SvelteKit SPA|
                         |    (Vercel)     |
                         +--------+--------+
                                  |
                         🔑 JWT (Authorization: Bearer)
                                  |
                                  v
+----------------+         +-----------------+         +-------------------+
| 🗄️ Supabase    | <-----> | 🐍 FastAPI      | <-----> | 🤖 Anthropic Claude|
|  Auth + JWKS   |         |    (Render)     |         |   Messages API    |
|  Postgres      |         |                 |         |   + tool use      |
|  Storage       |         +--------+--------+         +-------------------+
+----------------+                  |
       ^                            | 🌐 HTTPS (synchronous, blocking calls
       |                            |  wrapped via asyncio.to_thread)
       |                            v
       |                   +-----------------+
       +---- 📦 Parquet -- | ⌚ garminconnect |
              + 📄 JSON    |   (unofficial)  |
                           +-----------------+
```

## 🧩 Components

- 🎨 **SvelteKit SPA** — login + chat + settings. Talks to Supabase Auth
  on the client and to FastAPI for everything else.
- 🐍 **FastAPI backend** — verifies Supabase JWTs, exposes
  `/api/v1/garmin/*` and `/api/v1/chat`. Owns the agent loop with
  Claude (tool use). Stateless — no per-user singletons.
- ⚙️ **Activity processor** — pulls Garmin data, normalizes, persists a
  row in `activity` and a Parquet object in Supabase Storage at
  `{user_id}/{activity_id}.parquet`.
- 🧱 **Domain models** — `User`, `Activity` (SQLModel + Alembic).

## 🤔 Why not a vector DB?

Activity summaries are small and fit in the system prompt. Detailed
splits and time-series load on demand via tool calls — no embeddings
required.

## 🔌 Replacing Garmin

`runllm/garmin/client.py` is the only module that imports
`garminconnect`. Everything else goes through
`GarminClientProtocol`, so swapping the backing library or moving to
the official Garmin Connect IQ APIs is a one-file change.

