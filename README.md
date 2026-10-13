# Parking Lot Management API

A Django 5.2 LTS and Django REST Framework modular monolith running on Python 3.12 and PostgreSQL.
Phase 2 adds customer registration, JWT authentication, profile/password self-service, and guarded
user administration. Parking lots, floors, spots, sessions, pricing, and payments remain outside
this phase.

Interactive OpenAPI documentation is available at `/api/v1/docs/`; the schema is available at
`/api/v1/schema/`.

## Structure and request flow

- `config/settings/`: shared, local, test, and fail-fast production configuration.
- `config/api/`: cross-application HTTP behavior, including consistent errors and liveness.
- `apps/accounts/api/`: thin HTTP views, request serializers, and route definitions.
- `apps/accounts/services/`: registration, user update, password, and token-revocation use cases.
- `apps/accounts/selectors.py`: user-list read queries and filters.
- `apps/accounts/permissions.py`: reusable application-role authorization.
- `apps/<module>/`: accounts, parking, sessions, pricing, payments, reporting, and audit boundaries.
  Empty modules remain intentional Phase 1/2 skeletons.
- `tests/` and `apps/accounts/tests/`: PostgreSQL model, API, authentication, and authorization tests.
- `docs/decisions/`: architecture and collaboration decisions.

The write path is **request → view → serializer → service → Django ORM/PostgreSQL → safe response
serializer**. Views own HTTP and permissions, serializers own input shape and validation, and
services coordinate state changes. Reads with meaningful filters go through selectors. This keeps
responsibilities clear without adding a generic repository over Django's ORM.

The project created its `AbstractUser` subclass in Phase 1 because changing `AUTH_USER_MODEL` after
other tables and production data refer to it is difficult. Phase 2 extends that stable model with
application roles and timestamps.

## Roles and Django privilege flags

| Account type | Self profile | Future parking operations | Manage non-admin users | Django admin site |
| --- | --- | --- | --- | --- |
| CUSTOMER | Yes | No | No | Only if separately granted `is_staff` |
| OPERATOR | Yes | Reserved for later phases | No | Only if separately granted `is_staff` |
| ADMIN | Yes | Yes when implemented | Yes | Only if separately granted `is_staff` |
| Django superuser | Yes | Privileged override | Yes, but its record is API-edit protected | Yes |

`role` expresses business authority. `is_staff` controls access to Django's admin UI, while
`is_superuser` is Django's privileged override. Creating an application ADMIN does not set either
Django flag. A PostgreSQL check constraint accepts only `ADMIN`, `OPERATOR`, or `CUSTOMER`.

## Local environment setup

Prerequisites: Python 3.12, Docker Desktop with Compose, and Git.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The project and integration tests use PostgreSQL, not SQLite.

## Start containers and apply migrations

```powershell
docker compose up --build -d
docker compose ps
docker compose exec web python manage.py migrate
```

Open `http://localhost:8000/api/v1/health/live/` for liveness and
`http://localhost:8000/api/v1/docs/` for Swagger UI.

Compose bind-mounts the repository at `/app`, so local source changes are immediately visible in the
development container. The mount overlays the application directory copied into the image; rebuild
after dependency or Dockerfile changes. Migrations stay separate from web startup, especially in
production.

## Bootstrap administrators

Create an application ADMIN interactively (business administration, no Django flags):

```powershell
docker compose exec web python manage.py create_app_admin --username app-admin --email admin@example.com
```

Create a Django superuser for `/admin/` when needed:

```powershell
docker compose exec web python manage.py createsuperuser
```

There is deliberately no public endpoint for creating an ADMIN.

## Authentication examples

These examples assume the API is at `http://localhost:8000`. Substitute returned token values for
`<access-token>` and `<refresh-token>`.

Register a CUSTOMER:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","first_name":"Alice","password":"C0mpl3x!Parking-2026","password_confirm":"C0mpl3x!Parking-2026"}'
```

Log in and receive an access/refresh pair:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"C0mpl3x!Parking-2026"}'
```

Rotate a refresh token (the submitted refresh token is blacklisted):

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh":"<refresh-token>"}'
```

Read or update the authenticated profile:

```bash
curl http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <access-token>"

curl -X PATCH http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Alicia","last_name":"Example"}'
```

Change the password:

```bash
curl -X POST http://localhost:8000/api/v1/users/me/change-password/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"C0mpl3x!Parking-2026","new_password":"N3w!Parking-Password-2026","new_password_confirm":"N3w!Parking-Password-2026"}'
```

Log out by blacklisting the caller-owned refresh token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout/ \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh":"<refresh-token>"}'
```

Logout and password changes revoke refresh tokens. A stateless access token already issued remains
valid until its configured short expiry (15 minutes by default). Role and active status are not
trusted from token claims: authentication reloads the user, so role changes and deactivation apply
to existing access tokens on the next request.

Registration and token acquisition use configurable DRF throttles. These are application-level
controls and do not replace production rate limiting at a reverse proxy, API gateway, or firewall.

## Errors

API failures use a consistent envelope. Validation failures include field details:

```json
{
  "error": {
    "code": "validation_error",
    "detail": "Request validation failed.",
    "fields": {"username": ["A user with that username already exists."]}
  }
}
```

Invalid input returns 400, missing/invalid authentication 401, insufficient application authority
403, and missing resources 404.

## Tests and quality checks

```powershell
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web ruff format --check .
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

To apply formatting intentionally:

```powershell
docker compose exec web ruff format .
```

## Stop services

```powershell
docker compose down
```

## Destructive: reset all local database data

This permanently deletes the named PostgreSQL volume and every local row:

```powershell
docker compose down --volumes
```

Start again and explicitly apply migrations afterward.

## Production configuration

Use `config.settings.production`. It refuses to start unless `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, and every `POSTGRES_*` connection variable are present. Supply secrets from
the deployment environment or secret manager; never commit `.env`. The production image starts
Gunicorn and does not run migrations automatically.

## Git workflow

Use short-lived feature branches, pull requests, passing CI, and squash merges. Instructions for an
authorized maintainer to require the CI job on `main` are in
[ADR 0002](docs/decisions/0002-git-workflow.md). Never claim a remote rule, push, merge, or
deployment occurred without verifying it.

