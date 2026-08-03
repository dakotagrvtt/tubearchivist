# Repository Guidelines

## Project Structure & Module Organization

`backend/` contains the Django API, Celery tasks, migrations, and domain apps such as `video`, `download`, and `channel`. Backend tests live beside their apps under `tests/test_src/test_*.py`. `frontend/src/` contains the React/TypeScript UI; reusable UI belongs in `components/`, API helpers in `api/`, and state in `stores/`. Container and deployment support lives in `docker_assets/`, `scripts/`, `Dockerfile`, and `docker-compose.yml`.

Fork-specific behavior belongs in `backend/fork_features/` or `frontend/src/fork_features/`. Keep changes to upstream source files limited to small, documented hooks. Read `FORK_FEATURES.md` and `BRANCHING.md` before changing integration boundaries.

## Build, Test, and Development Commands

- `pip install -r requirements-dev.txt` installs backend development dependencies.
- `pytest backend` runs the Python unit suite used by CI.
- `cd backend && python manage.py runserver` starts the Django development server after required services and environment variables are configured.
- `npm --prefix frontend install` installs frontend dependencies; use `npm --prefix frontend run dev` for Vite development.
- `npm --prefix frontend run build` type-checks and builds the frontend.
- `pre-commit run --all-files` runs Black, isort, Flake8, codespell, ESLint, and Prettier.
- `docker compose up --build` validates the application in its production-like container layout.

## Coding Style & Naming Conventions

Use four-space indentation and 79-character lines for Python. Follow Black/isort formatting, `snake_case` for functions and modules, and `PascalCase` for classes. TypeScript and React are formatted by Prettier and checked by ESLint; use `PascalCase.tsx` for components and `camelCase` for functions. Prefer focused modules and explicit integration interfaces over cross-feature imports.

## Testing Guidelines

Name Python tests `test_*.py` and place focused fixtures in the nearest `conftest.py`. Add regression tests for bug fixes, especially download, migration, Redis lifecycle, and playback failure paths. There is no stated coverage threshold; new behavior should exercise success and cleanup/error cases. Run the full backend suite and frontend build before release work.

## Commit & Pull Request Guidelines

History favors concise, imperative subjects, sometimes with prefixes such as `fix:`, `feat:`, `docs:`, or `refactor:`. Keep each commit scoped to one concern. Target fork integration work at `fork/main`; use `fork/vX.Y.Z` only for tested release fixes. Pull requests should explain behavior and risk, link relevant issues, list validation performed, and include screenshots for visible UI changes. Note migrations, configuration changes, and deployment smoke-test results explicitly.

## Security & Configuration

Never commit `.env` files, credentials, cookies, tokens, or media/cache data. Use documented environment variables and Docker secrets, and enable `DJANGO_DEBUG` only while diagnosing development issues.
