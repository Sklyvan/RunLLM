# 🧭 RunLLM — Coding Standards

This document is the source of truth for how code in this repository is written.
Every prompt and every contributor must read it before making changes.

## 🐍 Python standards
- PEP8, type hints on every function and class.
- NumPy-style docstrings.
- Use `logging` over `print`.
- Modular single-responsibility functions.
- Black formatter, line length 100.
- Flat package structure, explicit `__init__.py`.
- Standard library preferred over third-party when reasonable.
- English only in code, comments, and commits.
- Minimal comments — only on non-obvious logic.

## 🧪 Testing
- pytest, cover normal and edge cases.
- Fixtures in `conftest.py`.
- No test should hit real network or real Supabase — mock everything.
- Aim for >80% coverage on business logic.

## 🌳 Git
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`,
  `test:`, `refactor:`, `ci:`.
- All work on `main`.
- Small, frequent commits — one per tested feature.
- Never commit secrets. Use `.env` locally, GitHub Secrets in CI.

## 🔐 Secrets & config
- Pydantic Settings + `.env`.
- Never hardcode secrets, even in POCs.
- Encrypt user-provided third-party credentials at rest.

## 🏗️ Architecture rules for this project
- Multi-tenant ready: every DB query filtered by `user_id`.
- Storage paths: `{user_id}/{activity_id}.parquet`.
- Garmin integration must be hidden behind an abstract interface so it
  can be swapped or mocked.
- No vector DB. Activity summaries go in the LLM system prompt;
  detailed time-series load on-demand via Claude tool use.

