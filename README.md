# Parking Lot Management API

Phase 1 establishes a runnable Django 5.2 LTS modular monolith on Python 3.12, PostgreSQL, Django REST
Framework, OpenAPI documentation, Docker, pytest, Ruff, and GitHub Actions. It deliberately contains
no parking business behavior, JWT endpoints, roles, Redis, or Celery.

## Structure

- `config/settings/`: shared, local, test, and fail-fast production configuration.
- `config/api/`: foundation-level HTTP views and serializers, currently only liveness.
- `apps/`: business-module boundaries: accounts, parking, sessions, pricing, payments, reporting,
  and audit. The custom user is the only Phase 1 business model.
- `tests/`: API smoke and PostgreSQL integration tests.
- `docs/decisions/`: architecture and collaboration decisions.
- `.github/`: CI workflow and pull request template.

Future code should keep HTTP handling in API views, input validation in serializers, orchestration in
application services, rules in domain policies, reads in selectors, significant persistence and
locking in focused repositories, and integrations behind adapters. Avoid generic ORM wrappers and
premature base classes. See [ADR 0001](docs/decisions/0001-modular-monolith.md).

The project owns an `AbstractUser` model from its first migration. Changing `AUTH_USER_MODEL` later
is difficult once foreign keys and production data exist, so the extension point is established now
without adding speculative role or JWT behavior.

## Local environment setup

Prerequisites: Python 3.12, Docker with Compose, and Git.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The Python environment uses PostgreSQL, never SQLite. For host-run Django commands, either expose a
PostgreSQL instance on `localhost:5432` or run the database container and set `POSTGRES_HOST=localhost`.

## Start containers

```powershell
docker compose up --build -d
docker compose ps
```

Open the liveness endpoint at `http://localhost:8000/api/v1/health/live/`, the generated OpenAPI
schema at `http://localhost:8000/api/v1/schema/`, and Swagger UI at
`http://localhost:8000/api/v1/docs/`.

Compose bind-mounts the repository at `/app` so local source edits are visible immediately. This
mount overlays the application files copied into the development image; rebuild after dependency or
Dockerfile changes.

## Apply migrations explicitly

Migrations are intentionally separate from web startup, especially in production.

```powershell
docker compose exec web python manage.py migrate
```

## Create a superuser

```powershell
docker compose exec web python manage.py createsuperuser
```

## Run tests

The test suite uses the Compose PostgreSQL service and test-only database credentials inherited by
the web container.

```powershell
docker compose exec web pytest
```

## Run lint, format checks, and Django checks

```powershell
docker compose exec web ruff check .
docker compose exec web ruff format --check .
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

To apply automatic formatting intentionally:

```powershell
docker compose exec web ruff format .
```

## Stop services

```powershell
docker compose down
```

## Destructive: reset all local database data

The following command stops the services and permanently deletes the named PostgreSQL volume,
including every local row:

```powershell
docker compose down --volumes
```

Start again with `docker compose up --build -d`, then explicitly apply migrations.

## Production configuration

Use `config.settings.production`. It refuses to start unless `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, and every `POSTGRES_*` connection variable are present. Supply secrets from
the deployment environment or secret manager; never commit `.env`. The production image starts
Gunicorn and does not run migrations automatically.

## Git workflow

Use short-lived feature branches, pull requests, passing CI, and squash merges. Instructions for an
authorized maintainer to require the CI job on `main` are in
[ADR 0002](docs/decisions/0002-git-workflow.md). This repository does not claim that remote branch
protection has been enabled.

