# Rental Marketplace (Tanzania)

A mobile-first, Swahili-first marketplace to rent anything (rooms, vehicles, venues,
equipment, offices) with mobile-money payments.

- `backend/`: FastAPI modular monolith + worker (Python 3.12, uv, PostgreSQL 16)
- `frontend/`: Next.js 15 App Router (TypeScript, Tailwind, next-intl `sw`/`en`)
- `docker-compose.yml`: db, db-test, MinIO, api, worker, web

## Getting started

See the **[quickstart](specs/001-rental-marketplace-mvp/quickstart.md)** for running the stack,
demo accounts and validation scenarios.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Web: http://localhost:3000 · API docs: http://localhost:8000/api/v1/docs · MinIO console: http://localhost:9001

## Design documents

[spec](specs/001-rental-marketplace-mvp/spec.md) ·
[plan](specs/001-rental-marketplace-mvp/plan.md) ·
[research](specs/001-rental-marketplace-mvp/research.md) ·
[data model](specs/001-rental-marketplace-mvp/data-model.md) ·
[contracts](specs/001-rental-marketplace-mvp/contracts/) ·
[tasks](specs/001-rental-marketplace-mvp/tasks.md) ·
[constitution](.specify/memory/constitution.md)
