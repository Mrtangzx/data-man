# Repository Guidelines

## Project Structure & Module Organization

- `web/` contains the Vue 3 + TypeScript client. Application code lives in `web/src/`; realtime implementations are under `web/src/realtime/`.
- `backend/nova/` contains the FastAPI control plane, SQLAlchemy models, services, adapters, and state machine. Backend tests live in `backend/tests/`.
- `deploy/` holds Caddy, ModelScope, notebook, and economy-deployment assets. `compose.dev.yml` and `compose.full.yml` define container profiles.
- `nova.ps1` is the supported Windows launcher. `data/` and `work/` contain runtime artifacts and browser-smoke output; do not treat them as source or commit generated files.
- Architecture decisions and acceptance criteria are documented in `PLAN.md`; upstream pins are recorded in `upstream-lock.yml`.

## Build, Test, and Development Commands

```powershell
pnpm install
uv run --project backend uvicorn nova.main:app --reload --port 8788
pnpm dev
```

These commands install frontend dependencies and run the API on `8788` plus Vite on `8787`. For the integrated local experience, use `./nova.ps1 start --lite`; inspect it with `./nova.ps1 status` or `./nova.ps1 logs api`, then stop it with `./nova.ps1 stop`.

Run validation before submitting changes:

```powershell
uv run --project backend pytest backend/tests -q
pnpm typecheck
pnpm test
pnpm build
```

## Coding Style & Naming Conventions

Use four spaces in Python and two spaces in TypeScript/Vue. Follow existing Python conventions: `snake_case` functions/modules, `PascalCase` classes, and typed Pydantic schemas. TypeScript is strict; keep semicolons, double quotes, `camelCase` functions, and `PascalCase` Vue components/classes. Keep API behavior in services or adapters rather than route handlers. No repository-wide formatter or linter is configured, so match neighboring code.

## Testing Guidelines

Pytest uses strict markers and branch coverage configuration; name files `test_*.py` and tests `test_<behavior>`. Vitest uses jsdom; colocate frontend tests as `*.test.ts`. Add regression tests for API envelopes, state transitions, adapters, and realtime-client contracts. No minimum coverage threshold is enforced, but new behavior should exercise success and failure paths.

## Commit & Pull Request Guidelines

This workspace has no Git history, so no existing commit convention can be verified. Use concise imperative commits, preferably scoped, for example `feat(web): add asset preflight status`. Pull requests should explain the behavior change, list validation commands, link relevant issues, and include screenshots for UI changes. Call out configuration, schema, deployment, license, or upstream-lock changes explicitly.

## Security & Configuration

Copy settings from `.env.example`; never commit `.env`, credentials, model tokens, uploaded media, databases, or logs. Preserve license evidence in `deploy/upstreams/` when changing models or external engines.
